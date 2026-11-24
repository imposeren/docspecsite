"""The `internal` renderer: docspecsite's own pages for every doc version, diff, code module and index.

It renders with markdown-it-py and Jinja, keeps the rendered bodies in a cache between builds, and maps each link
target to a relative ``<path>.html`` href or a flat code page URL.

Docs: architecture/site.md#the-internal-renderer
"""

import posixpath
import warnings
from collections.abc import Callable, Container, Iterable, Mapping
from dataclasses import replace
from functools import cached_property, partial
from html import escape
from pathlib import Path
from types import MappingProxyType
from typing import assert_never

import griffe

from .cache import BodyCache
from .codeindex import CodeIndex, CodeTarget
from .coderef import CodeReference
from .diskcache import CacheRoot
from .docs import DOCS_DIR, DocStatus, is_redirect, make_string_tuple
from .errors import DocspecsiteError, DocspecsiteWarning
from .history import Version
from .index_pages import IndexRenderer
from .links import list_front_matter_paths
from .markdown import HtmlRenderer, MarkdownText, RenderedLink
from .pages import (
    OldBanner,
    Page,
    PageLink,
    PickerEntry,
    RedirectNotice,
    Templates,
    build_breadcrumb,
    load_static_files,
    make_picker_label,
)
from .renderers import VENDOR_ENV, PageCount, PageCountLabel, PreparedSite, RenderedSite, SiteRenderer, stage_file
from .text import make_unified_diff
from .urls import (
    CODE_INDEX_DOC,
    COMPONENT_PAGES_DIR,
    RESERVED_PATH_MESSAGE,
    STATUS_PAGE,
    TAG_PAGES_DIR,
    CodeElementTarget,
    DocTarget,
    FileTarget,
    LinkTarget,
    PageLinks,
    ResolvedLink,
    UrlTarget,
    is_relative_down,
    list_ancestor_directories,
    make_code_url,
    make_diff_url,
    make_doc_url,
    make_relative_url,
    make_version_url,
)

# A built page: its name in error lines, and the page.
type BuiltPage = tuple[str, Page]

# A page not built yet: its name in error lines, and how to build it.
type Pending = tuple[str, Callable[[], Page]]


class ReservedPathError(DocspecsiteError):
    """Error for a doc whose page would take the URL of a generated page."""


class InternalRenderer(SiteRenderer):
    """The `internal` renderer."""

    def render(self, site: PreparedSite) -> RenderedSite:
        """Return the site's files, made by one :class:`InternalSite` from the prepared input.

        Args:
            site: The docs, code, links and files the build front prepared.
        """
        return InternalSite(site).run()


class InternalSite:
    """One site made by the `internal` renderer: the pages built from the prepared input and the files staged."""

    # Paths
    ROOT_PAGE = "index.html"
    """Root-level page: a URL resolved "as seen from" it stays site-root-relative."""

    # HTML
    MERMAID_MARK = '<pre class="mermaid">'
    """Start of a Mermaid diagram in a rendered page body."""

    # Helpers
    cache: BodyCache
    """Cache of the rendered page bodies."""

    templates: Templates
    """Templates the pages are rendered with."""

    # Output
    page_urls: list[str]
    """Site paths of the pages written to the site files."""

    site_files: dict[str, Path]
    """Staged files of the site made so far, by site path."""

    # Arguments of __init__
    site: PreparedSite
    """See :meth:`__init__`."""

    def __init__(self, site: PreparedSite) -> None:
        """Prepare to make the site's pages.

        Args:
            site: The docs, code, links and files the build front prepared.
        """
        self.site = site
        self.cache = BodyCache(site.cache_dir, CacheRoot.compute_fingerprint(), self.parts_label)
        self.templates = Templates()
        self.page_urls = []
        self.site_files = {}

    @property
    def parts_label(self) -> str:
        """The names of the parts built, sorted and joined by ``+``, e.g. ``code+docs``."""
        return "+".join(sorted(self.site.docs.parts))

    @property
    def code_index(self) -> CodeIndex:
        """The code elements that ``code:`` links lead to, as the resolver looked them up.

        Raises:
            RuntimeError: The code part is not built, so no link has a code element target.
        """
        code = self.site.resolver.code
        if code is None:
            raise RuntimeError("a code element target without the code part")
        return code

    # --- links ---

    def make_href(self, target: LinkTarget, page_url: str) -> str:
        """Return the href of a link target on a page.

        A doc's latest page is ``<path>.html``, a version's page ``<path>/v/<short-id>.html``, a code element's place
        is on its module's flat page; these and copied files are linked relative to the page. Other URLs are kept.

        Args:
            target: Where the link goes, as the resolver gives it.
            page_url: Site path of the page holding the link (latest, version or diff page, or the site root for
                site-root-relative URLs).
        """
        match target:
            case DocTarget(path=path, version=version, suffix=suffix):
                url = (make_doc_url(path) if version is None else make_version_url(path, version.short_id)) + suffix
            case CodeElementTarget(dotted_path=dotted_path):
                url = make_code_url(self.code_index[dotted_path])
            case FileTarget(site_url=site_url):
                url = site_url
            case UrlTarget(url=kept_url):
                return kept_url
            case _:
                assert_never(target)
        return make_relative_url(url, page_url)

    def render_link(self, link: ResolvedLink, page_url: str) -> RenderedLink:
        """Return how a resolved link is rendered on a page.

        Args:
            link: The link's target and markers.
            page_url: Site path of the page holding the link; the href is relative to it.
        """
        href = self.make_href(link.target, page_url) if link.target is not None else None
        return RenderedLink(href, link.markers, link.use_code_style)

    def locate_doc(self, path: str) -> str | None:
        """Return the URL a link to a doc goes to, or None to show the link as text.

        It is the doc's latest page, site-root-relative, when its pages are built, else where
        :meth:`~docspecsite.renderers.SiteDocs.locate_unbuilt_doc` says. A doc missing from the history has no page
        anywhere: None.

        Args:
            path: Doc path relative to ``docs/``, e.g. from a ``Docs:`` line or of a doc linking to another.
        """
        docs = self.site.docs
        if path not in docs.history.versions_by_path:
            return None
        if docs.is_built_doc(path):
            return make_doc_url(path)
        return docs.locate_unbuilt_doc(path)

    @cached_property
    def doc_paths_by_url(self) -> Mapping[str, str]:
        """Doc paths relative to ``docs/`` by the URL of their latest page, for every doc of the history.

        Kept once for the build: every page's breadcrumb looks its links up in it.
        """
        return MappingProxyType({make_doc_url(path): path for path in self.site.docs.history.versions_by_path})

    def limit_breadcrumb(
        self, breadcrumb: Iterable[PageLink], module_urls: Container[str] = frozenset()
    ) -> tuple[PageLink, ...]:
        """Return breadcrumb links without those to pages that do not exist, and with those to unbuilt docs as text.

        A link to a doc whose pages this build does not write keeps its title, without a URL.

        Args:
            breadcrumb: Links of a page's breadcrumb, to docs and to module pages.
            module_urls: URLs of the module pages of the code reference; links to them and links without a URL are
                kept, links to other URLs that are no doc's are left out.
        """
        links: list[PageLink] = []
        for link in breadcrumb:
            if link.url is None or link.url in module_urls:
                links.append(link)
                continue
            path = self.doc_paths_by_url.get(link.url)
            if path is not None:
                links.append(link if self.site.docs.is_built_doc(path) else PageLink(link.title, None))
        return tuple(links)

    # --- output ---

    def stage(self, site_path: str, data: bytes) -> None:
        """Stage a file of the site, replacing one staged at the same site path before.

        Args:
            site_path: Path of the file in the site.
            data: Contents of the file.
        """
        self.site_files[site_path] = stage_file(self.site.staging_dir, data)

    def emit(self, name: str, page: Page, index_urls: Container[str]) -> None:
        """Render a page and stage it as a site file.

        A page whose rendering fails is recorded as an error and not staged.

        Args:
            name: Name of the page in error lines.
            page: Page to render; it is stored at its :attr:`~docspecsite.pages.Page.url`.
            index_urls: URLs of the index pages that were built (status, tag and component pages); links to other tags
                and components are shown as plain text, and the Status link is left out without the status page.
        """
        site_title = self.site.docs.site_title
        html = self.site.attempt(name, lambda: self.templates.render(page, site_title, indexes=index_urls).encode())
        if html is not None:
            self.stage(page.url, html)
            self.page_urls.append(page.url)

    # --- doc pages ---

    def render_body(self, version: Version, page_url: str) -> str:
        """Return the body HTML of a version, with its links resolved for a page.

        Args:
            version: Decodable version whose text is rendered; its blob keys the cache entries. The resolver issues a
                warning for each of its unresolvable links.
            page_url: Site path of the page the body is on (latest or ``/v/`` page); the hrefs are relative to it.
        """
        links = PageLinks(self.site.resolver, version)
        text = self.site.docs.history.read_text(version)
        hrefs = self.cache.get_hrefs(
            version.blob_sha, lambda: [link.target for link in MarkdownText(text).extract_links()]
        )
        links_by_href = {href: self.render_link(links.resolve_link(href), page_url) for href in hrefs}

        def resolve_href(href: str) -> RenderedLink:
            found = links_by_href.get(href)
            return found if found is not None else self.render_link(links.resolve_link(href), page_url)

        minimum = self.site.config.toc_min_headings
        key = f"{self.cache.make_targets_key(links_by_href)}\0toc={minimum}"
        return self.cache.get_body(version.blob_sha, key, lambda: HtmlRenderer(resolve_href, minimum).render(text))

    def build_front_matter_link(self, root_links: PageLinks, front_matter_path: str) -> PageLink | None:
        """Return the page link for a front-matter path of a version, or None if it cannot be linked.

        The URL is site-root-relative.

        Args:
            root_links: Links of the version holding the front matter; the path is resolved as if it were a body link
                of that version, so the target's version and markers match, and links from an old version go to the
                version current then.
            front_matter_path: Path relative to ``docs/`` with an optional ``#anchor``, as written in ``related`` or
                ``redirect_to``.
        """
        path, sep, anchor = front_matter_path.partition("#")
        target = posixpath.normpath(path)
        href = posixpath.relpath(target, posixpath.dirname(root_links.version.path) or ".") + sep + anchor
        rendered_link = self.render_link(root_links.resolve_link(href), self.ROOT_PAGE)
        if rendered_link.href is None:
            return None
        docs = self.site.docs
        return PageLink(
            docs.latest_docs.titles.get(docs.history.find_doc_path(target), front_matter_path),
            rendered_link.href,
            markers=rendered_link.markers,
        )

    def build_front_matter_links(
        self, root_links: PageLinks, front_matter: Mapping[str, object], key: str
    ) -> tuple[PageLink, ...]:
        """Return the page links for a front-matter entry of a version, a path or a list of paths.

        Args:
            root_links: Links of the version holding the front matter; each path is resolved as if it were a body link
                of that version.
            front_matter: Front matter of the version.
            key: Field holding a path or a list of paths, ``related`` or ``redirect_to``; non-strings and unresolvable
                paths are skipped.
        """
        paths = list_front_matter_paths(front_matter, key)
        links = (self.build_front_matter_link(root_links, path) for path in paths)
        return tuple(link for link in links if link is not None)

    def build_doc_pages(self, extra_children: Mapping[str, tuple[PageLink, ...]]) -> list[Pending]:
        """List the pages still to build for every doc.

        These are its latest page, a ``/v/`` page per version and the diff pages. Each is named ``docs/<path>@<id>``
        in error lines. The code reference index has only its latest page: no ``/v/`` page, diff page or picker.
        A doc at a reserved path, whose page would take the URL of a generated page, gets none: one page named
        ``docs/<path>`` fails instead, with a :exc:`ReservedPathError`.

        Args:
            extra_children: Child links shown on a doc's pages, by doc path relative to ``docs/``; the build gives the
                code reference index its top-level packages. Docs missing from it get none.
        """
        docs = self.site.docs
        pages: list[Pending] = []
        for path, owner in sorted(docs.reserved_owners_by_path.items()):
            if docs.is_doc_part_built(path):
                pages.append((f"{DOCS_DIR}{path}", partial(self.refuse_reserved_doc, owner)))
        for path in sorted(filter(docs.is_built_doc, docs.history.versions_by_path)):
            versions = docs.history.versions_by_path[path]
            backlink_list = self.build_backlink_list(path)
            child_list = extra_children.get(path, ())
            if docs.is_versionless(path):
                versions = (docs.history.find_latest(path),)
                picker_entries: tuple[PickerEntry, ...] = ()
            else:
                picker_entries = tuple(
                    PickerEntry(make_picker_label(version), self.make_version_page_url(version), is_current=False)
                    for version in versions
                )
            for version, previous in zip(versions, (*versions[1:], None), strict=True):
                name = f"{DOCS_DIR}{path}@{version.short_id}"
                diff_base = self.find_diff_base(version, previous)
                pages.extend(
                    (
                        name,
                        partial(
                            self.build_doc_page,
                            version,
                            url,
                            backlink_list,
                            child_list,
                            picker_entries,
                            has_diff_page=diff_base is not None,
                        ),
                    )
                    for url in self.list_page_urls(version)
                )
                if diff_base is not None:
                    pages.append((name, partial(self.build_diff_page, version, diff_base)))
        return pages

    def build_backlink_list(self, path: str) -> tuple[PageLink, ...]:
        """Return the links to the latest docs that link to a doc, as its pages show them.

        A linking doc goes where :meth:`locate_doc` says: its page when its pages are built. A doc of the docs part in a
        build without that part (a code-only build, whose entry page shows it) that it gives no URL is its path as text.
        Other linking docs whose pages are not built, such as the code reference's entry page in a build without the
        code part, are left out.

        Args:
            path: Path relative to ``docs/`` of the linked doc.
        """
        docs = self.site.docs
        backlink_list: list[PageLink] = []
        for backlink in docs.latest_docs.backlinks_by_target.get(path, ()):
            source_path = backlink.doc.path
            if not docs.is_built_doc(source_path) and (docs.is_code_doc(source_path) or docs.is_docs_part_built):
                continue
            url = self.locate_doc(source_path)
            backlink_list.append(
                PageLink(backlink.title or source_path, url) if url is not None else PageLink(source_path, None)
            )
        return tuple(backlink_list)

    @staticmethod
    def refuse_reserved_doc(owner: str) -> Page:
        """Fail the page of a doc at a reserved path.

        Args:
            owner: The generated pages whose URL the doc's page would take, for the error message.

        Raises:
            ReservedPathError: Always.
        """
        raise ReservedPathError(RESERVED_PATH_MESSAGE, owner)

    def is_root_doc(self, path: str) -> bool:
        """Return whether the latest page of a doc is also written as the site's root page, ``index.html``.

        Without the docs part the home doc is not built, and the code reference index takes its place; the home doc's
        own page is the root page already.

        Args:
            path: Doc path relative to ``docs/``.
        """
        return self.site.docs.is_code_doc(path) and not self.site.docs.is_docs_part_built

    def list_page_urls(self, version: Version) -> list[str]:
        """Return the site paths the page of a version is written to.

        The latest version is at the doc's URL, and also at the root page for the root doc (see :meth:`is_root_doc`);
        every version but those of a versionless doc has a ``/v/`` page.

        Args:
            version: Version of a doc whose pages are built.
        """
        path = version.path
        urls: list[str] = []
        if self.site.docs.history.is_latest(version):
            urls.append(make_doc_url(path))
            if self.is_root_doc(path):
                urls.append(self.ROOT_PAGE)
        if not self.site.docs.is_versionless(path):
            urls.append(make_version_url(path, version.short_id))
        return urls

    def find_diff_base(self, version: Version, previous: Version | None) -> Version | None:
        """Return the earlier version that the diff page of a version compares it with, or None.

        None means the version has no diff page; a versionless doc has none. A version that is not valid UTF-8 has no
        diff and is no version's previous one; its own pages report it.

        Args:
            version: Version whose diff page is considered.
            previous: The version of the same doc just before ``version``; None for the doc's first version, which has
                no diff page.
        """
        if self.site.docs.is_versionless(version.path) or previous is None:
            return None
        history = self.site.docs.history
        has_diff = history.is_decodable(previous) and history.is_decodable(version)
        return previous if has_diff else None

    def make_version_page_url(self, version: Version) -> str:
        """Return the site path of the page the picker and diff pages link a version to.

        It is the doc's page for the latest version, else the version's ``/v/`` page.

        Args:
            version: Version of a doc whose pages are built.
        """
        if self.site.docs.history.is_latest(version):
            return make_doc_url(version.path)
        return make_version_url(version.path, version.short_id)

    def build_common_page(self, version: Version, url: str) -> Page:
        """Return the page of a version at a URL with the parts every doc page shares.

        The body and the other extras are filled in by the caller.

        Args:
            version: Version shown; gives the title, status, components, tags and breadcrumb, and an old-version banner
                when it is not the latest.
            url: Site path the page is written to: the doc's page, a ``/v/`` page or a diff page.
        """
        docs = self.site.docs
        front_matter = docs.get_front_matter(version) or {}
        old_banner = None
        if not docs.history.is_latest(version):
            old_banner = OldBanner(version, make_doc_url(version.path))
        return Page(
            url=url,
            title=str(front_matter.get("title", version.path)),
            statuses=DocStatus.from_front_matter(front_matter, version.path).values,
            components=make_string_tuple(front_matter.get("components")),
            tags=make_string_tuple(front_matter.get("tags")),
            body_html="",
            breadcrumb=self.limit_breadcrumb(build_breadcrumb(version.path, docs.latest_docs.titles)),
            old_banner=old_banner,
        )

    def build_doc_page(
        self,
        version: Version,
        url: str,
        backlink_list: tuple[PageLink, ...],
        child_list: tuple[PageLink, ...],
        picker_entries: tuple[PickerEntry, ...],
        *,
        has_diff_page: bool,
    ) -> Page:
        """Return the page of a version, with picker, related docs, backlinks and children.

        Args:
            version: Version shown on the page.
            url: Site path the page is written to; the latest version is built at both the doc's URL and its ``/v/``
                URL.
            backlink_list: Links to the latest docs that link to this doc, the same for every version.
            child_list: Extra child links of the doc (the code reference index's packages); empty for other docs.
            picker_entries: The picker's entries for all versions of the doc, the same for every version, with none
                current; the page marks the entry of ``version``. Empty for a doc without a picker.
            has_diff_page: Whether the version has a diff page, which the page links to.
        """
        front_matter = self.site.docs.get_front_matter(version) or {}
        root_links = PageLinks(self.site.resolver, version)
        current_url = self.make_version_page_url(version)
        picker = tuple(PickerEntry(entry.label, entry.url, entry.url == current_url) for entry in picker_entries)
        redirect = None
        if is_redirect(front_matter, version.path):
            kind = str(front_matter.get("redirect_kind", ""))
            redirect = RedirectNotice(
                RedirectNotice.REDIRECT_LABELS.get(kind, kind),
                self.build_front_matter_links(root_links, front_matter, "redirect_to"),
                str(front_matter.get("reason", "")),
            )
        body = self.render_body(version, url)
        return replace(
            self.build_common_page(version, url),
            body_html=body,
            picker=picker,
            diff_url=make_diff_url(version.path, version.short_id) if has_diff_page else None,
            redirect=redirect,
            children=child_list,
            children_heading="Packages",
            related_links=self.build_front_matter_links(root_links, front_matter, "related"),
            backlinks=backlink_list,
            has_mermaid=self.MERMAID_MARK in body,
        )

    def build_diff_page(self, version: Version, previous: Version) -> Page:
        """Return the page showing the diff of a version against its previous version.

        Args:
            version: Version the diff page is for, the newer side.
            previous: Version just before ``version``, as :meth:`find_diff_base` returns it; the older side.
        """
        history = self.site.docs.history
        diff_url = make_diff_url(version.path, version.short_id)
        version_url = self.make_version_page_url(version)
        previous_url = make_version_url(previous.path, previous.short_id)
        previous_href = escape(make_relative_url(previous_url, diff_url))
        version_href = escape(make_relative_url(version_url, diff_url))
        heading = (
            f'<p class="diff-versions">Changes from <a href="{previous_href}">{escape(make_picker_label(previous))}</a>'
            f' to <a href="{version_href}">{escape(make_picker_label(version))}</a></p>\n'
        )
        diff_html = self.cache.get_diff_body(
            previous.blob_sha,
            version.blob_sha,
            lambda: self.render_diff_html(history.read_text(previous), history.read_text(version)),
        )
        body = heading + diff_html
        page = self.build_common_page(version, diff_url)
        return replace(page, title=f"Diff: {page.title}", body_html=body)

    # --- other pages and files ---

    @staticmethod
    def render_diff_html(old: str, new: str) -> str:
        """Return the HTML of the unified diff between two raw Markdown texts.

        The diff text is :func:`~docspecsite.text.make_unified_diff`'s, in a ``<pre class="diff">`` block with added,
        removed and hunk lines marked up.

        Args:
            old: Raw Markdown of the previous version, the ``-`` side of the diff.
            new: Raw Markdown of the version the diff page is for, the ``+`` side.
        """
        html_lines: list[str] = []
        for line in make_unified_diff(old, new):
            text = escape(line)
            if line.startswith("@@"):
                html_lines.append(f'<span class="hunk">{text}</span>')
            elif line.startswith("+"):
                html_lines.append(f'<span class="add">{text}</span>')
            elif line.startswith("-"):
                html_lines.append(f'<span class="del">{text}</span>')
            else:
                html_lines.append(text)
        return '<pre class="diff">' + "\n".join(html_lines) + "</pre>"

    def build_code_pages(self, code_reference: CodeReference) -> list[Pending]:
        """List the pages still to build for the modules of the code.

        Each is named ``reference/code/<module>`` in error lines.

        Args:
            code_reference: Renderer of the code's pages; one page per module of its codebase, whose index maps the
                docs' ``code`` entries to modules.
        """
        codebase = code_reference.codebase
        # Links to the latest docs whose front matter ``code`` names a module, by module path.
        doc_links_by_module: dict[str, list[PageLink]] = {}
        for doc in self.site.docs.latest_docs:
            # Ordered set of the module paths the doc's ``code`` entries name (an unresolved entry as itself).
            modules: dict[str, None] = {}
            for entry in make_string_tuple((doc.front_matter or {}).get("code")):
                target = codebase.index.get(entry)
                modules[target.module if target is not None else entry] = None
            link = code_reference.build_doc_link(doc.path)
            for module in modules:
                doc_links_by_module.setdefault(module, []).append(link)
        module_urls = {make_code_url(CodeTarget(m.path, None)) for m in codebase.modules}

        def make(module: griffe.Module) -> Page:
            page = code_reference.build_page(module, doc_links_by_module.get(module.path, ()))
            return replace(
                page,
                breadcrumb=self.limit_breadcrumb(page.breadcrumb, module_urls),
                has_mermaid=self.MERMAID_MARK in page.body_html,
            )

        return [(f"reference/code/{module.path}", partial(make, module)) for module in codebase.modules]

    def copy_docs_files(self) -> None:
        """Add the copied files under ``docs/`` to the site files, each at its path within ``docs/``.

        They are :attr:`~docspecsite.renderers.PreparedSite.docs_files`. A file whose site path collides with a
        generated file or directory is not copied and a warning is issued.
        """
        generated_paths = set(self.site_files)
        generated_dirs = {parent for path in generated_paths for parent in list_ancestor_directories(path)}
        for path, staged in self.site.docs_files.items():
            site_path = path.removeprefix(DOCS_DIR)
            if (
                site_path in generated_paths
                or site_path in generated_dirs
                or generated_paths.intersection(list_ancestor_directories(site_path))
            ):
                warnings.warn(DocspecsiteWarning("%s: collides with a generated file, not copied", path), stacklevel=1)
                continue
            self.site_files[site_path] = staged

    def load_mermaid_bundle(self) -> dict[str, bytes] | None:
        """Return the Mermaid script and its licence as site files, or None.

        None is returned, with a warning, when the bundle is not found.
        """
        vendor_dir = self.site.vendor_dir
        directory = vendor_dir / "mermaid" if vendor_dir is not None else None
        script_file = directory / "mermaid.min.js" if directory is not None else None
        if directory is None or script_file is None or not script_file.is_file():
            where = f"in {directory}" if directory is not None else f"({VENDOR_ENV} is not set)"
            warnings.warn(
                DocspecsiteWarning("mermaid bundle not found %s; diagrams are shown as source", where), stacklevel=1
            )
            return None
        files = {"assets/mermaid.min.js": script_file.read_bytes()}
        license_file = directory / "LICENSE"
        if license_file.is_file():
            files["assets/mermaid.LICENSE.txt"] = license_file.read_bytes()
        return files

    @staticmethod
    def keep_built_links(page: Page, built_urls: Container[str]) -> Page:
        """Return a page with its version-picker entries and diff link limited to pages that were built.

        Args:
            page: Built page whose picker and diff link may point to pages that failed.
            built_urls: URLs of every page built without error.
        """
        picker = tuple(entry for entry in page.picker if entry.url in built_urls)
        diff_url = page.diff_url if page.diff_url is not None and page.diff_url in built_urls else None
        is_changed = (picker, diff_url) != (page.picker, page.diff_url)
        return replace(page, picker=picker, diff_url=diff_url) if is_changed else page

    @staticmethod
    def strip_mermaid(page: Page) -> Page:
        """Return a page that does not load the Mermaid script.

        Args:
            page: Built page, whose body may hold diagrams; they are then shown as source.
        """
        return replace(page, has_mermaid=False) if page.has_mermaid else page

    def make_code_reference(self) -> CodeReference | None:
        """Return the maker of the code pages, or None when the code is not loaded."""
        site = self.site
        if site.codebase is None:
            return None
        return CodeReference.for_commit(
            site.codebase,
            site.config,
            site.docs.history.head,
            site.docs.latest_docs.titles,
            locate_doc=self.locate_doc,
            changed_paths=site.changed_code_paths,
        )

    def run(self) -> RenderedSite:
        """Build the pages and stage the site's files; a site is made once.

        A page that cannot be built or rendered is left out, through the front's
        :attr:`~docspecsite.renderers.PreparedSite.attempt`.
        """
        site = self.site
        code_reference = self.make_code_reference()
        extra_children = {CODE_INDEX_DOC: code_reference.build_module_children()} if code_reference else {}
        index_renderer = IndexRenderer(site.site_index) if site.site_index is not None else None
        pending = [
            *self.build_doc_pages(extra_children),
            *(self.build_code_pages(code_reference) if code_reference else []),
            *(index_renderer.make_page_makers().items() if index_renderer else []),
        ]
        pages: list[BuiltPage] = []
        for name, make in pending:
            page = site.attempt(name, make)
            if page is not None:
                pages.append((name, page))
        built_urls = frozenset(page.url for _, page in pages)
        pages = [(name, self.keep_built_links(page, built_urls)) for name, page in pages]

        mermaid_files = self.load_mermaid_bundle() if any(page.has_mermaid for _, page in pages) else None
        if mermaid_files is None:
            pages = [(name, self.strip_mermaid(page)) for name, page in pages]
        else:
            for path, data in mermaid_files.items():
                self.stage(path, data)
        index_urls = frozenset(
            page.url
            for _, page in pages
            if page.url == STATUS_PAGE
            or (page.url.startswith((TAG_PAGES_DIR, COMPONENT_PAGES_DIR)) and is_relative_down(page.url))
        )
        for name, page in pages:
            self.emit(name, page, index_urls)
        site_index = site.site_index
        if site_index is not None:
            llms = site.attempt("llms.txt", lambda: site_index.make_llms_txt(site.docs.site_summary).encode())
            if llms is not None:
                self.stage("llms.txt", llms)
        for path, data in load_static_files().items():
            self.stage(path, data)
        self.copy_docs_files()
        self.cache.prune()
        return RenderedSite(
            files=self.site_files,
            page_paths=frozenset(self.page_urls),
            counts=(
                PageCount(PageCountLabel.RENDERED, self.cache.miss_count),
                PageCount(PageCountLabel.FROM_CACHE, self.cache.hit_count),
            ),
        )
