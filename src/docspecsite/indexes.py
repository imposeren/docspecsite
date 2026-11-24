"""The site's index entries, their grouping on the tag, component and status pages, and ``llms.txt``.

What every site renderer shows on its index pages is decided here; each renderer only places it.

Docs: architecture/site.md#the-renderer-seam
"""

import re
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Self

from .config import ProjectConfig
from .docs import DocStatus, Layer, Priority, Status, make_string_tuple
from .query import format_text_field
from .text import collapse_to_one_line
from .urls import encode_href_path, is_usable_tag, make_doc_url
from .vocabulary import Vocabulary


@dataclass(frozen=True)
class IndexEntry:
    """Page listed in the index pages and ``llms.txt``: a doc, or a module of the code reference."""

    path: str
    """Doc path relative to ``docs/``, or the dotted path of a module."""

    title: str
    """Title shown in the listings; the path when the doc has none."""

    summary: str
    """One-line summary shown in the listings; empty when the doc has none."""

    status: DocStatus
    """Status of the doc, with the milestone and the priority that group it on the status board; the board lists the
    entry under each of its values from :class:`~docspecsite.docs.Status` and leaves out other values."""

    layer: str
    """Layer from :class:`~docspecsite.docs.Layer`, or another value ``llms.txt`` leaves out; empty when the doc has
    none."""

    tags: tuple[str, ...]
    """Tags whose index pages list the entry."""

    components: tuple[str, ...]
    """Component ids whose index pages list the entry."""

    is_code_module: bool = False
    """Whether the entry is a module of the code reference; else it is a doc."""

    @classmethod
    def from_front_matter(cls, path: str, front_matter: Mapping[str, object]) -> Self:
        """Return the entry of a doc, with its fields read from its front matter.

        Args:
            path: Doc path relative to ``docs/``; the title when the front matter has none.
            front_matter: Parsed front matter of the doc; values that are not text are converted to text, list
                fields that are not lists give no values.
        """
        return cls(
            path=path,
            title=str(front_matter.get("title", path)),
            summary=str(front_matter.get("summary", "")),
            status=DocStatus.from_front_matter(front_matter, path),
            layer=str(front_matter.get("layer", "")),
            tags=make_string_tuple(front_matter.get("tags")),
            components=make_string_tuple(front_matter.get("components")),
        )


@dataclass(frozen=True)
class IndexGroup:
    """A group of the status board: a status, a milestone within it, or a priority within that."""

    name: str
    """The group's value, or a fixed name for the entries without one."""

    entries: tuple[IndexEntry, ...]
    """The entries of a group without subgroups, in any order; empty for a group with subgroups."""

    subgroups: tuple[IndexGroup, ...] = ()
    """The nested groups in their order; empty for the innermost groups."""


class SiteIndex:
    """The entries of a site's index pages and ``llms.txt``, their grouping and their order."""

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
        """Prepare the index of a site.

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

    def sort_entries(self, entries: Iterable[IndexEntry]) -> list[IndexEntry]:
        """Return entries in the order of a listing: by path, with ADRs ordered by prefix.

        Args:
            entries: Docs or code modules to list, in any order.
        """
        return sorted(entries, key=lambda e: self.config.make_sort_key(e.path))

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

    def group_by_tag(self) -> dict[str, list[IndexEntry]]:
        """Return the docs by each tag that gets an index page; a tag that is not usable as a file name gets none."""
        by_tag = self.group_entries(self.entries, lambda e: e.tags)
        return {tag: tag_entries for tag, tag_entries in by_tag.items() if is_usable_tag(tag)}

    def group_by_component(self) -> dict[str, list[IndexEntry]]:
        """Return the docs and code modules by each component they list."""
        return self.group_entries([*self.entries, *self.code_entries], lambda e: e.components)

    def find_milestone_group(self, entry: IndexEntry) -> str:
        """Return the name of the status board's milestone group of an entry, a fixed name without one.

        An entry without a milestone goes in the :attr:`NO_MILESTONE` group.

        Args:
            entry: Doc listed on the status board.
        """
        milestone = entry.status.milestone
        return self.NO_MILESTONE if milestone is None else milestone

    def find_priority_group(self, entry: IndexEntry) -> str:
        """Return the name of the status board's priority group of an entry, a fixed name without one.

        An entry without a priority goes in the :attr:`NO_PRIORITY` group.

        Args:
            entry: Doc listed on the status board.
        """
        priority = entry.status.priority
        return self.NO_PRIORITY if priority is None else priority

    @staticmethod
    def order_groups(used: set[str], known: Collection[str], none_name: str) -> list[str]:
        """Return the status board's group names in their order: the known ones, the other used ones, then none.

        Args:
            used: Group names the listed docs have, the one for docs without a value included.
            known: Group names in their own order, such as the roadmap's milestones.
            none_name: Group name of the docs without a value, shown last.
        """
        extra = sorted(used - set(known) - {none_name})
        return list(dict.fromkeys((*known, *extra, none_name)))

    def group_status_board(self) -> list[IndexGroup]:
        """Return the status board's groups: docs by status, then milestone (roadmap order), then priority.

        A doc is listed under each of its status values; values outside :class:`~docspecsite.docs.Status` are left
        out. Milestones used by docs but not in the roadmap follow the roadmap's by code point, then docs without one.
        Priorities come as :class:`~docspecsite.docs.Priority`, then other values by code point, then docs without
        one. Groups without entries are left out.
        """
        milestone_order = self.order_groups(
            {self.find_milestone_group(e) for e in self.entries}, self.vocabulary.milestones, self.NO_MILESTONE
        )
        priority_order = self.order_groups(
            {self.find_priority_group(e) for e in self.entries}, Priority, self.NO_PRIORITY
        )
        status_groups: list[IndexGroup] = []
        for status in Status:
            status_entries = [e for e in self.entries if status in e.status.values]
            milestone_groups: list[IndexGroup] = []
            for milestone in milestone_order:
                milestone_entries = [e for e in status_entries if self.find_milestone_group(e) == milestone]
                priority_groups = tuple(
                    IndexGroup(priority, tuple(priority_entries))
                    for priority in priority_order
                    if (priority_entries := [e for e in milestone_entries if self.find_priority_group(e) == priority])
                )
                if priority_groups:
                    milestone_groups.append(IndexGroup(milestone, (), priority_groups))
            if milestone_groups:
                status_groups.append(IndexGroup(status, (), tuple(milestone_groups)))
        return status_groups

    def make_llms_txt(self, site_summary: str) -> str:
        """Return the text of the site's ``llms.txt``.

        It is a plain-text list of the docs, grouped by layer; a doc whose ``layer`` is not a known layer is left out.
        Each line stays one valid Markdown link: the URL of the doc's latest page is percent-encoded and ``\\``,
        ``[`` and ``]`` in the title are escaped. A doc without a status has no ``status:`` part.

        Docs: behavior/site.md#navigation-and-indexes

        Args:
            site_summary: Summary of the home doc, written as the quote under the heading; may be empty.
        """
        llms_lines = [f"# {collapse_to_one_line(self.site_title)}", "", f"> {collapse_to_one_line(site_summary)}"]
        for layer in Layer:
            layer_entries = self.sort_entries(e for e in self.entries if e.layer == layer)
            if not layer_entries:
                continue
            llms_lines += ["", f"## {layer}", ""]
            for entry in layer_entries:
                components_text = ", ".join(entry.components) or "none"
                title = self.LINK_TEXT_SPECIALS.sub(r"\\\g<0>", collapse_to_one_line(entry.title))
                status_part = (
                    f"status: {format_text_field(entry.status.make_json_value())}; " if entry.status.values else ""
                )
                llms_lines.append(
                    f"- [{title}]({encode_href_path(make_doc_url(entry.path))}): {collapse_to_one_line(entry.summary)} "
                    f"({status_part}components: {components_text}; source: docs/{entry.path})"
                )
        return "\n".join(llms_lines) + "\n"
