"""The page model and the HTML chrome around it.

A page is a doc's rendered body with its chrome: breadcrumb, title, status badge, components and tags, version
picker, and the related and backlinks panel; an old version also gets a warning banner and a redirect doc a notice.

Docs: architecture/docs-tooling.md
"""

import posixpath
import re
from collections.abc import Callable, Container, Mapping
from dataclasses import dataclass
from importlib.resources import files
from types import MappingProxyType
from typing import ClassVar, cast

from jinja2 import Environment, PackageLoader, StrictUndefined, pass_context
from jinja2.runtime import Context

from .history import Version
from .markdown import Marker
from .urls import encode_href_path, make_component_url, make_doc_url, make_relative_url, make_tag_url

STATIC_FILES = ("docspecsite.css", "docspecsite.js")


@dataclass(frozen=True)
class PageLink:
    """Link in the page chrome (breadcrumb, picker, lists)."""

    title: str
    """Text of the link."""

    url: str | None
    """Site-root-relative URL the link points to; None shows the title as text."""

    summary: str = ""
    """Summary shown next to the link; empty for none."""

    markers: tuple[Marker, ...] = ()
    """Labels shown after the link."""


@dataclass(frozen=True)
class PickerEntry:
    """Entry of a page's version picker, for one version of the doc."""

    label: str
    """Text of the entry, naming the version."""

    url: str
    """Site-root-relative URL of the version's page."""

    current: bool
    """Whether the version is the one shown on the page."""


@dataclass(frozen=True)
class OldBanner:
    """Banner of a page that shows a version other than the latest."""

    date: str
    """Committer date of the version shown, ``YYYY-MM-DD``."""

    short: str
    """Short id of the version shown."""

    latest_url: str
    """Site-root-relative URL of the latest version's page."""


@dataclass(frozen=True)
class RedirectNotice:
    """Notice of a redirect doc."""

    REDIRECT_LABELS: ClassVar[Mapping[str, str]] = MappingProxyType(
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
    """Label of each redirect kind, shown as what happened to the doc."""

    label: str
    """What happened to the doc, from :attr:`REDIRECT_LABELS`; the redirect kind itself when it has no label."""

    targets: tuple[PageLink, ...]
    """Links to where readers should go instead."""

    reason: str
    """Why the doc redirects; empty when it gives no reason."""


@dataclass(frozen=True)
class Page:
    """One HTML page of the site, with everything its template shows.

    Every URL is site-root-relative; the template makes them relative to :attr:`url`.
    """

    LEADING_H1: ClassVar[re.Pattern[str]] = re.compile(r"\s*(<h1[\s>].*?</h1>)\s*", re.S)
    """An ``<h1>`` element at the start of a body, with the spaces around it."""

    url: str
    """Site path the page is written to."""

    title: str
    """Title of the page."""

    status: str | None
    """Status shown as a badge, e.g. ``implemented``; None for no badge."""

    components: tuple[str, ...]
    """Components shown as badges."""

    tags: tuple[str, ...]
    """Tags shown as badges."""

    body_html: str
    """Rendered HTML of the page's content."""

    breadcrumb: tuple[PageLink, ...] = ()
    """Links to the pages above this one, from the top."""

    picker: tuple[PickerEntry, ...] = ()
    """Entries of the version picker; empty for no picker."""

    diff_url: str | None = None
    """URL of the diff against the previous version; None when there is none."""

    old: OldBanner | None = None
    """Banner for a version other than the latest; None for the latest version."""

    redirect: RedirectNotice | None = None
    """Notice of a redirect doc; None for other pages."""

    children: tuple[PageLink, ...] = ()
    """Links shown in the children panel."""

    children_heading: str = "Submodules"
    """Heading of the children panel."""

    related: tuple[PageLink, ...] = ()
    """Links to the related docs."""

    backlinks: tuple[PageLink, ...] = ()
    """Links to the docs that link to this page's doc."""

    described_in: tuple[PageLink, ...] = ()
    """Links to the docs describing the code on this page."""

    mermaid: bool = False
    """Whether the body has a Mermaid diagram, so the page loads the Mermaid script."""

    @property
    def body_h1(self) -> str | None:
        """The ``<h1>`` element the body starts with, or None if it does not start with one.

        The template shows it in the title position.
        """
        match = self.LEADING_H1.match(self.body_html)
        return match.group(1) if match else None

    @property
    def body_rest(self) -> str:
        """The body HTML without its leading ``<h1>`` element."""
        match = self.LEADING_H1.match(self.body_html)
        return self.body_html[match.end() :] if match else self.body_html


def make_picker_label(version: Version) -> str:
    """Return the label of a version in the version picker.

    It reads ``<date> · <short SHA hash> · <subject>``; the working copy shows only its subject.

    Args:
        version: Version shown as an entry of the picker, or in a diff page's heading.
    """
    if version.is_worktree:
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
    """Jinja templates of the package, rendering ``Page`` objects to HTML."""

    environment: Environment
    """Jinja environment loading the package's templates, with docspecsite's filters."""

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
            path: Unencoded site path of a tag or component index page, as
                :func:`~docspecsite.urls.make_tag_url` and :func:`~docspecsite.urls.make_component_url` give it.
        """
        page: Page = context["page"]
        return make_relative_url(encode_href_path(path), page.url)

    def render(self, page: Page, site_title: str, *, indexes: Container[str] | None = None) -> str:
        """Render a page to HTML.

        Args:
            page: Page to render; its :attr:`Page.url` is the base of every relative link in the output.
            site_title: Title of the home doc, appended to the page title in ``<title>``.
            indexes: The index URLs that tag and component links and the site's Status link may point to; links to
                others are not made. None makes every such link.
        """
        return self.environment.get_template("page.html").render(page=page, site_title=site_title, indexes=indexes)


def load_static_files() -> dict[str, bytes]:
    """Return the site's own assets (stylesheet and script) as bytes, by site path."""
    static = files("docspecsite") / "static"
    return {f"assets/{name}": (static / name).read_bytes() for name in STATIC_FILES}
