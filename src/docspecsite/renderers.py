"""The renderer seam: what the build front hands a site renderer, and what the renderer gives back.

The build front loads everything a renderer must not decide twice and passes it as one :class:`PreparedSite`; a
:class:`SiteRenderer` places it on pages and returns a :class:`RenderedSite`, the list of the site's files, which the
front writes.

Docs: architecture/site.md#the-renderer-seam
"""

import pkgutil
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar, Protocol

from .coderef import Codebase
from .config import ProjectConfig
from .indexes import SiteIndex
from .sitedocs import SiteDocs
from .urls import Resolver

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
    """The file that holds each file of the site, by output path relative to the output directory: one staged in the
    staging directory, or a working-tree file under ``docs/`` that is copied as it is."""

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

    cache_fingerprint: str
    """Docspecsite version fingerprint, computed once per build; a renderer's cache entries made under another one are
    never read."""

    staging_dir: Path
    """Directory where the renderer stages the site's files (:func:`stage_file`); the front removes it."""

    attempt: PageAttempt
    """The front's page guard, which runs the making of each page or file so that an error stays local to it and
    ``--strict`` stops at the first."""


class SiteRenderer(ABC):
    """A site renderer: it turns the prepared input into the site's files."""

    IMPORT_PATHS: ClassVar[Mapping[RendererName, str]] = MappingProxyType(
        {RendererName.INTERNAL: "docspecsite.internal_renderer:InternalRenderer"}
    )
    """Where each renderer's class is, as ``<module>:<class>``; its module is imported only when it is used."""

    @classmethod
    def load(cls, name: RendererName) -> SiteRenderer:
        """Return the site renderer of a name, importing its module only now.

        Args:
            name: The renderer to use.

        Raises:
            TypeError: The renderer's import path does not name a site renderer class.
        """
        renderer_class = pkgutil.resolve_name(cls.IMPORT_PATHS[name])
        if not (isinstance(renderer_class, type) and issubclass(renderer_class, SiteRenderer)):
            raise TypeError(f"{cls.IMPORT_PATHS[name]} is not a site renderer")
        return renderer_class()

    @abstractmethod
    def render(self, site: PreparedSite) -> RenderedSite:
        """Return the site's files made from the prepared input.

        Args:
            site: The docs, code, links and files the build front prepared.
        """
