"""The docs tree as read from the working tree."""

import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from typing import Self, TypeGuard

import yaml

from .markdown import FrontMatterSplit, MarkdownText, split_source_lines

DOCS_DIR = "docs/"
"""Directory of the docs, as a prefix of repository-relative POSIX paths."""
TEMPLATES_DIR = "meta/templates/"
DOC_SUFFIX = ".md"
"""File name suffix of a doc."""
DIR_INDEX_NAME = "index.md"
"""File name of a directory's index doc."""


@dataclass(frozen=True)
class DocStatus:
    """The ``status`` of a doc: one value, or a list of them (for example ``[implemented, specified]``).

    Docs: behavior/status-notes.md#requirements
    Docs: architecture/docs-tooling.md#statuses-and-status-notes
    """

    values: tuple[str, ...]
    """The values as written, in doc order, duplicates kept; empty when the field is missing or of the wrong shape."""

    @classmethod
    def from_front_matter(cls, front_matter: Mapping[str, object]) -> Self:
        """Read the status of front matter.

        A string is one value and a list of strings is its items; anything else (a missing field, a number, a
        mapping, a list with a non-string item) gives no values.

        Args:
            front_matter: Parsed front matter of a doc; only its ``status`` field is read.
        """
        raw = front_matter.get("status")
        if isinstance(raw, str):
            return cls((raw,))
        if is_str_list(raw):
            return cls(tuple(raw))
        return cls(())

    @property
    def is_single(self) -> bool:
        """Whether the status has exactly one value, written as a string or as a one-value list."""
        return len(self.values) == 1

    def add_value(self, value: str) -> Self:
        """Return the status with one more value at the end.

        Args:
            value: Value to append.
        """
        return type(self)((*self.values, value))

    def remove_value(self, value: str) -> Self:
        """Return the status without any occurrence of a value.

        Args:
            value: Value to drop.
        """
        return type(self)(tuple(kept_value for kept_value in self.values if kept_value != value))

    def remove_duplicates(self) -> Self:
        """Return the status with each value once, at its first place."""
        return type(self)(tuple(dict.fromkeys(self.values)))


@dataclass(frozen=True)
class Doc:
    """A doc read from ``docs/``, with its front matter and body."""

    path: str
    """POSIX path of the doc, relative to ``docs/``."""

    front_matter: dict[str, object] | None
    """Front matter; ``None`` exactly when :attr:`error` is set."""

    body: str
    """Markdown text of the doc after its front matter; the whole text when it has none."""

    body_line: int
    """1-based line of the file where :attr:`body` starts."""

    error: str | None
    """Why the front matter cannot be read, for the user; None when it is valid."""

    @property
    def front_matter_title(self) -> str | None:
        """The front matter's ``title`` as text; None when it has none or the front matter did not load."""
        title = (self.front_matter or {}).get("title")
        return str(title) if title is not None else None

    @property
    def title(self) -> str:
        """The front matter's ``title``; the path when there is none."""
        title = self.front_matter_title
        return title if title is not None else self.path

    def get_file_line_number(self, body_line_number: int) -> int:
        """Return the 1-based line number in the doc's file of a line of its body.

        Args:
            body_line_number: 1-based line number within :attr:`body`, such as one that a
                :class:`~docspecsite.markdown.MarkdownText` of the body gives.
        """
        return self.body_line + body_line_number - 1

    @cached_property
    def body_markdown(self) -> MarkdownText:
        """The body parsed as Markdown on first use, then shared by everything that reads it, such as the checks.

        The parsed tokens live as long as the doc, so this is meant for the latest docs, such as the working tree's.
        """
        return MarkdownText(self.body)

    @cached_property
    def status(self) -> DocStatus:
        """The front matter's ``status``; no values when the front matter did not load."""
        return DocStatus.from_front_matter(self.front_matter or {})

    @property
    def is_redirect(self) -> bool:
        """Whether the doc is a redirect doc; see :func:`is_redirect`."""
        return is_redirect(self.front_matter or {})

    @classmethod
    def parse(cls, path: str, text: str, split: FrontMatterSplit | None = None) -> Self:
        """Split the text of a doc into front matter and body.

        Unreadable front matter is not raised: :attr:`front_matter` is None and :attr:`error` says why.

        Args:
            path: Doc path relative to ``docs/``; only stored in :attr:`path`, nothing is read from it.
            text: Whole file text, front matter included; :attr:`body_line` keeps the body's line numbers relative
                to it.
            split: The front matter's YAML and the body's line, as
                :meth:`docspecsite.markdown.MarkdownText.split_front_matter` gives them, when already known (kept in
                the body cache); the text is then not parsed as Markdown.
        """
        source, body_line = split if split is not None else MarkdownText(text).split_front_matter()
        body = "\n".join(split_source_lines(text)[body_line - 1 :])
        if source is None:
            return cls(path, None, body, body_line, "no front matter")
        try:
            front_matter = yaml.safe_load(source)
        except (yaml.YAMLError, ValueError) as exc:  # ValueError: impossible dates like 2026-02-31
            message = " ".join(str(exc).split())
            return cls(path, None, body, body_line, f"front matter is not valid YAML: {message}")
        if not isinstance(front_matter, dict):
            return cls(path, None, body, body_line, "front matter is not a mapping")
        return cls(path, {str(k): v for k, v in front_matter.items()}, body, body_line, None)


def is_redirect(front_matter: Mapping[str, object]) -> bool:
    """Return whether front matter belongs to a redirect doc (``status: redirect`` or ``[redirect]``).

    A redirect doc is kept in place of a doc that moved or went away.

    Args:
        front_matter: Parsed front matter of a doc; only its ``status`` field is read.
    """
    return DocStatus.from_front_matter(front_matter).values == ("redirect",)


def make_string_tuple(value: object, *, strings_only: bool = False) -> tuple[str, ...]:
    """Return the items of a list value as strings.

    The result is empty when the value is not a list.

    Args:
        value: Parsed front-matter or TOML setting value expected to be a list, such as the ``tags`` field or the
            ``code-dirs`` setting.
        strings_only: Whether to skip items that are not strings instead of converting them with ``str``.
    """
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if not strings_only or isinstance(item, str))


def is_str_list(value: object) -> TypeGuard[list[str]]:
    """Return whether a value is a list whose items are all strings; an empty list counts.

    Args:
        value: Parsed front-matter or TOML setting value of any type, such as ``components`` or ``code-dirs``.
    """
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def derive_doc_path(repo_path: str) -> str | None:
    """Return the path relative to ``docs/`` of a repo path under ``docs/``; None for a path outside it.

    Args:
        repo_path: Path relative to the repository root, such as a link target.
    """
    return repo_path.removeprefix(DOCS_DIR) if repo_path.startswith(DOCS_DIR) else None


def is_in_templates_dir(path: str) -> bool:
    """Return whether a path lies in the doc templates' directory ``meta/templates/``, its ``index.md`` included.

    Args:
        path: Path relative to ``docs/``.
    """
    return path.startswith(TEMPLATES_DIR)


def is_template(path: str) -> bool:
    """Return whether a path is a template rather than a doc.

    Files in ``meta/templates/`` are templates, except its ``index.md``.

    Args:
        path: Path relative to ``docs/`` to classify; any file, not only Markdown (assets in ``meta/templates/`` count
            as templates too).
    """
    return is_in_templates_dir(path) and path != f"{TEMPLATES_DIR}index.md"


def is_doc(path: str, *, is_symlink: bool, is_under_symlinked_dir: bool) -> bool:
    """Return whether a path under ``docs/`` is a doc: a regular ``.md`` file that is not a template.

    A symlink is never a doc, and neither is anything reached through a symlinked directory, whatever they lead to.

    Docs: architecture/docs-tooling.md#history-model
    Docs: behavior/doc-symlinks.md#requirements

    Args:
        path: Path relative to ``docs/`` of any file, from the working tree or a revision's tree.
        is_symlink: The file at the path is a symlink.
        is_under_symlinked_dir: A directory between the path and ``docs/`` is a symlink.
    """
    return path.endswith(DOC_SUFFIX) and not is_template(path) and not is_symlink and not is_under_symlinked_dir


def make_dir_index_path(directory: str) -> str:
    """Return the doc path of a directory's index doc; ``index.md`` for the docs root.

    Args:
        directory: Directory relative to ``docs/`` whose index is wanted; empty for ``docs/`` itself.
    """
    return posixpath.join(directory, DIR_INDEX_NAME)


def is_dir_index(path: str) -> bool:
    """Return whether a doc is the index doc of its directory.

    Args:
        path: Doc path relative to ``docs/``, or a bare file name.
    """
    return posixpath.basename(path) == DIR_INDEX_NAME
