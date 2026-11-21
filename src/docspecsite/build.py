"""The ``docspecsite build`` command and the static site it writes from a ref's history.

Docs: architecture/docs-tooling.md
"""

import difflib
import os
import posixpath
import warnings
from collections.abc import Callable, Container, Generator, Iterable, Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from functools import partial
from html import escape
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from types import MappingProxyType

import griffe

from .cache import BodyCache, compute_fingerprint, make_targets_key
from .codeindex import CodeTarget
from .coderef import CODE_INDEX, Codebase, CodeError, CodeReference
from .config import ConfigError, ProjectConfig
from .docs import DOCS, Doc, is_template, make_string_tuple
from .docset import DocSet
from .errors import DocspecsiteError, DocspecsiteWarning, InternalErrorWarning
from .git import Git
from .history import History, Version
from .indexes import IndexEntry, IndexRenderer
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
from .urls import (
    PageLinks,
    Resolver,
    is_usable_tag,
    list_ancestor_directories,
    make_code_url,
    make_diff_url,
    make_doc_url,
    make_relative_url,
    make_version_url,
)
from .vocabulary import Vocabulary

# A page not built yet: its name in error lines, and how to build it.
type Pending = tuple[str, Callable[[], Page]]

VENDOR_ENV = "DOCSPECSITE_VENDOR_DIR"


class BuildError(DocspecsiteError):
    """Error for a site that cannot be built: an invalid root ``docspecsite.toml``, or a failed strict build."""


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


class SiteBuilder:
    """One site build: what is read from the ref, the pages built from it and the files produced."""

    # Paths
    CACHE_DIR = ".docspecsite-cache"
    """Directory under the repository root that holds the cache of the rendered page bodies."""

    MANIFEST = ".docspecsite-manifest"
    """Name of the file in the output directory that lists the files the last build wrote."""

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
    """Doc versions at the build ref, with the working-tree docs with :attr:`.include_worktree`."""

    latest_docs: DocSet
    """Latest version of each doc that is valid UTF-8."""

    ref_tree: dict[str, str]
    """Blob SHA hashes of the ref's files, by repo path."""

    source_url_missing_reported: bool
    """Whether the build warned at its start that the settings have ``code-dirs`` but no ``source-url``.

    Then the resolver does not warn again about the links it turns into plain text.
    """

    worktree_files: frozenset[str]
    """Working-tree non-Markdown files under ``docs/`` with :attr:`.include_worktree`, else none."""

    # Filled by run()
    codebase: Codebase | None
    """The project code; None until :meth:`.run` loads it, and when the project has no code to load."""

    entries: list[IndexEntry]
    """Index entries of the latest docs with front matter; empty until :meth:`.run` collects them."""

    index_renderer: IndexRenderer | None
    """Renderer of the index pages and ``llms.txt``; None until :meth:`.run` makes it."""

    resolver: Resolver | None
    """Resolver of the docs' links; None until :meth:`.run` makes it."""

    vocabulary: Vocabulary | None
    """The vocabulary of the latest docs; None until :meth:`.run` reads it."""

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
    """See :meth:`.__init__`."""

    include_worktree: bool
    """See :meth:`.__init__`."""

    vendor_dir: Path | None
    """See :meth:`.__init__`."""

    strict: bool
    """See :meth:`.__init__`."""

    def __init__(self, root: Path, ref: str, *, include_worktree: bool, vendor_dir: Path | None, strict: bool) -> None:
        """Read the ref's history, project settings and docs, ready to build pages.

        Args:
            root: Repository root; git runs in it, and working-tree files are read from it.
            ref: Revision to build; its history gives the doc versions and, without
                ``include_worktree``, its ``docspecsite.toml`` the settings.
            include_worktree: Add working-tree docs that differ from ``ref`` as a newest version, and read
                ``docspecsite.toml``, the code and the non-Markdown files under ``docs/`` from the working tree.
            vendor_dir: Directory of the vendored third-party files the site uses, already taken from
                ``$DOCSPECSITE_VENDOR_DIR`` by :func:`.run_build`; None means there are none.
            strict: Raise on the first :exc:`~docspecsite.errors.DocspecsiteError` of a page instead of recording it.
        """
        self.root = root
        self.strict = strict
        self.errors = []
        self.failed_names = set()
        # Absolute paths cut from error messages (never relative ones: "./" would match anywhere).
        self.hidden_dirs = [root.resolve()]
        self.git = Git(root)
        self.include_worktree = include_worktree
        self.vendor_dir = vendor_dir
        self.history = History.load(self.git, ref, worktree=root if include_worktree else None)
        self.worktree_files = (
            frozenset(p for p in self.git.list_worktree_files(DOCS) if not p.endswith(".md"))
            if include_worktree
            else frozenset[str]()
        )
        self.ref_tree = self.git.read_tree(self.history.head)
        self.site_files = {}
        self.page_urls = []
        self.templates = Templates()
        self.cache = BodyCache(root / self.CACHE_DIR, compute_fingerprint())
        # Parsed docs by (doc path relative to docs/, blob SHA hash): each blob of a doc is parsed once.
        self.docs_by_path_and_blob = {}
        latest_versions = (self.history.find_latest(path) for path in sorted(self.history.docs))
        self.latest_docs = DocSet(self.parse_doc_version(v) for v in latest_versions if self.history.is_decodable(v))
        self.config = self.load_config()
        self.source_url_missing_reported = bool(self.config.code_dirs) and not self.config.source_url
        if self.source_url_missing_reported:
            warnings.warn(
                DocspecsiteWarning(
                    "%s has no source-url: links to repository files cannot be made", ProjectConfig.CONFIG_FILE
                ),
                stacklevel=1,
            )
        self.codebase = None
        self.resolver = None
        self.vocabulary = None
        self.entries = []
        self.index_renderer = None

    def parse_doc_version(self, version: Version) -> Doc:
        """Return the parsed doc of a version; the parse is reused for the same blob.

        Args:
            version: Decodable version of a doc; its path and blob key the reused parse.
        """
        key = (version.path, version.blob)
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

    @property
    def site_title(self) -> str:
        """Title of the home doc; ``Docs`` when it has none."""
        home_doc = self.home_doc
        front_matter = home_doc.front_matter if home_doc else None
        return str((front_matter or {}).get("title", "Docs"))

    @property
    def site_summary(self) -> str:
        """Summary of the home doc, for ``llms.txt``; empty when it has none."""
        home_doc = self.home_doc
        front_matter = home_doc.front_matter if home_doc else None
        return str((front_matter or {}).get("summary", ""))

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
            if self.strict:
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
        """Return the settings from the ref's ``docspecsite.toml``, or the working tree's with ``include_worktree`` set.

        Each unknown setting is ignored with a warning.

        Raises:
            BuildError: The file cannot be read, is not valid TOML, or a setting has an invalid value.
        """
        try:
            if self.include_worktree:
                return ProjectConfig.load(self.root).require_valid()
            blob = self.ref_tree.get(ProjectConfig.CONFIG_FILE)
            return ProjectConfig.from_bytes(self.git.read_blobs([blob])[blob] if blob else None).require_valid()
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

    def emit(self, name: str, page: Page, indexes: Container[str]) -> None:
        """Render a page and add it to the site files.

        A page whose rendering fails is recorded as an error and not added.

        Args:
            name: Name of the page in error lines.
            page: Page to render; it is stored at its :attr:`~docspecsite.pages.Page.url`.
            indexes: URLs of the tag and component index pages that were built; links to other tags and components
                are shown as plain text.
        """
        html = self.attempt(name, lambda: self.templates.render(page, self.site_title, indexes=indexes).encode())
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
        hrefs = self.cache.get_hrefs(version.blob, lambda: [link.target for link in MarkdownText(text).extract_links()])
        resolved = {href: links.resolve_link(href) for href in hrefs}

        def link(href: str) -> RenderedLink:
            found = resolved.get(href)
            return found if found is not None else links.resolve_link(href)

        minimum = self.config.toc_min_headings
        key = f"{make_targets_key(resolved)}\0toc={minimum}"
        return self.cache.get_body(version.blob, key, lambda: HtmlRenderer(link, minimum).render(text))

    def build_front_matter_link(self, root_links: PageLinks, value: str) -> PageLink | None:
        """Return the page link for a front-matter path of a version, or None if it cannot be linked.

        The URL is site-root-relative.

        Args:
            root_links: Links of the version holding the front matter, resolved for the site root; the path is
                resolved as if it were a body link of that version, so the target's version and markers match, and
                links from an old version go to the version current then.
            value: Path relative to ``docs/`` with an optional ``#anchor``, as written in ``related`` or
                ``redirect_to``.
        """
        path, sep, anchor = value.partition("#")
        target = posixpath.normpath(path)
        href = posixpath.relpath(target, posixpath.dirname(root_links.version.path) or ".") + sep + anchor
        rendered_link = root_links.resolve_link(href)
        if rendered_link.href is None:
            return None
        doc_path = f"{target}/index.md" if f"{target}/index.md" in self.history.docs else target
        return PageLink(self.latest_docs.titles.get(doc_path, value), rendered_link.href, markers=rendered_link.markers)

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
        front_matter_value = front_matter.get(key)
        paths = front_matter_value if isinstance(front_matter_value, list) else [front_matter_value]
        links = (self.build_front_matter_link(root_links, item) for item in paths if isinstance(item, str))
        return tuple(link for link in links if link is not None)

    def build_doc_pages(self, extra_children: Mapping[str, tuple[PageLink, ...]]) -> list[Pending]:
        """List the pages still to build for every doc.

        These are its latest page, a ``/v/`` page per version and the diff pages. Each is named ``docs/<path>@<id>``
        in error lines.

        Args:
            extra_children: Child links shown on a doc's pages, by doc path relative to ``docs/``; the build gives the
                code reference index its top-level packages. Docs missing from it get none.
        """
        pages: list[Pending] = []
        for path in sorted(self.history.docs):
            versions = self.history.docs[path]
            backlink_list = tuple(
                PageLink(b.title or b.source, make_doc_url(b.source))
                for b in self.latest_docs.backlinks_by_target.get(path, ())
            )
            child_list = extra_children.get(path, ())
            for version in versions:
                name = f"{DOCS}{path}@{version.short_id}"
                urls = [make_version_url(path, version.short_id)]
                if self.history.is_latest(version):
                    urls.insert(0, make_doc_url(path))
                pages.extend(
                    (name, partial(self.build_doc_page, version, url, backlink_list, child_list)) for url in urls
                )
                previous = self.find_diff_base(version)
                if previous is not None:
                    pages.append((name, partial(self.build_diff_page, version, previous)))
        return pages

    def find_diff_base(self, version: Version) -> Version | None:
        """Return the earlier version that the diff page of a version compares it with, or None.

        None means the version has no diff page. A version that is not valid UTF-8 has no diff and is no version's
        previous one; its own pages report it.

        Args:
            version: Version whose diff page is considered; the first version of a doc has none.
        """
        previous = self.history.find_previous(version)
        decodable = previous is not None and self.history.is_decodable(previous) and self.history.is_decodable(version)
        return previous if decodable else None

    def build_common_page(self, version: Version, url: str) -> Page:
        """Return the page of a version at a URL with the parts every doc page shares.

        The body and the other extras are filled in by the caller.

        Args:
            version: Version shown; gives the title, status, components, tags and breadcrumb, and an old-version banner
                when it is not the latest.
            url: Site path the page is written to: the doc's page, a ``/v/`` page or a diff page.
        """
        front_matter = self.get_front_matter(version) or {}
        status = front_matter.get("status")
        old = None
        if not self.history.is_latest(version):
            old = OldBanner(version.date, version.short_id, make_doc_url(version.path))
        return Page(
            url=url,
            title=str(front_matter.get("title", version.path)),
            status=str(status) if status is not None else None,
            components=make_string_tuple(front_matter.get("components")),
            tags=make_string_tuple(front_matter.get("tags")),
            body_html="",
            breadcrumb=build_breadcrumb(version.path, self.latest_docs.titles),
            old=old,
        )

    def build_doc_page(
        self,
        version: Version,
        url: str,
        backlink_list: tuple[PageLink, ...],
        child_list: tuple[PageLink, ...],
    ) -> Page:
        """Return the page of a version, with picker, related docs, backlinks and children.

        Args:
            version: Version shown on the page; the picker lists all versions of its doc.
            url: Site path the page is written to; the latest version is built at both the doc's URL and its ``/v/``
                URL.
            backlink_list: Links to the latest docs that link to this doc, the same for every version.
            child_list: Extra child links of the doc (the code reference index's packages); empty for other docs.
        """
        if self.resolver is None:
            raise RuntimeError("the resolver is made by run(), before the pages are built")
        front_matter = self.get_front_matter(version) or {}
        root_links = PageLinks(self.resolver, version, self.ROOT_PAGE)
        latest = self.history.find_latest(version.path)
        picker = tuple(
            PickerEntry(
                make_picker_label(other),
                make_doc_url(version.path) if other == latest else make_version_url(version.path, other.short_id),
                other == version,
            )
            for other in self.history.docs[version.path]
        )
        redirect = None
        if front_matter.get("status") == "redirect":
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
            diff_url=make_diff_url(version.path, version.short_id)
            if self.find_diff_base(version) is not None
            else None,
            redirect=redirect,
            children=child_list,
            children_heading="Packages",
            related=self.build_front_matter_links(root_links, front_matter, "related"),
            backlinks=backlink_list,
            mermaid=self.MERMAID_MARK in body,
        )

    def build_diff_page(self, version: Version, previous: Version) -> Page:
        """Return the page showing the diff of a version against its previous version.

        Args:
            version: Version the diff page is for, the newer side.
            previous: Version just before ``version``, as :meth:`.find_diff_base` returns it; the older side.
        """
        url = make_diff_url(version.path, version.short_id)
        this_url = (
            make_doc_url(version.path)
            if self.history.is_latest(version)
            else make_version_url(version.path, version.short_id)
        )
        prev_url = make_version_url(previous.path, previous.short_id)
        heading = (
            f'<p class="diff-versions">Changes from <a href="{escape(make_relative_url(prev_url, url))}">'
            f'{escape(make_picker_label(previous))}</a> to <a href="{escape(make_relative_url(this_url, url))}">'
            f"{escape(make_picker_label(version))}</a></p>\n"
        )
        body = heading + self.render_diff_html(self.history.read_text(previous), self.history.read_text(version))
        page = self.build_common_page(version, url)
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
        described: dict[str, list[PageLink]] = {}
        for doc in self.latest_docs:
            modules: dict[str, None] = {}
            for entry in make_string_tuple((doc.front_matter or {}).get("code")):
                target = codebase.index.get(entry)
                modules[target.module if target is not None else entry] = None
            link = PageLink(doc.title, make_doc_url(doc.path))
            for module in modules:
                described.setdefault(module, []).append(link)
        known = {make_doc_url(path) for path in self.history.docs} | {
            make_code_url(CodeTarget(m.path, None)) for m in codebase.modules
        }

        def make(module: griffe.Module) -> Page:
            page = code_reference.build_page(module, described.get(module.path, ()))
            return replace(
                page,
                breadcrumb=tuple(link for link in page.breadcrumb if link.url in known),
                mermaid=self.MERMAID_MARK in page.body_html,
            )

        return [(f"reference/code/{module.path}", partial(make, module)) for module in codebase.modules]

    def copy_docs_files(self) -> None:
        """Copy the non-Markdown files under ``docs/`` into the site at the same path.

        Templates are left out. With :attr:`.include_worktree` the files come from the working tree. A file whose site
        path collides with a generated file or directory is not copied and a warning is issued.
        """
        wanted = {
            path: path.removeprefix(DOCS)
            for path in sorted(self.history.tree | self.worktree_files)
            if path.startswith(DOCS) and not path.endswith(".md") and not is_template(path.removeprefix(DOCS))
        }
        generated = set(self.site_files)
        generated_dirs = {parent for path in generated for parent in list_ancestor_directories(path)}
        blobs = self.git.read_blobs(self.ref_tree[path] for path in wanted if path not in self.worktree_files)
        for path, site_path in wanted.items():
            if (
                site_path in generated
                or site_path in generated_dirs
                or generated.intersection(list_ancestor_directories(site_path))
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
        script = directory / "mermaid.min.js" if directory is not None else None
        if directory is None or script is None or not script.is_file():
            where = f"in {directory}" if directory is not None else f"({VENDOR_ENV} is not set)"
            warnings.warn(
                DocspecsiteWarning("mermaid bundle not found %s; diagrams are shown as source", where), stacklevel=1
            )
            return None
        files = {"assets/mermaid.min.js": script.read_bytes()}
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
    def prepare_code_root(self) -> Generator[Path]:
        """Provide the directory the code is read from.

        That is the working tree with :attr:`.include_worktree`, or else the ref's code directories extracted to a
        temporary directory that is removed on exit.
        """
        if self.include_worktree:
            yield self.root
            return
        with TemporaryDirectory(prefix="docspecsite-code-") as tmp:
            dirs = self.find_code_dirs()
            if dirs:
                self.git.extract(self.history.head, dirs, Path(tmp))
            yield Path(tmp)

    def read_latest_text(self, path: str) -> str | None:
        """Return the text of the latest version of a doc, or None when there is no such doc or it is not valid UTF-8.

        Args:
            path: Doc path relative to ``docs/``, as the vocabulary names its source docs.
        """
        latest = self.history.find_latest(path) if path in self.history.docs else None
        return self.history.read_text(latest) if latest is not None and self.history.is_decodable(latest) else None

    def collect_index_entries(self) -> list[IndexEntry]:
        """Return the index entries of the latest docs that have front matter, ordered by doc path."""
        return [
            IndexEntry(doc.path, make_doc_url(doc.path), doc.front_matter)
            for doc in sorted(self.latest_docs, key=lambda doc: doc.path)
            if doc.front_matter is not None
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
                m.path,
                make_code_url(CodeTarget(m.path, None)),
                {
                    "title": m.path,
                    "layer": "reference",
                    "status": "implemented",
                    "tags": [],
                    "components": list(self.config.get_components(m.path)),
                },
            )  # fmt: skip
            for m in self.codebase.modules
        ]

    @staticmethod
    def keep_built_links(page: Page, built: Container[str]) -> Page:
        """Return a page with its version-picker entries and diff link limited to pages that were built.

        Args:
            page: Built page whose picker and diff link may point to pages that failed.
            built: URLs of every page built without error.
        """
        picker = tuple(entry for entry in page.picker if entry.url in built)
        diff = page.diff_url if page.diff_url is not None and page.diff_url in built else None
        return replace(page, picker=picker, diff_url=diff) if (picker, diff) != (page.picker, page.diff_url) else page

    @staticmethod
    def strip_mermaid(page: Page) -> Page:
        """Return a page that does not load the Mermaid script.

        Args:
            page: Built page, whose body may hold diagrams; they are then shown as source.
        """
        return replace(page, mermaid=False) if page.mermaid else page

    @classmethod
    def find_outside(cls, out: Path, paths: Iterable[str]) -> list[str]:
        """Return those paths that the ``write_site`` method would refuse to write below a directory.

        Args:
            out: Output directory, resolved to follow symlinks.
            paths: Site paths of the files about to be written.
        """
        base = out.resolve()
        return [path for path in paths if not cls.is_inside(base, path)]

    @classmethod
    def write_site(cls, out: Path, files: Mapping[str, bytes]) -> list[str]:
        """Write the site's files below ``out`` and remove files left over from the previous build.

        Only files whose bytes changed are rewritten. ``<out>/.docspecsite-manifest`` lists the files written; nothing
        outside the previous manifest is ever deleted.

        Args:
            out: Output directory; created when missing, and holding the manifest of the previous build.
            files: Every file of the new site, as bytes by site path relative to ``out``; files of the previous build
                not in it are deleted.

        Returns:
            The paths that would land outside ``out`` (also through a symlink); they are neither written nor deleted.
        """
        out.mkdir(parents=True, exist_ok=True)
        base = out.resolve()
        manifest = out / cls.MANIFEST
        previous = manifest.read_text(encoding="utf-8").splitlines() if manifest.is_file() else []
        refused: list[str] = []
        for path, data in files.items():
            if cls.is_inside(base, path):
                cls.write_if_changed(out / path, data)
            else:
                refused.append(path)
        for path in previous:
            if path in files or not cls.is_inside(base, path):
                continue
            target = out / path
            if target.is_file() and not target.is_symlink():
                target.unlink()
        written = sorted(path for path in files if path not in refused)
        cls.write_if_changed(manifest, "".join(f"{path}\n" for path in written).encode())
        return refused

    @staticmethod
    def is_relative_down(path: str) -> bool:
        """Return whether a path is a non-empty relative path without ``..`` or NUL.

        Args:
            path: Site path to be written under the output directory, or a page URL to be linked as an index.
        """
        pure = PurePosixPath(path)
        return bool(path) and "\0" not in path and not pure.is_absolute() and ".." not in pure.parts

    @classmethod
    def is_inside(cls, base: Path, path: str) -> bool:
        """Return whether a path stays below a directory, also after resolving symlinks.

        Args:
            base: Resolved output directory that nothing may be written outside of.
            path: Site path to write or delete, relative to ``base``.
        """
        return cls.is_relative_down(path) and (base / path).resolve().is_relative_to(base)

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

    def run(self, out: Path) -> BuildResult:
        """Build the pages and write the site; a builder builds its site once.

        A page that cannot be built or rendered is left out; see :func:`.run_build`.

        Args:
            out: Output directory; its files from the previous build that are not rebuilt are deleted.

        Returns:
            What was built, with the errors of the pages that failed.

        Raises:
            BuildError: In a strict build, on the first :exc:`~docspecsite.errors.DocspecsiteError` of a page.
        """
        with self.prepare_code_root() as code_root:
            self.hidden_dirs.append(code_root.resolve())
            self.codebase = self.load_codebase(code_root)
            self.resolver = Resolver(
                self.history,
                self.codebase.index if self.codebase else MappingProxyType({}),
                self.config,
                self.get_front_matter,
                extra_files=self.worktree_files,
                warn_on_dropped_repo_link=not self.source_url_missing_reported,
            )
            self.vocabulary = Vocabulary.parse(self.read_latest_text)
            code_reference = (
                CodeReference.for_commit(self.codebase, self.config, self.history.head, self.latest_docs.titles)
                if self.codebase
                else None
            )
            extra_children = {CODE_INDEX: code_reference.build_module_children()} if code_reference else {}
            self.entries = self.collect_index_entries()
            tags = sorted({tag for entry in self.entries for tag in make_string_tuple(entry.front_matter.get("tags"))})
            for tag in tags:
                if not is_usable_tag(tag):
                    warnings.warn(
                        DocspecsiteWarning('tag "%s" cannot be a file name, no index page', tag), stacklevel=1
                    )
            self.index_renderer = IndexRenderer(
                self.entries,
                self.collect_code_entries(),
                self.config,
                self.site_title,
                self.vocabulary,
            )
            pending = [
                *self.build_doc_pages(extra_children),
                *(self.build_code_pages(code_reference) if code_reference else []),
                *self.index_renderer.make_page_makers().items(),
            ]
            pages: list[tuple[str, Page]] = []
            for name, make in pending:
                page = self.attempt(name, make)
                if page is not None:
                    pages.append((name, page))
        built = frozenset(page.url for _, page in pages)
        pages = [(name, self.keep_built_links(page, built)) for name, page in pages]

        mermaid = self.load_mermaid_bundle() if any(page.mermaid for _, page in pages) else None
        if mermaid is None:
            pages = [(name, self.strip_mermaid(page)) for name, page in pages]
        else:
            self.site_files.update(mermaid)
        indexes = frozenset(
            page.url
            for _, page in pages
            if page.url.startswith(("tags/", "components/")) and self.is_relative_down(page.url)
        )
        for name, page in pages:
            self.emit(name, page, indexes)
        llms = self.attempt(
            "llms.txt",
            lambda: self.index_renderer.render_llms_txt(self.site_summary).encode(),
        )
        if llms is not None:
            self.site_files["llms.txt"] = llms
        self.site_files.update(load_static_files())
        self.copy_docs_files()
        refused = self.find_outside(out, self.site_files)
        for path in refused:
            warnings.warn(DocspecsiteWarning("refusing to write outside --out: %s", path), stacklevel=1)
        self.write_site(out, self.site_files)
        self.cache.prune()
        return BuildResult(
            page_count=len(set(self.page_urls) - set(refused)),
            rendered_count=self.cache.miss_count,
            cached_count=self.cache.hit_count,
            errors=tuple(self.errors),
            failed_count=len(self.failed_names),
        )


@contextmanager
def make_warnings_fatal() -> Generator[None]:
    """Turn docspecsite's warnings into exceptions in the block, and the first one raised into a ``BuildError``.

    Raises:
        BuildError: A :exc:`~docspecsite.errors.DocspecsiteWarning` or :exc:`~docspecsite.errors.InternalErrorWarning`
            was issued in the block.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", DocspecsiteWarning)
        warnings.simplefilter("error", InternalErrorWarning)
        try:
            yield
        except (DocspecsiteWarning, InternalErrorWarning) as warning:
            raise BuildError("strict: %s", warning) from warning


def run_build(
    root: Path,
    ref: str,
    out: Path,
    *,
    include_worktree: bool = False,
    vendor_dir: Path | None = None,
    strict: bool = False,
) -> BuildResult:
    """Build the static site for a git ref.

    A page that cannot be built or rendered is left out. A :exc:`~docspecsite.errors.DocspecsiteError` is reported in
    :attr:`.BuildResult.errors`; an internal error is issued as an :exc:`~docspecsite.errors.InternalErrorWarning` and
    only counted in :attr:`.BuildResult.failed_count`. Problems that do not stop the build are issued as
    :exc:`~docspecsite.errors.DocspecsiteWarning`.

    Args:
        root: Repository root to build from.
        ref: Revision to build: its first-parent history gives the doc versions, its tree the code and
            settings.
        out: Output directory; its files from the previous build that are not rebuilt are deleted.
        include_worktree: Add working-tree docs that differ from ``ref`` as a newest version, and read the code,
            ``docspecsite.toml`` and docs assets from the working tree.
        vendor_dir: Directory of the vendored third-party files the site uses; None reads ``$DOCSPECSITE_VENDOR_DIR``,
            and without either the site is built without them.
        strict: Fail on the first :exc:`~docspecsite.errors.DocspecsiteError` of a page, internal error or warning,
            before anything is written: ``error`` warning filters are set for
            :exc:`~docspecsite.errors.DocspecsiteWarning` and :exc:`~docspecsite.errors.InternalErrorWarning` during the
            build.

    Returns:
        What was built, with the errors of the pages that failed.

    Raises:
        BuildError: The root ``docspecsite.toml`` cannot be read, is not valid TOML or has an invalid value; with
            ``strict``, also on the first :exc:`~docspecsite.errors.DocspecsiteError` of a page, internal error or
            warning.
    """
    if vendor_dir is None and os.environ.get(VENDOR_ENV):
        vendor_dir = Path(os.environ[VENDOR_ENV])
    with make_warnings_fatal() if strict else nullcontext():
        builder = SiteBuilder(root, ref, include_worktree=include_worktree, vendor_dir=vendor_dir, strict=strict)
        return builder.run(out)
