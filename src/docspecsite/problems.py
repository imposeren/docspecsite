"""Problem reports of the docs checks."""

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Problem:
    """A problem found in a doc or source file, as reported by ``docspecsite check``.

    It prints as ``<path>[:<line>]: <message>``; bytes of a file name that are not UTF-8 (kept in ``path`` and
    ``message`` as surrogate escapes) print as ``\\xNN``, so the line can be written to any UTF-8 stream.
    """

    path: str
    """Path of the file with the problem, relative to ``docs/`` unless ``under_docs`` is false."""
    line_number: int | None
    message: str
    under_docs: bool = True
    """Whether ``path`` is relative to ``docs/`` rather than to the repo root."""

    def __str__(self) -> str:
        """Return the problem as one line: its location, then the message."""
        where = f"docs/{self.path}" if self.under_docs else self.path
        if self.line_number is not None:
            where += f":{self.line_number}"
        line = f"{where}: {self.message}"
        return line.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")
