"""Text helpers shared by several modules."""

from pathlib import Path


def read_text(file: Path) -> str:
    """Return the text of a file, with a leading byte-order mark removed.

    Args:
        file: UTF-8 file to read, such as a doc, the vocabulary or ``docspecsite.toml``.
    """
    return file.read_text(encoding="utf-8-sig")


def collapse_to_one_line(value: object) -> str:
    """Return a value as text with whitespace runs collapsed to single spaces.

    The result is empty for None.

    Args:
        value: Text to print on one line, such as a front-matter title, summary or status or the site heading;
            non-strings are converted with ``str``.
    """
    return " ".join(str(value).split()) if value is not None else ""
