"""The docs of one tree, indexed by path and by the docs that link to them.

Docs: architecture/docs-tooling.md
"""

from collections.abc import Iterable, Mapping
from functools import cached_property
from pathlib import Path
from types import MappingProxyType
from typing import Self

from .config import ProjectConfig
from .docs import DOCS, Doc, is_template, parse_doc, read_text
from .links import collect_outgoing_refs
from .query import Backlink, Filters, collapse_to_one_line


class DocSet:
    """A set of docs, such as those of the working tree or the latest version of each doc in git history.

    Attributes:
        docs: The docs, in the order given.
        by_path: The docs by path relative to ``docs/``.
        backlinks_by_target: The backlinks of every linked doc, by its path, worked out on first use.
    """

    def __init__(self, docs: Iterable[Doc]) -> None:
        """Hold docs and index them by path.

        Args:
            docs: Docs with distinct paths, in the order ``docs`` keeps them.
        """
        self.docs = tuple(docs)
        self.by_path: Mapping[str, Doc] = MappingProxyType({doc.path: doc for doc in self.docs})

    @classmethod
    def load(cls, root: Path) -> Self:
        """Return the docs of a repository's working tree, sorted by path.

        Every ``docs/**/*.md`` is read except templates.

        Args:
            root: Repository root; docs are read from its ``docs/`` directory in the working tree, not from git.
        """
        docs_dir = root / "docs"
        files = {f.relative_to(docs_dir).as_posix(): f for f in docs_dir.rglob("*.md") if f.is_file()}
        return cls([parse_doc(path, read_text(files[path])) for path in sorted(files) if not is_template(path)])

    def select(self, filters: Filters, config: ProjectConfig) -> list[Doc]:
        """Return the docs matching all filters, sorted by path with ADRs ordered by prefix first.

        Docs whose front matter did not load are skipped.

        Args:
            filters: Front-matter values a doc must have to be selected; fields left None are not checked.
            config: Settings whose ADR prefixes order the ADRs.
        """
        return sorted(
            (d for d in self.docs if d.front_matter is not None and filters.matches(d.front_matter)),
            key=lambda d: config.make_sort_key(d.path),
        )

    @cached_property
    def backlinks_by_target(self) -> Mapping[str, tuple[Backlink, ...]]:
        """The backlinks of every linked doc, by its path relative to ``docs/``, sorted by source."""
        # Linked doc path -> linking doc path -> kinds of its links to it (paths relative to docs/).
        kinds: dict[str, dict[str, set[str]]] = {}
        for doc in self.docs:
            refs, _ = collect_outgoing_refs(doc)
            for ref in refs:
                # A link to a directory is a link to its index.md.
                for target in (ref.target, f"{ref.target}/index.md"):
                    path = target.removeprefix(DOCS)
                    if target.startswith(DOCS) and path != doc.path:
                        kinds.setdefault(path, {}).setdefault(doc.path, set()).add(ref.kind)
        return MappingProxyType(
            {
                target: tuple(
                    Backlink(
                        source,
                        collapse_to_one_line((self.by_path[source].front_matter or {}).get("title")),
                        tuple(sorted(found)),
                    )
                    for source, found in sorted(sources.items())
                )
                for target, sources in kinds.items()
            }
        )

    def find_backlinks(self, target: str) -> tuple[Backlink, ...]:
        """Return the docs other than the target that link to it, sorted by path.

        Each result has the kinds of its links: body, related, redirect_to or superseded_by. The backlinks of all docs
        are collected on the first call.

        Args:
            target: Path of the linked-to doc relative to ``docs/``; a link to its directory counts when it is an
                ``index.md``.
        """
        return self.backlinks_by_target.get(target, ())
