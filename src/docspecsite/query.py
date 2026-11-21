"""Front-matter filters for docs, and the text and JSON formats of doc listings and backlinks.

Docs: architecture/docs-tooling.md
"""

import json
import posixpath
from collections.abc import Sequence
from dataclasses import dataclass, fields
from pathlib import Path
from typing import ClassVar, Literal

from .docs import Doc
from .text import collapse_to_one_line

type Format = Literal["text", "json"]

LIST_FIELDS = ("title", "summary", "layer", "status", "components", "tags", "milestone", "priority")


@dataclass(frozen=True)
class Filters:
    """Front-matter values a doc must have to be listed; a field left None is not filtered on."""

    LIST_FIELD_BY_FILTER: ClassVar[dict[str, str]] = {"component": "components", "tag": "tags"}
    """Front-matter list field of each membership filter; the filter matches when its value is among the items."""

    layer: str | None = None
    """Value the ``layer`` field must have."""

    status: str | None = None
    """Value the ``status`` field must have."""

    component: str | None = None
    """Component the ``components`` field must list."""

    tag: str | None = None
    """Tag the ``tags`` field must list."""

    milestone: str | None = None
    """Value the ``milestone`` field must have."""

    priority: str | None = None
    """Value the ``priority`` field must have."""

    def matches(self, front_matter: dict[str, object]) -> bool:
        """Return whether front matter matches every filter that is set.

        :attr:`component` and :attr:`tag` match when the value is among the doc's components or tags.

        Args:
            front_matter: Front matter of one doc; ``components`` and ``tags`` must be lists to match a membership
                filter.
        """
        for f in fields(self):
            wanted = getattr(self, f.name)
            if wanted is None:
                continue
            if f.name in self.LIST_FIELD_BY_FILTER:
                member_values = front_matter.get(self.LIST_FIELD_BY_FILTER[f.name])
                if not (isinstance(member_values, list) and wanted in member_values):
                    return False
            elif front_matter.get(f.name) != wanted:
                return False
        return True


def format_list(docs: list[Doc], fmt: Format) -> str:
    """Format docs as a listing, one entry per doc in the given order.

    The result is tab-separated lines, or a JSON list with the ``json`` format.

    Args:
        docs: Docs to print in the given order, one line or JSON item each.
        fmt: ``json`` for a JSON list with the listed fields, else tab-separated path, status, title and summary.
    """
    if fmt == "json":
        items = [{"path": d.path, **{k: (d.front_matter or {}).get(k) for k in LIST_FIELDS}} for d in docs]
        return json.dumps(items, indent=2, ensure_ascii=False, default=str) + "\n"
    return "".join(
        "\t".join(
            [d.path, *(collapse_to_one_line((d.front_matter or {}).get(k)) for k in ("status", "title", "summary"))]
        )
        + "\n"
        for d in docs
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
        return collapse_to_one_line((self.doc.front_matter or {}).get("title"))


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
