"""Front-matter filters for docs, and the text and JSON formats of doc listings and backlinks.

Docs: architecture/docs-tooling.md
"""

import json
import posixpath
from collections.abc import Sequence
from dataclasses import dataclass, fields
from pathlib import Path
from typing import ClassVar, Literal

from .docs import Doc, DocStatus
from .text import collapse_to_one_line

type Format = Literal["text", "json"]

LIST_FIELDS = ("title", "summary", "layer", "status", "components", "tags", "milestone", "priority")
"""Fields each item of a JSON listing has, after the path."""

TEXT_LIST_FIELDS = ("status", "title", "summary")
"""Fields each line of a text listing has, after the path, in column order."""


@dataclass(frozen=True)
class Filters:
    """Front-matter values a doc must have to be listed; a field left None is not filtered on."""

    LIST_FIELD_BY_FILTER: ClassVar[dict[str, str]] = {"component": "components", "tag": "tags"}
    """Front-matter list field of each membership filter; the filter matches when its value is among the items."""

    layer: str | None = None
    """Value the ``layer`` field must have."""

    status: str | None = None
    """Value the ``status`` field must have, or list among its values."""

    component: str | None = None
    """Component the ``components`` field must list."""

    tag: str | None = None
    """Tag the ``tags`` field must list."""

    milestone: str | None = None
    """Value the ``milestone`` field must have."""

    priority: str | None = None
    """Value the ``priority`` field must have."""

    def matches(self, doc: Doc) -> bool:
        """Return whether a doc matches every filter that is set.

        :attr:`component` and :attr:`tag` match when the value is among the doc's components or tags. Any other
        filter matches the field's value as :func:`read_list_field` reads it, or one of its items when that is a list,
        so :attr:`status` matches any of the doc's status values.

        Args:
            doc: Doc to check; ``components`` and ``tags`` must be lists to match a membership filter. A doc whose
                front matter did not load matches no filters, even when none is set.
        """
        if doc.front_matter is None:
            return False
        for f in fields(self):
            wanted = getattr(self, f.name)
            if wanted is None:
                continue
            if f.name in self.LIST_FIELD_BY_FILTER:
                member_values = read_list_field(doc, self.LIST_FIELD_BY_FILTER[f.name])
                if not (isinstance(member_values, list) and wanted in member_values):
                    return False
                continue
            value = read_list_field(doc, f.name)
            if value != wanted and not (isinstance(value, list) and wanted in value):
                return False
        return True


def make_status_json_value(status: DocStatus) -> str | list[str] | None:
    """Return the JSON value of a status: a string for one value, a list for more, None for none.

    Args:
        status: Status to convert.
    """
    if status.is_single:
        return status.values[0]
    return list(status.values) if status.values else None


def read_list_field(doc: Doc, field: str) -> object:
    """Return a doc's value of a front-matter field as listings show it and filters match it.

    ``status`` is read as the doc's status: a string for one value, a list for more, None for none. Any other field
    is the value as written.

    Args:
        doc: Doc to read; a doc whose front matter did not load has None for every field.
        field: Name of the front-matter field, such as ``title`` or ``status``.
    """
    if field == "status":
        return make_status_json_value(doc.status)
    return (doc.front_matter or {}).get(field)


def format_text_field(value: object) -> str:
    """Return a field's value as one tab-separated column on one line: list items joined by commas.

    Args:
        value: Value read by :func:`read_list_field`; whitespace runs in it, tabs and line breaks too, become single
            spaces, and None becomes empty.
    """
    if isinstance(value, list):
        return ",".join(collapse_to_one_line(item) for item in value)
    return collapse_to_one_line(value)


def format_list(docs: list[Doc], fmt: Format) -> str:
    """Format docs as a listing, one entry per doc in the given order.

    The result is tab-separated lines, or a JSON list with the ``json`` format.

    Args:
        docs: Docs to print in the given order, one line or JSON item each.
        fmt: ``json`` for a JSON list with the listed fields, else tab-separated path, status, title and summary.
    """
    if fmt == "json":
        items = [{"path": d.path, **{k: read_list_field(d, k) for k in LIST_FIELDS}} for d in docs]
        return json.dumps(items, indent=2, ensure_ascii=False, default=str) + "\n"
    return "".join(
        "\t".join([d.path, *(format_text_field(read_list_field(d, k)) for k in TEXT_LIST_FIELDS)]) + "\n" for d in docs
    )


@dataclass(frozen=True)
class Backlink:
    """Doc that links to another doc."""

    doc: Doc
    """The linking doc."""

    kinds: tuple[str, ...]
    """Kinds of its links to the doc, sorted: ``body`` or the front-matter field holding the link."""

    @property
    def title(self) -> str:
        """Title of the linking doc on one line; empty when it has none."""
        return collapse_to_one_line(self.doc.front_matter_title)


def resolve_doc_path(root: Path, path: str) -> str | None:
    """Return the path relative to ``docs/`` of the doc a given path names, or None if it names no existing doc.

    The result is a POSIX path such as ``meta/x.md``, whatever form the given path has.

    Args:
        root: Repository root; relative paths are resolved against it or its ``docs/``.
        path: An absolute path, a path from the repo root (``docs/x.md``, ``./docs/x.md``) or a path relative to
            ``docs/`` (``x.md``).
    """
    docs_dir = (root / "docs").resolve()
    given = Path(path.replace("\\", "/"))
    if given.is_absolute():
        candidate = given
    elif posixpath.normpath(given.as_posix()).split("/")[0] == "docs":
        candidate = root / given
    else:
        candidate = docs_dir / given
    candidate = candidate.resolve()
    if candidate.suffix != ".md" or not candidate.is_file():
        return None
    try:
        return candidate.relative_to(docs_dir).as_posix()
    except ValueError:
        return None


def format_backlinks(links: Sequence[Backlink], fmt: Format) -> str:
    """Format backlinks as a listing, one entry per backlink in the given order.

    The result is tab-separated lines, or a JSON list with the ``json`` format.

    Args:
        links: Backlinks to print in the given order.
        fmt: ``json`` for a JSON list, else tab-separated source, kinds and title.
    """
    if fmt == "json":
        items = [{"source": b.doc.path, "title": b.title, "kinds": list(b.kinds)} for b in links]
        return json.dumps(items, indent=2, ensure_ascii=False) + "\n"
    return "".join(f"{b.doc.path}\t{','.join(b.kinds)}\t{b.title}\n" for b in links)
