"""The single Markdown parser of docspecsite, with what is read from its tokens."""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import NamedTuple, override
from urllib.parse import quote, unquote

from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.front_matter import front_matter_plugin

_md = MarkdownIt("commonmark").enable("table").use(front_matter_plugin).use(anchors_plugin, max_level=6)


@dataclass(frozen=True)
class Link:
    """Link or image found in a text."""

    target: str
    """Link ``href`` or image ``src``, percent-decoded."""

    line_number: int
    """Line of the link in the text, from 1."""


@dataclass(frozen=True)
class Entry:
    """List item that contains links."""

    targets: tuple[str, ...]
    """Targets of the item's links, in order, percent-decoded."""

    text: str
    """Text of the item without its links' text, e.g. a child's description."""

    line_number: int
    """Line where the item starts in the text, from 1."""


class MarkdownText:
    """Markdown text parsed once, with what is read from its tokens."""

    # Constants
    BREAKS = ("softbreak", "hardbreak")
    """Types of the inline child tokens that break a line."""

    # Arguments of __init__
    text: str
    """See :meth:`.__init__`."""

    def __init__(self, text: str) -> None:
        """Prepare a Markdown text for reading; it is parsed on first use.

        Args:
            text: Markdown of a doc body or whole file (front matter becomes a ``front_matter`` token and is skipped),
                or of a docstring; the lines of the results are 1-based within this text.
        """
        self.text = text

    @cached_property
    def tokens(self) -> list[Token]:
        """The markdown-it tokens of the text, parsed on first use."""
        return _md.parse(self.text)

    def split_front_matter(self) -> tuple[str | None, int]:
        """Split the text, a whole doc file, into its YAML front matter and the line where the body starts.

        The front matter is the YAML between the leading ``---`` lines at the very start, or None when there is none.
        The line is 1-based.
        """
        tokens = self.tokens
        if tokens and tokens[0].type == "front_matter" and tokens[0].map:
            return tokens[0].content + "\n", tokens[0].map[1] + 1
        return None, 1

    @staticmethod
    def iter_inline_links(inline: Token) -> Iterator[Link]:
        """Return the links and images of an inline token, with their lines.

        Args:
            inline: Inline token of one block; its ``map`` gives the first line, and line breaks inside count on from
                it.
        """
        line = (inline.map[0] if inline.map else 0) + 1
        for child in inline.children or []:
            if child.type in MarkdownText.BREAKS:
                line += 1
            elif child.type == "link_open":
                yield Link(unquote(str(child.attrGet("href") or "")), line)
            elif child.type == "image":
                yield Link(unquote(str(child.attrGet("src") or "")), line)

    @staticmethod
    def join_inline_text(inline: Token, *, skip_links: bool) -> str:
        """Return the plain text of an inline token, from text and code.

        Args:
            inline: Inline token of a heading or list item whose text is collected.
            skip_links: Leave out the text inside links, to get a list item's description apart from its link titles.
        """
        parts: list[str] = []
        in_link = 0
        for child in inline.children or []:
            if child.type == "link_open":
                in_link += 1
            elif child.type == "link_close":
                in_link -= 1
            elif in_link and skip_links:
                continue
            elif child.type in ("text", "code_inline"):
                parts.append(child.content)
            elif child.type in MarkdownText.BREAKS:
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
        or a higher level. The result has one flag per token of :attr:`.tokens`.

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
        inside = self.mark_in_section(section)
        codes: list[str] = []
        in_body = False
        first_cell = False
        for token_index, token in enumerate(tokens):
            if token.type == "tbody_open":
                in_body = True
            elif token.type == "tbody_close":
                in_body = False
            elif token.type == "tr_open":
                first_cell = True
            elif token.type == "inline" and in_body and first_cell:
                first_cell = False
                children = token.children or []
                if inside[token_index] and children and children[0].type == "code_inline":
                    codes.append(children[0].content)
        return codes

    def list_entries(self, section: str | None = None) -> list[Entry]:
        """Return the list items of the text that contain a link.

        Each is an :class:`.Entry` with its link targets and other text. The text is typically an ``index.md`` body.

        Args:
            section: Exact text of a heading, such as ``Children``; only list items under it count (subsections
                included), up to the next heading of the same or a higher level. None counts every list item.
        """
        tokens = self.tokens
        inside = self.mark_in_section(section)
        entries: list[Entry] = []
        for token_index, token in enumerate(tokens):
            if token.type != "list_item_open" or not token.map or not inside[token_index]:
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
                text_parts = (self.join_inline_text(t, skip_links=True) for t in inlines)
                entries.append(Entry(targets, " ".join(p.strip() for p in text_parts if p.strip()), token.map[0] + 1))
        return entries


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
    link: Callable[[str], RenderedLink]
    """See :meth:`.__init__`."""

    toc_min_headings: int
    """See :meth:`.__init__`."""

    def __init__(self, link: Callable[[str], RenderedLink], toc_min_headings: int = 0) -> None:
        """Prepare the rendering of texts whose links are resolved the same way.

        Args:
            link: Called for every link and image target (as :meth:`.MarkdownText.extract_links` returns it) to
                decide how it renders; a result with no href leaves the link text as plain text, and its markers
                follow the link.
            toc_min_headings: Fewest ``##`` headings from which a "Contents" list of them (``###`` nested) is
                inserted before the first ``##``; 0 turns it off.
        """
        self.link = link
        self.toc_min_headings = toc_min_headings

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
        return "".join(f'<span class="marker {escapeHtml(css)}">{escapeHtml(text)}</span>' for css, text in markers)

    @staticmethod
    def render_toc_item(anchor: str, label: str) -> str:
        """Return the HTML link to a heading in the Contents list.

        Args:
            anchor: Id of the heading the link points to.
            label: Plain text of the heading, shown as the link text.
        """
        return f'<a href="#{escapeHtml(anchor)}">{escapeHtml(label)}</a>'

    @staticmethod
    def render_toc_sublist(subs: list[tuple[str, str]]) -> str:
        """Return the HTML list of a section's subsections in the Contents list.

        Args:
            subs: The ``(anchor, label)`` of each ``###`` heading of the section, in order; empty gives no HTML.
        """
        items = "".join(f"<li>{HtmlRenderer.render_toc_item(*sub)}</li>" for sub in subs)
        return "<ol>" + items + "</ol>" if subs else ""

    def render(self, text: str) -> str:
        """Render Markdown to HTML.

        Args:
            text: Markdown of a doc (front matter is dropped) or of a docstring.
        """
        tokens = _md.parse(text)
        for token in tokens:
            if token.type == "inline":
                self.rewrite_inline(token)
        contents = self.build_toc(tokens)
        if contents:
            block = Token("html_block", "", 0)
            block.content = contents[1]
            tokens.insert(contents[0], block)
        renderer = BodyRenderer(_md)
        return renderer.render(tokens, _md.options, {})

    def rewrite_inline(self, inline: Token) -> None:
        """Rewrite in place the link and image targets of an inline token.

        Each target goes through :attr:`.link`: its href replaces the target, and its markers are added after the link.
        A link whose :attr:`href <.RenderedLink.href>` is None is reduced to its text.

        Args:
            inline: Inline token whose children are rewritten; links with no href lose their open and close tokens.
        """
        rewritten_tokens: list[Token] = []
        pending: list[RenderedLink] = []  # one per open link, innermost last
        for child in inline.children or []:
            if child.type == "link_open":
                raw = str(child.attrGet("href") or "")
                decoded = unquote(raw)
                rendered_link = self.link(decoded)
                pending.append(rendered_link)
                if rendered_link.href is None:
                    continue
                child.attrSet("href", self.make_out_href(raw, decoded, rendered_link.href))
            elif child.type == "link_close":
                rendered_link = pending.pop()
                if rendered_link.href is not None:
                    rewritten_tokens.append(child)
                if rendered_link.markers:
                    marker = Token("html_inline", "", 0)
                    marker.content = self.render_markers_html(rendered_link.markers)
                    rewritten_tokens.append(marker)
                continue
            elif child.type == "image":
                raw = str(child.attrGet("src") or "")
                decoded = unquote(raw)
                rendered_link = self.link(decoded)
                if rendered_link.href is not None:
                    child.attrSet("src", self.make_out_href(raw, decoded, rendered_link.href))
            rewritten_tokens.append(child)
        inline.children = rewritten_tokens

    def build_toc(self, tokens: list[Token]) -> tuple[int, str] | None:
        """Return the Contents list of a document and where to insert it, or None.

        The position is the token index of the first ``##`` heading. There is no list when the document has fewer
        ``##`` sections than :attr:`.toc_min_headings`, or when that is 0 or less.

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
            f"<li>{self.render_toc_item(a, label)}{self.render_toc_sublist(subs)}</li>" for a, label, subs in sections
        )
        return first_h2_index, f'<nav class="toc"><h2 class="toc-title">Contents</h2><ol>{items}</ol></nav>\n'
