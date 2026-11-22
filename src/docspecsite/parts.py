"""The parts of the site that a build can produce.

Docs: architecture/docs-tooling.md
"""

from enum import nonmember

from .choices import Choice


class Part(Choice):
    """A part of the site that can be built on its own."""

    KIND = nonmember("part")

    DOCS = "docs"
    """The docs pages, the index pages and ``llms.txt``."""

    CODE = "code"
    """The code reference pages."""
