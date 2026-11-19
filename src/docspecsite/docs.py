"""The docs tree as read from the working tree."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from .markdown import split_front_matter

DOCS = "docs/"
"""Directory of the docs, as a prefix of repository-relative POSIX paths."""
TEMPLATES_DIR = "meta/templates/"


@dataclass(frozen=True)
class Doc:
    """A doc read from ``docs/``, with its front matter and body."""

    path: str
    """POSIX path of the doc, relative to ``docs/``."""
    front_matter: dict[str, object] | None
    """Front matter; ``None`` exactly when ``error`` is set."""
    body: str
    body_line: int
    """1-based line of the file where ``body`` starts."""
    error: str | None


def read_text(file: Path) -> str:
    """Return the text of a file, with a leading byte-order mark removed.

    Args:
        file: UTF-8 file to read, such as a doc, the vocabulary or ``docspecsite.toml``.
    """
    return file.read_text(encoding="utf-8-sig")


def make_string_tuple(value: object, *, strings_only: bool = False) -> tuple[str, ...]:
    """Return the items of a list value as strings.

    The result is empty when the value is not a list.

    Args:
        value: Parsed front-matter or TOML value expected to be a list, such as ``tags``, ``code`` or
            ``code-dirs``.
        strings_only: Leave out the items that are not strings, instead of converting them with ``str``.
    """
    if not isinstance(value, list):
        return ()
    if strings_only:
        return tuple(item for item in value if isinstance(item, str))
    return tuple(str(item) for item in value)


def parse_doc(path: str, text: str) -> Doc:
    """Split the text of a doc into front matter and body.

    Unreadable front matter is not raised: ``front_matter`` is None and ``error`` says why.

    Args:
        path: Doc path relative to ``docs/``; only stored in ``Doc.path``, nothing is read from it.
        text: Whole file text, front matter included; ``body_line`` keeps the body's line numbers relative to it.
    """
    source, body_line = split_front_matter(text)
    body = "\n".join(text.splitlines()[body_line - 1 :])
    if source is None:
        return Doc(path, None, body, body_line, "no front matter")
    try:
        front_matter = yaml.safe_load(source)
    except (yaml.YAMLError, ValueError) as exc:  # ValueError: impossible dates like 2026-02-31
        message = " ".join(str(exc).split())
        return Doc(path, None, body, body_line, f"front matter is not valid YAML: {message}")
    if not isinstance(front_matter, dict):
        return Doc(path, None, body, body_line, "front matter is not a mapping")
    return Doc(path, {str(k): v for k, v in front_matter.items()}, body, body_line, None)


def is_template(path: str) -> bool:
    """Return whether a path is a template rather than a doc.

    Files in ``meta/templates/`` are templates, except its ``index.md``.

    Args:
        path: Path relative to ``docs/`` to classify; any file, not only Markdown (assets in ``meta/templates/`` count
            as templates too).
    """
    return path.startswith(TEMPLATES_DIR) and path != f"{TEMPLATES_DIR}index.md"
