"""The renderer seam: what the build front hands a site renderer, and what the renderer gives back.

The build front loads everything a renderer must not decide twice and passes it as one :class:`PreparedSite`; a
:class:`SiteRenderer` places it on pages and returns a :class:`RenderedSite`, the list of the site's files, which the
front writes.

Docs: architecture/site.md#the-renderer-seam
"""

import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from .coderef import Codebase
from .config import ProjectConfig
from .diskcache import FrontMatterCache
from .docs import DOCS_DIR, Doc
from .docset import DocSet
from .history import History, Version
from .indexes import SiteIndex
from .markdown import MarkdownText
from .parts import Part
from .urls import CODE_INDEX_DOC, Resolver, encode_href_path, map_reserved_owners

VENDOR_ENV = "DOCSPECSITE_VENDOR_DIR"
"""Environment variable naming the directory of the vendored third-party files the site uses."""


class RendererName(StrEnum):
    """The name of a site renderer; the ``sphinx`` renderer comes with its setting and option."""

    INTERNAL = "internal"
    """The custom renderer of docspecsite, kept for the migration."""


class PageCountLabel(StrEnum):
    """What a count of pages in the build's summary line counts."""

    RENDERED = "rendered"
    """Pages whose bodies were rendered in this build."""

    FROM_CACHE = "from cache"
    """Pages whose bodies came from an earlier build."""


RENDERER_PATHS: Mapping[RendererName, str] = MappingProxyType(
    {RendererName.INTERNAL: "docspecsite.internal_renderer:InternalRenderer"}
)
"""Where each renderer's :class:`SiteRenderer` class is, as ``<module>:<class>``, imported only when it is used."""


class PageAttempt(Protocol):
    """How the build front runs the making of one page or file, keeping an error local to it."""

    def __call__[T](self, name: str, make: Callable[[], T]) -> T | None:
        """Call a function and return its result, or None when it fails; the front records the failure.

        Args:
            name: Name of the page or file in error lines and warnings, e.g. ``docs/<path>@<id>``.
            make: Builds the page, its HTML or another site file.
        """
        ...


@dataclass(frozen=True)
class PageCount:
    """One count of the build's summary line."""

    label: PageCountLabel
    """What is counted."""

    count: int
    """How many pages."""


@dataclass(frozen=True)
class RenderedSite:
    """What a renderer made: the site's files, ready in the staging directory."""

    files: Mapping[str, Path]
    """The staged file that holds each file of the site, by output path relative to the output directory."""

    page_paths: frozenset[str]
    """Output paths of the files that are pages, counted in the summary line."""

    counts: tuple[PageCount, ...]
    """The labelled counts of the pages, in the order the summary line shows them."""


def stage_file(staging_dir: Path, data: bytes) -> Path:
    """Write a site file into the staging directory and return the staged file.

    The staged file gets a new name of its own, so no output path can lead out of the directory.

    Args:
        staging_dir: The build's staging directory, :attr:`PreparedSite.staging_dir`.
        data: Contents of the site file.
    """
    with tempfile.NamedTemporaryFile(dir=staging_dir, delete=False) as staged:
        staged.write(data)
    return Path(staged.name)


class SiteDocs:
    """The docs of one build: their parsed versions, and which of their pages the build writes.

    Docs: architecture/docs-tooling.md#parts
    """

    # Read from the history
    docs_by_path_and_blob: dict[tuple[str, str], Doc]
    """Parsed docs by doc path and blob SHA hash, so each blob of a doc is parsed once."""

    latest_docs: DocSet
    """Latest version of each doc that is valid UTF-8."""

    # Arguments of __init__
    history: History
    """See :meth:`__init__`."""

    parts: frozenset[Part]
    """See :meth:`__init__`."""

    source_url: str
    """See :meth:`__init__`."""

    front_matter_cache: FrontMatterCache
    """See :meth:`__init__`."""

    def __init__(
        self, history: History, parts: frozenset[Part], source_url: str, front_matter_cache: FrontMatterCache
    ) -> None:
        """Parse the latest version of each doc.

        Args:
            history: Doc versions at the build ref, without docs whose names are not valid UTF-8.
            parts: The parts of the site this build produces.
            source_url: Base URL of the repository on its host, from the settings; empty when there is none.
            front_matter_cache: Cache of the front matter splits, so a rebuild parses no unchanged doc again.
        """
        self.history = history
        self.parts = parts
        self.source_url = source_url
        self.front_matter_cache = front_matter_cache
        self.docs_by_path_and_blob = {}
        latest_versions = (history.find_latest(path) for path in sorted(history.versions_by_path))
        self.latest_docs = DocSet(self.parse_doc_version(v) for v in latest_versions if history.is_decodable(v))

    def parse_doc_version(self, version: Version) -> Doc:
        """Return the parsed doc of a version; the parse is reused for the same blob.

        Args:
            version: Decodable version of a doc; its path and blob key the reused parse.
        """
        key = (version.path, version.blob_sha)
        if key not in self.docs_by_path_and_blob:
            text = self.history.read_text(version)
            split = self.front_matter_cache.get_front_matter_split(
                version.blob_sha, lambda: MarkdownText(text).split_front_matter()
            )
            self.docs_by_path_and_blob[key] = Doc.parse(version.path, text, split)
        return self.docs_by_path_and_blob[key]

    def get_front_matter(self, version: Version) -> Mapping[str, object] | None:
        """Return the front matter of a version.

        The result is None when the version has none or is not valid UTF-8; its own pages report the latter.

        Args:
            version: Version whose front matter is wanted, e.g. a page's own version or a link's target version.
        """
        return self.parse_doc_version(version).front_matter if self.history.is_decodable(version) else None

    def read_latest_text(self, path: str) -> str | None:
        """Return the text of the latest version of a doc, or None when there is no such doc or it is not valid UTF-8.

        Args:
            path: Doc path relative to ``docs/``, as the vocabulary names its source docs.
        """
        latest = self.history.find_latest(path) if path in self.history.versions_by_path else None
        return self.history.read_text(latest) if latest is not None and self.history.is_decodable(latest) else None

    @property
    def home_doc(self) -> Doc | None:
        """The latest version of the home doc, ``index.md``; None when there is none."""
        return self.latest_docs.by_path.get("index.md")

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

    def locate_unbuilt_doc(self, path: str) -> str | None:
        """Return the URL a link to a doc whose pages are not built goes to, or None to show the link as text.

        A doc of the docs part is linked from the code reference, so the link goes to the doc's Markdown file at the
        built commit on the repository host, given by ``source-url``; None when the settings have no ``source-url`` or
        the doc is not in the built commit (a working-tree doc). A doc of the code part is linked from the docs, which
        never link outside the site for it: None. A doc missing from the history has no page anywhere: None.

        Args:
            path: Doc path relative to ``docs/``, e.g. from a ``Docs:`` line, a doc whose ``code`` names a module or a
                link in a doc's body or front matter.
        """
        if path not in self.history.versions_by_path:
            return None
        if self.is_code_doc(path):
            return None  # the code part's entry page, linked from the docs
        if not self.source_url:
            return None
        if f"{DOCS_DIR}{path}" not in self.history.tree:
            return None  # a working-tree doc, not in the built commit
        return f"{self.source_url}/blob/{self.history.head}/{DOCS_DIR}{encode_href_path(path)}"


@dataclass(frozen=True)
class PreparedSite:
    """Everything the build front prepares for a renderer: the docs, the code, the links, the files and the output."""

    docs: SiteDocs
    """The docs, their history and the parts built."""

    config: ProjectConfig
    """The project settings, with only the known ``code-components``."""

    resolver: Resolver
    """The version-aware target and marker of each link of the docs."""

    codebase: Codebase | None
    """The project code at the ref; None when the code part is not built or the code cannot be loaded."""

    changed_code_paths: frozenset[str]
    """Repo paths of the code files that differ from the built revision's; their pages have no source links."""

    site_index: SiteIndex | None
    """The index entries and their grouping, and the ``llms.txt`` text; None in a build without the docs part."""

    docs_files: Mapping[str, Path]
    """The staged file of each non-Markdown file under ``docs/`` that the site copies, by its repo path."""

    vendor_dir: Path | None
    """Directory of the vendored third-party files the site uses; None means there are none."""

    cache_dir: Path
    """Directory in the checked repo where a renderer keeps what it reuses between builds."""

    staging_dir: Path
    """Directory where the renderer stages the site's files (:func:`stage_file`); the front removes it."""

    attempt: PageAttempt
    """Runs the making of each page or file, so an error stays local to it and ``--strict`` stops at the first."""


class SiteRenderer(ABC):
    """A site renderer: it turns the prepared input into the site's files."""

    @abstractmethod
    def render(self, site: PreparedSite) -> RenderedSite:
        """Return the site's files made from the prepared input.

        Args:
            site: The docs, code, links and files the build front prepared.
        """
