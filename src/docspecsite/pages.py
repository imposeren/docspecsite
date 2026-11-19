"""The page model and the HTML chrome around it.

See the page anatomy in ``docs/architecture/docs-tooling.md``.

Docs: architecture/docs-tooling.md
"""

import posixpath
import re
from collections.abc import Callable, Container, Mapping
from dataclasses import dataclass
from importlib.resources import files
from types import MappingProxyType
from typing import cast

from jinja2 import Environment, PackageLoader, StrictUndefined, pass_context
from jinja2.runtime import Context

from .history import WORKTREE, Version
from .markdown import Marker
from .resolve import encode_href_path, make_component_url, make_doc_url, make_relative_url, make_tag_url

STATIC_FILES = ("docspecsite.css", "docspecsite.js")
LEADING_H1 = re.compile(r"\s*(<h1[\s>].*?</h1>)\s*", re.S)

REDIRECT_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "renamed": "Renamed",
        "moved": "Moved",
        "merged": "Merged",
        "split": "Split",
        "became-directory": "Became a directory",
        "replaced": "Replaced by",
        "removed": "Removed",
    }
)


@dataclass(frozen=True)
class PageLink:
    """Link in the page chrome (breadcrumb, picker, lists), with an optional summary.

    ``markers`` are shown after the link.
    """

    title: str
    url: str
    summary: str = ""
    markers: tuple[Marker, ...] = ()


@dataclass(frozen=True)
class PickerEntry:
    """Entry of a page's version picker: its label, the version's URL and whether it is the page shown."""

    label: str
    url: str
    current: bool


@dataclass(frozen=True)
class OldBanner:
    """Banner of a page that shows a version other than the latest, with its date, short id and the latest page."""

    date: str
    short: str
    latest_url: str


@dataclass(frozen=True)
class RedirectNotice:
    """Notice of a redirect doc: what happened to it, where readers should go and why."""

    label: str
    targets: tuple[PageLink, ...]
    reason: str


@dataclass(frozen=True)
class Page:
    """One HTML page of the site, with everything its template shows.

    Every URL is site-root-relative; the template makes them relative to ``url``.
    """

    url: str
    title: str
    status: str | None
    components: tuple[str, ...]
    tags: tuple[str, ...]
    body_html: str
    breadcrumb: tuple[PageLink, ...] = ()
    picker: tuple[PickerEntry, ...] = ()
    diff_url: str | None = None
    old: OldBanner | None = None
    redirect: RedirectNotice | None = None
    children: tuple[PageLink, ...] = ()
    children_heading: str = "Submodules"
    related: tuple[PageLink, ...] = ()
    backlinks: tuple[PageLink, ...] = ()
    described_in: tuple[PageLink, ...] = ()
    mermaid: bool = False

    @property
    def body_h1(self) -> str | None:
        """The ``<h1>`` element the body starts with, or None if it does not start with one.

        The template shows it in the title position.
        """
        match = LEADING_H1.match(self.body_html)
        return match.group(1) if match else None

    @property
    def body_rest(self) -> str:
        """The body HTML without its leading ``<h1>`` element."""
        match = LEADING_H1.match(self.body_html)
        return self.body_html[match.end() :] if match else self.body_html


def make_picker_label(version: Version) -> str:
    """Return the label of a version in the version picker.

    It reads ``<date> · <short-sha> · <subject>``; the working copy shows only its subject.

    Args:
        version: Version shown as an entry of the picker, or in a diff page's heading.
    """
    if version.short_id == WORKTREE:
        return version.subject
    return f"{version.date} · {version.short_id} · {version.subject}"


def make_dir_index_path(directory: str) -> str:
    """Return the doc path of the index of a directory; empty for the docs root.

    Args:
        directory: Directory relative to ``docs/`` whose ``index.md`` is wanted; empty for ``docs/`` itself.
    """
    return f"{directory}/index.md" if directory else "index.md"


def build_breadcrumb(path: str, titles: Mapping[str, str]) -> tuple[PageLink, ...]:
    """Return the breadcrumb links for a doc, root first.

    They go to the ``index.md`` of every directory above the doc that has one. A directory whose index is not in
    ``titles`` is left out.

    Args:
        path: Path of the doc the page shows, relative to ``docs/``; an ``index.md`` does not link to itself.
        titles: Titles of the latest docs by path relative to ``docs/``; give the link texts and decide which
            directory indexes exist.
    """
    directory = posixpath.dirname(path)
    if posixpath.basename(path) == "index.md":
        if not directory:
            return ()
        directory = posixpath.dirname(directory)
    chain: list[str] = []
    while True:
        chain.append(make_dir_index_path(directory))
        if not directory:
            break
        directory = posixpath.dirname(directory)
    return tuple(PageLink(titles[index], make_doc_url(index)) for index in reversed(chain) if index in titles)


def create_environment() -> Environment:
    """Return a Jinja environment configured to render this package's page templates."""
    return Environment(
        loader=PackageLoader("docspecsite"),
        autoescape=True,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )


class Templates:
    """Jinja templates of the package, rendering ``Page`` objects to HTML.

    Attributes:
        environment: Jinja environment loading the package's templates, with docspecsite's filters.
    """

    def __init__(self) -> None:
        self.environment = create_environment()
        # Jinja leaves ``filters`` unannotated, so its inferred value type is the union of the built-in filters.
        filters = cast(dict[str, Callable[..., object]], self.environment.filters)
        filters["rel"] = self.make_relative
        filters["rel_href"] = self.make_relative_href
        filters["tag_url"] = make_tag_url
        filters["component_url"] = make_component_url

    @staticmethod
    @pass_context
    def make_relative(context: Context, url: str) -> str:
        """Return a site-root-relative URL made relative to the page being rendered (Jinja filter).

        Args:
            context: Render context; its ``page`` gives the URL the result is relative to.
            url: Site-root-relative URL of a chrome link (breadcrumb, picker, asset); used as is, not percent-encoded.
        """
        page: Page = context["page"]
        return make_relative_url(url, page.url)

    @staticmethod
    @pass_context
    def make_relative_href(context: Context, path: str) -> str:
        """Return a site path percent-encoded and relative to the page being rendered (Jinja filter).

        Args:
            context: Render context; its ``page`` gives the URL the result is relative to.
            path: Unencoded site path of a tag or component index page, as ``make_tag_url`` and ``make_component_url``
                give it.
        """
        page: Page = context["page"]
        return make_relative_url(encode_href_path(path), page.url)

    def render(self, page: Page, site_title: str, *, indexes: Container[str] | None = None) -> str:
        """Render a page to HTML.

        Args:
            page: Page to render; its ``url`` is the base of every relative link in the output.
            site_title: Title of the home doc, appended to the page title in ``<title>``.
            indexes: The index URLs that tag and component links may point to; links to others are not made. None makes
                every such link.
        """
        return self.environment.get_template("page.html").render(page=page, site_title=site_title, indexes=indexes)


def load_static_files() -> dict[str, bytes]:
    """Return the site's own assets (stylesheet and script) as bytes, by site path."""
    static = files("docspecsite") / "static"
    return {f"assets/{name}": (static / name).read_bytes() for name in STATIC_FILES}
