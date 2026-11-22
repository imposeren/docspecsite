"""Text helpers shared by several modules."""

from pathlib import Path

from .errors import DocspecsiteError

NOT_UTF8_MESSAGE = "not valid UTF-8 (%s at byte %d)"
"""Message template for text that is not valid UTF-8, filled with the decoding error's reason and byte offset."""


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
