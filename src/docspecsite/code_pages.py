"""The `internal` renderer's code reference pages: one page per module of the project's code.

Docs: architecture/docs-tooling.md#code-reference
"""

import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property, partial
from types import MappingProxyType

import griffe
from jinja2 import Template

from .codeindex import CodeTarget
from .coderef import BrokenReference, Codebase, CodeError, ParsedDocstring, split_docs_lines
from .config import ProjectConfig
from .docs import Status
from .errors import DocspecsiteWarning
from .links import EMPTY_CODE_TARGET_MESSAGE
from .markdown import HtmlRenderer, RenderedLink
from .pages import Page, PageLink, create_environment
from .roles import RoleRef
from .urls import CODE_INDEX_DOC, MARKERS, encode_href_path, make_code_url, make_doc_url, make_relative_url

type Pieces = tuple[Piece, ...]

INDEX_TITLES: Mapping[str, str] = MappingProxyType(
    {"index.md": "Home", "reference/index.md": "Reference", CODE_INDEX_DOC: "Code reference"}
)


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
    def has_name_column(self) -> bool:
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

    source_url: str | None
    """URL of the element's source lines on the repository host; None when the reference has no source link base."""

    members: tuple[Member, ...] = ()
    """A class's own public members; empty for other elements."""

    inherited_groups: tuple[Inherited, ...] = ()
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


class CodeReference:
    """The code reference pages of a codebase: a page per module, and the links to its top-level packages."""

    codebase: Codebase
    """See :meth:`__init__`."""

    config: ProjectConfig
    """See :meth:`__init__`."""

    blob_base_url: str
    """See :meth:`__init__`."""

    titles: Mapping[str, str]
    """See :meth:`__init__`."""

    locate_doc: Callable[[str], str | None]
    """See :meth:`__init__`."""

    changed_paths: frozenset[str]
    """See :meth:`__init__`."""

    def __init__(
        self,
        codebase: Codebase,
        config: ProjectConfig,
        blob_base_url: str,
        titles: Mapping[str, str] = INDEX_TITLES,
        *,
        locate_doc: Callable[[str], str | None],
        changed_paths: frozenset[str] = frozenset(),
    ) -> None:
        """Prepare the pages of a codebase.

        Args:
            codebase: Loaded code whose modules get pages.
            config: Settings whose :attr:`~docspecsite.config.ProjectConfig.code_components` give each page its
                components.
            blob_base_url: URL to which a repo-relative file path is appended for the source links; empty leaves the
                source links out.
            titles: Titles of the latest docs by path relative to ``docs/``, for the breadcrumb and the ``Docs:``
                links; a doc missing from it is shown by its path.
            locate_doc: Gives the URL that a ``Docs:`` line links its doc to, from the doc's path relative to
                ``docs/``: site-root-relative for a doc page, or external; None shows the doc's path as text.
            changed_paths: Repo paths of the code files whose contents are not those of the commit the source links
                show, such as files new or changed in the working tree; their pages have no source links.
        """
        self.codebase = codebase
        self.config = config
        self.blob_base_url = blob_base_url
        self.titles = titles
        self.locate_doc = locate_doc
        self.changed_paths = changed_paths

    @classmethod
    def for_commit(
        cls,
        codebase: Codebase,
        config: ProjectConfig,
        commit: str,
        titles: Mapping[str, str] = INDEX_TITLES,
        *,
        locate_doc: Callable[[str], str | None],
        changed_paths: frozenset[str] = frozenset(),
    ) -> CodeReference:
        """Prepare the pages of a codebase whose source links show the files at a commit.

        Args:
            codebase: Loaded code whose modules get pages.
            config: Settings whose :attr:`~docspecsite.config.ProjectConfig.code_components` give each page its
                components, and whose :attr:`~docspecsite.config.ProjectConfig.source_url` is the base URL to which
                ``blob/<commit>/<file>`` is appended for the source links; without it the source links are left out.
            commit: Full SHA hash of the build ref's head, so source links show the code the pages were built from.
            titles: Titles of the latest docs by path relative to ``docs/``, for the breadcrumb and the ``Docs:``
                links; a doc missing from it is shown by its path.
            locate_doc: Gives the URL that a ``Docs:`` line links its doc to, from the doc's path relative to
                ``docs/``: site-root-relative for a doc page, or external; None shows the doc's path as text.
            changed_paths: Repo paths of the code files that differ from those at ``commit``, such as files new or
                changed in the working tree; their pages have no source links.
        """
        source_url = config.source_url
        blob_base_url = f"{source_url}/blob/{commit}" if source_url else ""
        return cls(codebase, config, blob_base_url, titles, locate_doc=locate_doc, changed_paths=changed_paths)

    @cached_property
    def template(self) -> Template:
        """The body template of the module pages (``code_module.html``), loaded when the first page is rendered."""
        return create_environment().get_template("code_module.html")

    def build_doc_link(self, path: str, suffix: str = "") -> PageLink:
        """Return the link to a doc as the code reference shows it.

        It goes where :attr:`locate_doc` says and shows the doc's title; without a URL it is the doc's path as text.

        Args:
            path: Doc path relative to ``docs/``.
            suffix: ``#anchor`` appended to the URL; empty for none.
        """
        url = self.locate_doc(path)
        if url is None:
            return PageLink(path, None)
        return PageLink(self.titles.get(path, path), url + suffix)

    @staticmethod
    def extract_summary(obj: griffe.Object) -> str:
        """Return the first line of the docstring of an object without its ``Docs:`` lines.

        The result is empty when the object has no docstring.

        Args:
            obj: Module or member whose docstring gives the summary.
        """
        if obj.docstring is None:
            return ""
        _, text = split_docs_lines(obj.docstring.value)
        return text.strip().split("\n", 1)[0]

    @classmethod
    def make_module_link(cls, module: griffe.Module) -> PageLink:
        """Return the link to the reference page of a module, with its summary.

        Args:
            module: Module listed as a child of an index page or a package page.
        """
        return PageLink(module.path, make_code_url(CodeTarget(module.path, None)), cls.extract_summary(module))

    def build_module_children(self, parent_path: str = "") -> tuple[PageLink, ...]:
        """Return the links to the modules directly under a package, with their summaries.

        Args:
            parent_path: Dotted path of the package whose submodules are listed; empty lists the top-level packages, the
                children of the code index page.
        """
        return tuple(
            self.make_module_link(m) for m in self.codebase.modules if m.path.rpartition(".")[0] == parent_path
        )

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

    # Arguments of __init__
    reference: CodeReference
    """See :meth:`__init__`."""

    module: griffe.Module
    """See :meth:`__init__`."""

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

    @property
    def url(self) -> str:
        """Site path of the page."""
        return make_code_url(CodeTarget(self.module.path, None))

    def build(self, described_in: Sequence[PageLink]) -> Page:
        """Build the page: its body, breadcrumb, children and the docs describing the module.

        Args:
            described_in: Links to the docs whose ``code`` front matter names the module or one of its members.
        """
        return Page(
            url=self.url,
            title=self.module.path,
            statuses=(Status.IMPLEMENTED,),
            components=self.reference.config.find_components(self.module.path),
            tags=(),
            body_html=self.render_body(),
            breadcrumb=self.build_breadcrumb(),
            children=self.reference.build_module_children(self.module.path),
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

    def render_body(self) -> str:
        """Return the HTML body of the module page: the module docstring, then its classes, functions and constants."""
        module = self.module
        sections, docs = self.build_docstring(module)
        groups: list[Group] = []
        for kind, title in self.GROUPS:
            members = tuple(self.build_member(m) for m in Codebase.iter_members(module) if m.kind is kind)
            if members:
                groups.append(Group(title, members))
        return self.reference.template.render(
            sections=sections, docs=docs, groups=groups, source_url=self.make_source_url(module, link_whole_file=True)
        )

    def make_href(self, url: str) -> str:
        """Return a site URL as an href relative to this page; an external URL is returned unchanged.

        Args:
            url: URL of the link target: relative to the site root, or external.
        """
        return make_relative_url(url, self.url)

    def make_code_href(self, dotted_path: str) -> str | None:
        """Return the page-relative href of a code element, or None if it is not in the reference.

        An element shown on this page gets a bare ``#anchor``.

        Args:
            dotted_path: Full dotted path of the element, e.g. a name's canonical path or a ``code:`` target.
        """
        target = self.reference.codebase.index.get(dotted_path)
        if target is None:
            return None
        if target.module == self.module.path and target.anchor:
            return f"#{target.anchor}"
        return self.make_href(make_code_url(target))

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

    def resolve_link(self, href: str, owner: griffe.Object) -> RenderedLink:
        """Resolve a link of a docstring: ``code:`` targets and Python roles go to the code reference, others stay.

        A role's link text becomes the found element's dotted path, as its :class:`~docspecsite.roles.RoleRef` says.
        A ``code:`` target or a role that the code reference does not show keeps its text and gets the "no longer
        exists" marker; for a role, this also issues a :class:`~docspecsite.errors.DocspecsiteWarning`. A ``code:`` link
        with nothing after the scheme keeps its text with no marker; :meth:`build_docstring` warns about it.

        Args:
            href: Percent-decoded target of a link in a docstring; a Python role's link starts with ``role:``.
            owner: Module or member whose docstring holds the link; a role's relative target is looked up from it.
        """
        target = self.reference.codebase.find_link_target(href, owner)
        if target is None:
            return RenderedLink(href)
        if target.is_empty_target:
            return RenderedLink(None)  # build_docstring warns about it with its place in the source
        if target.dotted_path is None:
            if target.role is not None:
                warnings.warn(
                    DocspecsiteWarning(
                        "unknown code element in the docstring of %s: %s", owner.path, href[len(RoleRef.SCHEME) :]
                    ),
                    stacklevel=1,
                )
            return RenderedLink(None, (MARKERS["code-gone"],))
        code_text = target.role.make_link_text(target.dotted_path) if target.role is not None else None
        return RenderedLink(self.make_code_href(target.dotted_path), code_text=code_text)

    def render_markdown(self, text: str, owner: griffe.Object) -> str:
        """Return docstring Markdown as HTML with its links and Python roles resolved; blank text gives an empty string.

        Args:
            text: Markdown of a docstring section or table cell.
            owner: Module or member whose docstring the text is from; roles with a relative target are looked up from
                it.
        """
        if not text.strip():
            return ""
        return HtmlRenderer(partial(self.resolve_link, owner=owner), use_roles=True).render(text)

    def make_source_url(self, obj: griffe.Object, *, link_whole_file: bool = False) -> str | None:
        """Return the URL of the source of an object on the repository host, or None when there is no such link.

        There is none when the reference has no source link base, when the object has no single file or line, and
        when its file is one of the reference's changed files.

        Docs: architecture/docs-tooling.md#code-reference

        Args:
            obj: Module or member whose defining file (and lines) the link points at.
            link_whole_file: Link to the whole file instead of the lines of ``obj``, as for a module page.
        """
        if (
            not self.reference.blob_base_url
            or isinstance(obj.filepath, list)
            or (not link_whole_file and obj.lineno is None)
        ):
            return None
        repo_path = self.reference.codebase.get_repo_path(obj)
        if repo_path in self.reference.changed_paths:
            return None
        url = f"{self.reference.blob_base_url}/{encode_href_path(repo_path)}"
        return url if link_whole_file else f"{url}#L{obj.lineno}-L{obj.endlineno or obj.lineno}"

    def build_docstring(self, obj: griffe.Object) -> tuple[tuple[Section, ...], Pieces]:
        """Split the docstring of an object into its rendered sections and the links of its ``Docs:`` lines.

        The ``Docs:`` lines themselves are not part of the sections. A ``Docs:`` link shows the doc's title, or the
        doc's path as plain text when :attr:`CodeReference.locate_doc` gives it no URL. Each empty ``code:`` link of
        the docstring issues a :class:`~docspecsite.errors.DocspecsiteWarning` with its place in the source. When the
        docstring's source cannot be scanned for them
        (:meth:`~docspecsite.coderef.Codebase.collect_broken_references_of` raises
        :class:`~docspecsite.coderef.CodeError`), none is reported here (``check`` reports why), and the page is still
        rendered.

        Args:
            obj: Module or member whose docstring is rendered; its parent context lets griffe parse the sections.
        """
        try:
            broken_references = self.reference.codebase.collect_broken_references_of(obj)
        except CodeError:
            # The code check reports why the source cannot be scanned; the page itself does not need the scan.
            broken_references: list[BrokenReference] = []
        for broken in broken_references:
            if broken.is_empty_target:
                warnings.warn(
                    DocspecsiteWarning(
                        "%s:%s: %s; left out", broken.file, broken.line_number, EMPTY_CODE_TARGET_MESSAGE
                    ),
                    stacklevel=1,
                )
        parsed = ParsedDocstring.parse(obj)
        docs: list[Piece] = []
        for target in parsed.docs_targets:
            path, sep, anchor = target.partition("#")
            link = self.reference.build_doc_link(path, sep + anchor)
            docs.append(Piece(link.title, self.make_href(link.url) if link.url is not None else None))
        render = partial(self.render_markdown, owner=obj)
        return tuple(self.build_section(s, render) for s in parsed.sections), tuple(docs)

    def build_section(self, section: griffe.DocstringSection, render: Callable[[str], str]) -> Section:
        """Render a parsed docstring section: a table for parameters, returns and similar sections, text otherwise.

        Args:
            section: Section from griffe's Google-style parse of the docstring; its kind picks the table or text
                rendering.
            render: Function rendering the docstring's Markdown, of a section or a table cell, to HTML.
        """
        items = ParsedDocstring.get_table_items(section)
        if items is not None:
            rows = [
                Row(
                    item.name if isinstance(item, griffe.DocstringNamedElement) else "",
                    self.build_expr_pieces(item.annotation),
                    render(item.description),
                )
                for item in items
            ]
            return Section(ParsedDocstring.TABLE_TITLES[section.kind], "", tuple(rows))
        return Section(ParsedDocstring.get_section_title(section), render(ParsedDocstring.get_section_text(section)))

    def build_member(self, obj: griffe.Object) -> Member:
        """Describe a code element for rendering: signature, docstring and, for a class, its members.

        Args:
            obj: Public member of the module (or of a class on it); a class's members are described with it.
        """
        overloads: tuple[Pieces, ...] = ()
        if isinstance(obj, griffe.Function):
            overloads = tuple(self.build_function_pieces(o) for o in obj.overloads or ())
        sections, docs = self.build_docstring(Codebase.find_docstring_holder(obj))
        decorators: tuple[Pieces, ...] = ()
        members: tuple[Member, ...] = ()
        inherited_groups: tuple[Inherited, ...] = ()
        if isinstance(obj, griffe.Function):
            decorators = tuple(((Piece("@"), *self.build_expr_pieces(d.value))) for d in obj.decorators)
            signature = self.build_function_pieces(obj)
            sections = self.merge_signature(obj, sections)
        elif isinstance(obj, griffe.Class):
            decorators = tuple(((Piece("@"), *self.build_expr_pieces(d.value))) for d in obj.decorators)
            signature = self.build_class_pieces(obj)
            members = tuple(self.build_member(m) for m in Codebase.iter_members(obj))
            inherited_groups = self.find_inherited(obj)
        elif isinstance(obj, griffe.Attribute):
            if self.is_property(obj):
                decorators = ((Piece("@cached_property" if "cached" in obj.labels else "@property"),),)
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
            source_url=self.make_source_url(obj),
            members=members,
            inherited_groups=inherited_groups,
            overloads=overloads,
        )

    @staticmethod
    def is_property(attribute: griffe.Attribute) -> bool:
        """Return whether an attribute is a property, shown with its decorator and without its value.

        A ``functools.cached_property`` counts as one; it is shown as ``@cached_property``.

        Args:
            attribute: Module constant, class attribute or property.
        """
        return "property" in attribute.labels

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
            star_prefixes = {griffe.TypeParameterKind.type_var_tuple: "*", griffe.TypeParameterKind.param_spec: "**"}
            pieces.append(Piece(star_prefixes.get(param.kind, "") + param.name))
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
        has_star = any(p.kind is griffe.ParameterKind.var_positional for p in params)
        for parameter_index, param in enumerate(params):
            if param.kind is griffe.ParameterKind.keyword_only and not has_star:
                parts.append((Piece("*"),))
                has_star = True
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
            is_last_positional = (
                parameter_index + 1 == len(params)
                or params[parameter_index + 1].kind is not griffe.ParameterKind.positional_only
            )
            if param.kind is griffe.ParameterKind.positional_only and is_last_positional:
                parts.append((Piece("/"),))
        for part_index, part_pieces in enumerate(parts):
            if part_index:
                pieces.append(Piece(", "))
            pieces += part_pieces
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
        if attribute.value is not None and not self.is_property(attribute):
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
                returns_row = section.rows[0]
                section = Section(
                    section.title,
                    "",
                    (
                        Row(
                            returns_row.name,
                            self.build_expr_pieces(function.returns),
                            returns_row.description_html,
                        ),
                    ),
                )
            merged.append(section)
        return tuple(merged)

    def build_parameter_rows(self, function: griffe.Function, documented_rows: tuple[Row, ...]) -> tuple[Row, ...]:
        """Return the rows of the Parameters table of a function: one per parameter, with the documented descriptions.

        Documented names that are not parameters are kept at the end.

        Args:
            function: Function whose parameters give the rows and their order; ``self`` and ``cls`` are left out unless
                documented.
            documented_rows: Rows of the docstring's Parameters table, matched to parameters by name (``*`` prefixes
                ignored).
        """
        by_name = {row.name.lstrip("*"): row for row in documented_rows}
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
        seen_names = set(class_.members)
        inherited_groups: list[Inherited] = []
        for base in mro:
            base_href = self.make_code_href(base.path)
            # Names of a base that is not shown (a private mixin) still hide those of later bases, as in Python.
            hidden_names = seen_names.copy()
            seen_names.update(base.members)
            if base_href is None:
                continue
            links: list[Piece] = []
            for member in Codebase.iter_members(base):
                if member.name not in hidden_names:
                    links.append(Piece(member.name, self.make_code_href(member.path)))
            if links:
                inherited_groups.append(Inherited(Piece(base.name, base_href), tuple(links)))
        return tuple(inherited_groups)
