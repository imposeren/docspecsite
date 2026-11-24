"""Tag, component and status index pages, and ``llms.txt``.

Docs: architecture/docs-tooling.md
"""

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from html import escape
from typing import Self

from .config import ProjectConfig
from .docs import DocStatus, make_string_tuple
from .pages import Page, PageLink
from .query import format_text_field, make_status_json_value
from .schema import LAYERS, PRIORITIES, STATUSES
from .text import collapse_to_one_line
from .urls import STATUS_PAGE, encode_href_path, is_usable_tag, make_component_url, make_relative_url, make_tag_url
from .vocabulary import Vocabulary


@dataclass(frozen=True)
class IndexEntry:
    """Page listed in the index pages and ``llms.txt``: a doc, or a module of the code reference."""

    path: str
    """Doc path relative to ``docs/``, or the dotted path of a module."""

    url: str
    """Site-root-relative URL of the page."""

    title: str
    """Title shown in the listings; the path when the doc has none."""

    summary: str
    """One-line summary shown in the listings; empty when the doc has none."""

    status: DocStatus
    """Status of the doc; the status board lists the entry under each of its values from
    :data:`~docspecsite.schema.STATUSES` and leaves out other values."""

    layer: str
    """Layer from :data:`~docspecsite.schema.LAYERS`, or another value ``llms.txt`` leaves out; empty when the doc has
    none."""

    milestone: str | None
    """Milestone that groups the entry on the status board; None when the doc has none."""

    priority: str | None
    """Priority that groups the entry on the status board; None when the doc has none."""

    tags: tuple[str, ...]
    """Tags whose index pages list the entry."""

    components: tuple[str, ...]
    """Component ids whose index pages list the entry."""

    @classmethod
    def from_front_matter(cls, path: str, url: str, front_matter: Mapping[str, object]) -> Self:
        """Return the entry of a doc, with its fields read from its front matter.

        Args:
            path: Doc path relative to ``docs/``; the title when the front matter has none.
            url: Site-root-relative URL of the doc's page.
            front_matter: Parsed front matter of the doc; values that are not text are converted to text, list
                fields that are not lists give no values.
        """
        milestone = front_matter.get("milestone")
        priority = front_matter.get("priority")
        return cls(
            path=path,
            url=url,
            title=str(front_matter.get("title", path)),
            summary=str(front_matter.get("summary", "")),
            status=DocStatus.from_front_matter(front_matter),
            layer=str(front_matter.get("layer", "")),
            milestone=None if milestone is None else str(milestone),
            priority=None if priority is None else str(priority),
            tags=make_string_tuple(front_matter.get("tags")),
            components=make_string_tuple(front_matter.get("components")),
        )


class IndexRenderer:
    """The index pages of a site and its ``llms.txt``, rendered from the entries they list."""

    # Markdown
    LINK_TEXT_SPECIALS = re.compile(r"[\\\[\]]")
    """Characters of a Markdown link's text that need a backslash before them, in ``llms.txt``."""

    # Status board groups
    NO_MILESTONE = "no milestone"
    """Status board group of the docs without a milestone."""

    NO_PRIORITY = "none"
    """Status board group of the docs without a priority."""

    # Arguments of __init__
    entries: list[IndexEntry]
    """See :meth:`__init__`."""

    code_entries: list[IndexEntry]
    """See :meth:`__init__`."""

    config: ProjectConfig
    """See :meth:`__init__`."""

    site_title: str
    """See :meth:`__init__`."""

    vocabulary: Vocabulary
    """See :meth:`__init__`."""

    def __init__(
        self,
        entries: list[IndexEntry],
        code_entries: list[IndexEntry],
        config: ProjectConfig,
        site_title: str,
        vocabulary: Vocabulary,
    ) -> None:
        """Prepare the index pages and ``llms.txt`` of a site.

        Args:
            entries: Latest docs whose front matter loaded, one per doc page; they fill the tag, component and status
                pages and ``llms.txt``.
            code_entries: Code modules, one per module reference page; they appear on component pages only. Empty when
                the code is not loaded.
            config: Settings whose ADR prefixes order the ADRs.
            site_title: Title of the site's home page, shown in each index page's breadcrumb and as the ``llms.txt``
                heading.
            vocabulary: Vocabulary of the docs, whose milestones in roadmap order order the status board's
                milestone groups.
        """
        self.entries = entries
        self.code_entries = code_entries
        self.config = config
        self.site_title = site_title
        self.vocabulary = vocabulary

    @staticmethod
    def render_item(entry: IndexEntry, page_url: str) -> str:
        """Return the list item HTML of an entry: link, a status marker per status value, and summary.

        Args:
            entry: Doc or code module to list; its title, status values and summary are shown.
            page_url: Site path of the index page holding the item; the entry's link is made relative to it.
        """
        title = escape(entry.title)
        summary = escape(entry.summary)
        href = escape(make_relative_url(entry.url, page_url), quote=True)
        escaped_statuses = (escape(status) for status in entry.status.values)
        markers = "".join(f' <span class="status status-{status}">{status}</span>' for status in escaped_statuses)
        return f'<li><a href="{href}">{title}</a>{markers}: {summary}</li>'

    def render_listing(self, listed_entries: list[IndexEntry], page_url: str) -> str:
        """Return the HTML list of entries, sorted by path with ADRs ordered by prefix, with links relative to a page.

        Args:
            listed_entries: Docs or code modules to list, in any order; may be empty.
            page_url: Site path of the index page holding the list; the links are made relative to it.
        """
        items_html = "".join(
            self.render_item(entry, page_url)
            for entry in sorted(listed_entries, key=lambda e: self.config.make_sort_key(e.path))
        )
        return f"<ul>{items_html}</ul>"

    @staticmethod
    def group_entries(
        entries: list[IndexEntry], read_values: Callable[[IndexEntry], tuple[str, ...]]
    ) -> dict[str, list[IndexEntry]]:
        """Group entries by each value of one of their list fields.

        Args:
            entries: Docs or code modules to group; an entry lands in one group per value it lists.
            read_values: Gives the values of an entry that name its groups, such as its tags or components.
        """
        groups: dict[str, list[IndexEntry]] = {}
        for entry in entries:
            for value in read_values(entry):
                groups.setdefault(value, []).append(entry)
        return groups

    def find_milestone_group(self, entry: IndexEntry) -> str:
        """Return the name of the status board's milestone group of an entry, a fixed name without one.

        An entry without a milestone goes in the :attr:`NO_MILESTONE` group.

        Args:
            entry: Doc listed on the status board.
        """
        return self.NO_MILESTONE if entry.milestone is None else entry.milestone

    def find_priority_group(self, entry: IndexEntry) -> str:
        """Return the name of the status board's priority group of an entry, a fixed name without one.

        An entry without a priority goes in the :attr:`NO_PRIORITY` group.

        Args:
            entry: Doc listed on the status board.
        """
        return self.NO_PRIORITY if entry.priority is None else entry.priority

    @staticmethod
    def order_groups(used: set[str], known: Sequence[str], none_name: str) -> list[str]:
        """Return the status board's group names in their order: the known ones, the other used ones, then none.

        Args:
            used: Group names the listed docs have, the one for docs without a value included.
            known: Group names in their own order, such as the roadmap's milestones.
            none_name: Group name of the docs without a value, shown last.
        """
        extra = sorted(used - set(known) - {none_name})
        return list(dict.fromkeys((*known, *extra, none_name)))

    def render_status_body(self) -> str:
        """Return the body HTML of the status board: docs by status, then milestone (roadmap order), then priority.

        A doc is listed under each of its status values; values outside :data:`~docspecsite.schema.STATUSES` are left
        out. Milestones used by docs but not in the roadmap follow the roadmap's by code point, then docs without one.
        Priorities come as :data:`~docspecsite.schema.PRIORITIES`, then other values by code point, then docs without
        one.
        The entry links are relative to :data:`~docspecsite.urls.STATUS_PAGE`.
        """
        parts: list[str] = []
        milestone_order = self.order_groups(
            {self.find_milestone_group(e) for e in self.entries}, self.vocabulary.milestones, self.NO_MILESTONE
        )
        priority_order = self.order_groups(
            {self.find_priority_group(e) for e in self.entries}, PRIORITIES, self.NO_PRIORITY
        )
        for status in STATUSES:
            status_entries = [e for e in self.entries if status in e.status.values]
            if not status_entries:
                continue
            parts.append(f"<h2>{escape(status)}</h2>")
            for milestone in milestone_order:
                milestone_entries = [e for e in status_entries if self.find_milestone_group(e) == milestone]
                if not milestone_entries:
                    continue
                parts.append(f"<h3>{escape(milestone)}</h3>")
                for priority in priority_order:
                    priority_entries = [e for e in milestone_entries if self.find_priority_group(e) == priority]
                    if priority_entries:
                        parts.append(f"<h4>{escape(priority)}</h4>")
                        parts.append(self.render_listing(priority_entries, STATUS_PAGE))
        return "".join(parts)

    def make_page_makers(self) -> dict[str, Callable[[], Page]]:
        """Return how to build each index page, by site path.

        The pages are one per tag and component (docs and code) and the status board. Each has a breadcrumb to the
        home page. Tags that are not :func:`~docspecsite.urls.is_usable_tag` get no page.
        """
        home_breadcrumb = (PageLink(self.site_title, "index.html"),)

        def make_page_maker(url: str, title: str, render_body: Callable[[], str]) -> Callable[[], Page]:
            return lambda: Page(url, title, (), (), (), render_body(), breadcrumb=home_breadcrumb)

        makers: dict[str, Callable[[], Page]] = {}
        for tag, tag_entries in sorted(self.group_entries(self.entries, lambda e: e.tags).items()):
            if not is_usable_tag(tag):
                continue
            url = make_tag_url(tag)
            makers[url] = make_page_maker(url, f"Tag: {tag}", partial(self.render_listing, tag_entries, url))
        by_component = self.group_entries([*self.entries, *self.code_entries], lambda e: e.components)
        for component, component_entries in sorted(by_component.items()):
            url = make_component_url(component)
            render_body = partial(self.render_listing, component_entries, url)
            makers[url] = make_page_maker(url, f"Component: {component}", render_body)
        makers[STATUS_PAGE] = make_page_maker(STATUS_PAGE, "Status", self.render_status_body)
        return makers

    def render_llms_txt(self, site_summary: str) -> str:
        """Return the text of the site's ``llms.txt``.

        It is a plain-text list of the docs, grouped by layer; a doc whose ``layer`` is not a known layer is left out.
        Each line stays one valid Markdown link: the URL is percent-encoded and ``\\``, ``[`` and ``]`` in the title
        are escaped.

        Args:
            site_summary: Summary of the home doc, written as the quote under the heading; may be empty.
        """
        llms_lines = [f"# {collapse_to_one_line(self.site_title)}", "", f"> {collapse_to_one_line(site_summary)}"]
        for layer in LAYERS:
            layer_entries = sorted(
                (e for e in self.entries if e.layer == layer),
                key=lambda e: self.config.make_sort_key(e.path),
            )
            if not layer_entries:
                continue
            llms_lines += ["", f"## {layer}", ""]
            for entry in layer_entries:
                components_text = ", ".join(entry.components) or "none"
                status_text = format_text_field(make_status_json_value(entry.status))
                title = self.LINK_TEXT_SPECIALS.sub(r"\\\g<0>", collapse_to_one_line(entry.title))
                llms_lines.append(
                    f"- [{title}]({encode_href_path(entry.url)}): {collapse_to_one_line(entry.summary)} "
                    f"(status: {status_text}; components: {components_text}; source: docs/{entry.path})"
                )
        return "\n".join(llms_lines) + "\n"
