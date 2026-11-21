"""The parts of the site that a build can produce.

Docs: architecture/docs-tooling.md
"""

from enum import StrEnum


class Part(StrEnum):
    """A part of the site that can be built on its own."""

    DOCS = "docs"
    """The docs pages, the index pages and ``llms.txt``."""

    CODE = "code"
    """The code reference pages."""


def parse_parts(text: str) -> frozenset[Part]:
    """Return the parts named in a comma-separated list.

    Args:
        text: Part names separated by commas, without spaces, e.g. ``docs,code``.

    Raises:
        ValueError: The text is empty, or a name is not a part (a space-padded name is not).
    """
    if not text:
        raise ValueError("no parts given")
    names = text.split(",")
    for name in names:
        if name not in Part:
            raise ValueError(f"unknown part: {name!r}")
    return frozenset(Part(name) for name in names)
