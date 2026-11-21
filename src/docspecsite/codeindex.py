"""The index of the project's public code elements and where their reference pages show them.

Docs: architecture/docs-tooling.md
"""

from collections.abc import Mapping
from dataclasses import dataclass

type CodeIndex = Mapping[str, CodeTarget]
"""Every public code element, by full dotted path, to the place its reference page shows it.

It is looked up exactly, with no prefix or alias resolution.
"""


@dataclass(frozen=True)
class CodeTarget:
    """Place where a code element is shown in the code reference."""

    module: str
    """Dotted path of the module whose page shows the element."""

    anchor: str | None
    """Anchor of the element on the module page, its full dotted path; None for the module itself."""
