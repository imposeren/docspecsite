"""The project's code as the docs see it, and its reference pages.

It knows which dotted paths exist and where they are shown.

Docs: architecture/docs-tooling.md
"""

import posixpath
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from types import MappingProxyType

import griffe
from jinja2 import Template

from .codeindex import CodeIndex, CodeTarget
from .config import ProjectConfig
from .errors import DocspecsiteError
from .markdown import HtmlRenderer, RenderedLink
from .pages import Page, PageLink, create_environment
from .urls import MARKERS, make_code_url, make_doc_url, make_relative_url

type Pieces = tuple[Piece, ...]

DOCS_LINE = re.compile(r"^\s*Docs:\s*(\S+)\s*$")
CODE_INDEX = "reference/code/index.md"
INDEX_TITLES: Mapping[str, str] = MappingProxyType(
    {"index.md": "Home", "reference/index.md": "Reference", CODE_INDEX: "Code reference"}
)


class CodeError(DocspecsiteError):
    """Error for code that cannot be read for the docs, naming its source file in the ``file`` attribute when known."""

    file: str | None
    """See :meth:`.__init__`."""

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

    src: Path
    """The package directory."""

    repo_src: str
    """The code directory containing it, relative to the repo root (POSIX); ``.`` for the root."""


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


def is_public(name: str, obj: griffe.Object) -> bool:
    """Return whether a member is shown: public names, and ``__init__`` when documented.

    Args:
        name: Name of the member in its parent; decides public versus private.
        obj: The member itself; only its docstring is read, for ``__init__``.
    """
    if name == "__init__":
        return obj.docstring is not None
    return not name.startswith("_")


def iter_members(obj: griffe.Object) -> Iterator[griffe.Object]:
    """Return the public members that a class or module defines itself, leaving out aliases and submodules.

    Args:
        obj: Class or module whose own members are listed, in definition order.
    """
    for name, member in obj.members.items():
        if isinstance(member, (griffe.Alias, griffe.Module)) or not is_public(name, member):
            continue
        yield member


class Codebase:
    """The project's code as docspecsite sees it.

    Its public modules, the repository paths of their packages, the index of ``code:`` link targets and the ``Docs:``
    lines of its docstrings.
    """

    # Constants
    CLOSING_QUOTES = re.compile(r'("""|\'\'\')\s*$')
    """Closing quotes of a docstring, with the spaces after them."""

    OPENING_QUOTES = re.compile(r'^\s*[A-Za-z]{0,2}("""|\'\'\')')
    """Opening quotes of a docstring, with its prefix and the indentation before it."""

    # Loaded code
    index: CodeIndex
    """The ``code:`` link targets: every module and public member, by dotted path."""

    modules: list[griffe.Module]
    """The loaded modules, sorted by path."""

    packages_by_name: dict[str, Package]
    """The packages the modules were loaded from, by package name."""

    def __init__(self, modules: list[griffe.Module], packages: list[Package]) -> None:
        """Index the loaded modules.

        Args:
            modules: Loaded modules to index; their public members become code elements, sorted by path.
            packages: Packages the modules were loaded from; used to find the file defining an object.
        """
        self.modules = sorted(modules, key=lambda m: m.path)
        self.packages_by_name = {p.name: p for p in packages}
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

        Args:
            root: Directory holding the code: the repository root, or the code extracted from the ref.
            config: Settings whose :attr:`~docspecsite.config.ProjectConfig.code_dirs` globs are expanded under ``root``
                to find the packages.

        Raises:
            CodeError: A package's code cannot be loaded, such as code that is not valid UTF-8.
            griffe.GriffeError: griffe cannot load a package.
        """
        packages = cls.find_packages(root, config)
        collection = griffe.ModulesCollection()
        modules: list[griffe.Module] = []
        for package in packages:
            try:
                loaded = griffe.load(
                    package.name,
                    search_paths=[package.src.parent],
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
        return cls(modules, packages)

    @staticmethod
    def find_packages(root: Path, config: ProjectConfig) -> list[Package]:
        """Return the packages of the code directories: each ``<code dir>/<pkg>/`` directory with an ``__init__.py``.

        A ``.`` entry of :attr:`~docspecsite.config.ProjectConfig.code_dirs` is the root itself.

        Args:
            root: Directory holding the code: the repository root, or the code extracted from the ref.
            config: Settings whose :attr:`~docspecsite.config.ProjectConfig.code_dirs` globs are expanded under
                ``root``.
        """
        root = root.resolve()
        candidates: set[Path] = set()
        for code_dir_glob in config.code_dirs:
            candidates.update([root] if code_dir_glob == "." else root.glob(code_dir_glob))
        found: list[Package] = []
        for code_dir in sorted(candidates):
            repo_src = code_dir.relative_to(root).as_posix()
            if not (code_dir.is_dir() and config.is_code_dir(repo_src)):
                continue
            for pkg in sorted(code_dir.iterdir()):
                if pkg.is_dir() and (pkg / "__init__.py").is_file():
                    found.append(Package(pkg.name, pkg, repo_src))
        return found

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

    @classmethod
    def walk(cls, obj: griffe.Object) -> Iterator[griffe.Object]:
        """Return every public member of an object, including those of nested classes.

        Args:
            obj: Module or class whose members are walked; members of nested classes follow their class.
        """
        for member in iter_members(obj):
            yield member
            if isinstance(member, griffe.Class):
                yield from cls.walk(member)

    def get_repo_path(self, obj: griffe.Object) -> str:
        """Return the POSIX path of the file defining an object, relative to the repository root.

        Args:
            obj: Loaded object of one of the packages this codebase was loaded from; its top-level package gives the
                ``src`` directory.

        Raises:
            CodeError: ``obj`` is in a namespace package, which has no single file, or its file is outside the code
                directory of its package.
        """
        filepath = obj.filepath
        if isinstance(filepath, list):
            raise CodeError("namespace package has no single file: %s", obj.path)
        package = self.packages_by_name[obj.path.split(".")[0]]
        try:
            package_path = filepath.relative_to(package.src.parent)
        except ValueError as error:
            raise CodeError(
                "the file of %s is outside the code directory of its package: %s", obj.path, filepath
            ) from error
        return posixpath.normpath(posixpath.join(package.repo_src, package_path.as_posix()))

    def collect_docs_lines(self) -> list[DocsLine]:
        """Return every ``Docs:`` line of the docstrings in the loaded code, with its file and line."""
        found: list[DocsLine] = []
        for module in self.modules:
            for obj in [module, *self.walk(module)]:
                found.extend(self.collect_docs_lines_of(obj))
        return found

    def collect_docs_lines_of(self, obj: griffe.Object) -> list[DocsLine]:
        """Return the ``Docs:`` lines of the docstring of an object, with their locations in the source file.

        Args:
            obj: Module or public member whose docstring is scanned; its source file is read to find the line numbers.

        Raises:
            CodeError: The source file is not valid UTF-8, or a line cannot be located in it.
        """
        docstring = obj.docstring
        if docstring is None or docstring.lineno is None:
            return []
        targets, _ = split_docs_lines(docstring.value)
        if not targets or isinstance(obj.filepath, list):
            return []
        try:
            lines = obj.filepath.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError as error:
            raise CodeError("%s is not valid UTF-8: %s", obj.path, error, file=self.get_repo_path(obj)) from error
        first = docstring.lineno
        last = docstring.endlineno or first
        numbers: list[int] = []
        for number in range(first, last + 1):
            text = lines[number - 1]
            if number == first:
                text = self.OPENING_QUOTES.sub("", text)
            if number == last:
                text = self.CLOSING_QUOTES.sub("", text)
            if DOCS_LINE.match(text):
                numbers.append(number)
        if len(numbers) != len(targets):
            raise CodeError("cannot locate Docs: lines of %s", obj.path, file=self.get_repo_path(obj))
        file = self.get_repo_path(obj)
        return [DocsLine(target, file, number) for target, number in zip(targets, numbers, strict=True)]


# --- Code reference pages ---


@dataclass(frozen=True)
class Piece:
    """Piece of rendered signature or docstring text, optionally a link (a page-relative ``href`` attribute)."""

    text: str
    """The text shown."""

    href: str | None = None
    """Where the text links to, relative to the page; None for plain text."""


@dataclass(frozen=True)
class Row:
    """Row of a docstring table: a parameter, return value, exception or similar, with its type and description."""

    name: str
    """Name of the parameter, attribute or similar; empty for an unnamed return value or exception."""

    type: Pieces
    """The annotated type, with links to the project's code; empty when there is none."""

    description_html: str
    """The description, rendered to HTML."""


@dataclass(frozen=True)
class Section:
    """One docstring section under a title, shown as rendered HTML or as a table of rows."""

    title: str
    """Heading of the section; empty for the docstring's leading text."""

    html: str
    """The section's text rendered to HTML; empty for a table."""

    rows: tuple[Row, ...] = ()
    """Rows of the table; empty for a text section."""

    @property
    def named(self) -> bool:
        """Whether the table has a name column (Returns and Raises usually do not)."""
        return any(row.name for row in self.rows)


@dataclass(frozen=True)
class Inherited:
    """Members a class inherits from one of its project-code bases, as links."""

    base: Piece
    """Link to the base class the members come from."""

    members: Pieces
    """Links to the inherited members."""


@dataclass(frozen=True)
class Member:
    """A code element as shown on a module page: signature, docstring sections and, for a class, its members."""

    anchor: str
    """HTML id of the element on the page: its dotted path."""

    name: str
    """The element's own name."""

    kind: str
    """The element's kind as griffe names it, with hyphens for spaces (``class``, ``function``, ``type-alias``)."""

    decorators: tuple[Pieces, ...]
    """The decorators shown above the signature, one per line."""

    signature: Pieces
    """The signature, with links to the project's code."""

    sections: tuple[Section, ...]
    """The rendered sections of the docstring, without its ``Docs:`` lines."""

    docs: Pieces
    """Links to the docs named by the docstring's ``Docs:`` lines."""

    source: str | None
    """URL of the element's source lines on the repository host; None without a ``source-url``."""

    members: tuple[Member, ...] = ()
    """A class's own public members; empty for other elements."""

    inherited: tuple[Inherited, ...] = ()
    """A class's members inherited from project-code bases, by base."""

    overloads: tuple[Pieces, ...] = ()
    """Signatures of a function's overloads; empty without overloads."""


@dataclass(frozen=True)
class Group:
    """Members of one kind on a module page, such as its classes or functions, under a title."""

    title: str
    """Heading of the group, such as "Classes"."""

    members: tuple[Member, ...]
    """The members of that kind, in module order."""


def get_summary(obj: griffe.Object) -> str:
    """Return the first line of the docstring of an object without its ``Docs:`` lines.

    The result is empty when the object has no docstring.

    Args:
        obj: Module whose summary is shown next to its link in a list of submodules or packages.
    """
    if obj.docstring is None:
        return ""
    _, text = split_docs_lines(obj.docstring.value)
    return text.strip().split("\n", 1)[0]


def make_module_link(module: griffe.Module) -> PageLink:
    """Return the link to the reference page of a module, with its summary.

    Args:
        module: Module listed as a child of an index page or a package page.
    """
    return PageLink(module.path, make_code_url(CodeTarget(module.path, None)), get_summary(module))


class CodeReference:
    """The code reference pages of a codebase: a page per module, and the links to its top-level packages."""

    codebase: Codebase
    """See :meth:`.__init__`."""

    config: ProjectConfig
    """See :meth:`.__init__`."""

    blob_base_url: str
    """See :meth:`.__init__`."""

    titles: Mapping[str, str]
    """See :meth:`.__init__`."""

    def __init__(
        self, codebase: Codebase, config: ProjectConfig, blob_base_url: str, titles: Mapping[str, str] = INDEX_TITLES
    ) -> None:
        """Prepare the pages of a codebase.

        Args:
            codebase: Loaded code whose modules get pages.
            config: Settings whose ``code-components`` give each page its components.
            blob_base_url: URL to which a repo-relative file path is appended for the source links; empty leaves the
                source links out.
            titles: Titles of the latest docs by path relative to ``docs/``, for the breadcrumb and the ``Docs:``
                links; a doc missing from it is shown by its path.
        """
        self.codebase = codebase
        self.config = config
        self.blob_base_url = blob_base_url
        self.titles = titles

    @classmethod
    def for_commit(
        cls,
        codebase: Codebase,
        config: ProjectConfig,
        commit: str,
        titles: Mapping[str, str] = INDEX_TITLES,
    ) -> CodeReference:
        """Prepare the pages of a codebase whose source links show the files at a commit.

        Args:
            codebase: Loaded code whose modules get pages.
            config: Settings whose ``code-components`` give each page its components, and whose ``source-url`` is
                the base URL to which ``blob/<commit>/<file>`` is appended for the source links; without it the
                source links are left out.
            commit: Full SHA hash of the build ref's head, so source links show the code the pages were built from.
            titles: Titles of the latest docs by path relative to ``docs/``, for the breadcrumb and the ``Docs:``
                links; a doc missing from it is shown by its path.
        """
        source_url = config.source_url
        blob_base_url = f"{source_url.rstrip('/')}/blob/{commit}" if source_url else ""
        return cls(codebase, config, blob_base_url, titles)

    @cached_property
    def template(self) -> Template:
        """The body template of the module pages (``code_module.html``), loaded when the first page is rendered."""
        return create_environment().get_template("code_module.html")

    def build_module_children(self) -> tuple[PageLink, ...]:
        """Return the links to the top-level packages, listed as the children of ``reference/code/index.md``."""
        return tuple(make_module_link(m) for m in self.codebase.modules if "." not in m.path)

    def build_page(self, module: griffe.Module, described_in: Sequence[PageLink]) -> Page:
        """Build the reference page of a module, listing its public classes, functions and constants.

        Args:
            module: Module the page is for, one of the codebase's modules.
            described_in: Links to the docs whose ``code`` front matter names the module or one of its members.

        Raises:
            CodeError: The module cannot be documented, e.g. griffe cannot resolve one of its names.
        """
        try:
            return CodePage(self, module).build(described_in)
        except griffe.GriffeError as error:
            raise CodeError("cannot document %s: %s", module.path, error) from error


class CodePage:
    """Renderer of one module's reference page; every href it produces is relative to that page."""

    # Constants
    GROUPS = (
        (griffe.Kind.CLASS, "Classes"),
        (griffe.Kind.FUNCTION, "Functions"),
        (griffe.Kind.ATTRIBUTE, "Constants"),
        (griffe.Kind.TYPE_ALIAS, "Type aliases"),
    )
    """Kinds of the module members, in the order the page lists them, with the heading of each group."""

    TABLE_TITLES = MappingProxyType(
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

    # Page
    renderer: HtmlRenderer
    """Renderer of the docstring Markdown, with its links resolved by :meth:`.resolve_link`."""

    url: str
    """Site path of the page."""

    # Arguments of __init__
    reference: CodeReference
    """See :meth:`.__init__`."""

    module: griffe.Module
    """See :meth:`.__init__`."""

    def __init__(self, reference: CodeReference, module: griffe.Module) -> None:
        """Prepare the page of a module.

        Args:
            reference: The code reference the page is part of; gives the codebase (which names are linked, the
                parent packages in the breadcrumb, the submodules listed as children), the settings, the source link
                base, the doc titles and the body template.
            module: Module the page is for, one of the codebase's modules.
        """
        self.reference = reference
        self.module = module
        self.url = make_code_url(CodeTarget(module.path, None))
        self.renderer = HtmlRenderer(self.resolve_link)

    def build(self, described_in: Sequence[PageLink]) -> Page:
        """Build the page: its body, breadcrumb, children and the docs describing the module.

        Args:
            described_in: Links to the docs whose ``code`` front matter names the module or one of its members.
        """
        return Page(
            url=self.url,
            title=self.module.path,
            status="implemented",
            components=self.reference.config.get_components(self.module.path),
            tags=(),
            body_html=self.render_body(),
            breadcrumb=self.build_breadcrumb(),
            children=self.build_children(),
            described_in=tuple(described_in),
        )

    def build_breadcrumb(self) -> tuple[PageLink, ...]:
        """Return the breadcrumb links of the page: the index pages, then the module's parent packages.

        A parent package gets a link only when it is in the code index; the module itself is not linked. The home,
        reference and code index entries fall back to built-in titles when missing from the titles.
        """
        links = [
            PageLink(self.reference.titles.get(path, INDEX_TITLES[path]), make_doc_url(path)) for path in INDEX_TITLES
        ]
        parts = self.module.path.split(".")
        for parent_length in range(1, len(parts)):
            parent = ".".join(parts[:parent_length])
            if self.reference.codebase.index.get(parent) is not None:
                links.append(PageLink(parent, make_code_url(CodeTarget(parent, None))))
        return tuple(links)

    def build_children(self) -> tuple[PageLink, ...]:
        """Return the links to the module's direct submodules, with their summaries."""
        return tuple(
            make_module_link(m)
            for m in self.reference.codebase.modules
            if m.path.rpartition(".")[0] == self.module.path
        )

    def render_body(self) -> str:
        """Return the HTML body of the module page: the module docstring, then its classes, functions and constants."""
        module = self.module
        sections, docs = self.build_docstring(module)
        groups: list[Group] = []
        for kind, title in self.GROUPS:
            members = tuple(self.build_member(m) for m in iter_members(module) if m.kind is kind)
            if members:
                groups.append(Group(title, members))
        return self.reference.template.render(
            sections=sections, docs=docs, groups=groups, source=self.make_source_url(module, whole_file=True)
        )

    def make_href(self, url: str) -> str:
        """Return a site URL as an href relative to this page.

        Args:
            url: Site URL of the link target, relative to the site root.
        """
        return make_relative_url(url, self.url)

    def make_code_href(self, dotted: str) -> str | None:
        """Return the page-relative href of a code element, or None if it is not in the reference.

        Args:
            dotted: Full dotted path of the element, e.g. a name's canonical path or a ``code:`` target.
        """
        target = self.reference.codebase.index.get(dotted)
        return self.make_href(make_code_url(target)) if target else None

    def build_expr_pieces(self, expr: str | griffe.Expr | None) -> Pieces:
        """Return the pieces of a type or value expression, with the names of project code elements linked.

        Args:
            expr: Annotation, default value, base class or decorator to render; a plain string is shown unlinked, and
                None gives no pieces.
        """
        if expr is None:
            return ()
        if isinstance(expr, str):
            return (Piece(expr),)
        pieces: list[Piece] = []
        for part in expr.iterate(flat=True):
            if isinstance(part, griffe.ExprName):
                pieces.append(Piece(part.name, self.make_code_href(part.canonical_path)))
            else:
                pieces.append(Piece(str(part)))
        return tuple(pieces)

    def resolve_link(self, href: str) -> RenderedLink:
        """Resolve a link of a docstring: ``code:`` targets go to the code reference, others stay as written.

        Args:
            href: Percent-decoded target of a link in a docstring.
        """
        if href.lower().startswith("code:"):
            found = self.make_code_href(href[len("code:") :])
            return RenderedLink(found) if found else RenderedLink(None, (MARKERS["code-gone"],))
        return RenderedLink(href)

    def render_markdown(self, text: str) -> str:
        """Return docstring Markdown as HTML with its links resolved; blank text gives an empty string.

        Args:
            text: Markdown of a docstring section or table cell.
        """
        return self.renderer.render(text) if text.strip() else ""

    def make_source_url(self, obj: griffe.Object, *, whole_file: bool = False) -> str | None:
        """Return the URL of the source of an object on the repository host, or None without a ``source-url``.

        Args:
            obj: Module or member whose defining file (and lines) the link points at.
            whole_file: Link to the whole file instead of the lines of ``obj``, as for a module page.
        """
        if not self.reference.blob_base_url or isinstance(obj.filepath, list):
            return None
        url = f"{self.reference.blob_base_url}/{self.reference.codebase.get_repo_path(obj)}"
        if whole_file:
            return url
        if obj.lineno is None:
            return None
        return f"{url}#L{obj.lineno}-L{obj.endlineno or obj.lineno}"

    def build_docstring(self, obj: griffe.Object) -> tuple[tuple[Section, ...], Pieces]:
        """Split the docstring of an object into its rendered sections and the links of its ``Docs:`` lines.

        The ``Docs:`` lines themselves are not part of the sections.

        Args:
            obj: Module or member whose docstring is rendered; its parent context lets griffe parse the sections.
        """
        if obj.docstring is None:
            return (), ()
        targets, text = split_docs_lines(obj.docstring.value)
        docs: list[Piece] = []
        for target in targets:
            path, sep, anchor = target.partition("#")
            docs.append(Piece(self.reference.titles.get(path, path), self.make_href(make_doc_url(path) + sep + anchor)))
        parsed = griffe.parse_google(griffe.Docstring(text, parent=obj), warnings=False)
        return tuple(self.build_section(s) for s in parsed), tuple(docs)

    def build_section(self, section: griffe.DocstringSection) -> Section:
        """Render a parsed docstring section: a table for parameters, returns and similar sections, text otherwise.

        Args:
            section: Section from griffe's Google-style parse of the docstring; its kind picks the table or text
                rendering.
        """
        section_value: object = section.value
        kind = section.kind
        if kind in self.TABLE_TITLES and isinstance(section_value, list):
            rows = [
                Row(
                    item.name if isinstance(item, griffe.DocstringNamedElement) else "",
                    self.build_expr_pieces(item.annotation),
                    self.render_markdown(item.description),
                )
                for item in section_value
                if isinstance(item, griffe.DocstringElement)
            ]
            return Section(self.TABLE_TITLES[kind], "", tuple(rows))
        if isinstance(section_value, griffe.DocstringAdmonition | griffe.DocstringDeprecated):
            return Section(section.title or "", self.render_markdown(section_value.description))
        if kind is griffe.DocstringSectionKind.examples and isinstance(section_value, list):
            parts: list[str] = []
            for item in section_value:
                if isinstance(item, tuple) and len(item) == 2:
                    part_kind, part = item
                    is_code = part_kind is griffe.DocstringSectionKind.examples
                    parts.append(f"```pycon\n{part}\n```" if is_code else str(part))
            return Section(section.title or "Examples", self.render_markdown("\n\n".join(parts)))
        return Section(section.title or "", self.render_markdown(str(section_value)))

    def build_member(self, obj: griffe.Object) -> Member:
        """Describe a code element for rendering: signature, docstring and, for a class, its members.

        Args:
            obj: Public member of the module (or of a class on it); a class's members are described with it.
        """
        overloads: tuple[Pieces, ...] = ()
        if isinstance(obj, griffe.Function) and obj.overloads:
            overloads = tuple(self.build_function_pieces(o) for o in obj.overloads)
            if obj.docstring is None:
                documented = next((o for o in obj.overloads if o.docstring is not None), None)
                sections, docs = self.build_docstring(obj if documented is None else documented)
            else:
                sections, docs = self.build_docstring(obj)
        else:
            sections, docs = self.build_docstring(obj)
        decorators: tuple[Pieces, ...] = ()
        members: tuple[Member, ...] = ()
        inherited: tuple[Inherited, ...] = ()
        if isinstance(obj, griffe.Function):
            decorators = tuple(((Piece("@"), *self.build_expr_pieces(d.value))) for d in obj.decorators)
            signature = self.build_function_pieces(obj)
            sections = self.merge_signature(obj, sections)
        elif isinstance(obj, griffe.Class):
            decorators = tuple(((Piece("@"), *self.build_expr_pieces(d.value))) for d in obj.decorators)
            signature = self.build_class_pieces(obj)
            members = tuple(self.build_member(m) for m in iter_members(obj))
            inherited = self.find_inherited(obj)
        elif isinstance(obj, griffe.Attribute):
            if "property" in obj.labels:
                decorators = ((Piece("@property"),),)
            signature = self.build_attribute_pieces(obj)
        elif isinstance(obj, griffe.TypeAlias):
            signature = (Piece(f"type {obj.name}"), *self.build_type_params(obj.type_parameters), Piece(" = "))
            signature += self.build_expr_pieces(obj.value)
        else:
            signature = (Piece(obj.name),)
        return Member(
            anchor=obj.path,
            name=obj.name,
            kind=str(obj.kind.value).replace(" ", "-"),
            decorators=decorators,
            signature=signature,
            sections=sections,
            docs=docs,
            source=self.make_source_url(obj),
            members=members,
            inherited=inherited,
            overloads=overloads,
        )

    @staticmethod
    def get_star_prefix(kind: griffe.ParameterKind | None) -> str:
        """Return the ``*`` or ``**`` prefix of a variadic parameter's name.

        The result is empty for other kinds of parameter.

        Args:
            kind: Kind of the parameter whose name is being written; None (unknown kind) gives no prefix.
        """
        return (
            "*"
            if kind is griffe.ParameterKind.var_positional
            else "**"
            if kind is griffe.ParameterKind.var_keyword
            else ""
        )

    def build_type_params(self, params: griffe.TypeParameters) -> Pieces:
        """Return the signature pieces of the type parameters of a generic, such as ``[T: int]``.

        The result is empty when there are none.

        Args:
            params: Type parameters of a class, function or type alias, from its PEP 695 declaration.
        """
        if not params:
            return ()
        pieces: list[Piece] = [Piece("[")]
        for parameter_index, param in enumerate(params):
            if parameter_index:
                pieces.append(Piece(", "))
            star = {griffe.TypeParameterKind.type_var_tuple: "*", griffe.TypeParameterKind.param_spec: "**"}
            pieces.append(Piece(star.get(param.kind, "") + param.name))
            if param.annotation is not None:
                pieces += [Piece(": "), *self.build_expr_pieces(param.annotation)]
            if param.default is not None:
                pieces += [Piece(" = "), *self.build_expr_pieces(param.default)]
        pieces.append(Piece("]"))
        return tuple(pieces)

    def build_function_pieces(self, function: griffe.Function) -> Pieces:
        """Return the signature pieces of a function, from ``def`` to its return annotation.

        Args:
            function: Function or method whose signature is rendered; also each overload of an overloaded function.
        """
        prefix = "async def" if "async" in function.labels else "def"
        pieces: list[Piece] = [
            Piece(f"{prefix} {function.name}"),
            *self.build_type_params(function.type_parameters),
            Piece("("),
        ]
        params = list(function.parameters)
        parts: list[Pieces] = []
        star_done = any(p.kind is griffe.ParameterKind.var_positional for p in params)
        for parameter_index, param in enumerate(params):
            if param.kind is griffe.ParameterKind.keyword_only and not star_done:
                parts.append((Piece("*"),))
                star_done = True
            star = self.get_star_prefix(param.kind)
            part: list[Piece] = [Piece(star + param.name)]
            if param.annotation is not None:
                part += [Piece(": "), *self.build_expr_pieces(param.annotation)]
            if param.default is not None and not star:
                part += [
                    Piece(" = " if param.annotation is not None else "="),
                    *self.build_expr_pieces(param.default),
                ]
            parts.append(tuple(part))
            last_positional = (
                parameter_index + 1 == len(params)
                or params[parameter_index + 1].kind is not griffe.ParameterKind.positional_only
            )
            if param.kind is griffe.ParameterKind.positional_only and last_positional:
                parts.append((Piece("/"),))
        for parameter_index, group in enumerate(parts):
            if parameter_index:
                pieces.append(Piece(", "))
            pieces += group
        pieces.append(Piece(")"))
        if function.returns is not None:
            pieces += [Piece(" -> "), *self.build_expr_pieces(function.returns)]
        return tuple(pieces)

    def build_class_pieces(self, class_: griffe.Class) -> Pieces:
        """Return the signature pieces of a class: ``class``, its name, type parameters and bases.

        Args:
            class_: Class whose name, type parameters and bases are rendered.
        """
        pieces: list[Piece] = [Piece(f"class {class_.name}"), *self.build_type_params(class_.type_parameters)]
        if class_.bases:
            pieces.append(Piece("("))
            for base_index, base in enumerate(class_.bases):
                if base_index:
                    pieces.append(Piece(", "))
                pieces += self.build_expr_pieces(base)
            pieces.append(Piece(")"))
        return tuple(pieces)

    def build_attribute_pieces(self, attribute: griffe.Attribute) -> Pieces:
        """Return the signature pieces of an attribute: its name, annotation and value.

        Args:
            attribute: Module constant, class attribute or property; a property's value is not shown.
        """
        pieces: list[Piece] = [Piece(attribute.name)]
        if attribute.annotation is not None:
            pieces += [Piece(": "), *self.build_expr_pieces(attribute.annotation)]
        if attribute.value is not None and "property" not in attribute.labels:
            pieces += [Piece(" = "), *self.build_expr_pieces(attribute.value)]
        return tuple(pieces)

    def merge_signature(self, function: griffe.Function, sections: tuple[Section, ...]) -> tuple[Section, ...]:
        """Return docstring sections with the Parameters and Returns tables completed from the signature of a function.

        Types come from the signature's annotations, descriptions from the docstring.

        Args:
            function: Function whose parameter and return annotations fill the tables' types.
            sections: Sections rendered from the function's docstring; only Parameters and Returns tables change.
        """
        merged: list[Section] = []
        for section in sections:
            if section.title == "Parameters" and not section.html:
                section = Section(section.title, "", self.build_parameter_rows(function, section.rows))
            elif (
                section.title == "Returns"
                and not section.html
                and len(section.rows) == 1
                and function.returns is not None
            ):
                parameter_row = section.rows[0]
                section = Section(
                    section.title,
                    "",
                    (
                        Row(
                            parameter_row.name,
                            self.build_expr_pieces(function.returns),
                            parameter_row.description_html,
                        ),
                    ),
                )
            merged.append(section)
        return tuple(merged)

    def build_parameter_rows(self, function: griffe.Function, documented: tuple[Row, ...]) -> tuple[Row, ...]:
        """Return the rows of the Parameters table of a function: one per parameter, with the documented descriptions.

        Documented names that are not parameters are kept at the end.

        Args:
            function: Function whose parameters give the rows and their order; ``self`` and ``cls`` are left out unless
                documented.
            documented: Rows of the docstring's Parameters table, matched to parameters by name (``*`` prefixes
                ignored).
        """
        by_name = {row.name.lstrip("*"): row for row in documented}
        rows: list[Row] = []
        for param in function.parameters:
            parameter_row = by_name.pop(param.name, None)
            if parameter_row is None and param.name in ("self", "cls"):
                continue
            star = self.get_star_prefix(param.kind)
            annotation = self.build_expr_pieces(param.annotation) if param.annotation is not None else None
            rows.append(
                Row(
                    star + param.name,
                    annotation or (parameter_row.type if parameter_row else ()),
                    parameter_row.description_html if parameter_row else "",
                )
            )
        rows.extend(by_name.values())
        return tuple(rows)

    def find_inherited(self, class_: griffe.Class) -> tuple[Inherited, ...]:
        """Return the members a class inherits from project-code bases, grouped by the base defining them.

        Args:
            class_: Class whose inherited members are listed; members of bases outside the project code are left out.
        """
        try:
            mro = class_.mro()
        except ValueError:
            mro: list[griffe.Class] = []
        seen = set(class_.members)
        found: list[Inherited] = []
        for base in mro:
            base_href = self.make_code_href(base.path)
            if base_href is None:
                continue
            links: list[Piece] = []
            for member in iter_members(base):
                if member.name not in seen:
                    links.append(Piece(member.name, self.make_code_href(member.path)))
            seen.update(base.members)
            if links:
                found.append(Inherited(Piece(base.name, base_href), tuple(links)))
        return tuple(found)
