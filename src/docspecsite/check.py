"""The ``docspecsite check`` command and its DS-20 checks.

Docs: behavior/requirements.md#checks
Docs: architecture/docs-tooling.md
"""

import posixpath
import tomllib
from functools import cache, cached_property
from pathlib import Path

import griffe

from .coderef import Codebase, CodeError
from .config import CONFIG_FILE, ConfigError, ProjectConfig
from .docs import DOCS, read_text
from .docset import DocSet
from .git import Git
from .links import collect_code_refs, collect_outgoing_refs
from .markdown import collect_heading_anchors, list_entries
from .problems import Problem
from .schema import FrontMatterValidator
from .vocabulary import Vocabulary, load_vocabulary

ADVICE = "docs are never deleted or renamed; keep the file as a redirect doc (meta/versioning.md)"
CHILDREN_HEADING = "Children"
FORBIDDEN_NAME_CHARACTERS = ("#", "%")
FORBIDDEN_NAME_MESSAGE = 'name contains "#" or "%", which break links to the rendered page'


class Checker:
    """The DS-20 checks of a repository's working tree, with its settings, docs, vocabulary and code loaded once.

    Attributes:
        root: The repository root.
        git: The repository's git, asked for the staged changes.
        loading_problems: The problems found so far while loading the settings and the code.
        config: The project settings, loaded on first use; None when ``docspecsite.toml`` failed to load.
        docs: The working-tree docs, loaded on first use.
        vocabulary: The vocabulary the front matter is validated against, loaded on first use.
        codebase: The project code, loaded on first use; None when the settings or the code failed to load.
    """

    def __init__(self, root: Path) -> None:
        """Prepare the checks of a repository; the settings, docs, vocabulary and code are loaded on first use.

        A ``docspecsite.toml`` that fails to load, and code that fails to load, become problems instead of errors.

        Args:
            root: Repository root whose working-tree docs, ``docspecsite.toml`` and code are checked.
        """
        self.root = root
        self.git = Git(root)
        self.loading_problems: list[Problem] = []

    @cached_property
    def config(self) -> ProjectConfig | None:
        """The project settings; None when ``docspecsite.toml`` failed to load. Their problems are recorded."""
        try:
            config = ProjectConfig.load(self.root)
        except ConfigError as error:
            # Raised only for a file that cannot be read; the problem's path already names the file.
            self.loading_problems.append(
                Problem(CONFIG_FILE, None, f"cannot be read: {error.__cause__}", under_docs=False)
            )
            return None
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
            self.loading_problems.append(
                Problem(CONFIG_FILE, None, f"invalid {CONFIG_FILE}: {error}", under_docs=False)
            )
            return None
        self.loading_problems.extend(
            Problem(CONFIG_FILE, None, message, under_docs=False) for message in config.problems
        )
        return config

    @cached_property
    def docs(self) -> DocSet:
        """The working-tree docs."""
        return DocSet.load(self.root)

    @cached_property
    def vocabulary(self) -> Vocabulary:
        """The vocabulary the front matter is validated against."""
        return load_vocabulary(self.root)

    @cached_property
    def codebase(self) -> Codebase | None:
        """The project code; None when the settings or the code failed to load. A code failure is recorded."""
        if self.config is None:
            return None
        try:
            return Codebase.load(self.root, self.config)
        except (ValueError, griffe.GriffeError) as error:
            self.loading_problems.append(self.make_code_problem(error))
            return None

    @staticmethod
    def make_code_problem(error: ValueError | griffe.GriffeError) -> Problem:
        """Return the problem for code that cannot be loaded or read.

        Args:
            error: Failure from loading the code or reading its ``Docs:`` lines; a ``CodeError`` names the file.
        """
        file = error.file if isinstance(error, CodeError) else None
        return Problem(file or "(code)", None, f"cannot load code: {error}", under_docs=False)

    def run(self, staged: bool) -> list[Problem]:
        """Run all DS-20 checks and return the problems found, sorted and without duplicates.

        Args:
            staged: Also report docs staged as deleted or renamed; needs git.

        Raises:
            GitError: ``staged`` is set and the repository root is not a git working tree.
        """
        problems = self.check_front_matter()
        problems.extend(self.check_links())
        problems.extend(self.check_indexes())
        problems.extend(self.check_names())
        try:
            problems.extend(self.check_code_links())
            problems.extend(self.check_docs_lines())
        except (ValueError, griffe.GriffeError) as error:
            problems.append(self.make_code_problem(error))
        if staged:
            problems.extend(self.find_staged_deletes_renames())
        # Read last: the checks above load the settings and the code, which records their problems.
        problems.extend(self.loading_problems)
        return sorted(set(problems), key=lambda p: (p.path, p.line_number or 0, p.message))

    def check_front_matter(self) -> list[Problem]:
        """Check the front matter of the docs and return the problems found.

        Without valid settings the ADR prefixes are unknown, so ADR names are not checked.
        """
        problems = [Problem(d.path, None, d.error) for d in self.docs.docs if d.error]
        adr_prefixes = self.config.adr_prefixes if self.config is not None else None
        validator = FrontMatterValidator(self.vocabulary, adr_prefixes)
        for doc in self.docs.docs:
            problems.extend(validator.validate(doc))
        return problems

    def check_links(self) -> list[Problem]:
        """Check that the links of the docs resolve and return the problems found.

        Body and front-matter links count; a missing target or heading anchor is a problem. Link targets are looked up
        as files under the repository root, and anchors in the target docs' text.
        """

        @cache
        def get_anchors(target: str) -> set[str]:
            return collect_heading_anchors(read_text(self.root / target))

        problems: list[Problem] = []
        for doc in self.docs.docs:
            refs, link_problems = collect_outgoing_refs(doc)
            problems.extend(link_problems)
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
                elif ref.anchor and is_doc and file.is_file() and ref.anchor not in get_anchors(ref.target):
                    problems.append(Problem(doc.path, ref.line_number, f'no heading "#{ref.anchor}" in {ref.target}'))
        return problems

    def check_code_links(self) -> list[Problem]:
        """Check that code links of the docs name public code elements and return the problems.

        Both ``code:`` links in the body and entries of the ``code`` front-matter field are checked. Without loaded
        code nothing is checked.
        """
        if self.codebase is None:
            return []
        problems: list[Problem] = []
        for doc in self.docs.docs:
            for ref in collect_code_refs(doc):
                if self.codebase.index.find(ref.dotted) is not None:
                    continue
                if ref.kind == "body":
                    message = f"code: link to unknown code element: {ref.dotted}"
                else:
                    message = f'"code" entry is not a code element: {ref.dotted}'
                problems.append(Problem(doc.path, ref.line_number, message))
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
            doc = self.docs.by_path.get(path)
            if doc is None:
                message = f"Docs: line points to a missing doc: {path}"
            elif anchor and anchor not in collect_heading_anchors(doc.body):
                message = f'no heading "#{anchor}" in docs/{path}'
            else:
                continue
            problems.append(Problem(docs_line.file, docs_line.line_number, message, under_docs=False))
        return problems

    def check_indexes(self) -> list[Problem]:
        """Check that every directory under ``docs/`` has an ``index.md`` listing its children; return the problems.

        Each child must be listed with a description under the ``## Children`` heading; redirect docs need no entry.
        The directories and child files are listed from disk, the ``## Children`` lists read from the docs.
        """
        docs_dir = self.root / "docs"
        problems: list[Problem] = []
        for directory in [docs_dir, *sorted(p for p in docs_dir.rglob("*") if p.is_dir())]:
            rel = directory.relative_to(docs_dir).as_posix()
            rel = "" if rel == "." else rel
            index_path = posixpath.join(rel, "index.md")
            index = self.docs.by_path.get(index_path)
            if index is None:
                problems.append(Problem(rel, None, "directory has no index.md"))
                continue
            described: dict[str, bool] = {}
            first_bare_line: dict[str, int] = {}
            for entry in list_entries(index.body, CHILDREN_HEADING):
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
            for child in sorted(directory.iterdir()):
                child_rel = posixpath.join(rel, child.name)
                if child.is_dir():
                    entry_name = f"{child.name}/"
                elif child.suffix == ".md" and child.name != "index.md":
                    child_doc = self.docs.by_path.get(child_rel)
                    if child_doc and child_doc.front_matter and child_doc.front_matter.get("status") == "redirect":
                        continue
                    entry_name = child.name
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

        Such names break links to the rendered page. Names are checked on disk; a directory with such a name is
        reported once, not again for everything inside it.
        """
        docs_dir = self.root / "docs"
        problems: list[Problem] = []
        reported_directories: list[Path] = []
        for path in sorted(docs_dir.rglob("*")):
            if not any(character in path.name for character in FORBIDDEN_NAME_CHARACTERS):
                continue
            if any(directory in path.parents for directory in reported_directories):
                continue
            if path.is_dir():
                reported_directories.append(path)
            problems.append(Problem(path.relative_to(docs_dir).as_posix(), None, FORBIDDEN_NAME_MESSAGE))
        return problems

    def find_staged_deletes_renames(self) -> list[Problem]:
        """Return the problems for docs that are staged as deleted or renamed in git (DS-6).

        Raises:
            GitError: The repository root is not a git working tree.
        """
        problems: list[Problem] = []
        for change in self.git.list_staged_changes(DOCS):
            old = change.old_path.removeprefix(DOCS)
            if change.status == "D":
                problems.append(Problem(old, None, f"deleted; {ADVICE}"))
            elif change.status.startswith("R"):
                problems.append(Problem(old, None, f"renamed to {change.new_path}; {ADVICE}"))
        return problems
