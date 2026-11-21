"""Diff pages, tag, component and status indexes, and ``llms.txt``.

Docs: architecture/docs-tooling.md
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from html import escape

from .config import ProjectConfig
from .docs import make_string_tuple
from .pages import Page, PageLink
from .schema import LAYERS, PRIORITIES, STATUSES
from .text import collapse_to_one_line
from .urls import is_usable_tag, make_component_url, make_relative_url, make_tag_url
from .vocabulary import Vocabulary


@dataclass(frozen=True)
class IndexEntry:
    """Page listed in the index pages and ``llms.txt``: a doc, or a module of the code reference."""

    path: str
    """Doc path relative to ``docs/``, or the dotted path of a module."""

    url: str
    """Site-root-relative URL of the page."""

    front_matter: Mapping[str, object]
    """Front matter of the doc; for a module, the fields the index pages read, made from the settings."""


class IndexRenderer:
    """The index pages of a site and its ``llms.txt``, rendered from the entries they list."""

    # Paths
    STATUS_PAGE = "status.html"
    """Site path of the status page."""

    # Status board groups
    NO_MILESTONE = "no milestone"
    """Status board group of the docs without a milestone."""

    NO_PRIORITY = "none"
    """Status board group of the docs without a priority."""

    # Arguments of __init__
    entries: list[IndexEntry]
    """See :meth:`.__init__`."""

    code_entries: list[IndexEntry]
    """See :meth:`.__init__`."""

    config: ProjectConfig
    """See :meth:`.__init__`."""

    site_title: str
    """See :meth:`.__init__`."""

    vocabulary: Vocabulary
    """See :meth:`.__init__`."""

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
        """Return the list item HTML of an entry: link, status marker and summary.

        Args:
            entry: Doc or code module to list; its ``title``, ``status`` and ``summary`` are shown, its path when it
                has no title.
            page_url: Site path of the index page holding the item; the entry's link is made relative to it.
        """
        title = escape(str(entry.front_matter.get("title", entry.path)))
        summary = escape(str(entry.front_matter.get("summary", "")))
        status = escape(str(entry.front_matter.get("status", "")))
        href = escape(make_relative_url(entry.url, page_url), quote=True)
        marker = f' <span class="status status-{status}">{status}</span>' if status else ""
        return f'<li><a href="{href}">{title}</a>{marker}: {summary}</li>'

    def render_listing(self, listed: list[IndexEntry], page_url: str) -> str:
        """Return the HTML list of entries, sorted by path with ADRs ordered by prefix, with links relative to a page.

        Args:
            listed: Docs or code modules to list, in any order; may be empty.
            page_url: Site path of the index page holding the list; the links are made relative to it.
        """
        items = "".join(
            self.render_item(entry, page_url)
            for entry in sorted(listed, key=lambda e: self.config.make_sort_key(e.path))
        )
        return f"<ul>{items}</ul>"

    @staticmethod
    def group_entries(entries: list[IndexEntry], key: str) -> dict[str, list[IndexEntry]]:
        """Group entries by each value of a front-matter list.

        Args:
            entries: Docs or code modules to group; an entry lands in one group per value it lists.
            key: Front-matter list field whose values name the groups, such as ``tags`` or ``components``.
        """
        groups: dict[str, list[IndexEntry]] = {}
        for entry in entries:
            for value in make_string_tuple(entry.front_matter.get(key)):
                groups.setdefault(value, []).append(entry)
        return groups

    @staticmethod
    def get_value(entry: IndexEntry, key: str, missing: str) -> str:
        """Return a front-matter field of an entry as text, or a placeholder when it is absent or null.

        Args:
            entry: Entry whose front matter is read.
            key: Field that sorts the entry into a status-board group, ``milestone`` or ``priority``.
            missing: Name of the group for entries without the field, e.g. :attr:`.NO_MILESTONE`.
        """
        value = entry.front_matter.get(key)
        return missing if value is None else str(value)

    def render_status_body(self) -> str:
        """Return the body HTML of the status board: docs by status, then milestone (roadmap order), then priority.

        Docs whose status is outside :data:`~docspecsite.schema.STATUSES` are left out. Milestones used by docs but not
        in the roadmap follow the roadmap's alphabetically, then docs without one. The entry links are relative to
        :attr:`.STATUS_PAGE`.
        """
        parts: list[str] = []
        used_milestones = {self.get_value(e, "milestone", self.NO_MILESTONE) for e in self.entries}
        extra_milestones = sorted(used_milestones - set(self.vocabulary.milestones) - {self.NO_MILESTONE})
        milestone_order = dict.fromkeys((*self.vocabulary.milestones, *extra_milestones, self.NO_MILESTONE))
        for status in STATUSES:
            in_status = [e for e in self.entries if e.front_matter.get("status") == status]
            if not in_status:
                continue
            parts.append(f"<h2>{escape(status)}</h2>")
            for milestone in milestone_order:
                in_milestone = [e for e in in_status if self.get_value(e, "milestone", self.NO_MILESTONE) == milestone]
                if not in_milestone:
                    continue
                parts.append(f"<h3>{escape(milestone)}</h3>")
                for priority in dict.fromkeys((*PRIORITIES, self.NO_PRIORITY)):
                    in_priority = [
                        e for e in in_milestone if self.get_value(e, "priority", self.NO_PRIORITY) == priority
                    ]
                    if in_priority:
                        parts.append(f"<h4>{escape(priority)}</h4>")
                        parts.append(self.render_listing(in_priority, self.STATUS_PAGE))
        return "".join(parts)

    def make_page_makers(self) -> dict[str, Callable[[], Page]]:
        """Return how to build each index page, by site path.

        The pages are one per tag and component (docs and code) and the status board. Each has a breadcrumb to the
        home page. Tags that are not :func:`~docspecsite.urls.is_usable_tag` get no page.
        """
        home = (PageLink(self.site_title, "index.html"),)

        def make_page(url: str, title: str, body: Callable[[], str]) -> Callable[[], Page]:
            return lambda: Page(url, title, None, (), (), body(), breadcrumb=home)

        makers: dict[str, Callable[[], Page]] = {}
        for tag, tagged in sorted(self.group_entries(self.entries, "tags").items()):
            if not is_usable_tag(tag):
                continue
            url = make_tag_url(tag)
            makers[url] = make_page(url, f"Tag: {tag}", partial(self.render_listing, tagged, url))
        by_component = self.group_entries([*self.entries, *self.code_entries], "components")
        for component, members in sorted(by_component.items()):
            url = make_component_url(component)
            makers[url] = make_page(url, f"Component: {component}", partial(self.render_listing, members, url))
        makers[self.STATUS_PAGE] = make_page(self.STATUS_PAGE, "Status", self.render_status_body)
        return makers

    def render_llms_txt(self, site_summary: str) -> str:
        """Return the text of the site's ``llms.txt``.

        It is a plain-text list of the docs, grouped by layer; a doc whose ``layer`` is not a known layer is left out.

        Args:
            site_summary: Summary of the home doc, written as the quote under the heading; may be empty.
        """
        llms_lines = [f"# {collapse_to_one_line(self.site_title)}", "", f"> {collapse_to_one_line(site_summary)}"]
        for layer in LAYERS:
            in_layer = sorted(
                (e for e in self.entries if e.front_matter.get("layer") == layer),
                key=lambda e: self.config.make_sort_key(e.path),
            )
            if not in_layer:
                continue
            llms_lines += ["", f"## {layer}", ""]
            for e in in_layer:
                components = ", ".join(make_string_tuple(e.front_matter.get("components"))) or "none"
                llms_lines.append(
                    f"- [{collapse_to_one_line(str(e.front_matter.get('title', e.path)))}]({e.url}): "
                    f"{collapse_to_one_line(str(e.front_matter.get('summary', '')))} "
                    f"(status: {e.front_matter.get('status', '')}; components: {components}; source: docs/{e.path})"
                )
        return "\n".join(llms_lines) + "\n"
