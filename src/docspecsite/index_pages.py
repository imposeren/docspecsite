"""The `internal` renderer's tag, component and status index pages, made from the shared index entries.

Docs: architecture/docs-tooling.md#site-renderers
"""

from collections.abc import Callable
from functools import partial
from html import escape

from .codeindex import CodeTarget
from .indexes import IndexEntry, IndexGroup, SiteIndex
from .pages import Page, PageLink
from .urls import STATUS_PAGE, make_code_url, make_component_url, make_doc_url, make_relative_url, make_tag_url


class IndexRenderer:
    """The index pages of a site as HTML, with the entries and groups of its index."""

    # Status board
    FIRST_GROUP_HEADING_LEVEL = 2
    """Heading level of the status board's top groups, the statuses; each nested group is one level deeper."""

    # Arguments of __init__
    site_index: SiteIndex
    """See :meth:`__init__`."""

    def __init__(self, site_index: SiteIndex) -> None:
        """Prepare the index pages of a site.

        Args:
            site_index: The entries the pages list, their grouping and the site's title.
        """
        self.site_index = site_index

    @staticmethod
    def make_entry_url(entry: IndexEntry) -> str:
        """Return the site-root-relative URL of the page of an entry: its doc's latest page, or its module's page.

        Args:
            entry: Doc or code module listed on an index page.
        """
        if entry.is_code_module:
            return make_code_url(CodeTarget(entry.path, None))
        return make_doc_url(entry.path)

    @classmethod
    def render_item(cls, entry: IndexEntry, page_url: str) -> str:
        """Return the list item HTML of an entry: link, a status marker per status value, and summary.

        Args:
            entry: Doc or code module to list; its title, status values and summary are shown.
            page_url: Site path of the index page holding the item; the entry's link is made relative to it.
        """
        title = escape(entry.title)
        summary = escape(entry.summary)
        href = escape(make_relative_url(cls.make_entry_url(entry), page_url), quote=True)
        escaped_statuses = (escape(status) for status in entry.status.values)
        markers = "".join(f' <span class="status status-{status}">{status}</span>' for status in escaped_statuses)
        return f'<li><a href="{href}">{title}</a>{markers}: {summary}</li>'

    def render_listing(self, listed_entries: list[IndexEntry], page_url: str) -> str:
        """Return the HTML list of entries in the index's order, with links relative to a page.

        Args:
            listed_entries: Docs or code modules to list, in any order; may be empty.
            page_url: Site path of the index page holding the list; the links are made relative to it.
        """
        items_html = "".join(
            self.render_item(entry, page_url) for entry in self.site_index.sort_entries(listed_entries)
        )
        return f"<ul>{items_html}</ul>"

    def render_groups(self, groups: list[IndexGroup], heading_level: int) -> str:
        """Return the HTML of the status board's groups: each one's heading, then its subgroups or its listing.

        Args:
            groups: Groups to show in their order.
            heading_level: Level of the groups' headings; their subgroups get the next one.
        """
        parts: list[str] = []
        for group in groups:
            parts.append(f"<h{heading_level}>{escape(group.name)}</h{heading_level}>")
            if group.subgroups:
                parts.append(self.render_groups(list(group.subgroups), heading_level + 1))
            else:
                parts.append(self.render_listing(list(group.entries), STATUS_PAGE))
        return "".join(parts)

    def render_status_body(self) -> str:
        """Return the body HTML of the status board: docs by status, then milestone, then priority.

        The entry links are relative to :data:`~docspecsite.urls.STATUS_PAGE`.
        """
        return self.render_groups(self.site_index.group_status_board(), self.FIRST_GROUP_HEADING_LEVEL)

    def make_page_makers(self) -> dict[str, Callable[[], Page]]:
        """Return how to build each index page, by site path.

        The pages are one per tag and component (docs and code) and the status board. Each has a breadcrumb to the
        home page.
        """
        home_breadcrumb = (PageLink(self.site_index.site_title, "index.html"),)

        def make_page_maker(url: str, title: str, render_body: Callable[[], str]) -> Callable[[], Page]:
            return lambda: Page(url, title, (), (), (), render_body(), breadcrumb=home_breadcrumb)

        makers: dict[str, Callable[[], Page]] = {}
        for tag, tag_entries in sorted(self.site_index.group_by_tag().items()):
            url = make_tag_url(tag)
            makers[url] = make_page_maker(url, f"Tag: {tag}", partial(self.render_listing, tag_entries, url))
        for component, component_entries in sorted(self.site_index.group_by_component().items()):
            url = make_component_url(component)
            render_body = partial(self.render_listing, component_entries, url)
            makers[url] = make_page_maker(url, f"Component: {component}", render_body)
        makers[STATUS_PAGE] = make_page_maker(STATUS_PAGE, "Status", self.render_status_body)
        return makers
