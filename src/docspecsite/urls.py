"""The site's URLs and the resolution of the docs' links to them.

The URL of each page, how one page links to another, and what the links written in the docs point to on the site,
like ``reverse`` and ``resolve`` in ``django.urls``.

Docs: meta/linking.md
"""

import posixpath
import re
import warnings
from collections.abc import Callable, Collection, Container, Mapping
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Protocol
from urllib.parse import quote

from .codeindex import CodeIndex, CodeTarget
from .config import ProjectConfig
from .docs import DOCS_DIR, derive_doc_path, is_docs_asset, is_redirect
from .errors import DocspecsiteWarning
from .history import History, Version
from .links import CodeRef, Ref, parse_body_ref
from .markdown import Marker, RenderedLink
from .problems import Problem

URL_SCHEME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
CODE_INDEX_DOC = "reference/code/index.md"
STATUS_PAGE = "status.html"
"""Site path of the status page, the index page of every doc's status; every page links to it when it is built."""

TAG_PAGES_DIR = "tags/"
"""Site directory of the index pages of the tags."""

COMPONENT_PAGES_DIR = "components/"
"""Site directory of the index pages of the components."""

CODE_PAGES_DIR = "reference/code/"
"""Site directory of the code reference pages, one per module."""

VERSIONS_DIR_NAME = "v"
"""Name of the directory beside a doc's page that holds the pages of its versions and their diffs."""

RESERVED_PATH_MESSAGE = "reserved path: the doc's page would take the URL of %s"

MARKERS: Mapping[str, Marker] = MappingProxyType(
    {
        "newer": Marker("newer", "newer doc"),
        "moved": Marker("moved", "→ moved"),
        "code-current": Marker("code-current", "current code — may differ from this version"),
        "code-gone": Marker("code-gone", "no longer exists"),
        "missing": Marker("missing", "doc no longer exists"),
    }
)


def make_doc_url(path: str) -> str:
    """Return the site URL of a doc: ``x/y.md`` becomes ``x/y.html``.

    Args:
        path: Doc path relative to ``docs/``; the URL of its latest page mirrors it.
    """
    return f"{path.removesuffix('.md')}.html"


def make_versions_dir(path: str) -> str:
    """Return the site directory of the version and diff pages of a doc, ``x/y/v/`` for ``x/y.md``.

    Args:
        path: Doc path relative to ``docs/``; the directory sits beside its page.
    """
    return f"{path.removesuffix('.md')}/{VERSIONS_DIR_NAME}/"


def find_reserved_owner(path: str, doc_paths: Container[str]) -> str | None:
    """Return which generated pages a doc's page would take the URL of, or None when the doc's path is not reserved.

    Reserved are the status page's path, every path under the tag, component and code reference page directories but
    the code reference's entry page, and every path under the version page directory of another doc. The result
    names the pages for the user, such as ``the status page``.

    Docs: architecture/docs-tooling.md#output-layout

    Args:
        path: Doc path relative to ``docs/``.
        doc_paths: Paths of every doc, relative to ``docs/``; a doc owns the version page directory beside its page.
    """
    url = make_doc_url(path)
    if url == STATUS_PAGE:
        return "the status page"
    if url.startswith(TAG_PAGES_DIR):
        return "the tag pages"
    if url.startswith(COMPONENT_PAGES_DIR):
        return "the component pages"
    if url.startswith(CODE_PAGES_DIR) and path != CODE_INDEX_DOC:
        return "the code reference pages"
    for directory in PurePosixPath(path).parents:
        owner_path = f"{directory.parent}.md"
        if directory.name == VERSIONS_DIR_NAME and directory.parent.name and owner_path in doc_paths:
            return f"the version pages of {DOCS_DIR}{owner_path}"
    return None


def map_reserved_owners(doc_paths: Collection[str]) -> dict[str, str]:
    """Return which generated pages the page of each doc at a reserved path would take the URL of, by doc path.

    The owners are named as the ``find_reserved_owner`` function names them.

    Args:
        doc_paths: Paths of every doc, relative to ``docs/``; docs at paths that are not reserved get no entry.
    """
    return {path: owner for path in doc_paths if (owner := find_reserved_owner(path, doc_paths)) is not None}


def make_version_url(path: str, vid: str) -> str:
    """Return the site URL of the page of a version of a doc.

    Args:
        path: Doc path relative to ``docs/``; the version pages sit in a ``v/`` directory beside its page.
        vid: :attr:`Version.short_id <docspecsite.history.Version.short_id>` of the version: a short commit SHA hash,
            or ``worktree`` for the working copy.
    """
    return f"{make_versions_dir(path)}{vid}.html"


def make_diff_url(path: str, vid: str) -> str:
    """Return the site URL of the diff page of a version of a doc.

    Args:
        path: Doc path relative to ``docs/``; the diff page sits beside its version pages.
        vid: :attr:`Version.short_id <docspecsite.history.Version.short_id>` of the newer version of the diff: a short
            commit SHA hash, or ``worktree``.
    """
    return f"{make_versions_dir(path)}{vid}.diff.html"


def is_usable_tag(tag: str) -> bool:
    """Return whether a tag can name an index page file.

    It cannot contain ``/``, which would make a subdirectory, or NUL.

    Args:
        tag: Tag value from a doc's ``tags`` front matter.
    """
    return "/" not in tag and "\0" not in tag


def make_tag_url(tag: str) -> str:
    """Return the site path of the index page of a tag, ``tags/<tag>.html``.

    It is built from the decoded tag; see :func:`is_usable_tag`.

    Args:
        tag: Tag value from front matter, unencoded; it should pass :func:`is_usable_tag`.
    """
    return f"{TAG_PAGES_DIR}{tag}.html"


def make_component_url(component_id: str) -> str:
    """Return the site path of the index page of a component, ``components/<id>.html``.

    A ``/`` in the id makes subdirectories.

    Args:
        component_id: Component id from a doc's or code module's ``components``, unencoded.
    """
    return f"{COMPONENT_PAGES_DIR}{component_id}.html"


def encode_href_path(path: str) -> str:
    """Return a site path as an href, with each ``/``-separated part percent-encoded.

    Args:
        path: Unencoded site path, such as a tag or component index URL; ``/`` separators are kept.
    """
    return "/".join(quote(part, safe="") for part in path.split("/"))


def make_code_url(target: CodeTarget) -> str:
    """Return the site URL of the reference page of a code element, with the anchor of its member if it has one.

    Args:
        target: Where the element is shown: its module names the page, its anchor (if any) the member on it.
    """
    url = f"{CODE_PAGES_DIR}{target.module}.html"
    return f"{url}#{target.anchor}" if target.anchor else url


def split_suffix(href: str) -> tuple[str, str]:
    """Split an href into its path and its ``?query`` and ``#anchor`` part.

    Either part is empty when the href has none.

    Args:
        href: Link target as written in a doc, or a site-root-relative URL; it is cut at its first ``?`` or ``#``.
    """
    cut = min((i for i in (href.find("?"), href.find("#")) if i >= 0), default=len(href))
    return href[:cut], href[cut:]


def make_relative_url(url: str, page_url: str) -> str:
    """Return a site-root-relative URL made relative to a page.

    External URLs and bare anchors are returned unchanged.

    Args:
        url: Site-root-relative URL to link to, possibly with ``?query`` or ``#anchor``; external URLs and bare
            anchors pass through.
        page_url: Site path of the page that holds the link; the result is relative to its directory.
    """
    if URL_SCHEME_PATTERN.match(url) or url.startswith(("#", "?")):
        return url
    path, suffix = split_suffix(url)
    return posixpath.relpath(path, posixpath.dirname(page_url) or ".") + suffix


class DocPages(Protocol):
    """Which doc pages a build writes, and where links to the docs whose pages it does not write go."""

    def is_built_doc(self, path: str) -> bool:
        """Return whether the build writes the pages of a doc.

        Args:
            path: Doc path relative to ``docs/``.
        """
        ...

    def is_versionless(self, path: str) -> bool:
        """Return whether a doc has only its latest page: a link to it from an old version goes there.

        Args:
            path: Doc path relative to ``docs/``.
        """
        ...

    def locate_doc(self, path: str) -> str | None:
        """Return the URL a link to a doc goes to, external for a doc whose pages are not built; None for text.

        Args:
            path: Doc path relative to ``docs/``.
        """
        ...


class Resolver:
    """Resolver of the links of doc versions to hrefs and markers; it issues warnings about unresolvable links."""

    # Existing paths
    dirs: frozenset[str]
    """Repo paths of the directories that hold a file or a doc."""

    files: frozenset[str]
    """Repo paths of the files that exist: the ref's tree and the extra files."""

    # Warnings
    is_dropped_repo_link_reported: bool
    """Whether a repository link turned into plain text has been warned about; only the first one is."""

    issued_warnings: set[str]
    """Texts of the warnings issued so far, each issued once."""

    # Arguments of __init__
    history: History
    """See :meth:`__init__`."""

    code: CodeIndex | None
    """See :meth:`__init__`."""

    config: ProjectConfig
    """See :meth:`__init__`."""

    front_matter_of: Callable[[Version], Mapping[str, object] | None]
    """See :meth:`__init__`."""

    doc_pages: DocPages
    """See :meth:`__init__`."""

    should_warn_on_dropped_repo_link: bool
    """See :meth:`__init__`."""

    def __init__(
        self,
        history: History,
        code: CodeIndex | None,
        config: ProjectConfig,
        front_matter_of: Callable[[Version], Mapping[str, object] | None],
        *,
        doc_pages: DocPages,
        extra_files: frozenset[str] = frozenset(),
        should_warn_on_dropped_repo_link: bool = True,
    ) -> None:
        """Prepare to resolve links against the docs, files and code of the ref.

        Args:
            history: Doc versions at the build ref; decide which docs exist, which version a link from an old version
                goes to, and which commit repository links point at. Its tree gives the existing repo files.
            code: Public code elements that ``code:`` links may name, empty when the code is not loaded; None when the
                code part is not built: ``code:`` links are then code-styled plain text, without a warning.
            config: Settings whose ``source-url`` is the base URL of the repository on its host, to which
                ``tree/<commit>/...`` or ``blob/<commit>/...`` is appended for links to repo files outside the site;
                without it such links are plain text.
            front_matter_of: Gives the front matter of a link's target version, to mark links to redirect docs; None
                when it did not load.
            doc_pages: Tells which docs have their pages built and which have only a latest page, and where a link
                to a doc whose pages are not built goes (plain text without a warning when nowhere).
            extra_files: Repo paths that exist besides the ref's tree: the working-tree non-Markdown files under
                ``docs/`` when building with the working tree, else none.
            should_warn_on_dropped_repo_link: Whether to warn about the first repository link of a latest version
                turned into plain text for want of a ``source-url``; false when the caller reports the missing setting
                itself.
        """
        self.history = history
        self.files = history.tree | extra_files
        self.code = code
        self.config = config
        self.front_matter_of = front_matter_of
        self.issued_warnings = set()
        self.doc_pages = doc_pages
        self.should_warn_on_dropped_repo_link = should_warn_on_dropped_repo_link
        self.is_dropped_repo_link_reported = False
        self.dirs = self.collect_directories([*self.files, *(f"{DOCS_DIR}{path}" for path in history.versions_by_path)])

    @staticmethod
    def collect_directories(paths: list[str]) -> frozenset[str]:
        """Return every directory that contains one of the paths.

        For ``a/b/c`` these are ``a`` and ``a/b``.

        Args:
            paths: Repo-relative file paths, from the tree, the extra files and the docs; only their parent directories
                are returned.
        """
        return frozenset(directory for path in paths for directory in list_ancestor_directories(path))

    def warn(self, version: Version, message: str, *values: object) -> None:
        """Issue a warning about a version if it is the latest version of its doc.

        A warning already issued by this resolver is not issued again.

        Args:
            version: Version holding the problem link; warnings about older versions are dropped.
            message: Static ``%``-style template of what is wrong with the link, prefixed with the doc path and
                version id in the warning.
            values: Values filled into ``message``.
        """
        if not self.history.is_latest(version):
            return
        warning = DocspecsiteWarning("docs/%s@%s: " + message, version.path, version.short_id, *values)
        if str(warning) not in self.issued_warnings:
            self.issued_warnings.add(str(warning))
            warnings.warn(warning, stacklevel=2)

    def resolve_repo_link(self, version: Version, href: str, rest: str) -> RenderedLink:
        """Return a link on the repository host, or plain text if no ``source-url`` is configured.

        The first link of a latest version turned into plain text issues a
        :exc:`~docspecsite.errors.DocspecsiteWarning` naming its version and ``href``, unless
        :attr:`should_warn_on_dropped_repo_link` is false; later ones and those of older versions issue none.

        Args:
            version: Version holding the link; named in the warning, and only a latest version is warned about.
            href: Link as written in the version; named in the warning.
            rest: Path after the source URL, e.g. ``blob/<commit>/<repo path>#anchor``.
        """
        source_url = self.config.source_url
        if source_url:
            return RenderedLink(f"{source_url}/{rest}")
        if (
            self.should_warn_on_dropped_repo_link
            and not self.is_dropped_repo_link_reported
            and self.history.is_latest(version)
        ):
            self.is_dropped_repo_link_reported = True
            self.warn(
                version,
                "%s has no source-url: links to repository files, such as %s, are plain text",
                ProjectConfig.CONFIG_FILE,
                href,
            )
        return RenderedLink(None)


class PageLinks:
    """Resolver of the links of one doc version as they appear on one page."""

    # Constants
    WEB_API_SCHEME_PATTERN = re.compile(r"^web-api:", re.IGNORECASE)
    """Scheme of a link to the web API, shown as plain text."""

    # Arguments of __init__
    resolver: Resolver
    """See :meth:`__init__`."""

    version: Version
    """See :meth:`__init__`."""

    page_url: str
    """See :meth:`__init__`."""

    def __init__(self, resolver: Resolver, version: Version, page_url: str) -> None:
        """Prepare to resolve the links of a version for a page.

        Args:
            resolver: Resolver holding the docs, files and code that links are resolved against, and the warnings
                issued so far.
            version: Version holding the links; relative paths resolve against its doc, it picks the target versions,
                and only warnings about the latest version are issued.
            page_url: Site path of the page being rendered (latest, version or diff page, or the site root for
                site-root-relative URLs); the hrefs are relative to it.
        """
        self.resolver = resolver
        self.version = version
        self.page_url = page_url

    def resolve_link(self, href: str) -> RenderedLink:
        """Resolve a link of the version for the page.

        Returns the link as it is to be rendered. A link that cannot be resolved becomes plain text (no ``href``), with
        a :exc:`~docspecsite.errors.DocspecsiteWarning` if the version is the latest. Web links and bare anchors are
        returned unchanged.

        Args:
            href: Link target as written in the version's body (as
                :meth:`~docspecsite.markdown.MarkdownText.extract_links` returns it).
        """
        if self.WEB_API_SCHEME_PATTERN.match(href):
            return RenderedLink(None)
        ref = parse_body_ref(self.version.path, href, 0)
        if ref is None:
            return RenderedLink(href)
        if isinstance(ref, Problem):
            self.resolver.warn(self.version, "%s", ref.message)
            return RenderedLink(None)
        if isinstance(ref, CodeRef):
            return self.resolve_code_link(ref)
        return self.resolve_path_link(ref, href)

    def resolve_code_link(self, ref: CodeRef) -> RenderedLink:
        """Resolve a ``code:`` link to its reference page, or to plain text with a marker if unknown.

        An older version's link gets the "current code" marker. Without the code part (:attr:`Resolver.code` is None)
        it is plain text in code style, with no marker and no warning.

        Args:
            ref: Parsed ``code:`` link whose dotted path is looked up.
        """
        if self.resolver.code is None:
            return RenderedLink(None, use_code_style=True)
        target = self.resolver.code.get(ref.dotted_path)
        if target is None:
            self.resolver.warn(self.version, "unknown code element: code:%s", ref.dotted_path)
            return RenderedLink(None, (MARKERS["code-gone"],))
        markers = () if self.resolver.history.is_latest(self.version) else (MARKERS["code-current"],)
        return RenderedLink(make_relative_url(make_code_url(target), self.page_url), markers)

    def resolve_path_link(self, ref: Ref, href: str) -> RenderedLink:
        """Resolve a local link.

        It goes to a site page, an asset or the repository host. A target that does not exist becomes plain text with a
        marker. Repository links use the version's commit (the ref's head for the working copy).

        Args:
            ref: Parsed local link; its repo-relative target decides where the link goes.
            href: Link as written in the version; gives the ``?query`` and ``#anchor`` to keep, and the warning text.
        """
        resolver = self.resolver
        path, suffix = split_suffix(href)
        if not path:
            return RenderedLink(href)
        target = ref.target
        # The docs root has no "docs/" prefix to derive from; its doc path is empty, so its index doc is found.
        doc_path = "" if target == DOCS_DIR.removesuffix("/") else derive_doc_path(target)
        if doc_path is not None:
            if target in resolver.dirs:
                doc_path = resolver.history.find_doc_path(doc_path)
            if doc_path in resolver.history.versions_by_path:
                return self.resolve_doc_link(doc_path, suffix)
        commit_sha = self.version.commit.sha if self.version.commit is not None else resolver.history.head
        if target == ".":
            return resolver.resolve_repo_link(self.version, href, f"tree/{commit_sha}{suffix}")
        if target in resolver.dirs:
            return resolver.resolve_repo_link(self.version, href, f"tree/{commit_sha}/{target}{suffix}")
        if target not in resolver.files:
            resolver.warn(self.version, "unresolvable link: %s", href)
            return RenderedLink(None, (MARKERS["missing"],))
        if is_docs_asset(target):
            return RenderedLink(make_relative_url(target.removeprefix(DOCS_DIR) + suffix, self.page_url))
        return resolver.resolve_repo_link(self.version, href, f"blob/{commit_sha}/{target}{suffix}")

    def resolve_doc_link(self, path: str, suffix: str) -> RenderedLink:
        """Resolve a link from the version to a doc.

        It goes to the version current when the linking version was written; from the latest version it goes to the
        latest page. Markers flag newer docs and redirect docs. A doc whose pages are not built is linked where
        :attr:`Resolver.doc_pages` says, or is plain text, with no warning. A versionless doc (the code reference
        index) has no old versions: a link to it from an old version goes to its latest page with the "current code"
        marker.

        Args:
            path: Path of the linked doc relative to ``docs/``; it must be a doc of the history.
            suffix: ``?query`` and ``#anchor`` of the link, appended to the target page URL; may be empty.
        """
        doc_pages = self.resolver.doc_pages
        if not doc_pages.is_built_doc(path):
            url = doc_pages.locate_doc(path)
            return RenderedLink(url + suffix if url is not None else None)
        history = self.resolver.history
        if doc_pages.is_versionless(path) and not history.is_latest(self.version):
            return RenderedLink(
                make_relative_url(make_doc_url(path) + suffix, self.page_url), (MARKERS["code-current"],)
            )
        markers: list[Marker] = []
        if history.is_latest(self.version):
            target_version = history.find_latest(path)
            url = make_doc_url(path)
        else:
            contemporary = history.find_contemporary(path, self.version)
            if contemporary is None:
                target_version = history.find_latest(path)
                url = make_doc_url(path)
                markers.append(MARKERS["newer"])
            else:
                target_version = contemporary
                url = make_version_url(path, contemporary.short_id)
        front_matter = self.resolver.front_matter_of(target_version) or {}
        if is_redirect(front_matter):
            markers.append(MARKERS["moved"])
        return RenderedLink(make_relative_url(url + suffix, self.page_url), tuple(markers))


def list_ancestor_directories(path: str) -> list[str]:
    """Return the ancestor directories of a path, shortest first.

    For ``a/b/c`` these are ``a`` and ``a/b``.

    Args:
        path: Slash-separated file path, repo- or site-relative; an empty result means it has no directory part.
    """
    parts = path.split("/")
    return ["/".join(parts[:i]) for i in range(1, len(parts))]
