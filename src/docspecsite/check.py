"""The checks of a repository's docs.

They cover front matter, links, code links, status notes, titles, indexes, names, reserved paths and staged deletes.

Docs: behavior/commands/check.md#requirements
Docs: architecture/docs-tooling.md
"""

import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from enum import nonmember
from functools import cached_property
from pathlib import Path, PurePosixPath
from typing import ClassVar

import griffe

from .choices import Choice
from .coderef import Codebase, CodeError
from .config import ProjectConfig
from .docs import (
    DIR_INDEX_NAME,
    DOC_SUFFIX,
    DOCS_DIR,
    LAYERS_WITHOUT_BUILD_STATUS,
    Doc,
    Layer,
    Status,
    derive_dir_layer,
    derive_doc_path,
    is_dir_index,
    is_in_templates_dir,
    is_str_list,
    is_template,
    make_dir_index_path,
)
from .docset import DocSet
from .git import Git
from .links import EMPTY_CODE_TARGET_MESSAGE, DocLinks, Ref
from .markdown import MarkdownText, SectionNote
from .problems import DocCheck, Problem
from .schema import (
    STATUS_NOTES,
    FrontMatterValidator,
    is_valid_status,
    make_status_edit_hint,
)
from .symlinks import DiskFiles, RepoFiles, SymlinkFollower, SymlinkKind
from .text import NON_UTF8_NAME_MESSAGE, UnreadableTextError, collapse_to_one_line, is_utf8_name, read_text
from .urls import RESERVED_PATH_MESSAGE, map_reserved_owners
from .vocabulary import Vocabulary


@dataclass(frozen=True)
class DocsDirectory:
    """A directory under ``docs/`` with the names of its children, as read from disk; no symlink is followed."""

    path: str
    """POSIX path of the directory relative to ``docs/``; empty for ``docs/`` itself."""

    dir_names: tuple[str, ...]
    """The names of its subdirectories that are not symlinks, sorted."""

    file_names: tuple[str, ...]
    """The names of its files that are not symlinks, sorted."""

    symlink_names: tuple[str, ...]
    """The names of its symlinks, whatever they lead to, sorted."""


class LinkCheck(DocCheck):
    """The check that a doc's links resolve, with the heading anchors of the link targets read once per run.

    Docs: behavior/commands/check.md#what-the-check-reports
    """

    # Problem texts
    INSIDE_SYMLINKED_DIRECTORY_MESSAGE = "broken link: {target} is inside a symlinked directory, not a doc"

    MISSING_HEADING_MESSAGE = 'no heading "#{anchor}" in {target}'

    MISSING_MESSAGE = "broken link: {target} does not exist"

    NOT_A_DOC_MESSAGE = '"{kind}" must be a doc (path relative to docs/): {target}'

    SYMLINKED_DIRECTORY_MESSAGE = "broken link: {target} is a symlinked directory of docs"

    SYMLINKED_DOC_MESSAGE = "broken link: {target} is a symlink, not a doc"

    UNREADABLE_HEADINGS_MESSAGE = 'cannot check heading "#{anchor}": {target}: {error}'

    # State
    heading_anchors_by_target: dict[str, set[str]]
    """The heading anchors of the link targets read so far, by target path relative to the repository root."""

    # Arguments of __init__
    root: Path
    """See :meth:`__init__`."""

    symlink_follower: SymlinkFollower
    """See :meth:`__init__`."""

    def __init__(self, root: Path, symlink_follower: SymlinkFollower) -> None:
        """Prepare the check of the links of a repository's docs.

        Args:
            root: Repository root under which link targets are looked up as files.
            symlink_follower: What the symlinks on the way to a link target lead to, looked up under ``root``.
        """
        self.root = root
        self.symlink_follower = symlink_follower
        self.heading_anchors_by_target = {}

    @property
    def repo_files(self) -> RepoFiles:
        """The files of the working tree where link targets and their symlinks are looked up."""
        return self.symlink_follower.files

    def check(self, doc: Doc) -> list[Problem]:
        """Check that the links of a doc resolve and return the problems found.

        Body and front-matter links count; a missing target or heading anchor is a problem. Link targets are looked
        up as files under :attr:`root`, and anchors among the headings of the target docs, read through
        :meth:`read_heading_anchors`; a body link to a directory under ``docs/`` is a link to its ``index.md``. A
        target reached through a symlink resolves when what the symlinks lead to is there, but never as a doc: a
        link to a symlink that leads to a doc or to a directory with a doc inside, and to a ``.md`` file inside a
        symlinked directory, is broken, each with its own message.

        Args:
            doc: Working-tree doc whose links are checked.
        """
        refs, problems = DocLinks(doc).collect_outgoing_refs()
        for ref in refs:
            message = self.describe_problem(ref)
            if message is not None:
                problems.append(Problem(doc.path, ref.line_number, message))
        return problems

    def describe_problem(self, ref: Ref) -> str | None:
        """Return the problem message of a local link; None when it resolves.

        Args:
            ref: Link of a doc, from its body or its front matter.
        """
        first_symlink_path = self.find_first_symlink(ref.target)
        if first_symlink_path is not None:
            return self.describe_symlinked_target_problem(ref, first_symlink_path)
        file = self.root / ref.target
        if not file.exists():
            return self.MISSING_MESSAGE.format(target=ref.target)
        is_doc_target = ref.target.startswith(DOCS_DIR) and ref.target.endswith(DOC_SUFFIX) and file.is_file()
        if not ref.is_body and not is_doc_target:
            return self.NOT_A_DOC_MESSAGE.format(kind=ref.kind, target=ref.target)
        if not ref.anchor:
            return None
        anchor_target = ref.target if is_doc_target else self.find_dir_index(ref.target)
        if anchor_target is None:
            return None
        try:
            heading_anchors = self.read_heading_anchors(anchor_target)
        except UnreadableTextError as error:
            return self.UNREADABLE_HEADINGS_MESSAGE.format(anchor=ref.anchor, target=anchor_target, error=error)
        if ref.anchor not in heading_anchors:
            return self.MISSING_HEADING_MESSAGE.format(anchor=ref.anchor, target=anchor_target)
        return None

    def describe_symlinked_target_problem(self, ref: Ref, first_symlink_path: str) -> str | None:
        """Return the problem message of a local link whose target is or lies below a symlink; None when it resolves.

        Its anchor is not checked: what a symlink leads to is never a doc.

        Args:
            ref: Link of a doc.
            first_symlink_path: Repo path of the first symlink on the way to the link's target: the target itself, or
                a directory it lies in (the target may then be a symlink too).
        """
        symlink_end = self.symlink_follower.follow(ref.target)
        if symlink_end.kind in (SymlinkKind.OUT_OF_REPO, SymlinkKind.NOTHING):
            return self.MISSING_MESSAGE.format(target=ref.target)
        if ref.target.startswith(DOCS_DIR):
            if first_symlink_path != ref.target and ref.target.endswith(DOC_SUFFIX):
                return self.INSIDE_SYMLINKED_DIRECTORY_MESSAGE.format(target=ref.target)
            # The target may be a symlink itself also when it lies inside a symlinked directory.
            is_symlink = first_symlink_path == ref.target or self.repo_files.is_symlink(ref.target)
            if is_symlink and symlink_end.kind is SymlinkKind.DOC:
                return self.SYMLINKED_DOC_MESSAGE.format(target=ref.target)
            if (
                is_symlink
                and symlink_end.kind is SymlinkKind.DIRECTORY
                and self.symlink_follower.has_doc_inside(ref.target)
            ):
                return self.SYMLINKED_DIRECTORY_MESSAGE.format(target=ref.target)
        if not ref.is_body:
            return self.NOT_A_DOC_MESSAGE.format(kind=ref.kind, target=ref.target)
        return None

    def find_first_symlink(self, target: str) -> str | None:
        """Return the repo path of the first symlink on the way to a link target; None when there is none.

        Args:
            target: Link target, a normalized repo path; the target itself counts as on the way.
        """
        parts = target.split("/")
        for count in range(1, len(parts) + 1):
            path = "/".join(parts[:count])
            if self.repo_files.is_symlink(path):
                return path
            if not self.repo_files.exists(path):
                return None
        return None

    def find_dir_index(self, target: str) -> str | None:
        """Return the repo path of the ``index.md`` a link to a directory under ``docs/`` leads to.

        Args:
            target: Existing link target, a normalized repo path.

        Returns:
            The index's path; None when the target is no directory under ``docs/`` (``docs/`` itself counts) or has
            no ``index.md``.
        """
        index_target = posixpath.join(target, DIR_INDEX_NAME)
        if not index_target.startswith(DOCS_DIR) or not (self.root / index_target).is_file():
            return None
        return index_target

    def read_heading_anchors(self, target: str) -> set[str]:
        """Return the heading anchors of a link target's text, read from the file once per target.

        The anchors are kept in :attr:`heading_anchors_by_target`, so each file is read once.

        Args:
            target: Path of an existing Markdown file relative to the repository root.

        Raises:
            UnreadableTextError: The file cannot be read or is not valid UTF-8.
        """
        if target not in self.heading_anchors_by_target:
            target_text = MarkdownText(read_text(self.root / target))
            self.heading_anchors_by_target[target] = target_text.collect_heading_anchors()
        return self.heading_anchors_by_target[target]


class CodeLinkCheck(DocCheck):
    """The check that a doc's code links name public elements of the loaded code."""

    # Arguments of __init__
    codebase: Codebase
    """See :meth:`__init__`."""

    def __init__(self, codebase: Codebase) -> None:
        """Prepare the check of the code links of docs.

        Args:
            codebase: Loaded project code the code links are looked up in.
        """
        self.codebase = codebase

    def check(self, doc: Doc) -> list[Problem]:
        """Check that the code links of a doc name public code elements and return the problems.

        Both ``code:`` links in the body and entries of the ``code`` front-matter field are checked.

        Args:
            doc: Working-tree doc whose code links are looked up in :attr:`codebase`.
        """
        problems: list[Problem] = []
        for ref in DocLinks(doc).collect_code_refs():
            if self.codebase.index.get(ref.dotted_path) is not None:
                continue
            if ref.is_body:
                message = f"code: link to unknown code element: {ref.dotted_path}"
            else:
                message = f'"code" entry is not a code element: {ref.dotted_path}'
            problems.append(Problem(doc.path, ref.line_number, message))
        return problems


@dataclass(frozen=True)
class StatusNote:
    """The kind of section note that gives its section a status, such as ``> **Not built yet.**``.

    Docs: behavior/status-notes.md#requirements
    """

    label: str
    """The bold text that opens the note, such as ``Not built yet.``."""

    status: str
    """The status the note gives its section, such as ``specified``."""

    @property
    def markdown(self) -> str:
        """The note line as written in a doc, such as ``> **Not built yet.**``."""
        return f"> **{self.label}**"


# A kind of section note, by what its bold label means.
type SectionNoteKind = StatusNote


class StatusNoteCheck(DocCheck):
    """The check that a doc's ``status`` and the status notes of its sections agree.

    Docs: behavior/status-notes.md#requirements
    """

    # Registries
    note_kinds_by_label: dict[str, SectionNoteKind]
    """The known kinds of section notes, by label; a note with another label is ordinary text."""

    status_note_kinds_by_status: dict[str, StatusNote]
    """The status note kinds, by the status they give."""

    def __init__(self, status_by_label: Mapping[str, str]) -> None:
        """Prepare the check of status notes.

        Args:
            status_by_label: The project's status note labels, each with the status it gives a section.
        """
        kinds = [StatusNote(label, status) for label, status in status_by_label.items()]
        self.note_kinds_by_label = {kind.label: kind for kind in kinds}
        self.status_note_kinds_by_status = {kind.status: kind for kind in kinds}

    def check(self, doc: Doc) -> list[Problem]:
        """Check that a doc's status notes agree with its ``status`` and return the problems found.

        A doc whose ``status`` the front-matter check rejects is not checked. Every heading but the title, the doc's
        first level-1 heading (``#`` or underlined with ``===``), opens a section of its own, up to the next heading
        of any level. A status note under the title is a problem and gives no status. Each section may have one status
        note, the first by line; each later one is a problem whose status still counts as given. A section status note
        is a problem in a doc with a single status, when its status is not listed, or when it gives the doc's first
        status. Each listed value after the first must be given by a status note. The full rules are the project's
        requirement DSR-46. A doc in a layer without a build status is not checked either: its status notes are
        ordinary notes.

        Docs: behavior/status-notes.md#requirements
        Docs: behavior/docs-format.md#layers-without-a-build-status

        Args:
            doc: Parsed doc whose ``status`` and body are compared; problems are located in its file.
        """
        if not doc.status.is_build_tracked or not is_valid_status(doc.status):
            return []
        return DocStatusNotes(doc, self).find_problems()


class DocStatusNotes:
    """The status notes of one doc with a valid ``status``, holding the problems of the rules they break."""

    # Found so far
    given_statuses: set[str]
    """The statuses the section status notes found so far give, later notes of a section included."""

    problems: list[Problem]
    """Problems found so far, in the order they were found."""

    status_kind_by_heading_line: dict[int, StatusNote]
    """The kind of the status note of each section found so far that has one, by the line of the section's
    heading."""

    # Arguments of __init__
    doc: Doc
    """See :meth:`__init__`."""

    note_check: StatusNoteCheck
    """See :meth:`__init__`."""

    def __init__(self, doc: Doc, note_check: StatusNoteCheck) -> None:
        """Prepare the check of a doc's status notes.

        Args:
            doc: Doc with a valid ``status`` whose body holds the notes; problems are located in its file.
            note_check: The run's check whose registries tell the kinds of notes.
        """
        self.doc = doc
        self.note_check = note_check
        self.given_statuses = set()
        self.problems = []
        self.status_kind_by_heading_line = {}

    def find_problems(self) -> list[Problem]:
        """Return the problems of the doc's status notes, as described in :meth:`StatusNoteCheck.check`.

        A check covers one doc once: call this a single time per :class:`DocStatusNotes`.
        """
        for note in self.doc.body_markdown.get_section_notes():
            kind = self.note_check.note_kinds_by_label.get(note.label)
            if isinstance(kind, StatusNote):
                self.check_status_note(note, kind)
        self.check_listed_statuses()
        return self.problems

    def check_status_note(self, note: SectionNote, kind: StatusNote) -> None:
        """Record the status a status note gives and a problem when it breaks a rule.

        A status note under the title gives no status. A later status note of a section gives only the problem of a
        second status note, but its status still counts as given.

        Args:
            note: The status note, in document order.
            kind: The status note kind of the note's label.
        """
        if note.is_title:
            message = f'{self.describe_note(kind)} right under the doc\'s title "{note.heading.first_line}"'
            self.report(message, 'set the doc\'s "status" instead', note)
            return
        self.given_statuses.add(kind.status)
        # Notes are grouped into sections by their heading's line. The first note of a section by line is its status
        # note; a later one is a problem of its own, but its status still counts as given (above).
        section_kind = self.status_kind_by_heading_line.get(note.heading.line_number)
        if section_kind is not None:
            message = (
                f'{self.describe_note(kind)} in the section "{note.heading.first_line}", '
                f"which already has the {self.describe_note(section_kind)}"
            )
            self.report(message, f'keep one status note in the section "{note.heading.first_line}"', note)
            return
        self.status_kind_by_heading_line[note.heading.line_number] = kind
        self.check_section_status(note, kind)

    def check_section_status(self, note: SectionNote, kind: StatusNote) -> None:
        """Record a problem unless a section's status note gives a listed status other than the doc's first one.

        Args:
            note: The section's status note.
            kind: The status note kind of the note's label.
        """
        status = self.doc.status
        removal_hint = f'remove the status note from the section "{note.heading.first_line}"'
        added_status = status.add_value(kind.status)
        addition_hint = make_status_edit_hint(f'add "{kind.status}" to', added_status)
        if status.is_single:
            message = f'{self.describe_note(kind)} in a doc with the single status "{status.values[0]}"'
            hint = f"{addition_hint}, or {removal_hint}" if is_valid_status(added_status) else removal_hint
            self.report(message, hint, note)
            return
        if kind.status not in status.values:
            message = f'{self.describe_note(kind)} in a doc whose "status" is "{status.format_yaml()}"'
            self.report(message, f"{addition_hint}, or {removal_hint}", note)
            return
        if kind.status != status.values[0]:
            return
        message = (
            f'{self.describe_note(kind)} gives the status the section "{note.heading.first_line}" already has '
            f'from "status: {status.format_yaml()}"'
        )
        self.report(
            message, f'remove the "{kind.label}" status note from the section "{note.heading.first_line}"', note
        )

    def check_listed_statuses(self) -> None:
        """Record a problem for each value of a status list after the first that no section status note gives."""
        status = self.doc.status
        for value in status.values[1:]:
            if value in self.given_statuses:
                continue
            kind = self.note_check.status_note_kinds_by_status[value]
            message = f'"{value}" is in "status", but no section has a "{kind.label}" status note'
            addition_hint = f'add a "{kind.markdown}" status note to a section'
            removal_hint = make_status_edit_hint(f'remove "{value}" from', status.remove_value(value))
            self.report(message, f"{addition_hint}, or {removal_hint}")

    def report(self, message: str, hint: str, note: SectionNote | None = None) -> None:
        """Record a problem of the doc.

        Args:
            message: What is wrong, for the user.
            hint: How to fix this particular case.
            note: Section note the problem is about, whose line in the doc's file it is reported on; None for line 1.
        """
        line_number = self.doc.get_file_line_number(note.line_number) if note is not None else 1
        self.problems.append(Problem(self.doc.path, line_number, message, hint=hint))

    @staticmethod
    def describe_note(kind: StatusNote) -> str:
        """Return how problems name a status note: its label and the status it gives.

        Args:
            kind: The status note kind to name.
        """
        return f'status note "{kind.label}" ("{kind.status}")'


class TitleCheck(DocCheck):
    """The check that a doc starts with its title and has no other level-1 heading.

    Docs: behavior/docs-format.md#requirements
    Docs: architecture/docs-tooling.md#statuses-and-status-notes
    """

    # Constants
    NOT_TITLE_MESSAGE = "the doc does not start with its title heading"

    def check(self, doc: Doc) -> list[Problem]:
        """Check a doc's title and return the problems found.

        The title is the doc's first level-1 heading in either style. Only blank lines may come between the front
        matter and the title: any other line before it (also an HTML comment or a link reference definition) is a
        problem on the line where that text starts; a doc without a title is a problem on that line too, or on the
        doc's first line when the body is blank. Each later level-1 heading is a problem on its line. A doc whose
        front matter is missing or does not load is not checked: it already has a problem. The full rules are the
        project's requirement DSR-52.

        Docs: behavior/docs-format.md#requirements

        Args:
            doc: Parsed doc whose body is checked; problems are located in its file, and its front matter's
                ``title`` is offered as the heading of a doc without one.
        """
        if doc.front_matter is None:
            return []
        text = doc.body_markdown
        title = text.get_title()
        problems: list[Problem] = []
        # Lines, not tokens: markdown-it makes no token of a link reference definition. A blank line has only spaces
        # and tabs, as in CommonMark; other Unicode spaces are text.
        text_line_number = next(
            (number for number, line in enumerate(text.source_lines, start=1) if line.strip(" \t")), None
        )
        if title is None:
            line_number = doc.get_file_line_number(text_line_number) if text_line_number is not None else 1
            problems.append(Problem(doc.path, line_number, self.NOT_TITLE_MESSAGE, hint=self.make_add_hint(doc)))
        elif text_line_number is not None and text_line_number != title.line_number:
            hint = f'move this text below "{title.first_line}", or remove it'
            line_number = doc.get_file_line_number(text_line_number)
            problems.append(Problem(doc.path, line_number, self.NOT_TITLE_MESSAGE, hint=hint))
        for heading in text.get_level_one_headings():
            if heading == title:
                continue
            message = f'"{heading.first_line}" is a second level-1 heading; a doc has one, its title'
            hint = f'write it as "## {heading.content}"' if heading.content else 'make it a "##" heading or remove it'
            problems.append(Problem(doc.path, doc.get_file_line_number(heading.line_number), message, hint=hint))
        return problems

    @staticmethod
    def make_add_hint(doc: Doc) -> str:
        """Return the hint for a doc without a title: add one, with the front matter's ``title`` when it has one.

        The ``title`` is put on one line, its whitespace runs collapsed to single spaces.

        Args:
            doc: Doc with loaded front matter and no title heading.
        """
        title = collapse_to_one_line(doc.front_matter_title)
        if title:
            return f'add the title "# {title}" right after the front matter'
        return 'add a "#" title heading right after the front matter'


class RelatedOwnersCheck(DocCheck):
    """The check that a doc without a build status names a current doc whose rules it gives cases for.

    Such a doc names that doc in ``related``.

    Docs: behavior/docs-format.md#layers-without-a-build-status
    Docs: behavior/commands/check.md#docs-without-a-build-status
    Docs: architecture/docs-tooling.md#statuses-and-status-notes
    """

    # Messages
    NO_CURRENT_OWNER_MESSAGE = '"related" names no {layers} doc that is neither deprecated nor redirect'
    ADD_OWNERS_HINT = 'add to "related" the {layers} docs whose rules this doc gives cases for'
    DEPRECATE_DOC_HINT = ', or write "status: deprecated" if they are all deprecated'

    # Arguments of __init__
    doc_set: DocSet
    """See :meth:`__init__`."""

    def __init__(self, doc_set: DocSet) -> None:
        """Prepare the check of the ``related`` lists of docs.

        Args:
            doc_set: The loaded docs, in which the docs that a ``related`` list names are looked up.
        """
        self.doc_set = doc_set

    def check(self, doc: Doc) -> list[Problem]:
        """Return the problems of a doc's ``related`` list: one if it names no current doc it gives cases for.

        Only a doc in a layer without a build status is checked, and only when it is current or a draft; an
        ``index.md``, a ``deprecated`` or ``redirect`` doc, a doc whose ``status`` the front-matter check rejects and
        a doc without a ``related`` list of strings are not. A ``related`` entry counts when it names a doc of the
        loaded docs in one of those layers that is neither ``deprecated`` nor ``redirect``. The problem is on the
        doc's first line; its hint offers deprecating the doc when a named doc of those layers is ``deprecated``.

        Args:
            doc: Parsed doc whose ``related`` list is checked.
        """
        owner_layers = LAYERS_WITHOUT_BUILD_STATUS.get(derive_dir_layer(doc.path))
        if owner_layers is None or is_dir_index(doc.path) or not self.is_checked(doc):
            return []
        owners = self.find_named_owners(doc, owner_layers)
        if any(not owner.status.is_retired for owner in owners):
            return []
        layers = " or ".join(owner_layers)
        hint = self.ADD_OWNERS_HINT.format(layers=layers)
        if any(owner.status.is_deprecated for owner in owners):
            hint += self.DEPRECATE_DOC_HINT
        return [Problem(doc.path, 1, self.NO_CURRENT_OWNER_MESSAGE.format(layers=layers), hint=hint)]

    @staticmethod
    def is_checked(doc: Doc) -> bool:
        """Return whether the rule applies to a doc: it has a ``related`` list of strings and is current or a draft.

        Args:
            doc: Doc in a layer without a build status.
        """
        if doc.front_matter is None or not is_str_list(doc.front_matter.get("related")):
            return False
        return not doc.status.is_written or doc.status.values == (Status.DRAFT,)

    def find_named_owners(self, doc: Doc, owner_layers: tuple[Layer, ...]) -> list[Doc]:
        """Return the docs of the given layers that a doc's ``related`` list names, in list order.

        An entry is read as the link check reads it; one that names no doc of :attr:`doc_set` is left out.

        Args:
            doc: Doc whose ``related`` list is read.
            owner_layers: Layers whose docs are kept.
        """
        owners: list[Doc] = []
        for ref in DocLinks(doc).build_front_matter_refs():
            path = derive_doc_path(ref.target) if ref.kind == "related" else None
            owner = self.doc_set.by_path.get(path) if path is not None else None
            if owner is not None and derive_dir_layer(owner.path) in owner_layers:
                owners.append(owner)
        return owners


class OptionalCheck(Choice):
    """A check that runs only when asked for by name."""

    KIND = nonmember("optional check")

    CODE = "code"
    """The references in the code's docstrings: ``Docs:`` lines, roles and ``code:`` links."""


class Checker:
    """The docs checks of a repository's working tree, with its settings, docs, vocabulary and code loaded once."""

    # Checked content
    CHILDREN_HEADING = "Children"
    """Heading of the section of an index that lists its directory's children."""

    FORBIDDEN_NAME_CHARACTERS = ("#", "%", "?")
    """Characters a file or directory name under ``docs/`` must not contain."""

    SYMLINK_ENDS_BY_KIND: ClassVar[Mapping[SymlinkKind, str]] = {
        SymlinkKind.OUT_OF_REPO: "out of the repo",
        SymlinkKind.NOTHING: "to nothing",
        SymlinkKind.DOC: "to a doc",
        SymlinkKind.DIRECTORY: "to a directory with docs",
    }
    """Where a symlink that is a problem leads, as its problem says it, by its kind."""

    # Problem texts
    KEEP_AS_REDIRECT_ADVICE = "docs are never deleted or renamed; keep the file as a redirect doc (meta/versioning.md)"

    FORBIDDEN_NAME_MESSAGE = 'name contains "#", "%" or "?", which break links to the rendered page'

    SYMLINK_MESSAGE = 'symlink to "{target}" leads {end}'

    UNKNOWN_CODE_COMPONENT_MESSAGE = (
        '"code-components" of "{key}" has an unknown component: "{component}" (add it to architecture/components.md)'
    )

    # State
    git: Git
    """The repository's git, asked for the staged changes."""

    loading_problems: list[Problem]
    """The problems found so far while loading the settings and the code."""

    # Arguments of __init__
    root: Path
    """See :meth:`__init__`."""

    def __init__(self, root: Path) -> None:
        """Prepare the checks of a repository; the settings, docs, vocabulary and code are loaded on first use.

        A ``docspecsite.toml`` that fails to load, and code that fails to load, become problems instead of errors.

        Args:
            root: Repository root whose working-tree docs, ``docspecsite.toml`` and code are checked.
        """
        self.root = root
        self.git = Git(root)
        self.loading_problems = []

    @cached_property
    def config(self) -> ProjectConfig | None:
        """The project settings; None when ``docspecsite.toml`` failed to load. Their problems are recorded."""
        config = ProjectConfig.load(self.root)
        self.loading_problems.extend(
            Problem(ProjectConfig.CONFIG_FILE, None, message, under_docs=False) for message in config.problems
        )
        if config.read_error:
            return None
        return config

    @cached_property
    def doc_set(self) -> DocSet:
        """The working-tree docs; each doc that cannot be read is left out, and recorded as a problem on it."""
        doc_set = DocSet.load(self.root)
        self.loading_problems.extend(
            Problem(path, None, str(error)) for path, error in doc_set.read_errors_by_path.items()
        )
        return doc_set

    @cached_property
    def docs_tree(self) -> list[DocsDirectory]:
        """The directories under ``docs/`` with their children's names, read from disk once.

        The index, name and symlink checks share it. The directories come sorted by path, ``docs/`` itself first.
        Symlinks are not followed, as for the docs themselves: a symlink, also one to a directory, is listed among
        the symlinks of its parent. A directory that cannot be read has an entry with no children, ``docs/`` too when
        it is missing.
        """
        docs_dir = self.root / "docs"
        tree: list[DocsDirectory] = []

        def make_path(directory: Path) -> str:
            path = directory.relative_to(docs_dir).as_posix()
            return "" if path == "." else path

        def add_unreadable(error: OSError) -> None:
            tree.append(DocsDirectory(make_path(Path(error.filename)), (), (), ()))

        # Path.walk lists a symlink to a directory among the files, and does not enter it.
        for directory, dir_names, file_names in docs_dir.walk(on_error=add_unreadable):
            symlink_names = {name for name in file_names if (directory / name).is_symlink()}
            tree.append(
                DocsDirectory(
                    make_path(directory),
                    tuple(sorted(dir_names)),
                    tuple(sorted(set(file_names) - symlink_names)),
                    tuple(sorted(symlink_names)),
                )
            )
        return sorted(tree, key=lambda docs_directory: docs_directory.path)

    @cached_property
    def symlink_follower(self) -> SymlinkFollower:
        """What the symlinks under ``docs/`` lead to, looked up in the working tree."""
        return SymlinkFollower(DiskFiles(self.root))

    @property
    def repo_files(self) -> RepoFiles:
        """The files of the working tree where the symlinks under ``docs/`` and their targets are looked up."""
        return self.symlink_follower.files

    @cached_property
    def vocabulary(self) -> Vocabulary:
        """The vocabulary the front matter is validated against."""
        return Vocabulary.load(self.root)

    @cached_property
    def front_matter_validator(self) -> FrontMatterValidator:
        """The validator of the docs' front matter, against the vocabulary and the ADR prefixes of the settings.

        Without valid settings the ADR prefixes are unknown, so ADR names are not checked.
        """
        adr_prefixes = self.config.adr_prefixes if self.config is not None else None
        return FrontMatterValidator(self.vocabulary, adr_prefixes)

    @cached_property
    def link_check(self) -> LinkCheck:
        """The check of the docs' links, with the heading anchors of each target read once for all checks."""
        return LinkCheck(self.root, self.symlink_follower)

    @cached_property
    def status_note_check(self) -> StatusNoteCheck:
        """The check of the docs' status notes, with the project's status note texts; the defaults without settings."""
        return StatusNoteCheck(self.config.status_notes if self.config is not None else STATUS_NOTES)

    @cached_property
    def codebase(self) -> Codebase | None:
        """The project code; None when the settings or the code failed to load.

        A code failure is recorded, and so is each input in the code directories that the code leaves out.
        """
        if self.config is None:
            return None
        try:
            codebase = Codebase.load(self.root, self.config)
        except (CodeError, griffe.GriffeError) as error:
            self.loading_problems.append(self.make_code_problem(error))
            return None
        self.loading_problems.extend(
            Problem(left_out.path, None, left_out.reason, under_docs=False) for left_out in codebase.left_out
        )
        return codebase

    @staticmethod
    def make_code_problem(error: CodeError | griffe.GriffeError) -> Problem:
        """Return the problem for code that cannot be loaded or read.

        Args:
            error: Failure from loading the code or reading its ``Docs:`` lines; a
                :exc:`~docspecsite.coderef.CodeError` names the file.
        """
        file = error.file if isinstance(error, CodeError) else None
        return Problem(file or "(code)", None, f"cannot load code: {error}", under_docs=False)

    def make_doc_checks(self) -> list[DocCheck]:
        """Return the checks of single docs available for the loaded settings and code.

        The front matter, the links, the status notes, the titles and the ``related`` lists of docs without a build
        status are always checked; the code links only when the code is loaded.
        """
        doc_checks: list[DocCheck] = [
            self.front_matter_validator,
            self.link_check,
            self.status_note_check,
            TitleCheck(),
            RelatedOwnersCheck(self.doc_set),
        ]
        if self.codebase is not None:
            doc_checks.append(CodeLinkCheck(self.codebase))
        return doc_checks

    def run(self, include_staged: bool, optional_checks: frozenset[OptionalCheck] = frozenset()) -> list[Problem]:
        """Run all checks of the docs and return the problems found, sorted and without duplicates, warnings last.

        Of problems that differ only in their hints, the first found is kept.

        The checks cover front matter, links and their heading anchors, status notes, titles, directory indexes, file
        names, symlinks, reserved paths, links from the code, and the settings; the full list is the project's
        requirement DSR-20. A doc whose name is not valid UTF-8 gets only the problem with its name.
        The references in the docstrings (``Docs:`` lines, roles and ``code:`` links) are checked only when
        ``optional_checks`` has :attr:`OptionalCheck.CODE`, by :meth:`check_code_references`.

        Docs: behavior/commands/check.md#requirements

        Args:
            include_staged: Also report docs staged as deleted or renamed; needs git.
            optional_checks: The optional checks to run as well.

        Raises:
            GitError: ``include_staged`` is set and the repository root is not a git working tree.
        """
        problems: list[Problem] = []
        doc_checks = self.make_doc_checks()
        for doc in self.doc_set:
            if not is_utf8_name(doc.path):
                continue  # its name is a problem of its own, and no link can name it
            for doc_check in doc_checks:
                problems.extend(doc_check.check(doc))
        problems.extend(self.check_indexes())
        problems.extend(self.check_names())
        problems.extend(self.check_symlinks())
        problems.extend(self.check_reserved_paths())
        problems.extend(self.check_code_components())
        try:
            if OptionalCheck.CODE in optional_checks:
                problems.extend(self.check_code_references())
        except (CodeError, griffe.GriffeError) as error:
            problems.append(self.make_code_problem(error))
        if include_staged:
            problems.extend(self.find_staged_deletes_renames())
        # Read last: the checks above load the settings and the code, which records their problems.
        problems.extend(self.loading_problems)
        return sorted(dict.fromkeys(problems), key=lambda p: (p.is_warning, p.path, p.line_number or 0, p.message))

    def check_code_components(self) -> list[Problem]:
        """Check that every id in the settings' ``code-components`` is in the component vocabulary; return the problems.

        Docs: behavior/configuration.md#settings
        """
        if self.config is None:
            return []
        checked = self.config.check_code_components(self.vocabulary.components)
        return [
            Problem(
                ProjectConfig.CONFIG_FILE,
                None,
                self.UNKNOWN_CODE_COMPONENT_MESSAGE.format(key=key, component=component),
                under_docs=False,
            )
            for key, component in checked.unknown
        ]

    def check_code_references(self) -> list[Problem]:
        """Check the references in the docstrings of the code; return the problems.

        These are the ``Docs:`` lines of :meth:`check_docs_lines`, and the roles and ``code:`` links that name no
        code element, found as the code reference pages find them. Without loaded code nothing is checked.

        Raises:
            CodeError: A docstring's ``Docs:`` lines cannot be located in its file.
        """
        if self.codebase is None:
            return []
        problems = self.check_docs_lines()
        for broken in self.codebase.collect_broken_references():
            message = EMPTY_CODE_TARGET_MESSAGE if broken.is_empty_target else f"unknown code element: {broken.text}"
            problems.append(Problem(broken.file, broken.line_number, message, under_docs=False))
        return problems

    def check_docs_lines(self) -> list[Problem]:
        """Check that the ``Docs:`` lines in the docstrings of the code point at existing docs; return the problems.

        A ``Docs:`` target must be one of the docs, and its anchor a heading in it; problems are reported on the code
        files. Without loaded code nothing is checked.

        Raises:
            CodeError: A docstring's ``Docs:`` lines cannot be located in its file.
        """
        if self.codebase is None:
            return []
        problems: list[Problem] = []
        for docs_line in self.codebase.collect_docs_lines():
            path, _, anchor = docs_line.target.partition("#")
            if path in self.doc_set.read_errors_by_path:
                continue  # an unreadable doc is a problem of its own
            doc = self.doc_set.by_path.get(path)
            if doc is None:
                message = f"Docs: line points to a missing doc: {path}"
            elif anchor and anchor not in self.link_check.read_heading_anchors(DOCS_DIR + path):
                message = LinkCheck.MISSING_HEADING_MESSAGE.format(anchor=anchor, target=DOCS_DIR + path)
            else:
                continue
            problems.append(Problem(docs_line.file, docs_line.line_number, message, under_docs=False))
        return problems

    def check_indexes(self) -> list[Problem]:
        """Check that every directory under ``docs/`` has an ``index.md`` listing its children; return the problems.

        Each child must be listed with a description under the ``## Children`` heading; redirect docs need no entry.
        A symlink is neither a directory that needs an index nor a child. A directory whose index cannot be read is
        not checked, and neither is a directory below ``meta/templates/``, which holds templates and no docs, nor a
        directory or child whose name is not valid UTF-8, which no link can name.
        The directories and child files come from :attr:`docs_tree`, the ``## Children`` lists from the docs.
        """
        problems: list[Problem] = []
        for directory in self.docs_tree:
            index_path = make_dir_index_path(directory.path)
            if is_template(index_path) or not is_utf8_name(directory.path):
                continue
            if index_path in self.doc_set.read_errors_by_path:
                continue  # an unreadable doc is a problem of its own
            index_doc = self.doc_set.by_path.get(index_path)
            if index_doc is None:
                problems.append(Problem(directory.path, None, "directory has no index.md"))
                continue
            # Keyed by the listed child's path relative to docs/: whether any of its entries has a description,
            # and the file line of its first entry without one.
            is_described_by_path: dict[str, bool] = {}
            first_bare_line_number_by_path: dict[str, int] = {}
            for entry in index_doc.body_markdown.list_entries(self.CHILDREN_HEADING):
                for target in entry.targets:
                    target_path = target.partition("#")[0].partition("?")[0]
                    if not target_path or ":" in target_path:
                        continue
                    listed_path = posixpath.normpath(posixpath.join(directory.path, target_path))
                    listed_path = listed_path.removesuffix("/index.md")
                    has_text = bool(entry.text)
                    is_described_by_path[listed_path] = is_described_by_path.get(listed_path, False) or has_text
                    if not has_text:
                        line_number = index_doc.get_file_line_number(entry.line_number)
                        first_bare_line_number_by_path.setdefault(listed_path, line_number)
            children = sorted(
                [*((name, True) for name in directory.dir_names), *((name, False) for name in directory.file_names)]
            )
            for name, is_dir in children:
                child_path = posixpath.join(directory.path, name)
                if not is_utf8_name(name):
                    continue
                if is_dir:
                    entry_name = f"{name}/"
                elif Path(name).suffix == DOC_SUFFIX and not is_dir_index(name):
                    child_doc = self.doc_set.by_path.get(child_path)
                    if child_doc is not None and child_doc.is_redirect:
                        continue
                    entry_name = name
                else:
                    continue
                if child_path not in is_described_by_path:
                    problems.append(Problem(index_path, None, f"child {entry_name} is not listed"))
                elif not is_described_by_path[child_path]:
                    problems.append(
                        Problem(
                            index_path,
                            first_bare_line_number_by_path[child_path],
                            f"child {entry_name} is listed without a description",
                        )
                    )
        return problems

    def check_names(self) -> list[Problem]:
        """Check that no name under ``docs/`` breaks links to the rendered page; return the problems.

        A file, directory or symlink name must be valid UTF-8 and have no ``#``, ``%`` or ``?``. Names are checked on
        disk, as :attr:`docs_tree` lists them; a directory with such a name is reported once, not again for anything
        inside it.
        """
        problems: list[Problem] = []
        reported_directories: list[PurePosixPath] = []
        paths = sorted(
            (PurePosixPath(directory.path, name), is_dir)
            for directory in self.docs_tree
            for names, is_dir in (
                (directory.dir_names, True),
                (directory.file_names, False),
                (directory.symlink_names, False),
            )
            for name in names
        )
        for path, is_dir in paths:
            messages: list[str] = []
            if not is_utf8_name(path.name):
                messages.append(NON_UTF8_NAME_MESSAGE)
            if any(character in path.name for character in self.FORBIDDEN_NAME_CHARACTERS):
                messages.append(self.FORBIDDEN_NAME_MESSAGE)
            if not messages or any(reported_dir in path.parents for reported_dir in reported_directories):
                continue
            if is_dir:
                reported_directories.append(path)
            problems.extend(Problem(path.as_posix(), None, message) for message in messages)
        return problems

    def check_symlinks(self) -> list[Problem]:
        """Check the symlinks under ``docs/`` by what they lead to; return the problems, each with its hint.

        A symlink is a problem when it leads out of the repo, to nothing, to a doc or to a directory with a doc
        inside; such a directory is one problem, on its symlink. Inside a symlinked directory with no doc inside,
        each symlink is checked in turn at its path below the directory's symlink. Symlinks inside
        ``meta/templates/`` are not checked.

        Docs: behavior/doc-symlinks.md#what-the-check-reports
        """
        problems: list[Problem] = []
        for directory in self.docs_tree:
            for name in directory.symlink_names:
                path = posixpath.join(directory.path, name)
                if not is_in_templates_dir(path):
                    problems.extend(self.check_symlink(path))
        return problems

    def check_symlink(self, path: str) -> list[Problem]:
        """Check a symlink by what it leads to, and the symlinks inside the directory it leads to; return the problems.

        Args:
            path: Path of the symlink relative to ``docs/``; it may lie below a symlinked directory.
        """
        repo_path = DOCS_DIR + path
        follower = self.symlink_follower
        symlink_end = follower.follow(repo_path)
        if symlink_end.kind is SymlinkKind.OTHER_FILE:
            return []
        if symlink_end.kind is SymlinkKind.DIRECTORY and not follower.has_doc_inside(repo_path):
            return self.check_symlinks_below(path, symlink_end.found_path)
        message = self.SYMLINK_MESSAGE.format(
            target=self.repo_files.read_link(repo_path), end=self.SYMLINK_ENDS_BY_KIND[symlink_end.kind]
        )
        return [Problem(path, None, message, hint=follower.make_hint(repo_path))]

    def check_symlinks_below(self, dir_path: str, real_dir_path: str) -> list[Problem]:
        """Check the symlinks in a directory reached through a symlink and in the directories below it.

        The walk ends even when the symlinks form a loop: a symlink is followed along its whole path below the
        directory's symlink, and one that comes back to a place passed on that path leads to nothing, so it is
        reported and not entered.

        Args:
            dir_path: Path relative to ``docs/`` of a directory with no doc inside, at or below a symlink.
            real_dir_path: Repo path of the directory itself, where its entries are listed.
        """
        problems: list[Problem] = []
        for name in self.repo_files.list_dir(real_dir_path):
            path = posixpath.join(dir_path, name)
            real_path = posixpath.join(real_dir_path, name)
            if self.repo_files.is_symlink(real_path):
                problems.extend(self.check_symlink(path))
            elif self.repo_files.is_dir(real_path):
                problems.extend(self.check_symlinks_below(path, real_path))
        return problems

    def check_reserved_paths(self) -> list[Problem]:
        """Check that no doc's page would take the URL of a generated page; return the problems.

        Docs that could not be read count too.
        """
        owners_by_path = map_reserved_owners({*self.doc_set.by_path, *self.doc_set.read_errors_by_path})
        return [Problem(path, None, RESERVED_PATH_MESSAGE % owner) for path, owner in sorted(owners_by_path.items())]

    def find_staged_deletes_renames(self) -> list[Problem]:
        """Return the problems for docs that are staged as deleted or renamed in git.

        Docs are never deleted or renamed; a doc that moves or goes away is kept as a redirect doc. A path that is a
        symlink in ``HEAD`` may be deleted or renamed.

        Raises:
            GitError: The repository root is not a git working tree.
        """
        changes = [
            change for change in self.git.list_staged_changes(DOCS_DIR) if change.is_deleted or change.is_renamed
        ]
        if not changes:
            return []
        # A symlink never was a doc, so it may be removed or renamed.
        tree = {file.path: file.entry for file in self.git.list_tree("HEAD", [DOCS_DIR])}
        problems: list[Problem] = []
        for change in changes:
            if tree[change.old_path].is_symlink:
                continue
            old = change.old_path.removeprefix(DOCS_DIR)
            if change.is_deleted:
                problems.append(Problem(old, None, f"deleted; {self.KEEP_AS_REDIRECT_ADVICE}"))
            elif change.is_renamed:
                problems.append(Problem(old, None, f"renamed to {change.new_path}; {self.KEEP_AS_REDIRECT_ADVICE}"))
        return problems
