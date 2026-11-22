"""The static site built from a ref's history: its pages, the files they need and their writing.

Docs: architecture/docs-tooling.md
"""

import difflib
import os
import posixpath
import warnings
from collections.abc import Callable, Container, Generator, Iterable, Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from functools import cached_property, partial
from html import escape
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from types import MappingProxyType

import griffe

from .cache import BodyCache
from .codeindex import CodeTarget
from .coderef import Codebase, CodeError, CodeReference
from .config import ConfigError, ProjectConfig
from .docs import DOCS_DIR, Doc, DocStatus, is_docs_asset, is_redirect, make_string_tuple
from .docset import DocSet
from .errors import DOCSPECSITE_WARNINGS, DocspecsiteError, DocspecsiteWarning, InternalErrorWarning
from .git import Git
from .history import History, Version
from .indexes import IndexEntry, IndexRenderer
from .links import list_front_matter_paths
from .markdown import HtmlRenderer, MarkdownText, RenderedLink
from .pages import (
    OldBanner,
    Page,
    PageLink,
    PickerEntry,
    RedirectNotice,
    Templates,
    build_breadcrumb,
    load_static_files,
    make_picker_label,
)
from .parts import Part
from .urls import (
    CODE_INDEX_DOC,
    COMPONENT_PAGES_DIR,
    RESERVED_PATH_MESSAGE,
    STATUS_PAGE,
    TAG_PAGES_DIR,
    PageLinks,
    Resolver,
    encode_href_path,
    is_usable_tag,
    list_ancestor_directories,
    make_code_url,
    make_diff_url,
    make_doc_url,
    make_relative_url,
    make_version_url,
    map_reserved_owners,
)
from .vocabulary import Vocabulary

# A built page: its name in error lines, and the page.
type BuiltPage = tuple[str, Page]

# A page not built yet: its name in error lines, and how to build it.
type Pending = tuple[str, Callable[[], Page]]

VENDOR_ENV = "DOCSPECSITE_VENDOR_DIR"


class BuildError(DocspecsiteError):
    """Error for a site that cannot be built: an invalid root ``docspecsite.toml``, or a failed strict build."""


class ReservedPathError(DocspecsiteError):
    """Error for a doc whose page would take the URL of a generated page."""


@dataclass(frozen=True)
class BuildResult:
    """Outcome of a site build."""

    page_count: int
    """Pages written to the site."""

    rendered_count: int
    """Page bodies rendered afresh."""

    cached_count: int
    """Page bodies taken from the cache."""

    errors: tuple[str, ...]
    """One line per :exc:`~docspecsite.errors.DocspecsiteError` of a page that could not be built."""

    failed_count: int
    """Number of pages that failed, through a :exc:`~docspecsite.errors.DocspecsiteError` or an internal error."""


class SiteWriter:
    """The output directory a site is written to, with the manifest of the files the last build wrote there."""

    MANIFEST_FILENAME = ".docspecsite-manifest"
    """Name of the file in the output directory that lists the files the last build wrote."""

    # Resolved
    resolved_out: Path
    """The output directory resolved to follow symlinks: nothing is written or deleted outside of it."""

    # Arguments of __init__
    out: Path
    """See :meth:`__init__`."""

    def __init__(self, out: Path) -> None:
        """Prepare to write below an output directory.

        Args:
            out: Output directory; created on the first write when missing, and holding the manifest of the previous
                build.
        """
        self.out = out
        self.resolved_out = out.resolve()

    def find_outside(self, paths: Iterable[str]) -> list[str]:
        """Return those paths that the write would refuse to write below the output directory.

        :meth:`write` refuses them: they land outside the output directory, also through a symlink.

        Args:
            paths: Site paths of the files about to be written.
        """
        return [path for path in paths if not self.is_inside(path)]

    def write(self, files: Mapping[str, bytes]) -> list[str]:
        """Write the site's files below the output directory and remove files left over from the previous build.

        Only files whose bytes changed are rewritten. ``<out>/.docspecsite-manifest`` lists the files written; nothing
        outside the previous manifest is ever deleted. The leftover files are deleted first, together with the
        directories they leave empty, so a path may turn from a file into a directory, or back, between builds.

        Args:
            files: Every file of the new site, as bytes by site path relative to the output directory; files of the
                previous build not in it are deleted.

        Returns:
            The paths that would land outside the output directory (also through a symlink); they are neither written
            nor deleted.
        """
        self.out.mkdir(parents=True, exist_ok=True)
        manifest = self.out / self.MANIFEST_FILENAME
        previous_paths = manifest.read_text(encoding="utf-8").splitlines() if manifest.is_file() else []
        for path in previous_paths:
            if path not in files and self.is_inside(path):
                self.delete_leftover(path)
        refused_paths: list[str] = []
        for path, data in files.items():
            if self.is_inside(path):
                self.write_if_changed(self.out / path, data)
            else:
                refused_paths.append(path)
        written = sorted(path for path in files if path not in refused_paths)
        self.write_if_changed(manifest, "".join(f"{path}\n" for path in written).encode())
        return refused_paths

    def delete_leftover(self, path: str) -> None:
        """Delete a file of the previous build, and the directories above it that it leaves empty.

        A symlink or a directory at the path is kept, and so is every directory that still holds something; the output
        directory itself is never removed.

        Args:
            path: Site path from the previous manifest, relative to the output directory; it must stay inside it.
        """
        target = self.out / path
        if not target.is_file() or target.is_symlink():
            return
        target.unlink()
        for parent in PurePosixPath(path).parents:
            if parent == PurePosixPath("."):
                break
            try:
                (self.out / parent).rmdir()
            except OSError:
                break  # not empty, or not a directory

    @staticmethod
    def is_relative_down(path: str) -> bool:
        """Return whether a path is a non-empty relative path without ``..`` or NUL.

        Args:
            path: Site path to be written under the output directory, or a page URL to be linked as an index.
        """
        pure = PurePosixPath(path)
        return bool(path) and "\0" not in path and not pure.is_absolute() and ".." not in pure.parts

    def is_inside(self, path: str) -> bool:
        """Return whether a path stays below the output directory, also after resolving symlinks.

        Args:
            path: Site path to write or delete, relative to the output directory.
        """
        return self.is_relative_down(path) and (self.resolved_out / path).resolve().is_relative_to(self.resolved_out)

    @staticmethod
    def write_if_changed(target: Path, data: bytes) -> None:
        """Write a file unless it already holds exactly these bytes.

        The modification time of an unchanged file is kept.

        Args:
            target: File in the output directory (a site file or the manifest); parent directories are created.
            data: New contents; when the file already holds exactly them, it is left untouched.
        """
        if target.is_file() and target.read_bytes() == data:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


class SiteBuilder:
    """One site build: what is read from the ref, the pages built from it and the files produced."""

    # Paths
    CACHE_DIR = ".docspecsite-cache"
    """Directory under the repository root that holds the cache of the rendered page bodies."""

    ROOT_PAGE = "index.html"
    """Root-level page: a URL resolved "as seen from" it stays site-root-relative."""

    # HTML
    MERMAID_MARK = '<pre class="mermaid">'
    """Start of a Mermaid diagram in a rendered page body."""

    # Helpers
    cache: BodyCache
    """Cache of the rendered page bodies."""

    git: Git
    """The repository's git."""

    templates: Templates
    """Templates the pages are rendered with."""

    # Read from the ref
    config: ProjectConfig
    """The project settings."""

    docs_by_path_and_blob: dict[tuple[str, str], Doc]
    """Parsed docs by doc path and blob SHA hash."""

    history: History
    """Doc versions at the build ref, with the working-tree docs with :attr:`include_worktree`."""

    latest_docs: DocSet
    """Latest version of each doc that is valid UTF-8."""

    ref_tree: dict[str, str]
    """Blob SHA hashes of the ref's files, by repo path."""

    worktree_files: frozenset[str]
    """Working-tree non-Markdown files under ``docs/`` with :attr:`include_worktree`, else none."""

    # Parts built
    parts: frozenset[Part]
    """The parts of the site this build produces."""

    # Filled by run()
    codebase: Codebase | None
    """The project code; None until :meth:`run` loads it, and when the project has no code to load."""

    index_renderer: IndexRenderer | None
    """Renderer of the index pages and ``llms.txt``; None until :meth:`run` makes it, and in a build without the docs
    part.
    """

    resolver: Resolver | None
    """Resolver of the docs' links; None until :meth:`run` makes it."""

    vocabulary: Vocabulary | None
    """The vocabulary of the latest docs; None until :meth:`run` reads it."""

    # Errors
    errors: list[str]
    """One line per :exc:`~docspecsite.errors.DocspecsiteError` of a page that could not be built, in the order they
    happened.
    """

    failed_names: set[str]
    """Names of the pages and files that failed, through a :exc:`~docspecsite.errors.DocspecsiteError` or an internal
    error.
    """

    hidden_dirs: list[Path]
    """Absolute paths cut from error messages: the repository root's and that of the directory the code is read from."""

    # Output
    page_urls: list[str]
    """Site paths of the pages written to the site files."""

    site_files: dict[str, bytes]
    """Files of the site built so far, as bytes by site path."""

    # Arguments of __init__
    root: Path
    """See :meth:`__init__`."""

    include_worktree: bool
    """See :meth:`__init__`."""

    vendor_dir: Path | None
    """See :meth:`__init__`."""

    is_strict: bool
    """See :meth:`__init__`."""

    def __init__(
        self,
        root: Path,
        ref: str,
        *,
        include_worktree: bool,
        vendor_dir: Path | None,
        is_strict: bool,
        parts: frozenset[Part] | None,
    ) -> None:
        """Read the ref's history, project settings and docs, ready to build pages.

        Args:
            root: Repository root; git runs in it, and working-tree files are read from it.
            ref: Revision to build; its history gives the doc versions. The settings always come from the working
                tree's ``docspecsite.toml``.
            include_worktree: Add working-tree docs that differ from ``ref`` as a newest version, and read the code
                and the non-Markdown files under ``docs/`` from the working tree.
            vendor_dir: Directory of the vendored third-party files the site uses; None means there are none.
            is_strict: Raise on the first :exc:`~docspecsite.errors.DocspecsiteError` of a page instead of recording it.
            parts: The parts of the site to build; None means the docs, and the code too when the settings have
                ``code-dirs``.

        Raises:
            BuildError: The settings cannot be read, or the code part is asked for without ``code-dirs``.
        """
        self.root = root
        self.is_strict = is_strict
        self.errors = []
        self.failed_names = set()
        # Absolute paths cut from error messages (never relative ones: "./" would match anywhere).
        self.hidden_dirs = [root.resolve()]
        self.git = Git(root)
        self.include_worktree = include_worktree
        self.vendor_dir = vendor_dir
        self.history = History.load(self.git, ref, worktree_root=root if include_worktree else None)
        self.worktree_files = (
            frozenset(p for p in self.git.list_worktree_files(DOCS_DIR) if not p.endswith(".md"))
            if include_worktree
            else frozenset[str]()
        )
        self.ref_tree = self.git.read_tree(self.history.head)
        self.site_files = {}
        self.page_urls = []
        self.templates = Templates()
        # Parsed docs by (doc path relative to docs/, blob SHA hash): each blob of a doc is parsed once.
        self.docs_by_path_and_blob = {}
        latest_versions = (self.history.find_latest(path) for path in sorted(self.history.versions_by_path))
        self.latest_docs = DocSet(self.parse_doc_version(v) for v in latest_versions if self.history.is_decodable(v))
        self.config = self.load_config()
        available_parts = self.get_available_parts()
        if parts is None:
            parts = available_parts
        elif not parts <= available_parts:
            raise BuildError("the code part needs code-dirs in %s", ProjectConfig.CONFIG_FILE)
        self.parts = parts
        self.cache = BodyCache(root / self.CACHE_DIR, BodyCache.compute_fingerprint(), self.parts_label)
        if not self.is_docs_part_built and CODE_INDEX_DOC not in self.latest_docs.by_path:
            warnings.warn(
                DocspecsiteWarning(
                    "no code reference entry page %s%s: the code-only site has no root page", DOCS_DIR, CODE_INDEX_DOC
                ),
                stacklevel=1,
            )
        if self.is_missing_source_url_reported:
            warnings.warn(
                DocspecsiteWarning(
                    "%s has no source-url: links to repository files cannot be made", ProjectConfig.CONFIG_FILE
                ),
                stacklevel=1,
            )
        self.codebase = None
        self.resolver = None
        self.vocabulary = None
        self.index_renderer = None

    def get_available_parts(self) -> frozenset[Part]:
        """Return every part the repo has the prerequisites for: the docs always, the code with ``code-dirs``."""
        return frozenset({Part.DOCS, Part.CODE} if self.config.code_dirs else {Part.DOCS})

    def parse_doc_version(self, version: Version) -> Doc:
        """Return the parsed doc of a version; the parse is reused for the same blob.

        Args:
            version: Decodable version of a doc; its path and blob key the reused parse.
        """
        key = (version.path, version.blob_sha)
        if key not in self.docs_by_path_and_blob:
            self.docs_by_path_and_blob[key] = Doc.parse(version.path, self.history.read_text(version))
        return self.docs_by_path_and_blob[key]

    def get_front_matter(self, version: Version) -> Mapping[str, object] | None:
        """Return the front matter of a version.

        The result is None when the version has none or is not valid UTF-8; its own pages report the latter.

        Args:
            version: Version whose front matter is wanted, e.g. a page's own version or a link's target version.
        """
        return self.parse_doc_version(version).front_matter if self.history.is_decodable(version) else None

    @property
    def home_doc(self) -> Doc | None:
        """The latest version of the home doc, ``index.md``; None when there is none."""
        return self.latest_docs.by_path.get("index.md")

    @staticmethod
    def find_part(path: str) -> Part:
        """Return the part of the site a doc belongs to.

        The code reference index is the entry page of the code reference, so it belongs to the code part; every other
        doc belongs to the docs part.

        Args:
            path: Doc path relative to ``docs/``.
        """
        return Part.CODE if path == CODE_INDEX_DOC else Part.DOCS

    @classmethod
    def is_code_doc(cls, path: str) -> bool:
        """Return whether a doc belongs to the code part of the site.

        Args:
            path: Doc path relative to ``docs/``.
        """
        return cls.find_part(path) is Part.CODE

    @classmethod
    def is_versionless(cls, path: str) -> bool:
        """Return whether a doc has only its latest version shown.

        A doc of the code part follows the code, so it has no ``/v/`` pages, diff page or version picker.

        Args:
            path: Doc path relative to ``docs/``.
        """
        return cls.is_code_doc(path)

    @cached_property
    def reserved_owners_by_path(self) -> Mapping[str, str]:
        """The generated pages whose URL the page of a doc at a reserved path would take, by the doc's path.

        Paths are relative to ``docs/``; docs at other paths have no entry.
        """
        return MappingProxyType(map_reserved_owners(self.history.versions_by_path))

    def is_built_doc(self, path: str) -> bool:
        """Return whether the pages of a doc are built, given the parts built.

        A doc at a reserved path, whose page would take the URL of a generated page, is never built.

        Args:
            path: Doc path relative to ``docs/``.
        """
        return self.is_doc_part_built(path) and path not in self.reserved_owners_by_path

    def is_doc_part_built(self, path: str) -> bool:
        """Return whether the part of the site that a doc belongs to is built.

        Args:
            path: Doc path relative to ``docs/``.
        """
        return self.find_part(path) in self.parts

    @property
    def is_docs_part_built(self) -> bool:
        """Whether the docs part is built, and with it the index pages and ``llms.txt``."""
        return Part.DOCS in self.parts

    @property
    def is_code_part_built(self) -> bool:
        """Whether the code part is built: the code reference pages and their entry page."""
        return Part.CODE in self.parts

    @property
    def is_missing_source_url_reported(self) -> bool:
        """Whether the build warns at its start that the code part is built but the settings have no ``source-url``.

        Then the resolver does not warn again about the links it turns into plain text.
        """
        return self.is_code_part_built and not self.config.source_url

    def is_root_doc(self, path: str) -> bool:
        """Return whether the latest page of a doc is also written as the site's root page, ``index.html``.

        Without the docs part the home doc is not built, and the code reference index takes its place; the home doc's
        own page is the root page already.

        Args:
            path: Doc path relative to ``docs/``.
        """
        return self.is_code_doc(path) and not self.is_docs_part_built

    def locate_doc(self, path: str) -> str | None:
        """Return the URL a link to a doc goes to, or None to show the link as text.

        It is the doc's page, site-root-relative, when its pages are built. A doc of the docs part that is not built
        is linked from the code reference, so the link goes to the doc's Markdown file at the built commit on the
        repository host, given by ``source-url``; None when the settings have no ``source-url`` or the doc is not in
        the built commit (a working-tree doc with :attr:`include_worktree`). A doc of the code part that is not built
        is linked from the docs, which never link outside the site for it: None. A doc missing from the history has no
        page anywhere: None.

        Args:
            path: Doc path relative to ``docs/``, e.g. from a ``Docs:`` line, a doc whose ``code`` names a module or a
                link in a doc's body or front matter.
        """
        if path not in self.history.versions_by_path:
            return None
        if self.is_built_doc(path):
            return make_doc_url(path)
        if self.is_code_doc(path):
            return None  # the code part's entry page, linked from the docs
        if not self.config.source_url:
            return None
        if f"{DOCS_DIR}{path}" not in self.ref_tree:
            return None  # a working-tree doc, not in the built commit
        return f"{self.config.source_url}/blob/{self.history.head}/{DOCS_DIR}{encode_href_path(path)}"

    @cached_property
    def doc_paths_by_url(self) -> Mapping[str, str]:
        """Doc paths relative to ``docs/`` by the URL of their latest page, for every doc of the history.

        Kept once for the build: every page's breadcrumb looks its links up in it.
        """
        return MappingProxyType({make_doc_url(path): path for path in self.history.versions_by_path})

    def limit_breadcrumb(
        self, breadcrumb: Iterable[PageLink], module_urls: Container[str] = frozenset()
    ) -> tuple[PageLink, ...]:
        """Return breadcrumb links without those to pages that do not exist, and with those to unbuilt docs as text.

        A link to a doc whose pages this build does not write keeps its title, without a URL.

        Args:
            breadcrumb: Links of a page's breadcrumb, to docs and to module pages.
            module_urls: URLs of the module pages of the code reference; links to them and links without a URL are
                kept, links to other URLs that are no doc's are left out.
        """
        links: list[PageLink] = []
        for link in breadcrumb:
            if link.url is None or link.url in module_urls:
                links.append(link)
                continue
            path = self.doc_paths_by_url.get(link.url)
            if path is not None:
                links.append(link if self.is_built_doc(path) else PageLink(link.title, None))
        return tuple(links)

    @property
    def parts_label(self) -> str:
        """The names of the parts built, sorted and joined by ``+``, e.g. ``code+docs``."""
        return "+".join(sorted(self.parts))

    def get_home_field(self, key: str, default: str) -> str:
        """Return a front-matter field of the home doc as text.

        Args:
            key: Field to read, e.g. ``title``.
            default: Text returned when there is no home doc, it has no front matter or the field is missing.
        """
        home_doc = self.home_doc
        front_matter = home_doc.front_matter if home_doc else None
        return str((front_matter or {}).get(key, default))

    @property
    def site_title(self) -> str:
        """Title of the home doc; ``Docs`` when it has none."""
        return self.get_home_field("title", "Docs")

    @property
    def site_summary(self) -> str:
        """Summary of the home doc, for ``llms.txt``; empty when it has none."""
        return self.get_home_field("summary", "")

    def attempt[T](self, name: str, make: Callable[[], T]) -> T | None:
        """Call a function and return its result, or None if it raises.

        A :exc:`~docspecsite.errors.DocspecsiteError` (an error in the docs or code being built) is recorded as an error
        line for the page. Any other exception is a bug in docspecsite: an
        :exc:`~docspecsite.errors.InternalErrorWarning` is issued for it while it is being handled, so a warning filter
        that turns it into an exception keeps the original one as its context.
        Warnings that a filter turned into exceptions are not caught.

        Args:
            name: Name of the page or file in error lines and warnings, e.g. ``docs/<path>@<id>``; a failed name is
                counted once.
            make: Builds the page, its HTML or another site file.

        Raises:
            BuildError: In a strict build, for a :exc:`~docspecsite.errors.DocspecsiteError` instead of recording it.
        """
        try:
            return make()
        except DocspecsiteError as error:
            message = self.describe_error(error)
            if self.is_strict:
                raise BuildError("%s: %s", name, message) from error
            self.failed_names.add(name)
            error_line = f"{name}: {message}"
            if error_line not in self.errors:
                self.errors.append(error_line)
            return None
        except Warning:
            raise
        except Exception as error:  # noqa: BLE001 -- a bug in one page is warned about, other pages are still built
            warnings.warn(
                InternalErrorWarning("%s: internal error: %s", name, self.describe_error(error)), stacklevel=1
            )
            self.failed_names.add(name)
            return None

    @staticmethod
    @contextmanager
    def make_warnings_fatal() -> Generator[None]:
        """Turn docspecsite's warnings into exceptions in the block, and the first one raised into a ``BuildError``.

        Raises:
            BuildError: A warning of :data:`~docspecsite.errors.DOCSPECSITE_WARNINGS` was issued in the block.
        """
        with warnings.catch_warnings():
            for category in DOCSPECSITE_WARNINGS:
                warnings.simplefilter("error", category)
            try:
                yield
            except DOCSPECSITE_WARNINGS as warning:
                raise BuildError("strict: %s", warning) from warning

    def describe_error(self, error: Exception) -> str:
        """Return an exception's type and message on one line, without the absolute paths of the build's directories.

        Args:
            error: Exception raised while building a page.
        """
        message = " ".join(str(error).splitlines())
        for directory in self.hidden_dirs:
            message = message.replace(f"{directory}/", "")
        return f"{type(error).__name__}: {message}"

    def load_config(self) -> ProjectConfig:
        """Return the settings from the working tree's ``docspecsite.toml``, whatever ref is built.

        The file is read from disk, never through git, so an older ref is built with today's settings. Each unknown
        setting is ignored with a warning.

        Raises:
            BuildError: The file cannot be read, is not valid TOML, or a setting has an invalid value.
        """
        try:
            return ProjectConfig.load(self.root).require_valid()
        except ConfigError as error:
            raise BuildError(error.message, *error.values) from error

    def load_codebase(self, code_root: Path) -> Codebase | None:
        """Load the project's code from a directory.

        Returns None, and issues a warning, when the code cannot be read.

        Args:
            code_root: Directory holding the code directories: the repository root, or the code directories
                extracted from the ref.
        """
        try:
            return Codebase.load(code_root, self.config)
        except (CodeError, griffe.GriffeError) as error:
            warnings.warn(DocspecsiteWarning("cannot load code: %s", error), stacklevel=1)
            return None

    def emit(self, name: str, page: Page, index_urls: Container[str]) -> None:
        """Render a page and add it to the site files.

        A page whose rendering fails is recorded as an error and not added.

        Args:
            name: Name of the page in error lines.
            page: Page to render; it is stored at its :attr:`~docspecsite.pages.Page.url`.
            index_urls: URLs of the index pages that were built (status, tag and component pages); links to other tags
                and components are shown as plain text, and the Status link is left out without the status page.
        """
        html = self.attempt(name, lambda: self.templates.render(page, self.site_title, indexes=index_urls).encode())
        if html is not None:
            self.site_files[page.url] = html
            self.page_urls.append(page.url)

    # --- doc pages ---

    def render_body(self, links: PageLinks) -> str:
        """Return the body HTML of a version, with its links resolved for a page.

        Args:
            links: Links of the decodable version whose text is rendered (its blob keys the cache entries), resolved
                for the page the body is on (latest or ``/v/`` page); it issues a warning for each unresolvable one.
        """
        version = links.version
        text = self.history.read_text(version)
        hrefs = self.cache.get_hrefs(
            version.blob_sha, lambda: [link.target for link in MarkdownText(text).extract_links()]
        )
        links_by_href = {href: links.resolve_link(href) for href in hrefs}

        def resolve_href(href: str) -> RenderedLink:
            found = links_by_href.get(href)
            return found if found is not None else links.resolve_link(href)

        minimum = self.config.toc_min_headings
        key = f"{self.cache.make_targets_key(links_by_href)}\0toc={minimum}"
        return self.cache.get_body(version.blob_sha, key, lambda: HtmlRenderer(resolve_href, minimum).render(text))

    def build_front_matter_link(self, root_links: PageLinks, front_matter_path: str) -> PageLink | None:
        """Return the page link for a front-matter path of a version, or None if it cannot be linked.

        The URL is site-root-relative.

        Args:
            root_links: Links of the version holding the front matter, resolved for the site root; the path is
                resolved as if it were a body link of that version, so the target's version and markers match, and
                links from an old version go to the version current then.
            front_matter_path: Path relative to ``docs/`` with an optional ``#anchor``, as written in ``related`` or
                ``redirect_to``.
        """
        path, sep, anchor = front_matter_path.partition("#")
        target = posixpath.normpath(path)
        href = posixpath.relpath(target, posixpath.dirname(root_links.version.path) or ".") + sep + anchor
        rendered_link = root_links.resolve_link(href)
        if rendered_link.href is None:
            return None
        return PageLink(
            self.latest_docs.titles.get(self.history.find_doc_path(target), front_matter_path),
            rendered_link.href,
            markers=rendered_link.markers,
        )

    def build_front_matter_links(
        self, root_links: PageLinks, front_matter: Mapping[str, object], key: str
    ) -> tuple[PageLink, ...]:
        """Return the page links for a front-matter entry of a version, a path or a list of paths.

        Args:
            root_links: Links of the version holding the front matter, resolved for the site root; each path is
                resolved as if it were a body link of that version.
            front_matter: Front matter of the version.
            key: Field holding a path or a list of paths, ``related`` or ``redirect_to``; non-strings and unresolvable
                paths are skipped.
        """
        paths = list_front_matter_paths(front_matter, key)
        links = (self.build_front_matter_link(root_links, path) for path in paths)
        return tuple(link for link in links if link is not None)

    def build_doc_pages(self, extra_children: Mapping[str, tuple[PageLink, ...]]) -> list[Pending]:
        """List the pages still to build for every doc.

        These are its latest page, a ``/v/`` page per version and the diff pages. Each is named ``docs/<path>@<id>``
        in error lines. The code reference index has only its latest page: no ``/v/`` page, diff page or picker.
        A doc at a reserved path, whose page would take the URL of a generated page, gets none: one page named
        ``docs/<path>`` fails instead, with a :exc:`ReservedPathError`.

        Args:
            extra_children: Child links shown on a doc's pages, by doc path relative to ``docs/``; the build gives the
                code reference index its top-level packages. Docs missing from it get none.
        """
        pages: list[Pending] = []
        for path, owner in sorted(self.reserved_owners_by_path.items()):
            if self.is_doc_part_built(path):
                pages.append((f"{DOCS_DIR}{path}", partial(self.refuse_reserved_doc, owner)))
        for path in sorted(filter(self.is_built_doc, self.history.versions_by_path)):
            versions = self.history.versions_by_path[path]
            backlink_list = self.build_backlink_list(path)
            child_list = extra_children.get(path, ())
            if self.is_versionless(path):
                versions = (self.history.find_latest(path),)
                picker_entries: tuple[PickerEntry, ...] = ()
            else:
                picker_entries = tuple(
                    PickerEntry(make_picker_label(version), self.make_version_page_url(version), is_current=False)
                    for version in versions
                )
            for version, previous in zip(versions, (*versions[1:], None), strict=True):
                name = f"{DOCS_DIR}{path}@{version.short_id}"
                diff_base = self.find_diff_base(version, previous)
                pages.extend(
                    (
                        name,
                        partial(
                            self.build_doc_page,
                            version,
                            url,
                            backlink_list,
                            child_list,
                            picker_entries,
                            has_diff_page=diff_base is not None,
                        ),
                    )
                    for url in self.list_page_urls(version)
                )
                if diff_base is not None:
                    pages.append((name, partial(self.build_diff_page, version, diff_base)))
        return pages

    def build_backlink_list(self, path: str) -> tuple[PageLink, ...]:
        """Return the links to the latest docs that link to a doc, as its pages show them.

        A linking doc goes where :meth:`locate_doc` says: its page when its pages are built. A doc of the docs part in a
        build without that part (a code-only build, whose entry page shows it) that it gives no URL is its path as text.
        Other linking docs whose pages are not built, such as the code reference's entry page in a build without the
        code part, are left out.

        Args:
            path: Path relative to ``docs/`` of the linked doc.
        """
        backlink_list: list[PageLink] = []
        for backlink in self.latest_docs.backlinks_by_target.get(path, ()):
            source_path = backlink.doc.path
            if not self.is_built_doc(source_path) and (self.is_code_doc(source_path) or self.is_docs_part_built):
                continue
            url = self.locate_doc(source_path)
            backlink_list.append(
                PageLink(backlink.title or source_path, url) if url is not None else PageLink(source_path, None)
            )
        return tuple(backlink_list)

    @staticmethod
    def refuse_reserved_doc(owner: str) -> Page:
        """Fail the page of a doc at a reserved path.

        Args:
            owner: The generated pages whose URL the doc's page would take, for the error message.

        Raises:
            ReservedPathError: Always.
        """
        raise ReservedPathError(RESERVED_PATH_MESSAGE, owner)

    def list_page_urls(self, version: Version) -> list[str]:
        """Return the site paths the page of a version is written to.

        The latest version is at the doc's URL, and also at the root page for the root doc (see :meth:`is_root_doc`);
        every version but those of a versionless doc has a ``/v/`` page.

        Args:
            version: Version of a doc whose pages are built.
        """
        path = version.path
        urls: list[str] = []
        if self.history.is_latest(version):
            urls.append(make_doc_url(path))
            if self.is_root_doc(path):
                urls.append(self.ROOT_PAGE)
        if not self.is_versionless(path):
            urls.append(make_version_url(path, version.short_id))
        return urls

    def find_diff_base(self, version: Version, previous: Version | None) -> Version | None:
        """Return the earlier version that the diff page of a version compares it with, or None.

        None means the version has no diff page; a versionless doc has none. A version that is not valid UTF-8 has no
        diff and is no version's previous one; its own pages report it.

        Args:
            version: Version whose diff page is considered.
            previous: The version of the same doc just before ``version``; None for the doc's first version, which has
                no diff page.
        """
        if self.is_versionless(version.path) or previous is None:
            return None
        has_diff = self.history.is_decodable(previous) and self.history.is_decodable(version)
        return previous if has_diff else None

    def make_version_page_url(self, version: Version) -> str:
        """Return the site path of the page the picker and diff pages link a version to.

        It is the doc's page for the latest version, else the version's ``/v/`` page.

        Args:
            version: Version of a doc whose pages are built.
        """
        if self.history.is_latest(version):
            return make_doc_url(version.path)
        return make_version_url(version.path, version.short_id)

    def build_common_page(self, version: Version, url: str) -> Page:
        """Return the page of a version at a URL with the parts every doc page shares.

        The body and the other extras are filled in by the caller.

        Args:
            version: Version shown; gives the title, status, components, tags and breadcrumb, and an old-version banner
                when it is not the latest.
            url: Site path the page is written to: the doc's page, a ``/v/`` page or a diff page.
        """
        front_matter = self.get_front_matter(version) or {}
        old_banner = None
        if not self.history.is_latest(version):
            old_banner = OldBanner(version, make_doc_url(version.path))
        return Page(
            url=url,
            title=str(front_matter.get("title", version.path)),
            statuses=DocStatus.from_front_matter(front_matter).values,
            components=make_string_tuple(front_matter.get("components")),
            tags=make_string_tuple(front_matter.get("tags")),
            body_html="",
            breadcrumb=self.limit_breadcrumb(build_breadcrumb(version.path, self.latest_docs.titles)),
            old_banner=old_banner,
        )

    def build_doc_page(
        self,
        version: Version,
        url: str,
        backlink_list: tuple[PageLink, ...],
        child_list: tuple[PageLink, ...],
        picker_entries: tuple[PickerEntry, ...],
        *,
        has_diff_page: bool,
    ) -> Page:
        """Return the page of a version, with picker, related docs, backlinks and children.

        Args:
            version: Version shown on the page.
            url: Site path the page is written to; the latest version is built at both the doc's URL and its ``/v/``
                URL.
            backlink_list: Links to the latest docs that link to this doc, the same for every version.
            child_list: Extra child links of the doc (the code reference index's packages); empty for other docs.
            picker_entries: The picker's entries for all versions of the doc, the same for every version, with none
                current; the page marks the entry of ``version``. Empty for a doc without a picker.
            has_diff_page: Whether the version has a diff page, which the page links to.
        """
        if self.resolver is None:
            raise RuntimeError("the resolver is made by run(), before the pages are built")
        front_matter = self.get_front_matter(version) or {}
        root_links = PageLinks(self.resolver, version, self.ROOT_PAGE)
        current_url = self.make_version_page_url(version)
        picker = tuple(PickerEntry(entry.label, entry.url, entry.url == current_url) for entry in picker_entries)
        redirect = None
        if is_redirect(front_matter):
            kind = str(front_matter.get("redirect_kind", ""))
            redirect = RedirectNotice(
                RedirectNotice.REDIRECT_LABELS.get(kind, kind),
                self.build_front_matter_links(root_links, front_matter, "redirect_to"),
                str(front_matter.get("reason", "")),
            )
        body = self.render_body(PageLinks(self.resolver, version, url))
        return replace(
            self.build_common_page(version, url),
            body_html=body,
            picker=picker,
            diff_url=make_diff_url(version.path, version.short_id) if has_diff_page else None,
            redirect=redirect,
            children=child_list,
            children_heading="Packages",
            related_links=self.build_front_matter_links(root_links, front_matter, "related"),
            backlinks=backlink_list,
            has_mermaid=self.MERMAID_MARK in body,
        )

    def build_diff_page(self, version: Version, previous: Version) -> Page:
        """Return the page showing the diff of a version against its previous version.

        Args:
            version: Version the diff page is for, the newer side.
            previous: Version just before ``version``, as :meth:`find_diff_base` returns it; the older side.
        """
        diff_url = make_diff_url(version.path, version.short_id)
        version_url = self.make_version_page_url(version)
        previous_url = make_version_url(previous.path, previous.short_id)
        previous_href = escape(make_relative_url(previous_url, diff_url))
        version_href = escape(make_relative_url(version_url, diff_url))
        heading = (
            f'<p class="diff-versions">Changes from <a href="{previous_href}">{escape(make_picker_label(previous))}</a>'
            f' to <a href="{version_href}">{escape(make_picker_label(version))}</a></p>\n'
        )
        diff_html = self.cache.get_diff_body(
            previous.blob_sha,
            version.blob_sha,
            lambda: self.render_diff_html(self.history.read_text(previous), self.history.read_text(version)),
        )
        body = heading + diff_html
        page = self.build_common_page(version, diff_url)
        return replace(page, title=f"Diff: {page.title}", body_html=body)

    # --- other pages and files ---

    @staticmethod
    def render_diff_html(old: str, new: str) -> str:
        """Return the HTML of a unified diff between two raw Markdown texts.

        The diff has 3 lines of context and is a ``<pre class="diff">`` block with added, removed and hunk lines marked
        up.

        Args:
            old: Raw Markdown of the previous version, the ``-`` side of the diff.
            new: Raw Markdown of the version the diff page is for, the ``+`` side.
        """
        diff_lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(), n=3, lineterm=""))[2:]
        html_lines: list[str] = []
        for line in diff_lines:
            text = escape(line)
            if line.startswith("@@"):
                html_lines.append(f'<span class="hunk">{text}</span>')
            elif line.startswith("+"):
                html_lines.append(f'<span class="add">{text}</span>')
            elif line.startswith("-"):
                html_lines.append(f'<span class="del">{text}</span>')
            else:
                html_lines.append(text)
        return '<pre class="diff">' + "\n".join(html_lines) + "</pre>"

    def build_code_pages(self, code_reference: CodeReference) -> list[Pending]:
        """List the pages still to build for the modules of the code.

        Each is named ``reference/code/<module>`` in error lines.

        Args:
            code_reference: Renderer of the code's pages; one page per module of its codebase, whose index maps the
                docs' ``code`` entries to modules.
        """
        codebase = code_reference.codebase
        # Links to the latest docs whose front matter ``code`` names a module, by module path.
        doc_links_by_module: dict[str, list[PageLink]] = {}
        for doc in self.latest_docs:
            # Ordered set of the module paths the doc's ``code`` entries name (an unresolved entry as itself).
            modules: dict[str, None] = {}
            for entry in make_string_tuple((doc.front_matter or {}).get("code")):
                target = codebase.index.get(entry)
                modules[target.module if target is not None else entry] = None
            link = code_reference.build_doc_link(doc.path)
            for module in modules:
                doc_links_by_module.setdefault(module, []).append(link)
        module_urls = {make_code_url(CodeTarget(m.path, None)) for m in codebase.modules}

        def make(module: griffe.Module) -> Page:
            page = code_reference.build_page(module, doc_links_by_module.get(module.path, ()))
            return replace(
                page,
                breadcrumb=self.limit_breadcrumb(page.breadcrumb, module_urls),
                has_mermaid=self.MERMAID_MARK in page.body_html,
            )

        return [(f"reference/code/{module.path}", partial(make, module)) for module in codebase.modules]

    def copy_docs_files(self) -> None:
        """Copy the non-Markdown files under ``docs/`` into the site at the same path.

        Templates are left out. With :attr:`include_worktree` the files come from the working tree. A file whose site
        path collides with a generated file or directory is not copied and a warning is issued.
        """
        site_paths_by_repo_path = {
            path: path.removeprefix(DOCS_DIR)
            for path in sorted(self.history.tree | self.worktree_files)
            if is_docs_asset(path)
        }
        generated_paths = set(self.site_files)
        generated_dirs = {parent for path in generated_paths for parent in list_ancestor_directories(path)}
        blobs = self.git.read_blobs(
            self.ref_tree[path] for path in site_paths_by_repo_path if path not in self.worktree_files
        )
        for path, site_path in site_paths_by_repo_path.items():
            if (
                site_path in generated_paths
                or site_path in generated_dirs
                or generated_paths.intersection(list_ancestor_directories(site_path))
            ):
                warnings.warn(DocspecsiteWarning("%s: collides with a generated file, not copied", path), stacklevel=1)
                continue
            if path in self.worktree_files:
                self.site_files[site_path] = (self.root / path).read_bytes()
            else:
                self.site_files[site_path] = blobs[self.ref_tree[path]]

    def load_mermaid_bundle(self) -> dict[str, bytes] | None:
        """Return the Mermaid script and its licence as site files, or None.

        None is returned, with a warning, when the bundle is not found.
        """
        directory = self.vendor_dir / "mermaid" if self.vendor_dir is not None else None
        script_file = directory / "mermaid.min.js" if directory is not None else None
        if directory is None or script_file is None or not script_file.is_file():
            where = f"in {directory}" if directory is not None else f"({VENDOR_ENV} is not set)"
            warnings.warn(
                DocspecsiteWarning("mermaid bundle not found %s; diagrams are shown as source", where), stacklevel=1
            )
            return None
        files = {"assets/mermaid.min.js": script_file.read_bytes()}
        license_file = directory / "LICENSE"
        if license_file.is_file():
            files["assets/mermaid.LICENSE.txt"] = license_file.read_bytes()
        return files

    def find_code_dirs(self) -> list[str]:
        """Return the code directories that exist in the ref's tree; ``.`` alone when the root is one of them.

        The settings' code directories (``code-dirs``) are matched against each file's parent directories.
        """
        if self.config.is_code_dir("."):
            return ["."]
        directories = {
            directory.as_posix()
            for path in self.history.tree
            for directory in PurePosixPath(path).parents
            if directory.name
        }
        return sorted(directory for directory in directories if self.config.is_code_dir(directory))

    @contextmanager
    def prepare_code_root(self) -> Generator[Path | None]:
        """Provide the directory the code is read from, or None when the code part is not built.

        That is the working tree with :attr:`include_worktree`, or else the ref's code directories extracted to a
        temporary directory that is removed on exit. A symlink there that points to an absolute path or out of the code
        directories is left out, with a :class:`~docspecsite.errors.DocspecsiteWarning` naming it.
        """
        if not self.is_code_part_built:
            yield None
            return
        if self.include_worktree:
            yield self.root
            return
        with TemporaryDirectory(prefix="docspecsite-code-") as tmp:
            dirs = self.find_code_dirs()
            if dirs:
                for path in self.git.extract(self.history.head, dirs, Path(tmp)):
                    warnings.warn(
                        DocspecsiteWarning(
                            "%s: symlink to an absolute path or out of the code directories, left out", path
                        ),
                        stacklevel=1,
                    )
            yield Path(tmp)

    def read_latest_text(self, path: str) -> str | None:
        """Return the text of the latest version of a doc, or None when there is no such doc or it is not valid UTF-8.

        Args:
            path: Doc path relative to ``docs/``, as the vocabulary names its source docs.
        """
        latest = self.history.find_latest(path) if path in self.history.versions_by_path else None
        return self.history.read_text(latest) if latest is not None and self.history.is_decodable(latest) else None

    def collect_index_entries(self) -> list[IndexEntry]:
        """Return the index entries of the built latest docs that have front matter, ordered by doc path."""
        return [
            IndexEntry.from_front_matter(doc.path, make_doc_url(doc.path), doc.front_matter)
            for doc in sorted(self.latest_docs, key=lambda doc: doc.path)
            if doc.front_matter is not None and self.is_built_doc(doc.path)
        ]

    def collect_code_entries(self) -> list[IndexEntry]:
        """Return the index entries of the code modules, for the component pages; none when the code is not loaded.

        Each module becomes an entry linked to its reference page, with its components from the settings'
        ``code-components``.
        """
        if self.codebase is None:
            return []
        return [
            IndexEntry(
                path=m.path,
                url=make_code_url(CodeTarget(m.path, None)),
                title=m.path,
                summary="",
                status=DocStatus(("implemented",)),
                layer="reference",
                milestone=None,
                priority=None,
                tags=(),
                components=self.config.find_components(m.path),
            )
            for m in self.codebase.modules
        ]

    @staticmethod
    def keep_built_links(page: Page, built_urls: Container[str]) -> Page:
        """Return a page with its version-picker entries and diff link limited to pages that were built.

        Args:
            page: Built page whose picker and diff link may point to pages that failed.
            built_urls: URLs of every page built without error.
        """
        picker = tuple(entry for entry in page.picker if entry.url in built_urls)
        diff_url = page.diff_url if page.diff_url is not None and page.diff_url in built_urls else None
        is_changed = (picker, diff_url) != (page.picker, page.diff_url)
        return replace(page, picker=picker, diff_url=diff_url) if is_changed else page

    @staticmethod
    def strip_mermaid(page: Page) -> Page:
        """Return a page that does not load the Mermaid script.

        Args:
            page: Built page, whose body may hold diagrams; they are then shown as source.
        """
        return replace(page, has_mermaid=False) if page.has_mermaid else page

    def make_index_renderer(self) -> IndexRenderer:
        """Return the renderer of the index pages and ``llms.txt``, with the index entries of the built docs and code.

        A warning is issued for each tag that cannot be a file name, and so gets no index page.
        """
        if self.vocabulary is None:
            raise RuntimeError("the vocabulary is read by run(), before the index renderer is made")
        entries = self.collect_index_entries()
        tags = sorted({tag for entry in entries for tag in entry.tags})
        for tag in tags:
            if not is_usable_tag(tag):
                warnings.warn(DocspecsiteWarning('tag "%s" cannot be a file name, no index page', tag), stacklevel=1)
        return IndexRenderer(
            entries,
            self.collect_code_entries(),
            self.config,
            self.site_title,
            self.vocabulary,
        )

    def run(self, out: Path) -> BuildResult:
        """Build the pages and write the site; a builder builds its site once.

        A page that cannot be built or rendered is left out; see :func:`run_build`.

        Args:
            out: Output directory; its files from the previous build that are not rebuilt are deleted.

        Returns:
            What was built, with the errors of the pages that failed.

        Raises:
            BuildError: In a strict build, on the first :exc:`~docspecsite.errors.DocspecsiteError` of a page.
        """
        with self.prepare_code_root() as code_root:
            if code_root is not None:
                self.hidden_dirs.append(code_root.resolve())
                self.codebase = self.load_codebase(code_root)
            self.resolver = Resolver(
                self.history,
                (self.codebase.index if self.codebase else MappingProxyType({})) if code_root is not None else None,
                self.config,
                self.get_front_matter,
                doc_pages=self,
                extra_files=self.worktree_files,
                should_warn_on_dropped_repo_link=not self.is_missing_source_url_reported,
            )
            self.vocabulary = Vocabulary.parse(self.read_latest_text)
            code_reference = (
                CodeReference.for_commit(
                    self.codebase, self.config, self.history.head, self.latest_docs.titles, locate_doc=self.locate_doc
                )
                if self.codebase
                else None
            )
            extra_children = {CODE_INDEX_DOC: code_reference.build_module_children()} if code_reference else {}
            self.index_renderer = self.make_index_renderer() if self.is_docs_part_built else None
            pending = [
                *self.build_doc_pages(extra_children),
                *(self.build_code_pages(code_reference) if code_reference else []),
                *(self.index_renderer.make_page_makers().items() if self.index_renderer else []),
            ]
            pages: list[BuiltPage] = []
            for name, make in pending:
                page = self.attempt(name, make)
                if page is not None:
                    pages.append((name, page))
        built_urls = frozenset(page.url for _, page in pages)
        pages = [(name, self.keep_built_links(page, built_urls)) for name, page in pages]

        mermaid_files = self.load_mermaid_bundle() if any(page.has_mermaid for _, page in pages) else None
        if mermaid_files is None:
            pages = [(name, self.strip_mermaid(page)) for name, page in pages]
        else:
            self.site_files.update(mermaid_files)
        index_urls = frozenset(
            page.url
            for _, page in pages
            if page.url == STATUS_PAGE
            or (page.url.startswith((TAG_PAGES_DIR, COMPONENT_PAGES_DIR)) and SiteWriter.is_relative_down(page.url))
        )
        for name, page in pages:
            self.emit(name, page, index_urls)
        index_renderer = self.index_renderer
        if index_renderer is not None:
            llms = self.attempt("llms.txt", lambda: index_renderer.render_llms_txt(self.site_summary).encode())
            if llms is not None:
                self.site_files["llms.txt"] = llms
        self.site_files.update(load_static_files())
        self.copy_docs_files()
        writer = SiteWriter(out)
        refused_paths = writer.find_outside(self.site_files)
        for path in refused_paths:
            warnings.warn(DocspecsiteWarning("refusing to write outside --out: %s", path), stacklevel=1)
        writer.write(self.site_files)
        self.cache.prune()
        return BuildResult(
            page_count=len(set(self.page_urls) - set(refused_paths)),
            rendered_count=self.cache.miss_count,
            cached_count=self.cache.hit_count,
            errors=tuple(self.errors),
            failed_count=len(self.failed_names),
        )


def run_build(
    root: Path,
    ref: str,
    out: Path,
    *,
    include_worktree: bool = False,
    vendor_dir: Path | None = None,
    is_strict: bool = False,
    parts: frozenset[Part] | None = None,
) -> BuildResult:
    """Build the static site for a git ref.

    A page that cannot be built or rendered is left out. A :exc:`~docspecsite.errors.DocspecsiteError` is reported in
    :attr:`BuildResult.errors`; an internal error is issued as an :exc:`~docspecsite.errors.InternalErrorWarning` and
    only counted in :attr:`BuildResult.failed_count`. Problems that do not stop the build are issued as
    :exc:`~docspecsite.errors.DocspecsiteWarning`.

    Args:
        root: Repository root to build from.
        ref: Revision to build: its first-parent history gives the doc versions, its tree the code; the settings
            always come from the working tree's ``docspecsite.toml``.
        out: Output directory; its files from the previous build that are not rebuilt are deleted.
        include_worktree: Add working-tree docs that differ from ``ref`` as a newest version, and read the code and
            docs assets from the working tree.
        vendor_dir: Directory of the vendored third-party files the site uses; None reads ``$DOCSPECSITE_VENDOR_DIR``,
            and without either the site is built without them.
        is_strict: Fail on the first :exc:`~docspecsite.errors.DocspecsiteError` of a page, internal error or warning,
            before anything is written: ``error`` warning filters are set for
            :exc:`~docspecsite.errors.DocspecsiteWarning` and :exc:`~docspecsite.errors.InternalErrorWarning` during the
            build.
        parts: The parts of the site to build; None means the docs, and the code too when ``docspecsite.toml`` has
            ``code-dirs``.

    Returns:
        What was built, with the errors of the pages that failed.

    Raises:
        BuildError: The working tree's root ``docspecsite.toml`` cannot be read, is not valid TOML or has an invalid
            value; with ``is_strict``, also on the first :exc:`~docspecsite.errors.DocspecsiteError` of a page, internal
            error or warning; also when ``parts`` has the code part and the settings have no ``code-dirs``.
    """
    if vendor_dir is None and os.environ.get(VENDOR_ENV):
        vendor_dir = Path(os.environ[VENDOR_ENV])
    with SiteBuilder.make_warnings_fatal() if is_strict else nullcontext():
        builder = SiteBuilder(
            root, ref, include_worktree=include_worktree, vendor_dir=vendor_dir, is_strict=is_strict, parts=parts
        )
        return builder.run(out)
