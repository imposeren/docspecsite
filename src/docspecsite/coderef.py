"""The project's code as the docs see it.

It knows which dotted paths exist and where they are shown.

Docs: architecture/docs-tooling.md
"""

import keyword
import posixpath
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar, Self, assert_never

import griffe

from .codeindex import CodeIndex, CodeTarget
from .config import ProjectConfig
from .errors import DocspecsiteError
from .links import is_empty_code_target, parse_code_target
from .markdown import Link, MarkdownText
from .roles import RoleRef
from .symlinks import CODE_DIR_TO_FILE_REASON, LEFT_OUT_SYMLINK_REASON, DiskFiles, SymlinkFollower, SymlinkKind

DOCS_LINE = re.compile(r"^\s*Docs:\s*(\S+)\s*$")


class CodeError(DocspecsiteError):
    """Error for code that cannot be read for the docs, naming its source file in the ``file`` attribute when known."""

    file: str | None
    """See :meth:`__init__`."""

    def __init__(self, message: str, *values: object, file: str | None = None) -> None:
        """Hold a message template, its values and the source file the error is about.

        Args:
            message: Static ``%``-style template that never changes between occurrences, so error trackers group by
                it.
            *values: Values filled into the template with ``str()``; with none, the template is the message as is.
            file: Repo-relative path of the source file the error is about; None when unknown.
        """
        super().__init__(message, *values)
        self.file = file


@dataclass(frozen=True)
class Package:
    """Python package found in one of the code directories, with its directory and the code directory holding it."""

    name: str
    """The package's import name."""

    package_dir: Path
    """The package directory."""

    repo_code_dir: str
    """The code directory containing it, relative to the repo root (POSIX); ``.`` for the root.

    For a code directory that is a symlink, the directory it leads to.
    """


@dataclass(frozen=True)
class UnusableInput:
    """Input in the code directories that the code reference cannot use, and leaves out.

    Docs: behavior/commands/index.md#input-that-cannot-be-used
    """

    path: str
    """Repo path of the file or directory left out."""

    reason: str
    """Why it cannot be used, as the check's problem and the build's warning give it."""


@dataclass(frozen=True)
class FoundPackages:
    """The packages found in the code directories, and what in them is left out."""

    packages: tuple[Package, ...]
    """The packages that can be loaded, by code directory and then by name."""

    left_out: tuple[UnusableInput, ...]
    """The package directories and code directories left out, with the reason for each."""


@dataclass(frozen=True)
class BrokenReference:
    """Role or ``code:`` link of a docstring that names no code element, with its place in the source."""

    text: str
    """The reference as written, such as ``:meth:`nope``` or ``code:a.b``."""

    file: str
    """Repo-relative path of the source file."""

    line_number: int
    """Line of the reference in the source file, from 1."""

    is_empty_target: bool = False
    """Whether the reference is a ``code:`` link with nothing after the scheme, which names no element to look for."""


@dataclass(frozen=True)
class DocsLine:
    """``Docs:`` line of a docstring, with its place in the source."""

    target: str
    """Doc path relative to ``docs/``, with an optional ``#anchor``."""

    file: str
    """Repo-relative path of the source file."""

    line_number: int
    """Line of the ``Docs:`` line in the source file, from 1."""


def split_docs_lines(text: str) -> tuple[list[str], str]:
    """Split a docstring into the targets of its ``Docs:`` lines and the remaining text.

    Args:
        text: Docstring text (cleaned, as griffe gives it); a ``Docs:`` line is one holding only ``Docs: <target>``.

    Returns:
        The targets and the text without the ``Docs:`` lines.
    """
    targets: list[str] = []
    kept: list[str] = []
    for line in text.splitlines(keepends=True):
        match = DOCS_LINE.match(line)
        if match:
            targets.append(match.group(1))
        else:
            kept.append(line)
    return targets, "".join(kept).rstrip("\n") + "\n" if kept and targets else "".join(kept)


@dataclass(frozen=True)
class CodeLinkTarget:
    """Code element that a docstring's Python role or ``code:`` link refers to, as the codebase finds it."""

    role: RoleRef | None
    """What the role says; None for a ``code:`` link."""

    dotted_path: str | None
    """Full dotted path of the code element found; None when the codebase does not show it."""

    is_empty_target: bool = False
    """Whether the link is a ``code:`` link with nothing after the scheme; it has no role and no dotted path."""


@dataclass(frozen=True)
class ParsedDocstring:
    """Docstring as the code reference pages show it: its ``Docs:`` targets and its Google-style sections."""

    # Constants
    TABLE_TITLES: ClassVar[Mapping[griffe.DocstringSectionKind, str]] = MappingProxyType[
        griffe.DocstringSectionKind, str
    ](
        {
            griffe.DocstringSectionKind.parameters: "Parameters",
            griffe.DocstringSectionKind.other_parameters: "Other parameters",
            griffe.DocstringSectionKind.type_parameters: "Type parameters",
            griffe.DocstringSectionKind.returns: "Returns",
            griffe.DocstringSectionKind.yields: "Yields",
            griffe.DocstringSectionKind.receives: "Receives",
            griffe.DocstringSectionKind.raises: "Raises",
            griffe.DocstringSectionKind.warns: "Warns",
            griffe.DocstringSectionKind.attributes: "Attributes",
            griffe.DocstringSectionKind.functions: "Functions",
            griffe.DocstringSectionKind.classes: "Classes",
            griffe.DocstringSectionKind.type_aliases: "Type aliases",
            griffe.DocstringSectionKind.modules: "Modules",
        }
    )
    """Headings of the docstring sections shown as tables, by section kind."""

    # Fields
    docs_targets: tuple[str, ...]
    """Targets of the ``Docs:`` lines, doc paths relative to ``docs/`` with an optional ``#anchor``."""

    sections: tuple[griffe.DocstringSection, ...]
    """The sections of the rest of the docstring, in source order."""

    @classmethod
    def parse(cls, obj: griffe.Object) -> Self:
        """Split the docstring of an object into its ``Docs:`` targets and its sections; no docstring gives neither.

        Args:
            obj: Module or member whose docstring is parsed; its parent context lets griffe parse the sections.
        """
        if obj.docstring is None:
            return cls((), ())
        targets, text = split_docs_lines(obj.docstring.value)
        return cls(tuple(targets), tuple(griffe.parse_google(griffe.Docstring(text, parent=obj), warnings=False)))

    @classmethod
    def get_table_items(cls, section: griffe.DocstringSection) -> list[griffe.DocstringElement] | None:
        """Return the items of a section shown as a table (parameters, returns and similar), or None for a text section.

        Args:
            section: Section from griffe's Google-style parse of a docstring.
        """
        section_value: object = section.value
        if section.kind not in cls.TABLE_TITLES or not isinstance(section_value, list):
            return None
        return [item for item in section_value if isinstance(item, griffe.DocstringElement)]

    @staticmethod
    def is_examples(section: griffe.DocstringSection) -> bool:
        """Return whether a section is an Examples section, whose code parts are shown as ``pycon`` blocks.

        Args:
            section: Section from griffe's Google-style parse of a docstring.
        """
        return section.kind is griffe.DocstringSectionKind.examples

    @classmethod
    def get_section_title(cls, section: griffe.DocstringSection) -> str:
        """Return the heading of a text section: its own title, else "Examples" for an Examples section, else empty.

        Args:
            section: Section from griffe's Google-style parse of a docstring that is not shown as a table.
        """
        return section.title or ("Examples" if cls.is_examples(section) else "")

    @staticmethod
    def get_section_text(section: griffe.DocstringSection) -> str:
        """Return the Markdown of a text section; examples become ``pycon`` code blocks between their prose.

        Args:
            section: Section from griffe's Google-style parse of a docstring that is not shown as a table.
        """
        section_value: object = section.value
        if isinstance(section_value, griffe.DocstringAdmonition | griffe.DocstringDeprecated):
            return section_value.description
        if ParsedDocstring.is_examples(section) and isinstance(section_value, list):
            parts: list[str] = []
            for item in section_value:
                if isinstance(item, tuple) and len(item) == 2:
                    part_kind, part = item
                    is_code = part_kind is griffe.DocstringSectionKind.examples
                    parts.append(f"```pycon\n{part}\n```" if is_code else str(part))
            return "\n\n".join(parts)
        return str(section_value)

    def iter_texts(self) -> Iterator[str]:
        """Return the Markdown texts the code reference renders, in source order: text sections and table cells."""
        for section in self.sections:
            items = self.get_table_items(section)
            if items is None:
                yield self.get_section_text(section)
            else:
                yield from (item.description for item in items)


class Codebase:
    """The project's code as docspecsite sees it.

    Its public modules, the repository paths of their packages, the index of ``code:`` link targets and the ``Docs:``
    lines of its docstrings.
    """

    # Constants
    INVALID_PACKAGE_NAME_REASON = 'directory name "{name}" is not a valid Python package name'

    OPENING_QUOTES = re.compile(r'^\s*[A-Za-z]{0,2}("""|\'\'\'|"|\')')
    """Opening quotes of a docstring (group 1), with its prefix and the indentation before it."""

    # Loaded code
    index: CodeIndex
    """The ``code:`` link targets: every module and public member, by dotted path."""

    left_out: tuple[UnusableInput, ...]
    """The input in the code directories that was not loaded, with the reason for each."""

    modules: list[griffe.Module]
    """The loaded modules, sorted by path."""

    packages_by_name: dict[str, Package]
    """The packages the modules were loaded from, by package name."""

    # Read sources
    source_lines_by_file: dict[Path, list[str]]
    """Lines of the source files read so far, by file, so that each file is read once."""

    def __init__(
        self, modules: list[griffe.Module], packages: Sequence[Package], left_out: Sequence[UnusableInput] = ()
    ) -> None:
        """Index the loaded modules.

        Args:
            modules: Loaded modules to index; their public members become code elements, sorted by path.
            packages: Packages the modules were loaded from; used to find the file defining an object.
            left_out: Input in the code directories that was not loaded, for the check and the build to report.
        """
        self.modules = sorted(modules, key=lambda m: m.path)
        self.packages_by_name = {p.name: p for p in packages}
        self.left_out = tuple(left_out)
        self.source_lines_by_file = {}
        targets: dict[str, CodeTarget] = {}
        for module in self.modules:
            targets[module.path] = CodeTarget(module.path, None)
            for member in self.walk(module):
                targets[member.path] = CodeTarget(module.path, member.path)
        self.index = MappingProxyType(targets)

    @classmethod
    def load(cls, root: Path, config: ProjectConfig) -> Codebase:
        """Load the code of the packages in the code directories, without importing or running it.

        Docstrings are parsed as Google style. All packages share one collection, so aliases across packages resolve.
        What :meth:`find_packages` leaves out is in the codebase's ``left_out`` attribute.

        Args:
            root: Directory holding the code: the repository root, or the code extracted from the ref.
            config: Settings whose :attr:`~docspecsite.config.ProjectConfig.code_dirs` globs are expanded under ``root``
                to find the packages.

        Raises:
            CodeError: A package's code cannot be loaded, such as code that is not valid UTF-8, or a package name is
                found in more than one code directory.
            griffe.GriffeError: griffe cannot load a package.
        """
        found = cls.find_packages(root, config)
        collection = griffe.ModulesCollection()
        modules: list[griffe.Module] = []
        for package in found.packages:
            try:
                loaded = griffe.load(
                    package.name,
                    search_paths=[package.package_dir.parent],
                    docstring_parser="google",
                    allow_inspection=False,
                    resolve_aliases=True,
                    modules_collection=collection,
                    try_relative_path=False,
                )
            except ValueError as error:  # also UnicodeDecodeError, for code that is not valid UTF-8
                raise CodeError("cannot load the code of package %s: %s", package.name, error) from error
            if isinstance(loaded, griffe.Module):
                modules.extend(cls.iter_modules(loaded))
        return cls(modules, found.packages, found.left_out)

    @classmethod
    def find_packages(cls, root: Path, config: ProjectConfig) -> FoundPackages:
        """Return the packages of the code directories: each ``<code dir>/<pkg>/`` directory with an ``__init__.py``.

        A ``.`` entry of :attr:`~docspecsite.config.ProjectConfig.code_dirs` is the root itself. A code directory
        that is a symlink is followed under ``root``, where the code is read, and the directory it leads to is its
        packages' code directory; one that leads to an absolute path, out of ``root`` or to nothing is left out. A
        package directory whose name Python cannot import is left out too; only these top-level names are checked.

        Docs: behavior/commands/index.md#input-that-cannot-be-used
        Docs: behavior/commands/build.md#what-the-build-does

        Args:
            root: Directory holding the code: the repository root, or the code extracted from the ref.
            config: Settings whose :attr:`~docspecsite.config.ProjectConfig.code_dirs` globs are expanded under
                ``root``.

        Raises:
            CodeError: A package name is found in more than one code directory.
        """
        root = root.resolve()
        follower = SymlinkFollower(DiskFiles(root))
        candidates: set[Path] = set()
        for code_dir_glob in config.code_dirs:
            candidates.update([root] if code_dir_glob == "." else root.glob(code_dir_glob))
        real_code_dirs: dict[str, None] = {}  # repo paths of the directories the code directories are, each once
        left_out: list[UnusableInput] = []
        for code_dir in sorted(candidates):
            repo_code_dir = code_dir.relative_to(root).as_posix()
            if not config.is_code_dir(repo_code_dir):
                continue
            if follower.files.is_symlink(repo_code_dir):
                target = follower.follow(repo_code_dir)
                match target.kind:
                    case SymlinkKind.OUT_OF_REPO | SymlinkKind.NOTHING:
                        left_out.append(UnusableInput(repo_code_dir, LEFT_OUT_SYMLINK_REASON))
                    case SymlinkKind.DIRECTORY:
                        real_code_dirs[target.found_path] = None
                    case SymlinkKind.DOC | SymlinkKind.OTHER_FILE:
                        left_out.append(UnusableInput(repo_code_dir, CODE_DIR_TO_FILE_REASON))
                    case _:
                        assert_never(target.kind)
            elif code_dir.is_dir():
                real_code_dirs[repo_code_dir] = None
        packages: list[Package] = []
        for repo_code_dir in real_code_dirs:
            for package_dir in sorted((root / repo_code_dir).iterdir()):
                if not (package_dir.is_dir() and (package_dir / "__init__.py").is_file()):
                    continue
                if cls.is_package_name(package_dir.name):
                    packages.append(Package(package_dir.name, package_dir, repo_code_dir))
                else:
                    left_out.append(
                        UnusableInput(
                            posixpath.normpath(posixpath.join(repo_code_dir, package_dir.name)),
                            cls.INVALID_PACKAGE_NAME_REASON.format(name=package_dir.name),
                        )
                    )
        # Repo paths of the code directories holding each package name, in code directory order.
        code_dirs_by_name: dict[str, list[str]] = {}
        for package in packages:
            code_dirs_by_name.setdefault(package.name, []).append(package.repo_code_dir)
        for name, repo_code_dirs in sorted(code_dirs_by_name.items()):
            if len(repo_code_dirs) > 1:
                raise CodeError("package %s is in more than one code directory: %s", name, ", ".join(repo_code_dirs))
        return FoundPackages(tuple(packages), tuple(left_out))

    @staticmethod
    def is_package_name(name: str) -> bool:
        """Return whether Python can import a directory name as a package: an identifier that is not a keyword.

        Args:
            name: Name of a package directory.
        """
        return name.isidentifier() and not keyword.iskeyword(name)

    @classmethod
    def iter_modules(cls, module: griffe.Module) -> Iterator[griffe.Module]:
        """Return a module and its public submodules, recursively.

        Args:
            module: Loaded package or module, yielded first; submodules whose name starts with ``_`` are skipped with
                their subtrees.
        """
        yield module
        for name, member in module.members.items():
            if isinstance(member, griffe.Module) and not name.startswith("_"):
                yield from cls.iter_modules(member)

    @staticmethod
    def is_public(name: str, obj: griffe.Object) -> bool:
        """Return whether a member is shown: public names, and ``__init__`` when documented.

        Args:
            name: Name of the member in its parent; decides public versus private.
            obj: The member itself; only its docstring is read, for ``__init__``.
        """
        if name == "__init__":
            return obj.docstring is not None
        return not name.startswith("_")

    @classmethod
    def iter_members(cls, obj: griffe.Object) -> Iterator[griffe.Object]:
        """Return the public members that a class or module defines itself, leaving out aliases and submodules.

        Args:
            obj: Class or module whose own members are listed, in definition order.
        """
        for name, member in obj.members.items():
            if isinstance(member, (griffe.Alias, griffe.Module)) or not cls.is_public(name, member):
                continue
            yield member

    @classmethod
    def walk(cls, obj: griffe.Object) -> Iterator[griffe.Object]:
        """Return every public member of an object, including those of nested classes.

        Args:
            obj: Module or class whose members are walked; members of nested classes follow their class.
        """
        for member in cls.iter_members(obj):
            yield member
            if isinstance(member, griffe.Class):
                yield from cls.walk(member)

    @staticmethod
    def get_filepath(obj: griffe.Object) -> Path:
        """Return the file defining an object.

        Args:
            obj: Module or member of the loaded code whose defining file is returned.

        Raises:
            CodeError: ``obj`` is in a namespace package, which has no single file.
        """
        filepath = obj.filepath
        if isinstance(filepath, list):
            raise CodeError("namespace package has no single file: %s", obj.path)
        return filepath

    def get_repo_path(self, obj: griffe.Object) -> str:
        """Return the POSIX path of the file defining an object, relative to the repository root.

        Args:
            obj: Loaded object of one of the packages this codebase was loaded from; its top-level package gives the
                code directory the path starts from.

        Raises:
            CodeError: ``obj`` is in a namespace package, which has no single file, or its file is outside the code
                directory of its package.
        """
        filepath = self.get_filepath(obj)
        package = self.packages_by_name[obj.path.split(".")[0]]
        try:
            relative_filepath = filepath.relative_to(package.package_dir.parent)
        except ValueError as error:
            raise CodeError(
                "the file of %s is outside the code directory of its package: %s", obj.path, filepath
            ) from error
        return posixpath.normpath(posixpath.join(package.repo_code_dir, relative_filepath.as_posix()))

    def find_role_target(self, target: str, owner: griffe.Object) -> str | None:
        """Return the full dotted path of the code element a docstring's role refers to, or None if it is not shown.

        A target with a leading ``.`` is looked up first among the members of the docstring's class (``owner`` itself
        when it is a class, else the class ``owner`` belongs to), then among the definitions of ``owner``'s module,
        never its imports. A target without a leading ``.`` is first tried as a full dotted path, and when that is no
        element, it is looked up the same way as with a leading ``.``. A target ending in ``.__init__`` leads to its
        class when the class's ``__init__`` is not in :attr:`index`. Only targets in :attr:`index` are found.

        Args:
            target: Target of the role without ``~``, such as ``.attempt`` or ``docspecsite.build.SiteBuilder``.
            owner: Module or member whose docstring holds the role; the place a leading ``.`` starts from.
        """
        candidates = [] if target.startswith(".") else [target]
        rest = target.removeprefix(".")
        parent = owner.parent
        class_ = owner if owner.is_class else parent if parent is not None and parent.is_class else None
        if class_ is not None:
            candidates.append(f"{class_.path}.{rest}")
        candidates.append(f"{owner.module.path}.{rest}")
        for candidate in candidates:
            if candidate in self.index:
                return candidate
            class_path = candidate.removesuffix(".__init__")
            if class_path != candidate and class_path in self.index:
                return class_path
        return None

    def find_link_target(self, href: str, owner: griffe.Object) -> CodeLinkTarget | None:
        """Find the code element a link of a docstring refers to; None when the link is no role or ``code:`` link.

        A Python role is looked up as :meth:`find_role_target` does, a ``code:`` target in :attr:`index`.

        Args:
            href: Percent-decoded target of a link in a docstring; a Python role's link starts with ``role:``.
            owner: Module or member whose docstring holds the link; a role's relative target is looked up from it.
        """
        if href.startswith(RoleRef.SCHEME):
            role = RoleRef.parse(href[len(RoleRef.SCHEME) :])
            return CodeLinkTarget(role, self.find_role_target(role.target, owner))
        if is_empty_code_target(href):
            return CodeLinkTarget(None, None, is_empty_target=True)
        dotted_path = parse_code_target(href)
        if dotted_path is None:
            return None
        return CodeLinkTarget(None, dotted_path if dotted_path in self.index else None)

    def collect_in_objects[T](self, collect: Callable[[griffe.Object], list[T]]) -> list[T]:
        """Return what a collector finds in each loaded module and each of its public members, in order.

        Args:
            collect: Function returning what it finds in one module or member.
        """
        return [found for module in self.modules for obj in [module, *self.walk(module)] for found in collect(obj)]

    def collect_docs_lines(self) -> list[DocsLine]:
        """Return every ``Docs:`` line of the docstrings in the loaded code, with its file and line.

        Raises:
            CodeError: A source file is not valid UTF-8, or a docstring's ``Docs:`` lines cannot be located in it.
        """
        return self.collect_in_objects(self.collect_docs_lines_of)

    def collect_broken_references(self) -> list[BrokenReference]:
        """Return the roles and ``code:`` links in the loaded code's docstrings that name no shown code element.

        Raises:
            CodeError: A source file is not valid UTF-8, or a broken reference cannot be located in it.
        """
        return self.collect_in_objects(self.collect_broken_references_of)

    def read_source_lines(self, obj: griffe.Object) -> list[str]:
        """Return the lines of the file defining an object; each file is read once.

        Args:
            obj: Module or member of the loaded code, not in a namespace package.

        Raises:
            CodeError: ``obj`` is in a namespace package, or its file is not valid UTF-8.
        """
        filepath = self.get_filepath(obj)
        lines = self.source_lines_by_file.get(filepath)
        if lines is None:
            try:
                # Python counts a line only at "\n" (read_text turns "\r\n" and "\r" into it), where splitlines() also
                # splits at form feeds and Unicode separators, which shifts every line number after them.
                lines = filepath.read_text(encoding="utf-8").split("\n")
            except UnicodeDecodeError as error:
                raise CodeError("%s is not valid UTF-8: %s", obj.path, error, file=self.get_repo_path(obj)) from error
            self.source_lines_by_file[filepath] = lines
        return lines

    def read_docstring_lines(self, obj: griffe.Object, docstring: griffe.Docstring) -> list[str]:
        """Return the source lines of a docstring, from its opening to its closing quotes, without the quotes.

        Args:
            obj: Module or member of the loaded code whose source file is read, not in a namespace package.
            docstring: The docstring of ``obj``; its line numbers give the lines, and no ``lineno`` gives none.

        Raises:
            CodeError: ``obj`` is in a namespace package, or its file is not valid UTF-8.
        """
        if docstring.lineno is None:
            return []
        lines = self.read_source_lines(obj)[docstring.lineno - 1 : docstring.endlineno or docstring.lineno]
        opening = self.OPENING_QUOTES.match(lines[0])
        if opening is None:
            return lines
        quotes = opening.group(1)
        lines[0] = lines[0][opening.end() :]
        # The closing quotes are the first of their kind on the last line (a docstring cannot hold them unescaped);
        # what follows them, such as a comment, is not part of the docstring.
        closing = re.search(rf"(?<!\\){re.escape(quotes)}", lines[-1])
        if closing is not None:
            lines[-1] = lines[-1][: closing.start()]
        return lines

    @staticmethod
    def find_docstring_holder(obj: griffe.Object) -> griffe.Object:
        """Return the object whose docstring the code reference page shows for an object.

        An overloaded function without a docstring of its own shows the docstring of its first documented overload.

        Args:
            obj: Module or public member.
        """
        if isinstance(obj, griffe.Function) and obj.docstring is None:
            return next((overload for overload in obj.overloads or () if overload.docstring is not None), obj)
        return obj

    def collect_broken_references_of(self, obj: griffe.Object) -> list[BrokenReference]:
        """Return the broken roles and ``code:`` links of the docstring of an object, with their lines.

        The texts scanned are those its code reference page renders (see :class:`ParsedDocstring`), and a link is
        broken when :meth:`find_link_target` finds no code element for it. The docstring is the one the page shows
        (:meth:`find_docstring_holder`). Objects of a namespace package have no single file and are skipped.

        Args:
            obj: Module or public member whose docstring is scanned.

        Raises:
            CodeError: The file is outside the code directory of its package or not valid UTF-8, or a broken reference
                cannot be located in it.
        """
        holder = self.find_docstring_holder(obj)
        docstring = holder.docstring
        if docstring is None or docstring.lineno is None or isinstance(holder.filepath, list):
            return []
        # One (rendered text line holding the link, the link, what it refers to) per broken link, in source order.
        broken_links: list[tuple[str, Link, CodeLinkTarget]] = []
        for text in ParsedDocstring.parse(holder).iter_texts():
            text_lines = text.splitlines()
            for link in MarkdownText(text, use_roles=True).extract_links():
                target = self.find_link_target(link.target, holder)
                if target is not None and target.dotted_path is None:
                    broken_links.append((text_lines[link.line_number - 1].strip(), link, target))
        if not broken_links:
            return []
        file = self.get_repo_path(holder)
        source_lines = self.read_docstring_lines(holder, docstring)
        value_start = docstring.lineno + next(i for i, text in enumerate(source_lines) if text.strip())
        value_lines = [line.strip() for line in docstring.value.splitlines()]
        broken_references: list[BrokenReference] = []
        value_line_index = 0
        for text_line, link, target in broken_links:
            reference_text = link.role_source or link.target
            # A rendered line is a docstring line without its indentation, or without a table item's name and type.
            located_index = next(
                (i for i in range(value_line_index, len(value_lines)) if value_lines[i].endswith(text_line)), None
            )
            if located_index is None:
                raise CodeError("cannot locate %s in the docstring of %s", reference_text, obj.path, file=file)
            value_line_index = located_index
            broken_references.append(
                BrokenReference(
                    reference_text, file, value_start + value_line_index, is_empty_target=target.is_empty_target
                )
            )
        return broken_references

    def collect_docs_lines_of(self, obj: griffe.Object) -> list[DocsLine]:
        """Return the ``Docs:`` lines of the docstring of an object, with their locations in the source file.

        The docstring is the one the page shows (:meth:`find_docstring_holder`).

        Args:
            obj: Module or public member whose docstring is scanned; its source file is read to find the line numbers.
                Objects of a namespace package have no single file and are skipped.

        Raises:
            CodeError: The source file is not valid UTF-8, or a line cannot be located in it.
        """
        holder = self.find_docstring_holder(obj)
        docstring = holder.docstring
        if docstring is None or docstring.lineno is None or isinstance(holder.filepath, list):
            return []
        targets, _ = split_docs_lines(docstring.value)
        if not targets:
            return []
        source_lines = self.read_docstring_lines(holder, docstring)
        line_numbers = [docstring.lineno + i for i, text in enumerate(source_lines) if DOCS_LINE.match(text)]
        file = self.get_repo_path(holder)
        if len(line_numbers) != len(targets):
            raise CodeError("cannot locate Docs: lines of %s", obj.path, file=file)
        return [DocsLine(target, file, line_number) for target, line_number in zip(targets, line_numbers, strict=True)]
