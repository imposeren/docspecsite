"""The components and milestones that docs may use, read from the docs themselves.

Docs: meta/vocabulary.md
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .docs import read_text
from .markdown import extract_table_first_column_codes


@dataclass(frozen=True)
class Vocabulary:
    """Component ids and milestones that docs may use in their front matter."""

    components: frozenset[str]
    milestones: tuple[str, ...]
    """Milestone names, in roadmap order."""


def extract_codes(text: str | None, section: str | None = None) -> list[str]:
    """Return the inline-code values of the first column of the tables in a doc.

    The result is empty when the text is None.

    Args:
        text: Markdown source of the vocabulary doc to scan; None (doc missing) gives no codes.
        section: Heading text limiting the scan to the tables under that heading; None scans every table.
    """
    return extract_table_first_column_codes(text, section) if text is not None else []


def parse_vocabulary(read: Callable[[str], str | None]) -> Vocabulary:
    """Return the vocabulary found in the docs.

    Args:
        read: Gives the text of a doc by its path relative to ``docs/``, or None when missing; called for
            ``meta/vocabulary.md``, ``architecture/components.md`` and ``roadmap.md``. Lets the check read the working
            tree and the build read git history.
    """
    shared = extract_codes(read("meta/vocabulary.md"), "Components")
    project = extract_codes(read("architecture/components.md"))
    return Vocabulary(
        components=frozenset(shared + project),
        milestones=tuple(extract_codes(read("roadmap.md"))),
    )


def load_vocabulary(root: Path) -> Vocabulary:
    """Return the vocabulary found in the docs of a repository.

    Args:
        root: Repository root whose working-tree ``docs/`` holds the vocabulary docs.
    """

    def read(path: str) -> str | None:
        file = root / "docs" / path
        return read_text(file) if file.is_file() else None

    return parse_vocabulary(read)
