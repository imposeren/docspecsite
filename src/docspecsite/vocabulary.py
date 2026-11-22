"""The components and milestones that docs may use, read from the docs themselves.

Docs: meta/vocabulary.md
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from .markdown import MarkdownText
from .text import UnreadableTextError, read_text


@dataclass(frozen=True)
class Vocabulary:
    """Component ids and milestones that docs may use in their front matter."""

    components: frozenset[str]
    """Component ids, the shared ones and the project's own."""

    milestones: tuple[str, ...]
    """Milestone names, in roadmap order."""

    @classmethod
    def parse(cls, read: Callable[[str], str | None]) -> Self:
        """Return the vocabulary found in the docs.

        Args:
            read: Gives the text of a doc by its path relative to ``docs/``, or None when missing; called for
                ``meta/vocabulary.md``, ``architecture/components.md`` and ``roadmap.md``. Lets the check read the
                working tree and the build read git history.
        """
        shared_components = cls.extract_codes(read("meta/vocabulary.md"), "Components")
        project_components = cls.extract_codes(read("architecture/components.md"))
        return cls(
            components=frozenset(shared_components + project_components),
            milestones=tuple(cls.extract_codes(read("roadmap.md"))),
        )

    @classmethod
    def load(cls, root: Path) -> Self:
        """Return the vocabulary found in the docs of a repository.

        A vocabulary doc that cannot be read or is not valid UTF-8 counts as missing.

        Args:
            root: Repository root whose working-tree ``docs/`` holds the vocabulary docs.
        """

        def read(path: str) -> str | None:
            file = root / "docs" / path
            if not file.is_file():
                return None
            try:
                return read_text(file)
            except UnreadableTextError:
                return None

        return cls.parse(read)

    @staticmethod
    def extract_codes(text: str | None, section: str | None = None) -> list[str]:
        """Return the inline-code values of the first column of the tables in a doc.

        The result is empty when the text is None.

        Args:
            text: Markdown source of the vocabulary doc to scan; None (doc missing) gives no codes.
            section: Heading text limiting the scan to the tables under that heading; None scans every table.
        """
        return MarkdownText(text).extract_table_first_column_codes(section) if text is not None else []
