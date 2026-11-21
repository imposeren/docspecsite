"""The checks of a repository's docs: front matter, links, code links, indexes, names and staged deletes.

Docs: behavior/requirements.md#checks
Docs: architecture/docs-tooling.md
"""

import posixpath
from functools import cached_property
from pathlib import Path

import griffe

from .coderef import Codebase, CodeError
from .config import ProjectConfig
from .docs import DOCS_DIR, Doc, is_dir_index, make_dir_index_path
from .docset import DocSet
from .git import Git
from .links import DocLinks
from .markdown import MarkdownText
from .problems import DocCheck, Problem
from .schema import FrontMatterValidator
from .text import read_text
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
            elif ref.anchor and is_existing_doc_target and ref.anchor not in self.read_heading_anchors(ref.target):
                problems.append(Problem(doc.path, ref.line_number, f'no heading "#{ref.anchor}" in {ref.target}'))
        return problems

    def read_heading_anchors(self, target: str) -> set[str]:
        """Return the heading anchors of a link target's text, read from the file once per target.

        The anchors are kept in :attr:`heading_anchors_by_target`, so each file is read once.

        Args:
            target: Path of an existing Markdown file relative to the repository root.
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
        """The working-tree docs."""
        return DocSet.load(self.root)

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

        The front matter and the links are always checked; the code links only when the code is loaded.
        """
        doc_checks: list[DocCheck] = [self.front_matter_validator, self.link_check]
        if self.codebase is not None:
            doc_checks.append(CodeLinkCheck(self.codebase))
        return doc_checks

    def run(self, include_staged: bool, include_code: bool = False) -> list[Problem]:
        """Run all checks of the docs and return the problems found, sorted and without duplicates.

        The checks cover front matter, links and their heading anchors, directory indexes, file names, links from
        the code, and the settings; the full list is the project's requirement DS-20. The references in the
        docstrings (``Docs:`` lines, roles and ``code:`` links) are checked only when ``include_code`` is set, by
        :meth:`check_code_references`.

        Docs: behavior/requirements.md#checks

        Args:
            include_staged: Also report docs staged as deleted or renamed; needs git.
            include_code: Also check the references in the code's docstrings.

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
        try:
            if include_code:
                problems.extend(self.check_code_references())
        except (CodeError, griffe.GriffeError) as error:
            problems.append(self.make_code_problem(error))
        if include_staged:
            problems.extend(self.find_staged_deletes_renames())
        # Read last: the checks above load the settings and the code, which records their problems.
        problems.extend(self.loading_problems)
        return sorted(set(problems), key=lambda p: (p.path, p.line_number or 0, p.message))

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
        The directories and child files come from :attr:`docs_tree`, the ``## Children`` lists from the docs.
        """
        docs_dir = self.root / "docs"
        problems: list[Problem] = []
        for directory, dir_names, file_names in self.docs_tree:
            directory_path = directory.relative_to(docs_dir).as_posix()
            directory_path = "" if directory_path == "." else directory_path
            index_path = make_dir_index_path(directory_path)
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
                        line_number = index_doc.body_line + entry.line_number - 1
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
