"""The docs of one tree, indexed by path and by the docs that link to them.

Docs: architecture/docs-tooling.md
"""

from collections.abc import Iterable, Iterator, Mapping
from functools import cached_property
from pathlib import Path
from types import MappingProxyType
from typing import Self

from .config import ProjectConfig
from .docs import DOCS_DIR, Doc, derive_doc_path, is_template
from .links import DocLinks
from .query import Backlink, Filters
from .text import UnreadableTextError, read_text


class DocSet:
    """A set of docs, such as those of the working tree or the latest version of each doc in git history."""

    # Index
    by_path: Mapping[str, Doc]
    """The docs by path relative to ``docs/``."""

    # Arguments of __init__
    docs: tuple[Doc, ...]
    """See :meth:`__init__`."""

    read_errors_by_path: Mapping[str, UnreadableTextError]
    """See :meth:`__init__`."""

    def __init__(
        self, docs: Iterable[Doc], read_errors_by_path: Mapping[str, UnreadableTextError] | None = None
    ) -> None:
        """Hold docs and index them by path.

        Args:
            docs: Docs with distinct paths, in the order :attr:`docs` keeps them.
            read_errors_by_path: Why each doc that could not be read is left out of ``docs``, by path relative to
                ``docs/``; None means every doc was read.
        """
        self.docs = tuple(docs)
        self.by_path = MappingProxyType({doc.path: doc for doc in self.docs})
        self.read_errors_by_path = MappingProxyType({} if read_errors_by_path is None else dict(read_errors_by_path))

    def __iter__(self) -> Iterator[Doc]:
        """Return an iterator over the docs in their order."""
        return iter(self.docs)

    @cached_property
    def titles(self) -> Mapping[str, str]:
        """Titles of the docs that have front matter, by path relative to ``docs/``."""
        return MappingProxyType({doc.path: doc.title for doc in self if doc.front_matter is not None})

    @classmethod
    def load(cls, root: Path) -> Self:
        """Return the docs of a repository's working tree, sorted by path.

        Every ``docs/**/*.md`` is read except templates. A doc that cannot be read or is not valid UTF-8 is left out,
        with its error in :attr:`read_errors_by_path`.

        Args:
            root: Repository root; docs are read from its ``docs/`` directory in the working tree, not from git.
        """
        docs_dir = root / "docs"
        files = {f.relative_to(docs_dir).as_posix(): f for f in docs_dir.rglob("*.md") if f.is_file()}
        docs: list[Doc] = []
        read_errors_by_path: dict[str, UnreadableTextError] = {}
        for path in sorted(files):
            if is_template(path):
                continue
            try:
                docs.append(Doc.parse(path, read_text(files[path])))
            except UnreadableTextError as error:
                read_errors_by_path[path] = error
        return cls(docs, read_errors_by_path)

    def require_readable(self) -> Self:
        """Return this doc set if every doc was read.

        Raises:
            UnreadableTextError: A doc could not be read or is not valid UTF-8; the message names the first such doc.
        """
        if self.read_errors_by_path:
            path = min(self.read_errors_by_path)
            raise UnreadableTextError("%s%s: %s", DOCS_DIR, path, self.read_errors_by_path[path])
        return self

    def select(self, filters: Filters, config: ProjectConfig) -> list[Doc]:
        """Return the docs matching all filters, sorted by path with ADRs ordered by prefix first.

        Docs whose front matter did not load are skipped.

        Args:
            filters: Front-matter values a doc must have to be selected; fields left None are not checked.
            config: Settings whose ADR prefixes order the ADRs.
        """
        return sorted(
            (d for d in self if d.front_matter is not None and filters.matches(d.front_matter)),
            key=lambda d: config.make_sort_key(d.path),
        )

    @cached_property
    def backlinks_by_target(self) -> Mapping[str, tuple[Backlink, ...]]:
        """The backlinks of every linked doc, by its path relative to ``docs/``, sorted by source.

        Each backlink is another doc that links to the target, with the kinds of its links: body, related, redirect_to
        or superseded_by. A link to a directory counts for its ``index.md``. A doc nobody links to has no entry.
        """
        # Linked doc path -> linking doc path -> kinds of its links to it (paths relative to docs/).
        link_kinds_by_target: dict[str, dict[str, set[str]]] = {}
        for doc in self:
            refs, _ = DocLinks(doc).collect_outgoing_refs()
            for ref in refs:
                # A link to a directory is a link to its index.md.
                for repo_path in (ref.target, f"{ref.target}/index.md"):
                    target = derive_doc_path(repo_path)
                    if target is not None and target != doc.path:
                        link_kinds_by_target.setdefault(target, {}).setdefault(doc.path, set()).add(ref.kind)
        return MappingProxyType(
            {
                target: tuple(
                    Backlink(self.by_path[source], tuple(sorted(found))) for source, found in sorted(sources.items())
                )
                for target, sources in link_kinds_by_target.items()
            }
        )
