"""Problem reports of the docs checks, and the base of the checks of single docs."""

import abc
from dataclasses import dataclass

from .docs import Doc


@dataclass(frozen=True, order=True)
class Problem:
    """A problem found in a doc or source file by a docs check.

    It prints as ``<path>[:<line>]: <message>``; bytes of a file name that are not UTF-8 (kept in :attr:`path` and
    :attr:`message` as surrogate escapes) print as ``\\xNN``, so the line can be written to any UTF-8 stream.
    """

    path: str
    """Path of the file with the problem, relative to ``docs/`` unless :attr:`under_docs` is false."""

    line_number: int | None
    """Line of the problem in the file, from 1; None when it is about the whole file."""

    message: str
    """What is wrong, for the user."""

    under_docs: bool = True
    """Whether :attr:`path` is relative to ``docs/`` rather than to the repo root."""

    def __str__(self) -> str:
        """Return the problem as one line: its location, then the message."""
        where = f"docs/{self.path}" if self.under_docs else self.path
        if self.line_number is not None:
            where += f":{self.line_number}"
        line = f"{where}: {self.message}"
        return line.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")


class DocCheck(abc.ABC):
    """A check of single docs: set up once, then called for every doc."""

    @abc.abstractmethod
    def check(self, doc: Doc) -> list[Problem]:
        """Return one doc's problems from this check.

        Args:
            doc: Parsed doc whose front matter and body this check examines; the problems are located in its file.
        """
