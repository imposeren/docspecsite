"""Problem reports of the docs checks, and the base of the checks of single docs."""

import abc
from dataclasses import dataclass, field

from .docs import Doc


@dataclass(frozen=True, order=True)
class Problem:
    """A problem found in a doc or source file by a docs check.

    It prints as ``<path>[:<line>]: <message>``, then, when it has a hint, ``  hint: <hint>`` on the next line; bytes
    of a file name that are not UTF-8 (kept in :attr:`path`, :attr:`message` and :attr:`hint` as surrogate escapes)
    print as ``\\xNN``, so the report can be written to any UTF-8 stream.

    Docs: architecture/docs-tooling.md#problems-and-hints
    """

    path: str
    """Path of the file with the problem, relative to ``docs/`` unless :attr:`under_docs` is false."""

    line_number: int | None
    """Line of the problem in the file, from 1; None when it is about the whole file."""

    message: str
    """What is wrong, for the user."""

    under_docs: bool = True
    """Whether :attr:`path` is relative to ``docs/`` rather than to the repo root."""

    hint: str | None = field(default=None, compare=False)
    """How to fix this particular problem, for the user; None when there is no hint. Comparisons ignore it."""

    def __str__(self) -> str:
        """Return the problem line and, when the problem has a hint, the hint line."""
        return self.format_report(show_hint=True)

    def format_report(self, *, show_hint: bool) -> str:
        """Return the problem as printed: its location and message, then optionally its hint on an indented line.

        Docs: architecture/docs-tooling.md#problems-and-hints

        Args:
            show_hint: Whether to add the hint line; a problem without a hint gets none either way.
        """
        where = f"docs/{self.path}" if self.under_docs else self.path
        if self.line_number is not None:
            where += f":{self.line_number}"
        report = f"{where}: {self.message}"
        if show_hint and self.hint is not None:
            report += f"\n  hint: {self.hint}"
        return report.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")


class DocCheck(abc.ABC):
    """A check of single docs: set up once, then called for every doc."""

    @abc.abstractmethod
    def check(self, doc: Doc) -> list[Problem]:
        """Return one doc's problems from this check.

        Args:
            doc: Parsed doc whose front matter and body this check examines; the problems are located in its file.
        """
