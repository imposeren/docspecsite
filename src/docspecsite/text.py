"""Text helpers shared by several modules."""

import difflib
from pathlib import Path

from .errors import DocspecsiteError

NOT_UTF8_MESSAGE = "not valid UTF-8 (%s at byte %d)"
"""Message template for text that is not valid UTF-8, filled with the decoding error's reason and byte offset."""

NON_UTF8_NAME_MESSAGE = "name is not valid UTF-8, which breaks links to the rendered page"


class UnreadableTextError(DocspecsiteError):
    """Error for a text file that cannot be read or is not valid UTF-8."""


def decode_text(data: bytes) -> str:
    """Return UTF-8 bytes as text, with a leading byte-order mark removed.

    Args:
        data: Contents of a text file, such as a doc from the working tree or a git blob.

    Raises:
        UnicodeDecodeError: The data is not valid UTF-8; its ``start`` attribute counts from the first byte of
            ``data``, a byte-order mark included.
    """
    return data.decode("utf-8").removeprefix("\ufeff")


def is_utf8_name(name: str) -> bool:
    """Return whether a file name or path read from disk or from git is valid UTF-8.

    Docs: behavior/commands/index.md#input-that-cannot-be-used

    Args:
        name: Name as Python decodes it from file-system bytes, each byte that is not UTF-8 kept as a surrogate escape.
    """
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def show_name_bytes(text: str) -> str:
    """Return text for printing, with each byte of a file name that is not UTF-8 shown as ``\\x`` and two hex digits.

    Args:
        text: Text that may hold file names as Python decodes them, bytes that are not UTF-8 kept as surrogate
            escapes, such as a problem report or a warning.
    """
    return text.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")


def read_text(file: Path) -> str:
    """Return the text of a file, with a leading byte-order mark removed.

    Args:
        file: UTF-8 file to read, such as a doc or the vocabulary.

    Raises:
        UnreadableTextError: The file cannot be read or is not valid UTF-8; the message says why, without the path.
    """
    try:
        return decode_text(file.read_bytes())
    except UnicodeDecodeError as error:
        raise UnreadableTextError(NOT_UTF8_MESSAGE, error.reason, error.start) from error
    except OSError as error:
        raise UnreadableTextError("cannot be read: %s", error.strerror or error) from error


def collapse_to_one_line(value: object) -> str:
    """Return a value as text with whitespace runs collapsed to single spaces.

    The result is empty for None.

    Args:
        value: Text to print on one line, such as a front-matter title, summary or status or the site heading;
            non-strings are converted with ``str``.
    """
    return " ".join(str(value).split()) if value is not None else ""


def make_unified_diff(old: str, new: str) -> list[str]:
    """Return the lines of the unified diff between two texts, with 3 lines of context and without its file headers.

    It is the diff text of a version's diff page, which every site renderer shows.

    Docs: architecture/site.md#the-renderer-seam

    Args:
        old: Text of the previous version, the ``-`` side of the diff.
        new: Text of the version the diff page is for, the ``+`` side.
    """
    return list(difflib.unified_diff(old.splitlines(), new.splitlines(), n=3, lineterm=""))[2:]
