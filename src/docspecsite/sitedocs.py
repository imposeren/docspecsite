"""The docs of one site build: their parsed versions, the parts built and which doc pages the build writes.

The build front makes it and hands it to the site renderer in the prepared input.

Docs: architecture/docs-tooling.md#parts
"""

from collections.abc import Mapping
from functools import cached_property
from pathlib import Path
from types import MappingProxyType

from .config import ProjectConfig
from .diskcache import FrontMatterCache
from .docs import DOCS_DIR, Doc
from .docset import DocSet
from .history import History, Version
from .markdown import MarkdownText
from .parts import Part
from .urls import CODE_INDEX_DOC, encode_href_path, map_reserved_owners


class SiteDocs:
    """The docs of one build: their parsed versions, and which of their pages the build writes.

    Docs: architecture/docs-tooling.md#parts
    """

    # Helpers
    front_matter_cache: FrontMatterCache
    """Cache of the front matter splits, so a rebuild parses no unchanged doc again."""

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

    config: ProjectConfig
    """See :meth:`__init__`."""

    def __init__(
        self,
        history: History,
        parts: frozenset[Part],
        config: ProjectConfig,
        *,
        cache_dir: Path,
        cache_fingerprint: str,
    ) -> None:
        """Parse the latest version of each doc.

        Args:
            history: Doc versions at the build ref, without docs whose names are not valid UTF-8.
            parts: The parts of the site this build produces.
            config: The project settings; their ``source-url`` gives the links to docs whose pages are not built.
            cache_dir: Directory holding the cache roots; the front matter splits are kept in a root of their own
                under it, one per set of built parts.
            cache_fingerprint: Docspecsite version fingerprint; cache entries made under another one are never read.
        """
        self.history = history
        self.parts = parts
        self.config = config
        self.front_matter_cache = FrontMatterCache(cache_dir, cache_fingerprint, self.parts_label)
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
            split = self.front_matter_cache.load_or_compute_front_matter_split(
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
    def compute_doc_part(path: str) -> Part:
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
        return cls.compute_doc_part(path) is Part.CODE

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
        return self.compute_doc_part(path) in self.parts

    @property
    def parts_label(self) -> str:
        """The names of the parts built, sorted and joined by ``+``, e.g. ``code+docs``."""
        return "+".join(sorted(self.parts))

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
        source_url = self.config.source_url
        if not source_url:
            return None
        if f"{DOCS_DIR}{path}" not in self.history.tree:
            return None  # a working-tree doc, not in the built commit
        return f"{source_url}/blob/{self.history.head}/{DOCS_DIR}{encode_href_path(path)}"
