"""The index of the project's public code elements and where their reference pages show them.

Docs: architecture/docs-tooling.md
"""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class CodeTarget:
    """Place where a code element is shown: its module page and, for a member, its anchor (the full dotted path)."""

    module: str
    anchor: str | None


@dataclass(frozen=True)
class CodeIndex:
    """Every public code element, by dotted path."""

    targets: Mapping[str, CodeTarget]

    def find(self, dotted_path: str) -> CodeTarget | None:
        """Return the ``CodeTarget`` of a code element, or None if there is none.

        Args:
            dotted_path: Full dotted path to look up, such as ``pkg.module.Class.method``; matched exactly, with no
                prefix or alias resolution.
        """
        return self.targets.get(dotted_path)

    @classmethod
    def make_empty(cls) -> CodeIndex:
        """Return an index without code elements."""
        return cls({})
