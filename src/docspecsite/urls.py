"""The site's URLs and the resolution of the docs' links to them.

The URL of each page, how one page links to another, and what the links written in the docs point to on the site,
like ``reverse`` and ``resolve`` in ``django.urls``.

Docs: meta/linking.md
"""

import posixpath
import re
import warnings
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Protocol
from urllib.parse import quote

from .codeindex import CodeIndex, CodeTarget
from .config import ProjectConfig
from .docs import DOCS, is_template
from .errors import DocspecsiteWarning
from .history import History, Version
from .links import CodeRef, Ref, parse_body_ref
from .markdown import Marker, RenderedLink
from .problems import Problem

EXTERNAL = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
CODE_INDEX = "reference/code/index.md"

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


def make_version_url(path: str, vid: str) -> str:
    """Return the site URL of the page of a version of a doc.

    Args:
        path: Doc path relative to ``docs/``; the version pages sit in a ``v/`` directory beside its page.
        vid: :attr:`Version.short_id <docspecsite.history.Version.short_id>` of the version: a short commit SHA hash,
            or ``worktree`` for the working copy.
    """
    return f"{path.removesuffix('.md')}/v/{vid}.html"


def make_diff_url(path: str, vid: str) -> str:
    """Return the site URL of the diff page of a version of a doc.

    Args:
        path: Doc path relative to ``docs/``; the diff page sits beside its version pages.
        vid: :attr:`Version.short_id <docspecsite.history.Version.short_id>` of the newer version of the diff: a short
            commit SHA hash, or ``worktree``.
    """
    return f"{path.removesuffix('.md')}/v/{vid}.diff.html"


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
    return f"tags/{tag}.html"


def make_component_url(component: str) -> str:
    """Return the site path of the index page of a component, ``components/<id>.html``.

    A ``/`` in the id makes subdirectories.

    Args:
        component: Component id from a doc's or code module's ``components``, unencoded.
    """
    return f"components/{component}.html"


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
    url = f"reference/code/{target.module}.html"
    return f"{url}#{target.anchor}" if target.anchor else url


def split_suffix(href: str) -> tuple[str, str]:
    """Split an href into its path and its ``?query`` and ``#anchor`` part.

    Either part is empty when the href has none.

    Args:
        href: Link target as written in a doc, or a site-root-relative URL; it is cut at its first ``?`` or ``#``.
    """
    cut = min((i for i in (href.find("?"), href.find("#")) if i >= 0), default=len(href))
    return href[:cut], href[cut:]


def make_relative_url(url: str, page: str) -> str:
    """Return a site-root-relative URL made relative to a page.

    External URLs and bare anchors are returned unchanged.

    Args:
        url: Site-root-relative URL to link to, possibly with ``?query`` or ``#anchor``; external URLs and bare
            anchors pass through.
        page: Site path of the page that holds the link; the result is relative to its directory.
    """
    if EXTERNAL.match(url) or url.startswith(("#", "?")):
        return url
    path, suffix = split_suffix(url)
    return posixpath.relpath(path, posixpath.dirname(page) or ".") + suffix


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
    dropped_repo_link_reported: bool
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

    warn_on_dropped_repo_link: bool
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
        warn_on_dropped_repo_link: bool = True,
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
            warn_on_dropped_repo_link: Warn about the first repository link of a latest version turned into plain
                text for want of a ``source-url``; false when the caller reports the missing setting itself.
        """
        self.history = history
        self.files = history.tree | extra_files
        self.code = code
        self.config = config
        self.front_matter_of = front_matter_of
        self.issued_warnings = set()
        self.doc_pages = doc_pages
        self.warn_on_dropped_repo_link = warn_on_dropped_repo_link
        self.dropped_repo_link_reported = False
        self.dirs = self.collect_directories([*self.files, *(f"{DOCS}{path}" for path in history.docs)])

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
        :attr:`warn_on_dropped_repo_link` is false; later ones and those of older versions issue none.

        Args:
            version: Version holding the link; named in the warning, and only a latest version is warned about.
            href: Link as written in the version; named in the warning.
            rest: Path after the source URL, e.g. ``blob/<commit>/<repo path>#anchor``.
        """
        source_url = self.config.source_url
        if source_url:
            return RenderedLink(f"{source_url}/{rest}")
        if self.warn_on_dropped_repo_link and not self.dropped_repo_link_reported and self.history.is_latest(version):
            self.dropped_repo_link_reported = True
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
    WEB_API = re.compile(r"^web-api:", re.IGNORECASE)
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
        if self.WEB_API.match(href):
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
        target = self.resolver.code.get(ref.dotted)
        if target is None:
            self.resolver.warn(self.version, "unknown code element: code:%s", ref.dotted)
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
        if (
            target.startswith(DOCS)
            and target in resolver.dirs
            and f"{target}/index.md".removeprefix(DOCS) in resolver.history.docs
        ):
            target = f"{target}/index.md"
        if target.startswith(DOCS) and target.removeprefix(DOCS) in resolver.history.docs:
            return self.resolve_doc_link(target.removeprefix(DOCS), suffix)
        commit = self.version.commit or resolver.history.head
        if target == ".":
            return resolver.resolve_repo_link(self.version, href, f"tree/{commit}{suffix}")
        if target in resolver.dirs:
            return resolver.resolve_repo_link(self.version, href, f"tree/{commit}/{target}{suffix}")
        if target not in resolver.files:
            resolver.warn(self.version, "unresolvable link: %s", href)
            return RenderedLink(None, (MARKERS["missing"],))
        site_path = target.removeprefix(DOCS)
        if target.startswith(DOCS) and not target.endswith(".md") and not is_template(site_path):
            return RenderedLink(make_relative_url(site_path + suffix, self.page_url))
        return resolver.resolve_repo_link(self.version, href, f"blob/{commit}/{target}{suffix}")

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
        markers: list[Marker] = []
        if doc_pages.is_versionless(path) and not history.is_latest(self.version):
            return RenderedLink(
                make_relative_url(make_doc_url(path) + suffix, self.page_url), (MARKERS["code-current"],)
            )
        if history.is_latest(self.version):
            resolved = history.find_latest(path)
            url = make_doc_url(path)
        else:
            contemporary = history.find_contemporary(path, self.version)
            if contemporary is None:
                resolved = history.find_latest(path)
                url = make_doc_url(path)
                markers.append(MARKERS["newer"])
            else:
                resolved = contemporary
                url = make_version_url(path, contemporary.short_id)
        front_matter = self.resolver.front_matter_of(resolved) or {}
        if front_matter.get("status") == "redirect":
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
