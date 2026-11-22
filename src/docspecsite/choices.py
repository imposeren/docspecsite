"""Named options that a command line selects in a comma-separated list.

Docs: behavior/commands.md
"""

from enum import StrEnum, nonmember
from typing import Self


class Choice(StrEnum):
    """A named option that is selected by name, in a list of names separated by commas."""

    KIND = nonmember("choice")
    """What one option is called in messages, such as ``part``; each subclass sets its own."""

    @classmethod
    def parse_list(cls, text: str) -> frozenset[Self]:
        """Return the options named in a comma-separated list.

        Args:
            text: Option names separated by commas, without spaces, e.g. ``docs,code``.

        Raises:
            ValueError: The text is empty, or a name is not an option (a space-padded name is not); the message lists
                the available options.
        """
        available = f"(available: {', '.join(cls)})"
        if not text:
            raise ValueError(f"no {cls.KIND}s given {available}")
        names = text.split(",")
        for name in names:
            if name not in cls:
                raise ValueError(f"unknown {cls.KIND}: {name!r} {available}")
        return frozenset(cls(name) for name in names)
