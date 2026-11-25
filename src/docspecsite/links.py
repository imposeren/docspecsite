"""The links of a doc and what they point at.

Docs: meta/linking.md
"""

import posixpath
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .docs import Doc, make_string_tuple
from .problems import Problem

type RefKind = Literal["body", "related", "redirect_to", "superseded_by"]

SCHEME_PATTERN = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")
WEB_SCHEMES = {"http", "https", "mailto"}
EMPTY_CODE_TARGET_MESSAGE = "empty code: target"


@dataclass(frozen=True)
class CodeRef:
    """Link from a doc to a code element, by dotted path."""

    dotted_path: str
    """Dotted path of the code element, as written in the doc."""

    kind: Literal["body", "code"]
    """Where the link is written.

    ``body`` is a ``code:`` link in the text; ``code`` is an entry of the ``code`` front-matter field.
    """

    line_number: int
    """Line of the link in the doc file, from 1; the front matter's first line for a ``code`` entry."""

    @property
    def is_body(self) -> bool:
        """Whether the link is a ``code:`` link in the doc's text, not an entry of the ``code`` front-matter field."""
        return self.kind == "body"


@dataclass(frozen=True)
class Ref:
    """Local link from a doc to a file of the repository, with an optional heading anchor."""

    target: str
    """Normalized POSIX path of the target relative to the repo root, e.g. ``docs/a.md``."""

    kind: RefKind
    """Where the link is written: ``body`` for the text, else the front-matter field holding it."""

    line_number: int
    """Line of the link in the doc file, from 1; the front matter's first line for a front-matter link."""

    anchor: str | None
    """Heading anchor of the link, without ``#``; None when it has none."""

    @property
    def is_body(self) -> bool:
        """Whether the link is written in the doc's text, not in a front-matter field (which must name a doc)."""
        return self.kind == "body"


def parse_code_target(href: str) -> str | None:
    """Return the dotted path a ``code:`` link names (empty when the link has no path), or None for any other link.

    Args:
        href: Link target to inspect; its scheme is matched case-insensitively.
    """
    scheme_match = SCHEME_PATTERN.match(href)
    if scheme_match is None or scheme_match.group(1).lower() != "code":
        return None
    return href[scheme_match.end() :].strip()


def is_empty_code_target(href: str) -> bool:
    """Return whether a link is a ``code:`` link with nothing after the scheme, such as ``code:``.

    Args:
        href: Link target to inspect; its scheme is matched case-insensitively.
    """
    return parse_code_target(href) == ""


def parse_body_ref(doc_path: str, href: str, line_number: int) -> Ref | CodeRef | Problem | None:  # noqa: C901 - one classification of a body link by its form; the cases read as one table
    """Classify a link found in the body of a doc.

    Returns a :class:`Ref` for a local link, a :class:`CodeRef` for a ``code:`` link, a
    :class:`~docspecsite.problems.Problem` for a malformed or unsupported link, and None for web links and bare anchors.

    Args:
        doc_path: Path of the doc holding the link, relative to ``docs/``; relative hrefs are resolved against its
            directory, and problems are reported on it.
        href: Link target as written in the doc (as :meth:`~docspecsite.markdown.MarkdownText.extract_links` returns
            it), with any ``?query`` and ``#anchor``.
        line_number: 1-based file line of the link, stored in the returned ref or problem; callers that only classify
            the link pass 0.
    """
    if href.strip() in ("", "#"):
        return Problem(doc_path, line_number, "empty link target")
    scheme_match = SCHEME_PATTERN.match(href)
    if scheme_match:
        scheme_name = scheme_match.group(1).lower()
        if scheme_name in WEB_SCHEMES:
            return None
        if is_empty_code_target(href):
            return Problem(doc_path, line_number, EMPTY_CODE_TARGET_MESSAGE)
        dotted_path = parse_code_target(href)
        if dotted_path is not None:
            return CodeRef(dotted_path, "body", line_number)
        if scheme_name == "web-api":
            return Problem(doc_path, line_number, f"web-api: links cannot be resolved yet (no API schema): {href}")
        return Problem(doc_path, line_number, f"unsupported link scheme: {href}")
    path, _, anchor = href.partition("#")
    path = path.partition("?")[0]
    if path.startswith("/"):
        return Problem(doc_path, line_number, f"use a relative link instead of {href}")
    if not path:
        if not anchor:
            return None
        return Ref(f"docs/{doc_path}", "body", line_number, anchor)
    target = posixpath.normpath(posixpath.join("docs", posixpath.dirname(doc_path), path))
    if target == ".." or target.startswith("../"):
        return Problem(doc_path, line_number, f"link points outside the repository: {href}")
    return Ref(target, "body", line_number, anchor or None)


def list_front_matter_paths(front_matter: Mapping[str, object], key: str) -> list[str]:
    """Return the paths in a front-matter field that holds a path or a list of paths.

    Args:
        front_matter: Front matter of a doc whose ``key`` field is read; other fields are ignored.
        key: Field to read, e.g. ``related`` or ``redirect_to``; only string values (single or in a list) count, and a
            missing field gives none.
    """
    value = front_matter.get(key)
    values = value if isinstance(value, list) else [value]
    return [item for item in values if isinstance(item, str)]


class DocLinks:
    """The links of one doc: its local links, its links to code elements and the problems found in them."""

    # Constants
    FRONT_MATTER_LINE_NUMBER = 1
    """Line number given to front-matter links: the first line of the doc file, where the front matter starts."""

    FRONT_MATTER_LINK_FIELDS: tuple[RefKind, ...] = ("related", "redirect_to", "superseded_by")
    """Front-matter fields holding local links, in the order their links are collected."""

    # Arguments of __init__
    doc: Doc
    """See :meth:`__init__`."""

    def __init__(self, doc: Doc) -> None:
        """Hold a doc whose links are collected.

        Args:
            doc: Doc whose body links and front-matter link fields are read.
        """
        self.doc = doc

    def parse_body_links(self) -> list[Ref | CodeRef | Problem | None]:
        """Classify each link in the body of the doc, in order.

        Each link is classified as :func:`parse_body_ref` does.
        """
        return [
            parse_body_ref(self.doc.path, link.target, self.doc.get_file_line_number(link.line_number))
            for link in self.doc.body_markdown.extract_links()
        ]

    def build_front_matter_refs(self) -> list[Ref]:
        """Return the local links in the ``related``, ``redirect_to`` and ``superseded_by`` fields, by field.

        Only string values (single or in a list) count, and a doc without front matter gives none.
        """
        front_matter = self.doc.front_matter or {}
        front_matter_refs: list[Ref] = []
        for kind in self.FRONT_MATTER_LINK_FIELDS:
            for value in list_front_matter_paths(front_matter, kind):
                path, _, anchor = value.partition("#")
                target = posixpath.normpath(posixpath.join("docs", path))
                front_matter_refs.append(Ref(target, kind, self.FRONT_MATTER_LINE_NUMBER, anchor or None))
        return front_matter_refs

    def collect_outgoing_refs(self) -> tuple[list[Ref], list[Problem]]:
        """Return the local links of the doc and the problems found in its links.

        Body links come first, then front-matter links. Web links and ``code:`` links are not local links.
        """
        parsed_links = self.parse_body_links()
        refs = [parsed_link for parsed_link in parsed_links if isinstance(parsed_link, Ref)]
        problems = [parsed_link for parsed_link in parsed_links if isinstance(parsed_link, Problem)]
        return [*refs, *self.build_front_matter_refs()], problems

    def collect_code_refs(self) -> list[CodeRef]:
        """Return the code elements that the doc points at.

        Body ``code:`` links come first, in order, then the string entries of the front-matter ``code`` list.
        """
        code_refs = [parsed_link for parsed_link in self.parse_body_links() if isinstance(parsed_link, CodeRef)]
        dotted_paths = make_string_tuple((self.doc.front_matter or {}).get("code"), strings_only=True)
        code_refs.extend(CodeRef(dotted_path, "code", self.FRONT_MATTER_LINE_NUMBER) for dotted_path in dotted_paths)
        return code_refs
