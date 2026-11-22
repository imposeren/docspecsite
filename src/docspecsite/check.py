"""The checks of a repository's docs.

They cover front matter, links, code links, status notes, titles, indexes, names, reserved paths and staged deletes.

Docs: behavior/requirements.md#checks
Docs: architecture/docs-tooling.md
"""

import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from enum import nonmember
from functools import cached_property
from pathlib import Path

import griffe

from .choices import Choice
from .coderef import Codebase, CodeError
from .config import ProjectConfig
from .docs import DOCS_DIR, Doc, is_dir_index, make_dir_index_path
from .docset import DocSet
from .git import Git
from .links import DocLinks
from .markdown import MarkdownText, SectionNote
from .problems import DocCheck, Problem
from .schema import (
    STATUS_NOTES,
    FrontMatterValidator,
    format_status_yaml,
    is_valid_status,
    make_status_edit_hint,
)
from .text import UnreadableTextError, collapse_to_one_line, read_text
from .urls import RESERVED_PATH_MESSAGE, map_reserved_owners
from .vocabulary import Vocabulary

# A directory under docs/: its path, and the names of its subdirectories and of its other children, each sorted.
type DocsDirectory = tuple[Path, list[str], list[str]]


class LinkCheck(DocCheck):
    """The check that a doc's links resolve, with the heading anchors of the link targets read once per run."""

    # State
    heading_anchors_by_target: dict[str, set[str]]
    """The heading anchors of the link targets read so far, by target path relative to the repository root."""

    # Arguments of __init__
    root: Path
    """See :meth:`__init__`."""

    def __init__(self, root: Path) -> None:
        """Prepare the check of the links of a repository's docs.

        Args:
            root: Repository root under which link targets are looked up as files.
        """
        self.root = root
        self.heading_anchors_by_target = {}

    def check(self, doc: Doc) -> list[Problem]:
        """Check that the links of a doc resolve and return the problems found.

        Body and front-matter links count; a missing target or heading anchor is a problem. Link targets are looked up
        as files under :attr:`root`, and anchors are looked up among the headings of the target docs through
        :meth:`read_heading_anchors`.

        Args:
            doc: Working-tree doc whose links are checked.
        """
        refs, problems = DocLinks(doc).collect_outgoing_refs()
        for ref in refs:
            file = self.root / ref.target
            is_existing_doc_target = ref.target.startswith(DOCS_DIR) and ref.target.endswith(".md") and file.is_file()
            if not file.exists():
                problems.append(Problem(doc.path, ref.line_number, f"broken link: {ref.target} does not exist"))
            elif ref.kind != "body" and not is_existing_doc_target:
                problems.append(
                    Problem(
                        doc.path,
                        ref.line_number,
                        f'"{ref.kind}" must be a doc (path relative to docs/): {ref.target}',
                    )
                )
            elif ref.anchor and is_existing_doc_target:
                try:
                    heading_anchors = self.read_heading_anchors(ref.target)
                except UnreadableTextError as error:
                    message = f'cannot check heading "#{ref.anchor}": {ref.target}: {error}'
                    problems.append(Problem(doc.path, ref.line_number, message))
                    continue
                if ref.anchor not in heading_anchors:
                    problems.append(Problem(doc.path, ref.line_number, f'no heading "#{ref.anchor}" in {ref.target}'))
        return problems

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
            if ref.kind == "body":
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
        requirement DS-46.

        Docs: behavior/status-notes.md#requirements

        Args:
            doc: Parsed doc whose ``status`` and body are compared; problems are located in its file.
        """
        if not is_valid_status(doc.status):
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
        for note in MarkdownText(self.doc.body).get_section_notes():
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
            message = f'{self.describe_note(kind)} in a doc whose "status" is "{format_status_yaml(status)}"'
            self.report(message, f"{addition_hint}, or {removal_hint}", note)
            return
        if kind.status != status.values[0]:
            return
        message = (
            f'{self.describe_note(kind)} gives the status the section "{note.heading.first_line}" already has '
            f'from "status: {format_status_yaml(status)}"'
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

    Docs: behavior/requirements.md#checks
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
        project's requirement DS-52.

        Docs: behavior/requirements.md#checks

        Args:
            doc: Parsed doc whose body is checked; problems are located in its file, and its front matter's
                ``title`` is offered as the heading of a doc without one.
        """
        if doc.front_matter is None:
            return []
        text = MarkdownText(doc.body)
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

    FORBIDDEN_NAME_CHARACTERS = ("#", "%")
    """Characters a file or directory name under ``docs/`` must not contain."""

    # Problem texts
    KEEP_AS_REDIRECT_ADVICE = "docs are never deleted or renamed; keep the file as a redirect doc (meta/versioning.md)"

    FORBIDDEN_NAME_MESSAGE = 'name contains "#" or "%", which break links to the rendered page'

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

        The index and name checks share it. The directories come sorted by path, ``docs/`` itself first. Symlinks are
        not followed, as for the docs themselves: a symlink to a directory counts as a subdirectory of its parent and
        has an entry with no children; so does a directory that cannot be read, ``docs/`` too when it is missing.
        """
        tree: list[DocsDirectory] = []

        def add_unreadable(error: OSError) -> None:
            tree.append((Path(error.filename), [], []))

        for directory, dir_names, file_names in (self.root / "docs").walk(on_error=add_unreadable):
            dir_links = [name for name in file_names if (directory / name).is_dir()]
            tree.extend((directory / name, [], []) for name in dir_links)
            tree.append(
                (
                    directory,
                    sorted([*dir_names, *dir_links]),
                    sorted(name for name in file_names if name not in dir_links),
                )
            )
        return sorted(tree)

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
        return LinkCheck(self.root)

    @cached_property
    def status_note_check(self) -> StatusNoteCheck:
        """The check of the docs' status notes, with the project's status note texts; the defaults without settings."""
        return StatusNoteCheck(self.config.status_notes if self.config is not None else STATUS_NOTES)

    @cached_property
    def codebase(self) -> Codebase | None:
        """The project code; None when the settings or the code failed to load. A code failure is recorded."""
        if self.config is None:
            return None
        try:
            return Codebase.load(self.root, self.config)
        except (CodeError, griffe.GriffeError) as error:
            self.loading_problems.append(self.make_code_problem(error))
            return None

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

        The front matter, the links, the status notes and the titles are always checked; the code links only when the
        code is loaded.
        """
        doc_checks: list[DocCheck] = [
            self.front_matter_validator,
            self.link_check,
            self.status_note_check,
            TitleCheck(),
        ]
        if self.codebase is not None:
            doc_checks.append(CodeLinkCheck(self.codebase))
        return doc_checks

    def run(self, include_staged: bool, optional_checks: frozenset[OptionalCheck] = frozenset()) -> list[Problem]:
        """Run all checks of the docs and return the problems found, sorted and without duplicates.

        Of problems that differ only in their hints, the first found is kept.

        The checks cover front matter, links and their heading anchors, status notes, titles, directory indexes, file
        names, reserved paths, links from the code, and the settings; the full list is the project's requirement DS-20.
        The references in the docstrings (``Docs:`` lines, roles and ``code:`` links) are checked only when
        ``optional_checks`` has :attr:`OptionalCheck.CODE`, by :meth:`check_code_references`.

        Docs: behavior/requirements.md#checks

        Args:
            include_staged: Also report docs staged as deleted or renamed; needs git.
            optional_checks: The optional checks to run as well.

        Raises:
            GitError: ``include_staged`` is set and the repository root is not a git working tree.
        """
        problems: list[Problem] = []
        doc_checks = self.make_doc_checks()
        for doc in self.doc_set:
            for doc_check in doc_checks:
                problems.extend(doc_check.check(doc))
        problems.extend(self.check_indexes())
        problems.extend(self.check_names())
        problems.extend(self.check_reserved_paths())
        try:
            if OptionalCheck.CODE in optional_checks:
                problems.extend(self.check_code_references())
        except (CodeError, griffe.GriffeError) as error:
            problems.append(self.make_code_problem(error))
        if include_staged:
            problems.extend(self.find_staged_deletes_renames())
        # Read last: the checks above load the settings and the code, which records their problems.
        problems.extend(self.loading_problems)
        return sorted(dict.fromkeys(problems), key=lambda p: (p.path, p.line_number or 0, p.message))

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
            message = f"unknown code element: {broken.text}"
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
                message = f'no heading "#{anchor}" in docs/{path}'
            else:
                continue
            problems.append(Problem(docs_line.file, docs_line.line_number, message, under_docs=False))
        return problems

    def check_indexes(self) -> list[Problem]:
        """Check that every directory under ``docs/`` has an ``index.md`` listing its children; return the problems.

        Each child must be listed with a description under the ``## Children`` heading; redirect docs need no entry.
        A directory whose index cannot be read is not checked.
        The directories and child files come from :attr:`docs_tree`, the ``## Children`` lists from the docs.
        """
        docs_dir = self.root / "docs"
        problems: list[Problem] = []
        for directory, dir_names, file_names in self.docs_tree:
            directory_path = directory.relative_to(docs_dir).as_posix()
            directory_path = "" if directory_path == "." else directory_path
            index_path = make_dir_index_path(directory_path)
            if index_path in self.doc_set.read_errors_by_path:
                continue  # an unreadable doc is a problem of its own
            index_doc = self.doc_set.by_path.get(index_path)
            if index_doc is None:
                problems.append(Problem(directory_path, None, "directory has no index.md"))
                continue
            # Keyed by the listed child's path relative to docs/: whether any of its entries has a description,
            # and the file line of its first entry without one.
            is_described_by_path: dict[str, bool] = {}
            first_bare_line_number_by_path: dict[str, int] = {}
            for entry in MarkdownText(index_doc.body).list_entries(self.CHILDREN_HEADING):
                for target in entry.targets:
                    target_path = target.partition("#")[0].partition("?")[0]
                    if not target_path or ":" in target_path:
                        continue
                    listed_path = posixpath.normpath(posixpath.join(directory_path, target_path))
                    listed_path = listed_path.removesuffix("/index.md")
                    has_text = bool(entry.text)
                    is_described_by_path[listed_path] = is_described_by_path.get(listed_path, False) or has_text
                    if not has_text:
                        line_number = index_doc.get_file_line_number(entry.line_number)
                        first_bare_line_number_by_path.setdefault(listed_path, line_number)
            children = sorted([*((name, True) for name in dir_names), *((name, False) for name in file_names)])
            for name, is_dir in children:
                child_path = posixpath.join(directory_path, name)
                if is_dir:
                    entry_name = f"{name}/"
                elif Path(name).suffix == ".md" and not is_dir_index(name):
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
        """Check that no file or directory under ``docs/`` has ``#`` or ``%`` in its name; return the problems.

        Such names break links to the rendered page. Names are checked on disk, as :attr:`docs_tree` lists them; a
        directory with such a name is reported once, not again for everything inside it.
        """
        docs_dir = self.root / "docs"
        problems: list[Problem] = []
        reported_directories: list[Path] = []
        paths = sorted(
            (directory / name, is_dir)
            for directory, dir_names, file_names in self.docs_tree
            for names, is_dir in ((dir_names, True), (file_names, False))
            for name in names
        )
        for path, is_dir in paths:
            if not any(character in path.name for character in self.FORBIDDEN_NAME_CHARACTERS):
                continue
            if any(directory in path.parents for directory in reported_directories):
                continue
            if is_dir:
                reported_directories.append(path)
            problems.append(Problem(path.relative_to(docs_dir).as_posix(), None, self.FORBIDDEN_NAME_MESSAGE))
        return problems

    def check_reserved_paths(self) -> list[Problem]:
        """Check that no doc's page would take the URL of a generated page; return the problems.

        Docs that could not be read count too.
        """
        owners_by_path = map_reserved_owners({*self.doc_set.by_path, *self.doc_set.read_errors_by_path})
        return [Problem(path, None, RESERVED_PATH_MESSAGE % owner) for path, owner in sorted(owners_by_path.items())]

    def find_staged_deletes_renames(self) -> list[Problem]:
        """Return the problems for docs that are staged as deleted or renamed in git.

        Docs are never deleted or renamed; a doc that moves or goes away is kept as a redirect doc.

        Raises:
            GitError: The repository root is not a git working tree.
        """
        problems: list[Problem] = []
        for change in self.git.list_staged_changes(DOCS_DIR):
            old = change.old_path.removeprefix(DOCS_DIR)
            if change.is_deleted:
                problems.append(Problem(old, None, f"deleted; {self.KEEP_AS_REDIRECT_ADVICE}"))
            elif change.is_renamed:
                problems.append(Problem(old, None, f"renamed to {change.new_path}; {self.KEEP_AS_REDIRECT_ADVICE}"))
        return problems
