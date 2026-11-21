"""The links of a doc and what they point at.

Docs: meta/linking.md
"""

import posixpath
import re
from dataclasses import dataclass
from typing import Literal

from .docs import Doc
from .markdown import MarkdownText
from .problems import Problem

type RefKind = Literal["body", "related", "redirect_to", "superseded_by"]

SCHEME = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")
WEB_SCHEMES = {"http", "https", "mailto"}
FRONT_MATTER_LINE = 1


@dataclass(frozen=True)
class CodeRef:
    """Link from a doc to a code element, by dotted path."""

    dotted: str
    """Dotted path of the code element, as written in the doc."""

    kind: Literal["body", "code"]
    """Where the link is written.

    ``body`` is a ``code:`` link in the text; ``code`` is an entry of the ``code`` front-matter field.
    """

    line_number: int
    """Line of the link in the doc file, from 1; the front matter's first line for a ``code`` entry."""


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


def parse_code_target(href: str) -> str | None:
    """Return the dotted path a ``code:`` link names, or None for any other link.

    Args:
        href: Link target; the scheme is case-insensitive. The result is empty for a ``code:`` link without a path.
    """
    scheme = SCHEME.match(href)
    if scheme is None or scheme.group(1).lower() != "code":
        return None
    return href[scheme.end() :].strip()


def parse_body_ref(doc_path: str, href: str, line: int) -> Ref | CodeRef | Problem | None:
    """Classify a link found in the body of a doc.

    Returns a :class:`.Ref` for a local link, a :class:`.CodeRef` for a ``code:`` link, a
    :class:`~docspecsite.problems.Problem` for a malformed or unsupported link, and None for web links and bare anchors.

    Args:
        doc_path: Path of the doc holding the link, relative to ``docs/``; relative hrefs are resolved against its
            directory, and problems are reported on it.
        href: Link target as written in the doc (as :meth:`~docspecsite.markdown.MarkdownText.extract_links` returns
            it), with any ``?query`` and ``#anchor``.
        line: 1-based file line of the link, stored in the returned ref or problem; callers that only classify the
            link pass 0.
    """
    if href.strip() in ("", "#"):
        return Problem(doc_path, line, "empty link target")
    scheme = SCHEME.match(href)
    if scheme:
        name = scheme.group(1).lower()
        if name in WEB_SCHEMES:
            return None
        dotted = parse_code_target(href)
        if dotted is not None:
            if not dotted:
                return Problem(doc_path, line, "empty code: target")
            return CodeRef(dotted, "body", line)
        if name == "web-api":
            return Problem(doc_path, line, f"web-api: links cannot be resolved yet (no API schema): {href}")
        return Problem(doc_path, line, f"unsupported link scheme: {href}")
    path, _, anchor = href.partition("#")
    path = path.partition("?")[0]
    if path.startswith("/"):
        return Problem(doc_path, line, f"use a relative link instead of {href}")
    if not path:
        if not anchor:
            return None
        return Ref(f"docs/{doc_path}", "body", line, anchor)
    target = posixpath.normpath(posixpath.join("docs", posixpath.dirname(doc_path), path))
    if target == ".." or target.startswith("../"):
        return Problem(doc_path, line, f"link points outside the repository: {href}")
    return Ref(target, "body", line, anchor or None)


def collect_front_matter_targets(doc: Doc) -> list[tuple[RefKind, str]]:
    """Return the link targets in the ``related``, ``redirect_to`` and ``superseded_by`` fields of a doc, by field.

    Args:
        doc: Doc whose front matter is read; only string values (single or in a list) count, and a doc without front
            matter gives none.
    """
    front_matter = doc.front_matter or {}
    found: list[tuple[RefKind, str]] = []
    for kind in ("related", "redirect_to", "superseded_by"):
        front_matter_value = front_matter.get(kind)
        target_paths = front_matter_value if isinstance(front_matter_value, list) else [front_matter_value]
        found.extend((kind, v) for v in target_paths if isinstance(v, str))
    return found


def collect_outgoing_refs(doc: Doc) -> tuple[list[Ref], list[Problem]]:
    """Return the local links of a doc and the problems found in its links.

    Body links come first, then front-matter links. Web links and ``code:`` links are not local links.

    Args:
        doc: Doc whose body links and ``related``, ``redirect_to`` and ``superseded_by`` front matter are collected.
    """
    refs: list[Ref] = []
    problems: list[Problem] = []
    for link in MarkdownText(doc.body).extract_links():
        code_ref = parse_body_ref(doc.path, link.target, doc.body_line + link.line_number - 1)
        if isinstance(code_ref, Ref):
            refs.append(code_ref)
        elif isinstance(code_ref, Problem):
            problems.append(code_ref)
    for kind, value in collect_front_matter_targets(doc):
        path, _, anchor = value.partition("#")
        target = posixpath.normpath(posixpath.join("docs", path))
        refs.append(Ref(target, kind, FRONT_MATTER_LINE, anchor or None))
    return refs, problems


def collect_code_refs(doc: Doc) -> list[CodeRef]:
    """Return the code elements that a doc points at.

    Body ``code:`` links come first, in order, then the entries of the front-matter ``code`` field.

    Args:
        doc: Doc whose body ``code:`` links and front-matter ``code`` list are collected.
    """
    found: list[CodeRef] = []
    for link in MarkdownText(doc.body).extract_links():
        ref = parse_body_ref(doc.path, link.target, doc.body_line + link.line_number - 1)
        if isinstance(ref, CodeRef):
            found.append(ref)
    front_matter_value = (doc.front_matter or {}).get("code")
    target_paths = front_matter_value if isinstance(front_matter_value, list) else []
    found.extend(CodeRef(v, "code", FRONT_MATTER_LINE) for v in target_paths if isinstance(v, str))
    return found
