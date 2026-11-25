"""The single Markdown parser of docspecsite, with what is read from its tokens."""

import re
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import NamedTuple, override
from urllib.parse import quote, unquote

from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml
from markdown_it.renderer import RendererHTML
from markdown_it.rules_inline import StateInline, escape, newline
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.front_matter import front_matter_plugin

from .roles import RoleRule


class BreakLineRule:
    """Parser rules that mark each line break token with the source line it ends.

    Markdown keeps no line breaks inside some inline elements, such as a code span over two lines, so the line of a
    token cannot be found by counting the break tokens before it.

    Docs: architecture/docs-tooling.md#statuses-and-status-notes
    """

    # Constants
    ENV_KEY = "break_line_count"
    """Key of the parse environment holding the last count of line breaks: the inline state it was made in, the
    position in its source counted up to, and the count."""

    META_KEY = "line_offset"
    """Key of a break token's ``meta`` holding the line it ends: the number of line breaks before it in the source of
    its inline token."""

    @staticmethod
    def install(md: MarkdownIt) -> None:
        """Replace the inline rules of a parser that make line breaks with ones that also mark them.

        Args:
            md: Parser to change; its ``newline`` and ``escape`` rules (the latter makes ``\\`` breaks) are wrapped.
        """
        md.inline.ruler.at("newline", BreakLineRule.wrap(newline))
        md.inline.ruler.at("escape", BreakLineRule.wrap(escape))

    @staticmethod
    def wrap(rule: Callable[[StateInline, bool], bool]) -> Callable[[StateInline, bool], bool]:
        """Return an inline rule that runs a rule and marks the break tokens it pushes with the line they end.

        The line is kept under :attr:`META_KEY`.

        Args:
            rule: Inline rule of markdown-it that may push a ``softbreak`` or ``hardbreak`` token at the line break
                where it starts.
        """

        def mark_breaks(state: StateInline, silent: bool) -> bool:
            start, token_count = state.pos, len(state.tokens)
            if not rule(state, silent):
                return False
            for token in state.tokens[token_count:]:
                if token.type in MarkdownText.BREAK_TOKEN_TYPES:
                    token.meta[BreakLineRule.META_KEY] = BreakLineRule.count_line_breaks(state, start)
            return True

        return mark_breaks

    @staticmethod
    def count_line_breaks(state: StateInline, position: int) -> int:
        """Return the number of line breaks before a position in the source of an inline state.

        The count goes on from the position the previous call for the same state asked about, when it lies before,
        so marking every break of a paragraph reads its source once.

        Args:
            state: Inline state whose ``src`` is counted; its parse environment keeps the last position and count.
            position: Index in the source to count up to.
        """
        last_state, last_position, last_count = state.env.get(BreakLineRule.ENV_KEY, (None, 0, 0))
        if last_state is not state or last_position > position:
            last_position, last_count = 0, 0
        count = last_count + state.src.count("\n", last_position, position)
        state.env[BreakLineRule.ENV_KEY] = (state, position, count)
        return count


def _create_parser() -> MarkdownIt:
    """Return a new Markdown parser: CommonMark with tables, front matter, heading anchors and marked line breaks."""
    return (
        MarkdownIt("commonmark")
        .enable("table")
        .use(front_matter_plugin)
        .use(anchors_plugin, max_level=6)
        .use(BreakLineRule.install)
    )


_md = _create_parser()
_md_with_roles = _create_parser().use(RoleRule.install)


def _select_parser(*, use_roles: bool) -> MarkdownIt:
    """Return the parser for a text, which reads Sphinx's Python roles only in docstrings.

    Args:
        use_roles: Read Python roles such as `` :meth:`x` `` as links; for docstrings, not for docs.
    """
    return _md_with_roles if use_roles else _md


def split_source_lines(text: str) -> list[str]:
    """Return the lines of a text as Markdown counts them, split at ``\\n``, ``\\r\\n`` and ``\\r`` only.

    Other separators, such as ``\\f`` and U+2028, stay inside their line, so line ``n`` of a markdown-it token's
    ``map`` is item ``n`` (``str.splitlines`` would split more often).

    Args:
        text: Markdown text, such as a whole doc file.
    """
    return re.split(r"\r\n?|\n", text)


class FrontMatterSplit(NamedTuple):
    """A doc file split into its front matter and its body."""

    source: str | None
    """YAML between the leading ``---`` lines; None when the file has no front matter."""

    body_line: int
    """Line of the file where the body starts, from 1."""


@dataclass(frozen=True)
class Link:
    """Link or image found in a text."""

    target: str
    """Link ``href`` or image ``src``, percent-decoded."""

    line_number: int
    """Line of the link in the text, from 1."""

    role_source: str | None = None
    """The role's source text when the link is a role, such as ``:meth:`go```; None for other links."""


@dataclass(frozen=True)
class Entry:
    """List item that contains links."""

    targets: tuple[str, ...]
    """Targets of the item's links, in order, percent-decoded."""

    text: str
    """Text of the item without its links' text, e.g. a child's description."""

    line_number: int
    """Line where the item starts in the text, from 1."""


@dataclass(frozen=True)
class Heading:
    """Heading of any level at the top level of a text, not inside a block quote or a list.

    Docs: architecture/docs-tooling.md#statuses-and-status-notes
    """

    first_line: str
    """First source line of the heading, stripped, ``#`` marks included, such as ``# Import``; for a heading
    underlined with ``===`` or ``---``, its first text line."""

    content: str
    """Markdown of the heading without its ``#`` marks or underline, its lines joined by spaces, such as
    ``Import``."""

    line_number: int
    """Line where the heading starts in the text, from 1."""


@dataclass(frozen=True)
class SectionNote:
    """Note line with a bold label in the block quote right after a heading, such as ``> **Built.**``.

    Docs: architecture/docs-tooling.md#statuses-and-status-notes
    """

    label: str
    """The bold text that opens the note line, such as ``Built.``."""

    heading: Heading
    """The heading the block quote follows."""

    is_title: bool
    """Whether the heading is the doc's title, which opens no section: its first level-1 heading at the top level, in
    either style (``# Import``, or ``Import`` underlined with ``===``), as :meth:`MarkdownText.get_title` finds it."""

    line_number: int
    """Line of the note in the text, from 1."""


class MarkdownText:
    """Markdown text parsed once, with what is read from its tokens."""

    # Constants
    BREAK_TOKEN_TYPES = ("softbreak", "hardbreak")
    """Types of the inline child tokens that break a line."""

    # Arguments of __init__
    text: str
    """See :meth:`__init__`."""

    use_roles: bool
    """See :meth:`__init__`."""

    def __init__(self, text: str, *, use_roles: bool = False) -> None:
        """Prepare a Markdown text for reading; it is parsed on first use.

        Args:
            text: Markdown of a doc body or whole file (front matter becomes a ``front_matter`` token and is skipped),
                or of a docstring; the lines of the results are 1-based within this text.
            use_roles: Read Sphinx's Python roles as links whose target starts with ``role:``, as in a docstring.
        """
        self.text = text
        self.use_roles = use_roles

    @cached_property
    def tokens(self) -> list[Token]:
        """The markdown-it tokens of the text, parsed on first use."""
        return _select_parser(use_roles=self.use_roles).parse(self.text)

    @cached_property
    def source_lines(self) -> list[str]:
        """The lines of the text as written, split at the line breaks Markdown knows.

        The breaks are ``\\n``, ``\\r\\n`` and ``\\r``, so that line ``n`` of a token's ``map`` is item ``n``.
        """
        return split_source_lines(self.text)

    def split_front_matter(self) -> FrontMatterSplit:
        """Split the text, a whole doc file, into its YAML front matter and the line where the body starts.

        The front matter is the YAML between the leading ``---`` lines at the very start, or None when there is none.
        The line is 1-based.
        """
        tokens = self.tokens
        if tokens and tokens[0].type == "front_matter" and tokens[0].map:
            return FrontMatterSplit(tokens[0].content + "\n", tokens[0].map[1] + 1)
        return FrontMatterSplit(None, 1)

    @staticmethod
    def get_inline_line_number(inline: Token, line_break: Token | None = None) -> int:
        """Return the 1-based line number in the text where an inline token, or the part after a break, starts.

        The token's first line is its ``map[0]`` plus one. The part after a break starts the number of lines further
        on that the break's ``meta`` holds under :attr:`BreakLineRule.META_KEY` (the line breaks before it in the
        token's source), plus one.

        Docs: architecture/docs-tooling.md#statuses-and-status-notes

        Args:
            inline: Inline token of one block; its ``map`` gives its first line.
            line_break: One of the token's ``softbreak`` or ``hardbreak`` children, marked by :class:`BreakLineRule`;
                None gives the token's first line.
        """
        first_line_number = (inline.map[0] if inline.map else 0) + 1
        if line_break is None:
            return first_line_number
        return first_line_number + line_break.meta[BreakLineRule.META_KEY] + 1

    @staticmethod
    def iter_inline_links(inline: Token) -> Iterator[Link]:
        """Return the links and images of an inline token, with their lines.

        Args:
            inline: Inline token of one block; its ``map`` and its break tokens give the lines, and line breaks inside a
                role's written text count on from them.
        """
        line_number = MarkdownText.get_inline_line_number(inline)
        for child in inline.children or []:
            if child.type in MarkdownText.BREAK_TOKEN_TYPES:
                line_number = MarkdownText.get_inline_line_number(inline, child)
            elif child.type == "link_open":
                role_source: str | None = child.meta.get("role_source")
                yield Link(unquote(str(child.attrGet("href") or "")), line_number, role_source)
                line_number += role_source.count("\n") if role_source is not None else 0
            elif child.type == "image":
                yield Link(unquote(str(child.attrGet("src") or "")), line_number)

    @staticmethod
    def join_inline_text(inline: Token, *, skip_links: bool) -> str:
        """Return the plain text of an inline token, from text and code.

        Args:
            inline: Inline token of a heading or list item whose text is collected.
            skip_links: Leave out the text inside links, to get a list item's description apart from its link titles.
        """
        parts: list[str] = []
        link_depth = 0
        for child in inline.children or []:
            if child.type == "link_open":
                link_depth += 1
            elif child.type == "link_close":
                link_depth -= 1
            elif link_depth > 0 and skip_links:
                continue
            elif child.type in ("text", "code_inline"):
                parts.append(child.content)
            elif child.type in MarkdownText.BREAK_TOKEN_TYPES:
                parts.append(" ")
        return "".join(parts)

    def extract_links(self) -> list[Link]:
        """Return the link and image targets in the text, with their lines.

        Targets are in document order and percent-decoded.
        """
        return [link for token in self.tokens if token.type == "inline" for link in self.iter_inline_links(token)]

    def collect_heading_anchors(self) -> set[str]:
        """Return the GitHub-style anchors of all headings in the text.

        Duplicate headings get ``-1``, ``-2`` suffixes; the text is typically the doc a link's ``#anchor`` points
        into.
        """
        return {
            str(token.attrGet("id")) for token in self.tokens if token.type == "heading_open" and token.attrGet("id")
        }

    def mark_in_section(self, section: str | None) -> list[bool]:
        """Return one flag per token telling whether it is under a heading.

        All flags are true when ``section`` is None. A section runs from its heading to the next heading of the same
        or a higher level. The result has one flag per token of :attr:`tokens`.

        Args:
            section: Exact text of the heading (stripped, links and code as plain text) that opens the section; None
                flags every token.
        """
        tokens = self.tokens
        flags: list[bool] = []
        inside = section is None
        level = 0
        for token_index, token in enumerate(tokens):
            if token.type == "heading_open" and section is not None:
                this_level = int(token.tag[1])
                if self.join_inline_text(tokens[token_index + 1], skip_links=False).strip() == section:
                    inside, level = True, this_level
                elif inside and this_level <= level:
                    inside = False
            flags.append(inside)
        return flags

    def extract_table_first_column_codes(self, section: str | None = None) -> list[str]:
        """Return the inline-code value of the first cell of each table body row in the text.

        The text is typically a vocabulary doc whose tables list ids in their first column.

        Args:
            section: Exact text of a heading; only tables under it count, up to the next heading of the same or a higher
                level. None counts every table.
        """
        tokens = self.tokens
        in_section_flags = self.mark_in_section(section)
        codes: list[str] = []
        in_body = False
        is_first_cell = False
        for token_index, token in enumerate(tokens):
            if token.type == "tbody_open":
                in_body = True
            elif token.type == "tbody_close":
                in_body = False
            elif token.type == "tr_open":
                is_first_cell = True
            elif token.type == "inline" and in_body and is_first_cell:
                is_first_cell = False
                children = token.children or []
                if in_section_flags[token_index] and children and children[0].type == "code_inline":
                    codes.append(children[0].content)
        return codes

    def list_entries(self, section: str | None = None) -> list[Entry]:
        """Return the list items of the text that contain a link.

        Each is an :class:`Entry` with its link targets and other text. The text is typically an ``index.md`` body.

        Args:
            section: Exact text of a heading, such as ``Children``; only list items under it count (subsections
                included), up to the next heading of the same or a higher level. None counts every list item.
        """
        tokens = self.tokens
        in_section_flags = self.mark_in_section(section)
        entries: list[Entry] = []
        for token_index, token in enumerate(tokens):
            if token.type != "list_item_open" or not token.map or not in_section_flags[token_index]:
                continue
            inlines: list[Token] = []
            depth = 0
            scan_index = token_index + 1
            while scan_index < len(tokens) and not (tokens[scan_index].type == "list_item_close" and depth == 0):
                scan_token = tokens[scan_index]
                if scan_token.type in ("bullet_list_open", "ordered_list_open"):
                    depth += 1
                elif scan_token.type in ("bullet_list_close", "ordered_list_close"):
                    depth -= 1
                elif scan_token.type == "inline" and depth == 0:
                    inlines.append(scan_token)
                scan_index += 1
            targets = tuple(link.target for inline in inlines for link in self.iter_inline_links(inline))
            if targets:
                text_parts = (self.join_inline_text(inline, skip_links=True) for inline in inlines)
                text = " ".join(part.strip() for part in text_parts if part.strip())
                entries.append(Entry(targets, text, token.map[0] + 1))
        return entries

    def make_heading(self, token_index: int) -> Heading:
        """Return the heading that a ``heading_open`` token opens.

        Args:
            token_index: Index in :attr:`tokens` of a ``heading_open`` token with a ``map``; its ``inline`` token
                follows it.
        """
        heading_open = self.tokens[token_index]
        first_line_index = heading_open.map[0] if heading_open.map else 0
        content = " ".join(line.strip() for line in self.tokens[token_index + 1].content.splitlines())
        return Heading(self.source_lines[first_line_index].strip(), content, first_line_index + 1)

    def get_level_one_headings(self) -> list[Heading]:
        """Return the level-1 headings at the top level of the text, in document order.

        Both styles count, ``# Import`` and ``Import`` underlined with ``===``; headings inside a block quote or a list
        do not. The first is the doc's title (:meth:`get_title`).

        Docs: behavior/docs-format.md#requirements
        """
        return [
            self.make_heading(token_index)
            for token_index, token in enumerate(self.tokens)
            if token.type == "heading_open" and token.tag == "h1" and token.level == 0 and token.map
        ]

    def get_title(self) -> Heading | None:
        """Return the doc's title heading, its first level-1 heading at the top level, or None when it has none.

        The title is this heading wherever it is in the text; whether only blank lines come before it is for the
        title check to say.

        Docs: behavior/docs-format.md#requirements
        """
        headings = self.get_level_one_headings()
        return headings[0] if headings else None

    def get_section_notes(self) -> list[SectionNote]:
        """Return the note lines with a bold label in the block quotes right after each heading, in document order.

        Only headings at nesting level 0 count: headings inside block quotes or lists open no section. A heading's
        notes are read from the block quote paragraphs that follow its ``heading_close`` token, up to the first token
        outside a block quote; paragraphs in a list or a block quote inside them do not count, and code blocks hold no
        notes. Consecutive ``>`` lines form one paragraph, which is split into its lines at its break tokens; each
        line that starts with ``>`` and then ``**`` bold text is a note, whatever the label.

        Docs: architecture/docs-tooling.md#statuses-and-status-notes
        """
        title = self.get_title()
        notes: list[SectionNote] = []
        for token_index, token in enumerate(self.tokens):
            if token.type != "heading_open" or token.level != 0 or not token.map:
                continue
            heading = self.make_heading(token_index)
            is_title = heading == title
            # The heading's tokens are heading_open, inline and heading_close.
            for inline in self.iter_quote_paragraphs(token_index + 3):
                for line_number, line_children in self.split_inline_lines(inline):
                    if self.is_note_line(self.source_lines[line_number - 1], line_children):
                        notes.append(SectionNote(line_children[1].content, heading, is_title, line_number))
        return notes

    @staticmethod
    def is_note_line(source_line: str, line_children: Sequence[Token]) -> bool:
        """Return whether a line of a block quote paragraph is a note: it starts with ``>``, then ``**`` bold text.

        A lazy continuation line, without the ``>``, and ``__`` bold text are no notes.

        Args:
            source_line: The line as written in the text.
            line_children: Child tokens of the line, without breaks and empty ``text`` tokens.
        """
        return (
            source_line.lstrip().startswith(">")
            and [child.type for child in line_children[:3]] == ["strong_open", "text", "strong_close"]
            and line_children[0].markup == "**"
        )

    def iter_quote_paragraphs(self, start_token_index: int) -> Iterator[Token]:
        """Return the inline tokens of the paragraphs in the block quotes that follow one another from a position.

        Only paragraphs directly in those block quotes count, not those in a list or a block quote inside them.

        Args:
            start_token_index: Index in :attr:`tokens` where the block quotes may start, such as the token after a
                heading; no block quote there gives nothing.
        """
        tokens = self.tokens
        quote_depth = 0
        paragraph_level = 0  # Nesting level of a paragraph directly in the outer block quote.
        for token_index in range(start_token_index, len(tokens)):
            token = tokens[token_index]
            if token.type == "blockquote_open":
                if quote_depth == 0:
                    paragraph_level = token.level + 1
                quote_depth += 1
            elif token.type == "blockquote_close":
                quote_depth -= 1
            elif quote_depth == 0:
                return
            elif token.type == "paragraph_open" and token.level == paragraph_level:
                yield tokens[token_index + 1]

    @staticmethod
    def split_inline_lines(inline: Token) -> Iterator[tuple[int, list[Token]]]:
        """Return the ``(line number, child tokens)`` of each source line of an inline token.

        The breaks are left out, and so are the empty ``text`` tokens that markdown-it puts around emphasis.

        Args:
            inline: Inline token of one paragraph; its ``map`` and its break tokens give the lines.
        """
        line_number = MarkdownText.get_inline_line_number(inline)
        line_children: list[Token] = []
        for child in inline.children or []:
            if child.type in MarkdownText.BREAK_TOKEN_TYPES:
                yield line_number, line_children
                line_number = MarkdownText.get_inline_line_number(inline, child)
                line_children = []
            elif child.type != "text" or child.content:
                line_children.append(child)
        yield line_number, line_children


class Marker(NamedTuple):
    """Label shown after a link, such as "newer doc"."""

    css_class: str
    """CSS class of the label (``marker`` is added), which also names its kind, e.g. ``newer``."""

    text: str
    """Text of the label."""


@dataclass(frozen=True)
class RenderedLink:
    """How a link is rendered."""

    href: str | None
    """New ``href`` attribute of the link; None leaves the link text as plain text."""

    markers: tuple[Marker, ...] = ()
    """Labels shown after the link."""

    use_code_style: bool = False
    """Whether link text left without an ``href`` is shown as code, as a link to code would be, unless it already is
    one code span."""

    code_text: str | None = None
    """Text that replaces the link's content, shown as one code span; None keeps the content."""


class BodyRenderer(RendererHTML):
    """HTML renderer for doc bodies that draws ``mermaid`` code fences as diagrams."""

    @override
    def fence(self, tokens: Sequence[Token], idx: int, options: OptionsDict, env: EnvType) -> str:
        """Return the HTML of a fenced code block; a ``mermaid`` fence becomes a ``<pre class="mermaid">`` block.

        Args:
            tokens: Tokens being rendered; only the one at ``idx`` is read.
            idx: Position of the fence token in ``tokens``; its info string decides whether it is a diagram.
            options: Renderer options, passed on to the default fence rendering.
            env: Render environment, passed on to the default fence rendering.
        """
        token = tokens[idx]
        if token.info.strip().split(maxsplit=1)[:1] == ["mermaid"]:
            return f'<pre class="mermaid">{escapeHtml(token.content)}</pre>\n'
        return super().fence(tokens, idx, options, env)


class HtmlRenderer:
    """Renderer of doc and docstring Markdown to HTML, with its links rewritten by a callback.

    Fences with info ``mermaid`` become ``<pre class="mermaid">`` blocks; raw HTML in the source is kept as is
    (markdown-it ``commonmark`` preset).
    """

    # Arguments of __init__
    resolve_link: Callable[[str], RenderedLink]
    """See :meth:`__init__`."""

    toc_min_headings: int
    """See :meth:`__init__`."""

    use_roles: bool
    """See :meth:`__init__`."""

    def __init__(
        self, resolve_link: Callable[[str], RenderedLink], toc_min_headings: int = 0, *, use_roles: bool = False
    ) -> None:
        """Prepare the rendering of texts whose links are resolved the same way.

        Args:
            resolve_link: Called for every link and image target (as :meth:`MarkdownText.extract_links` returns it) to
                decide how it renders; a result with no href leaves the link text as plain text, and its markers
                follow the link.
            toc_min_headings: Fewest ``##`` headings from which a "Contents" list of them (``###`` nested) is
                inserted before the first ``##``; 0 turns it off.
            use_roles: Read Sphinx's Python roles as links whose target starts with ``role:``, as in a docstring; their
                link text is set by the :attr:`~RenderedLink.code_text` of what ``resolve_link`` returns.
        """
        self.resolve_link = resolve_link
        self.toc_min_headings = toc_min_headings
        self.use_roles = use_roles

    @staticmethod
    def quote_href(href: str) -> str:
        """Return an href percent-encoded for an HTML attribute, keeping the characters that URLs use as delimiters.

        Args:
            href: Decoded href; ``%`` is kept, so an href that is already encoded stays as it is.
        """
        return quote(href, safe="/#?=&:%~.-_!$'()*+,;@")

    @staticmethod
    def make_out_href(raw: str, decoded: str, href: str) -> str:
        """Return the href to write into a rendered link.

        The original attribute is kept when the link target was not rewritten, so percent-encoded characters in
        external URLs stay as written.

        Args:
            raw: Target attribute as written in the source; kept when the callback returned the target unchanged.
            decoded: Percent-decoded ``raw``, the value the link callback was given.
            href: Href chosen by the link callback; percent-encoded again when it differs from ``decoded``.
        """
        return raw if href == decoded else HtmlRenderer.quote_href(href)

    @staticmethod
    def render_markers_html(markers: tuple[Marker, ...]) -> str:
        """Return the HTML of the labels shown after a link.

        Args:
            markers: Labels in the order they are shown; empty gives no HTML.
        """
        return "".join(
            f'<span class="marker {escapeHtml(css_class)}">{escapeHtml(text)}</span>' for css_class, text in markers
        )

    @staticmethod
    def render_toc_item(anchor: str, label: str) -> str:
        """Return the HTML link to a heading in the Contents list.

        Args:
            anchor: Id of the heading the link points to.
            label: Plain text of the heading, shown as the link text.
        """
        return f'<a href="#{escapeHtml(anchor)}">{escapeHtml(label)}</a>'

    @staticmethod
    def render_toc_sublist(subsections: list[tuple[str, str]]) -> str:
        """Return the HTML list of a section's subsections in the Contents list.

        Args:
            subsections: The ``(anchor, label)`` of each ``###`` heading of the section, in order; empty gives no HTML.
        """
        items = "".join(f"<li>{HtmlRenderer.render_toc_item(*subsection)}</li>" for subsection in subsections)
        return "<ol>" + items + "</ol>" if subsections else ""

    def render(self, text: str) -> str:
        """Render Markdown to HTML.

        Args:
            text: Markdown of a doc (front matter is dropped) or of a docstring.
        """
        parser = _select_parser(use_roles=self.use_roles)
        tokens = parser.parse(text)
        for token in tokens:
            if token.type == "inline":
                self.rewrite_inline(token)
        toc = self.build_toc(tokens)
        if toc is not None:
            toc_index, toc_html = toc
            block = Token("html_block", "", 0)
            block.content = toc_html
            tokens.insert(toc_index, block)
        renderer = BodyRenderer(parser)
        return renderer.render(tokens, parser.options, {})

    def rewrite_inline(self, inline: Token) -> None:
        """Rewrite in place the link and image targets of an inline token.

        Each target goes through :attr:`resolve_link`: its href replaces the target, and its markers are added after the
        link. A link with a :attr:`~RenderedLink.code_text` gets that text as its only content, in one code span. A link
        whose :attr:`href <RenderedLink.href>` is None is reduced to its text, in ``<code>`` when its
        :attr:`~RenderedLink.use_code_style` is set and the text is not one code span already.

        Args:
            inline: Inline token whose children are rewritten; links with no href lose their open and close tokens.
        """
        rewritten_tokens: list[Token] = []
        # One (link, index in rewritten_tokens of its first content token) per open link, innermost last.
        open_links: list[tuple[RenderedLink, int]] = []
        for child in inline.children or []:
            if child.type == "link_open":
                raw = str(child.attrGet("href") or "")
                decoded = unquote(raw)
                rendered_link = self.resolve_link(decoded)
                if rendered_link.href is not None:
                    child.attrSet("href", self.make_out_href(raw, decoded, rendered_link.href))
                    rewritten_tokens.append(child)
                open_links.append((rendered_link, len(rewritten_tokens)))
                continue
            elif child.type == "link_close":
                rendered_link, content_start = open_links.pop()
                self._close_link(rendered_link, rewritten_tokens, content_start, child)
                continue
            elif child.type == "image":
                raw = str(child.attrGet("src") or "")
                decoded = unquote(raw)
                rendered_link = self.resolve_link(decoded)
                if rendered_link.href is not None:
                    child.attrSet("src", self.make_out_href(raw, decoded, rendered_link.href))
            rewritten_tokens.append(child)
        inline.children = rewritten_tokens

    def _close_link(
        self, rendered_link: RenderedLink, tokens: list[Token], content_start: int, close_token: Token
    ) -> None:
        """Finish one link at its close token, in the inline tokens being rewritten, as :meth:`rewrite_inline` says.

        Args:
            rendered_link: How the link renders, as :attr:`resolve_link` returned it for the link's target.
            tokens: Inline tokens rewritten so far, ending with the link's content; changed in place.
            content_start: Index in ``tokens`` of the link's first content token.
            close_token: The link's ``link_close`` token, kept when the link has an href.
        """
        if rendered_link.code_text is not None:
            code_token = Token("code_inline", "code", 0)
            code_token.content = rendered_link.code_text
            tokens[content_start:] = [code_token]
        if rendered_link.href is not None:
            tokens.append(close_token)
        elif rendered_link.use_code_style:
            self.wrap_in_code(tokens, content_start)
        if rendered_link.markers:
            markers_token = Token("html_inline", "", 0)
            markers_token.content = self.render_markers_html(rendered_link.markers)
            tokens.append(markers_token)

    @staticmethod
    def wrap_in_code(tokens: list[Token], start: int) -> None:
        """Wrap the tokens from a position to the end in ``<code>``, unless they are one code span already.

        Args:
            tokens: Inline tokens being rewritten; changed in place.
            start: Index of the first token to wrap.
        """
        if len(tokens) - start == 1 and tokens[start].type == "code_inline":
            return
        opening = Token("html_inline", "", 0)
        opening.content = "<code>"
        closing = Token("html_inline", "", 0)
        closing.content = "</code>"
        tokens.insert(start, opening)
        tokens.append(closing)

    def build_toc(self, tokens: list[Token]) -> tuple[int, str] | None:
        """Return the Contents list of a document and where to insert it, or None.

        The position is the token index of the first ``##`` heading. There is no list when the document has fewer
        ``##`` sections than :attr:`toc_min_headings`, or when that is 0 or less.

        Args:
            tokens: Tokens of the document being rendered, with heading ids already set by the anchors plugin.
        """
        if self.toc_min_headings <= 0:
            return None
        first_h2_index: int | None = None
        # One entry per ``##`` heading, in document order: (anchor, label, subsections), where subsections lists the
        # (anchor, label) of the ``###`` headings that follow it, up to the next ``##``. A ``###`` before the first
        # ``##`` belongs to no section and is skipped.
        sections: list[tuple[str, str, list[tuple[str, str]]]] = []
        for token_index, token in enumerate(tokens):
            if token.type != "heading_open" or token.tag not in ("h2", "h3"):
                continue
            label = MarkdownText.join_inline_text(tokens[token_index + 1], skip_links=False).strip()
            entry = (str(token.attrGet("id") or ""), label)
            if token.tag == "h2":
                first_h2_index = token_index if first_h2_index is None else first_h2_index
                sections.append((*entry, []))
            elif sections:
                sections[-1][2].append(entry)
        if first_h2_index is None or len(sections) < self.toc_min_headings:
            return None
        items = "".join(
            f"<li>{self.render_toc_item(anchor, label)}{self.render_toc_sublist(subsections)}</li>"
            for anchor, label, subsections in sections
        )
        return first_h2_index, f'<nav class="toc"><h2 class="toc-title">Contents</h2><ol>{items}</ol></nav>\n'
