"""The ``docspecsite check`` command and its checks of the docs.

Docs: behavior/requirements.md#checks
Docs: architecture/docs-tooling.md
"""

import posixpath
from functools import cached_property
from pathlib import Path

import griffe

from .coderef import Codebase, CodeError
from .config import ProjectConfig
from .docs import DOCS, Doc
from .docset import DocSet
from .git import Git
from .links import collect_code_refs, collect_outgoing_refs
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
    """See :meth:`.__init__`."""

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
        as files under :attr:`.root`, and anchors in the target docs' text through :meth:`.read_heading_anchors`.

        Args:
            doc: Working-tree doc whose links are checked.
        """
        refs, problems = collect_outgoing_refs(doc)
        for ref in refs:
            file = self.root / ref.target
            is_doc = ref.target.startswith(DOCS) and ref.target.endswith(".md")
            if not file.exists():
                problems.append(Problem(doc.path, ref.line_number, f"broken link: {ref.target} does not exist"))
            elif ref.kind != "body" and not (is_doc and file.is_file()):
                problems.append(
                    Problem(
                        doc.path,
                        ref.line_number,
                        f'"{ref.kind}" must be a doc (path relative to docs/): {ref.target}',
                    )
                )
            elif ref.anchor and is_doc and file.is_file() and ref.anchor not in self.read_heading_anchors(ref.target):
                problems.append(Problem(doc.path, ref.line_number, f'no heading "#{ref.anchor}" in {ref.target}'))
        return problems

    def read_heading_anchors(self, target: str) -> set[str]:
        """Return the heading anchors of a link target's text, read from the file once per target.

        Args:
            target: Path of an existing Markdown file relative to the repository root; the anchors are kept in
                :attr:`.heading_anchors_by_target` for later calls.
        """
        if target not in self.heading_anchors_by_target:
            target_text = MarkdownText(read_text(self.root / target))
            self.heading_anchors_by_target[target] = target_text.collect_heading_anchors()
        return self.heading_anchors_by_target[target]


class CodeLinkCheck(DocCheck):
    """The check that a doc's code links name public elements of the loaded code."""

    # Arguments of __init__
    codebase: Codebase
    """See :meth:`.__init__`."""

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
            doc: Working-tree doc whose code links are looked up in :attr:`.codebase`.
        """
        problems: list[Problem] = []
        for ref in collect_code_refs(doc):
            if self.codebase.index.get(ref.dotted) is not None:
                continue
            if ref.kind == "body":
                message = f"code: link to unknown code element: {ref.dotted}"
            else:
                message = f'"code" entry is not a code element: {ref.dotted}'
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
    ADVICE = "docs are never deleted or renamed; keep the file as a redirect doc (meta/versioning.md)"

    FORBIDDEN_NAME_MESSAGE = 'name contains "#" or "%", which break links to the rendered page'

    # State
    git: Git
    """The repository's git, asked for the staged changes."""

    loading_problems: list[Problem]
    """The problems found so far while loading the settings and the code."""

    # Arguments of __init__
    root: Path
    """See :meth:`.__init__`."""

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

    def run(self, staged: bool) -> list[Problem]:
        """Run all checks of the docs and return the problems found, sorted and without duplicates.

        The checks cover front matter, links and their heading anchors, directory indexes, file names, links from
        the code and its ``Docs:`` lines, and the settings; the full list is the project's requirement DS-20. The
        checks of single docs (front matter, links, code links) run in one pass over the docs, the others per
        directory, path or code element.

        Docs: behavior/requirements.md#checks

        Args:
            staged: Also report docs staged as deleted or renamed; needs git.

        Raises:
            GitError: ``staged`` is set and the repository root is not a git working tree.
        """
        problems: list[Problem] = []
        doc_checks: list[DocCheck] = [self.front_matter_validator, LinkCheck(self.root)]
        if self.codebase is not None:
            doc_checks.append(CodeLinkCheck(self.codebase))
        for doc in self.doc_set:
            for doc_check in doc_checks:
                problems.extend(doc_check.check(doc))
        problems.extend(self.check_indexes())
        problems.extend(self.check_names())
        try:
            problems.extend(self.check_docs_lines())
        except (CodeError, griffe.GriffeError) as error:
            problems.append(self.make_code_problem(error))
        if staged:
            problems.extend(self.find_staged_deletes_renames())
        # Read last: the checks above load the settings and the code, which records their problems.
        problems.extend(self.loading_problems)
        return sorted(set(problems), key=lambda p: (p.path, p.line_number or 0, p.message))

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
            elif anchor and anchor not in MarkdownText(doc.body).collect_heading_anchors():
                message = f'no heading "#{anchor}" in docs/{path}'
            else:
                continue
            problems.append(Problem(docs_line.file, docs_line.line_number, message, under_docs=False))
        return problems

    def check_indexes(self) -> list[Problem]:
        """Check that every directory under ``docs/`` has an ``index.md`` listing its children; return the problems.

        Each child must be listed with a description under the ``## Children`` heading; redirect docs need no entry.
        The directories and child files come from :attr:`.docs_tree`, the ``## Children`` lists from the docs.
        """
        docs_dir = self.root / "docs"
        problems: list[Problem] = []
        for directory, dir_names, file_names in self.docs_tree:
            rel = directory.relative_to(docs_dir).as_posix()
            rel = "" if rel == "." else rel
            index_path = posixpath.join(rel, "index.md")
            index = self.doc_set.by_path.get(index_path)
            if index is None:
                problems.append(Problem(rel, None, "directory has no index.md"))
                continue
            described: dict[str, bool] = {}
            first_bare_line: dict[str, int] = {}
            for entry in MarkdownText(index.body).list_entries(self.CHILDREN_HEADING):
                for target in entry.targets:
                    path = target.partition("#")[0].partition("?")[0]
                    if not path or ":" in path:
                        continue
                    resolved = posixpath.normpath(posixpath.join(rel, path))
                    resolved = resolved.removesuffix("/index.md")
                    has_text = bool(entry.text)
                    described[resolved] = described.get(resolved, False) or has_text
                    if not has_text:
                        first_bare_line.setdefault(resolved, index.body_line + entry.line_number - 1)
            children = sorted([*((name, True) for name in dir_names), *((name, False) for name in file_names)])
            for name, is_dir in children:
                child_rel = posixpath.join(rel, name)
                if is_dir:
                    entry_name = f"{name}/"
                elif Path(name).suffix == ".md" and name != "index.md":
                    child_doc = self.doc_set.by_path.get(child_rel)
                    if child_doc and child_doc.front_matter and child_doc.front_matter.get("status") == "redirect":
                        continue
                    entry_name = name
                else:
                    continue
                if child_rel not in described:
                    problems.append(Problem(index_path, None, f"child {entry_name} is not listed"))
                elif not described[child_rel]:
                    problems.append(
                        Problem(
                            index_path,
                            first_bare_line[child_rel],
                            f"child {entry_name} is listed without a description",
                        )
                    )
        return problems

    def check_names(self) -> list[Problem]:
        """Check that no file or directory under ``docs/`` has ``#`` or ``%`` in its name; return the problems.

        Such names break links to the rendered page. Names are checked on disk, as :attr:`.docs_tree` lists them; a
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
        for change in self.git.list_staged_changes(DOCS):
            old = change.old_path.removeprefix(DOCS)
            if change.status == "D":
                problems.append(Problem(old, None, f"deleted; {self.ADVICE}"))
            elif change.status.startswith("R"):
                problems.append(Problem(old, None, f"renamed to {change.new_path}; {self.ADVICE}"))
        return problems
