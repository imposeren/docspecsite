"""The docs tree as read from the working tree."""

import posixpath
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from functools import cached_property
from types import MappingProxyType
from typing import ClassVar, Literal, Self, TypeGuard

import yaml

from .markdown import FrontMatterSplit, MarkdownText, split_source_lines

type RoadmapField = Literal["milestone", "priority"]

DOCS_DIR = "docs/"
"""Directory of the docs, as a prefix of repository-relative POSIX paths."""
TEMPLATES_DIR = "meta/templates/"
DOC_SUFFIX = ".md"
"""File name suffix of a doc."""
DIR_INDEX_NAME = "index.md"
"""File name of a directory's index doc."""
ROOT_LAYER = "root"
"""Layer of a doc directly in ``docs/``."""
LIST_STATUSES = ("implemented", "specified", "changed")
"""The build statuses, which say how far the code has caught up with a doc; also the values a status list may hold.

Docs: behavior/status-notes.md#requirements
"""
LAYERS_WITHOUT_BUILD_STATUS: Mapping[str, tuple[str, ...]] = MappingProxyType({"scenarios": ("behavior", "ui")})
"""Each layer without a build status, mapped to the layers whose docs its docs must name in ``related``.

A method rule, not a setting.

Docs: behavior/docs-format.md#layers-without-a-build-status
Docs: architecture/docs-tooling.md#statuses-and-status-notes
"""


@dataclass(frozen=True)
class DocStatus:
    """The ``status`` of a doc, one value or a list of them, with the doc's ``milestone`` and ``priority`` fields.

    In a layer without a build status, the build statuses, the milestone and the priority are left out, so every
    reader sees the doc as if they were not written.

    Docs: behavior/status-notes.md#requirements
    Docs: behavior/docs-format.md#layers-without-a-build-status
    Docs: architecture/docs-tooling.md#statuses-and-status-notes
    """

    ROADMAP_FIELDS: ClassVar[tuple[RoadmapField, ...]] = ("milestone", "priority")
    """Front-matter fields that place a doc on the roadmap, read with the status."""

    written_values: tuple[str, ...]
    """The values as written, in doc order, duplicates and left-out build statuses kept; empty when the field is
    missing or of the wrong shape."""

    front_matter: Mapping[str, object] = field(default_factory=dict, hash=False)
    """The doc's front matter, from which the milestone and the priority are read; empty when the status was not
    read from a doc."""

    is_written: bool = True
    """Whether the front matter has ``status`` and not all of its values were left out."""

    is_build_tracked: bool = True
    """Whether the layer of the doc's directory has a build status."""

    @classmethod
    def from_front_matter(cls, front_matter: Mapping[str, object], path: str) -> Self:
        """Read the status, milestone and priority of a doc's front matter.

        A string status is one value and a list of strings is its items; anything else (a missing field, a number, a
        mapping, a list with a non-string item) gives no values. In a layer without a build status, which the doc's
        directory decides whatever its ``layer`` field says, the build statuses, the milestone and the priority are
        left out.

        Args:
            front_matter: Parsed front matter of a doc; its ``status``, ``milestone`` and ``priority`` fields are
                read, the mapping is kept for the last two.
            path: Doc path relative to ``docs/``, whose directory gives the layer.
        """
        raw = front_matter.get("status")
        if isinstance(raw, str):
            written_values: tuple[str, ...] = (raw,)
        elif is_str_list(raw):
            written_values = tuple(raw)
        else:
            written_values = ()
        status = cls(
            written_values,
            front_matter,
            is_build_tracked=derive_dir_layer(path) not in LAYERS_WITHOUT_BUILD_STATUS,
        )
        is_written = "status" in front_matter and not (status.ignored_values and not status.values)
        return replace(status, is_written=is_written)

    @property
    def values(self) -> tuple[str, ...]:
        """The values as written, in doc order, duplicates kept; in a layer without a build status, the build statuses
        are left out."""
        return tuple(value for value in self.written_values if not self.is_ignored(value))

    @property
    def ignored_values(self) -> tuple[str, ...]:
        """Build statuses left out of :attr:`values` in a layer without a build status, in doc order; read only for the
        warning about them."""
        return tuple(value for value in self.written_values if self.is_ignored(value))

    def is_ignored(self, value: str) -> bool:
        """Return whether a written value is left out of :attr:`values`: a build status in a layer without one.

        Args:
            value: One value of the ``status`` field.
        """
        return not self.is_build_tracked and value in LIST_STATUSES

    @property
    def roadmap_front_matter(self) -> Mapping[str, object]:
        """The front matter the milestone and the priority are read from: the doc's own, empty in a layer without a
        build status."""
        return self.front_matter if self.is_build_tracked else {}

    @property
    def is_single(self) -> bool:
        """Whether the status has exactly one value, written as a string or as a one-value list."""
        return len(self.values) == 1

    @property
    def is_redirect(self) -> bool:
        """Whether the doc is a redirect doc: its status is ``redirect`` alone."""
        return self.values == ("redirect",)

    @property
    def is_deprecated(self) -> bool:
        """Whether the doc is deprecated: its status is ``deprecated`` alone."""
        return self.values == ("deprecated",)

    @property
    def is_retired(self) -> bool:
        """Whether the doc is ``deprecated`` or a ``redirect``: it no longer describes the system."""
        return self.is_deprecated or self.is_redirect

    @property
    def milestone(self) -> str | None:
        """The milestone as text; None when the doc has none, it is null, or the layer has no build status."""
        return self._read_roadmap_text("milestone")

    @property
    def priority(self) -> str | None:
        """The priority as text; None when the doc has none, it is null, or the layer has no build status."""
        return self._read_roadmap_text("priority")

    def _read_roadmap_text(self, name: RoadmapField) -> str | None:
        """Return a roadmap field's value as text; None when it is missing or null.

        Args:
            name: The roadmap field to read.
        """
        value = self.roadmap_front_matter.get(name)
        return None if value is None else str(value)

    def make_json_value(self) -> str | list[str] | None:
        """Return the JSON value of the status: a string for one value, a list for more, None for none."""
        if self.is_single:
            return self.values[0]
        return list(self.values) if self.values else None

    def format_yaml(self) -> str:
        """Return the YAML value of the field as written: ``implemented`` for one value, ``[implemented, specified]``
        for more; left-out build statuses are kept."""
        if len(self.written_values) == 1:
            return self.written_values[0]
        return f"[{', '.join(self.written_values)}]"

    def add_value(self, value: str) -> Self:
        """Return the status with one more value at the end.

        Args:
            value: Value to append.
        """
        return replace(self, written_values=(*self.written_values, value))

    def remove_value(self, value: str) -> Self:
        """Return the status without any occurrence of a value.

        Args:
            value: Value to drop.
        """
        return replace(self, written_values=tuple(kept for kept in self.written_values if kept != value))

    def remove_duplicates(self) -> Self:
        """Return the status with each of its values once, at its first place; left-out values stay as written."""
        seen: set[str] = set()
        written_values: list[str] = []
        for value in self.written_values:
            if self.is_ignored(value) or value not in seen:
                written_values.append(value)
                seen.add(value)
        return replace(self, written_values=tuple(written_values))


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
        """The front matter's ``status``, ``milestone`` and ``priority``; nothing written when the front matter did not
        load."""
        return DocStatus.from_front_matter(self.front_matter or {}, self.path)

    @property
    def is_redirect(self) -> bool:
        """Whether the doc is a redirect doc; see :func:`is_redirect`."""
        return self.status.is_redirect

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


def is_redirect(front_matter: Mapping[str, object], path: str) -> bool:
    """Return whether front matter belongs to a redirect doc (``status: redirect`` or ``[redirect]``).

    A redirect doc is kept in place of a doc that moved or went away. In a layer without a build status, build
    statuses next to ``redirect`` are left out.

    Args:
        front_matter: Parsed front matter of a doc; only its ``status`` field is read.
        path: Doc path relative to ``docs/``, whose directory gives the layer.
    """
    return DocStatus.from_front_matter(front_matter, path).is_redirect


def derive_dir_layer(path: str) -> str:
    """Return the layer of a doc's directory: its top-level directory, or ``root`` for a file directly in ``docs/``.

    Args:
        path: Doc path relative to ``docs/``.
    """
    return path.split("/")[0] if "/" in path else ROOT_LAYER


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
