"""The build front of the static site: it reads a ref's history, hands it to a site renderer and writes the site.

Docs: architecture/site.md#build-front
Docs: architecture/docs-tooling.md
"""

import os
import posixpath
import warnings
from collections.abc import Callable, Generator, Iterable, Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
from functools import cached_property
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from types import MappingProxyType
from typing import assert_never

import griffe

from .coderef import Codebase, CodeError
from .config import ConfigError, ProjectConfig
from .diskcache import CacheRoot
from .docs import DOCS_DIR, DocStatus, Layer, Status, derive_doc_path, is_doc, is_template
from .errors import DOCSPECSITE_WARNINGS, DocspecsiteError, DocspecsiteWarning, InternalErrorWarning
from .git import Git, TreeEntry, WorktreeFile
from .history import History
from .indexes import IndexEntry, SiteIndex
from .parts import Part
from .renderers import VENDOR_ENV, PageCount, PreparedSite, RendererName, SiteRenderer, stage_file
from .sitedocs import SiteDocs
from .symlinks import (
    CODE_DIR_TO_FILE_REASON,
    LEFT_OUT_SYMLINK_REASON,
    GitSeenFiles,
    SymlinkFollower,
    SymlinkKind,
    TreeFiles,
)
from .text import NON_UTF8_NAME_MESSAGE, is_utf8_name
from .urls import CODE_INDEX_DOC, CODE_PAGES_DIR, Resolver, is_relative_down, is_usable_tag
from .vocabulary import Vocabulary


class BuildError(DocspecsiteError):
    """Error for a site that cannot be built: an invalid root ``docspecsite.toml``, or a failed strict build."""


@dataclass(frozen=True)
class DocsFile:
    """A file under ``docs/`` that the site copies, and where its contents are read."""

    source_path: str
    """Repo path of the contents: the file's own, or for a file reached through symlinks, the path they lead to."""

    is_in_worktree: bool
    """Whether the contents are read from the working tree; else from the built revision's tree."""


@dataclass(frozen=True)
class BuildResult:
    """Outcome of a site build."""

    page_count: int
    """Pages written to the site."""

    counts: tuple[PageCount, ...]
    """The renderer's labelled counts of the pages, in the order the summary line shows them."""

    errors: tuple[str, ...]
    """One line per :exc:`~docspecsite.errors.DocspecsiteError` of a page that could not be built."""

    failed_count: int
    """Number of pages that failed, through a :exc:`~docspecsite.errors.DocspecsiteError` or an internal error."""


class SiteWriter:
    """The output directory a site is written to, with the manifest of the files the last build wrote there."""

    MANIFEST_FILENAME = ".docspecsite-manifest"
    """Name of the file in the output directory that lists the files the last build wrote."""

    # Resolved
    resolved_out: Path
    """The output directory resolved to follow symlinks: nothing is written or deleted outside of it."""

    # Arguments of __init__
    out: Path
    """See :meth:`__init__`."""

    def __init__(self, out: Path) -> None:
        """Prepare to write below an output directory.

        Args:
            out: Output directory; created on the first write when missing, and holding the manifest of the previous
                build.
        """
        self.out = out
        self.resolved_out = out.resolve()

    def find_outside(self, paths: Iterable[str]) -> list[str]:
        """Return those paths that the write would refuse to write below the output directory.

        :meth:`write` refuses them: they land outside the output directory, also through a symlink.

        Args:
            paths: Site paths of the files about to be written.
        """
        return [path for path in paths if not self.is_inside(path)]

    def write(self, files: Mapping[str, bytes]) -> list[str]:
        """Write the site's files below the output directory and remove files left over from the previous build.

        Only files whose bytes changed are rewritten. ``<out>/.docspecsite-manifest`` lists the files written; nothing
        outside the previous manifest is ever deleted. The leftover files are deleted first, together with the
        directories they leave empty, so a path may turn from a file into a directory, or back, between builds.

        Args:
            files: Every file of the new site, as bytes by site path relative to the output directory; files of the
                previous build not in it are deleted.

        Returns:
            The paths that would land outside the output directory (also through a symlink); they are neither written
            nor deleted.
        """
        self.out.mkdir(parents=True, exist_ok=True)
        manifest = self.out / self.MANIFEST_FILENAME
        previous_paths = manifest.read_text(encoding="utf-8").splitlines() if manifest.is_file() else []
        for path in previous_paths:
            if path not in files and self.is_inside(path):
                self.delete_leftover(path)
        refused_paths: list[str] = []
        for path, data in files.items():
            if self.is_inside(path):
                self.write_if_changed(self.out / path, data)
            else:
                refused_paths.append(path)
        written = sorted(path for path in files if path not in refused_paths)
        self.write_if_changed(manifest, "".join(f"{path}\n" for path in written).encode())
        return refused_paths

    def delete_leftover(self, path: str) -> None:
        """Delete a file of the previous build, and the directories above it that it leaves empty.

        A symlink or a directory at the path is kept, and so is every directory that still holds something; the output
        directory itself is never removed.

        Args:
            path: Site path from the previous manifest, relative to the output directory; it must stay inside it.
        """
        target = self.out / path
        if not target.is_file() or target.is_symlink():
            return
        target.unlink()
        for parent in PurePosixPath(path).parents:
            if parent == PurePosixPath("."):
                break
            try:
                (self.out / parent).rmdir()
            except OSError:
                break  # not empty, or not a directory

    def is_inside(self, path: str) -> bool:
        """Return whether a path stays below the output directory, also after resolving symlinks.

        Args:
            path: Site path to write or delete, relative to the output directory.
        """
        return is_relative_down(path) and (self.resolved_out / path).resolve().is_relative_to(self.resolved_out)

    @staticmethod
    def write_if_changed(target: Path, data: bytes) -> None:
        """Write a file unless it already holds exactly these bytes.

        The modification time of an unchanged file is kept.

        Args:
            target: File in the output directory (a site file or the manifest); parent directories are created.
            data: New contents; when the file already holds exactly them, it is left untouched.
        """
        if target.is_file() and target.read_bytes() == data:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


class SiteBuilder:
    """One site build, the build front: what is read from the ref, handed to the site renderer, and written."""

    # Paths
    CACHE_DIR = ".docspecsite-cache"
    """Directory under the repository root that holds what the build reuses between builds."""

    # Warnings
    LEFT_OUT_WARNING = "%s: %s; left out"
    """Warning template for input the build cannot use, filled with the file's repo path and the reason."""

    UNKNOWN_CODE_COMPONENT_WARNING = '%s: "code-components" of "%s" has an unknown component: "%s"; ignored'

    # Helpers
    cache_fingerprint: str
    """Docspecsite version fingerprint that keys the build's cache entries, computed once per build."""

    git: Git
    """The repository's git."""

    # Read from the ref
    config: ProjectConfig
    """The project settings."""

    docs: SiteDocs
    """The docs at the build ref, with the working-tree docs with :attr:`include_worktree`, and the parts built."""

    # Errors
    errors: list[str]
    """One line per :exc:`~docspecsite.errors.DocspecsiteError` of a page that could not be built, in the order they
    happened.
    """

    failed_names: set[str]
    """Names of the pages and files that failed, through a :exc:`~docspecsite.errors.DocspecsiteError` or an internal
    error.
    """

    hidden_dirs: list[Path]
    """Absolute paths cut from error messages: the repository root's and that of the directory the code is read from."""

    # Arguments of __init__
    root: Path
    """See :meth:`__init__`."""

    include_worktree: bool
    """See :meth:`__init__`."""

    vendor_dir: Path | None
    """See :meth:`__init__`."""

    is_strict: bool
    """See :meth:`__init__`."""

    def __init__(
        self,
        root: Path,
        ref: str,
        *,
        include_worktree: bool,
        vendor_dir: Path | None,
        is_strict: bool,
        parts: frozenset[Part] | None,
    ) -> None:
        """Read the ref's history, project settings and docs, ready to build pages.

        Args:
            root: Repository root; git runs in it, and working-tree files are read from it.
            ref: Revision to build; its history gives the doc versions. The settings always come from the working
                tree's ``docspecsite.toml``.
            include_worktree: Add working-tree docs that differ from ``ref`` as a newest version, and read the code
                and the non-Markdown files under ``docs/`` from the working tree.
            vendor_dir: Directory of the vendored third-party files the site uses; None means there are none.
            is_strict: Raise on the first :exc:`~docspecsite.errors.DocspecsiteError` of a page instead of recording it.
            parts: The parts of the site to build; None means the docs, and the code too when the settings have
                ``code-dirs``.

        Raises:
            BuildError: The settings cannot be read, or the code part is asked for without ``code-dirs``.
        """
        self.root = root
        self.is_strict = is_strict
        self.errors = []
        self.failed_names = set()
        # Absolute paths cut from error messages (never relative ones: "./" would match anywhere).
        self.hidden_dirs = [root.resolve()]
        self.git = Git(root)
        self.include_worktree = include_worktree
        self.vendor_dir = vendor_dir
        loaded_history = History.load(self.git, ref, worktree_root=root if include_worktree else None)
        self.config = self.load_config()
        available_parts = self.get_available_parts()
        if parts is None:
            parts = available_parts
        elif not parts <= available_parts:
            raise BuildError("the code part needs code-dirs in %s", ProjectConfig.CONFIG_FILE)
        history = self.leave_out_non_utf8_docs(loaded_history)
        self.cache_fingerprint = CacheRoot.compute_fingerprint()
        self.docs = SiteDocs(
            history, parts, self.config, cache_dir=root / self.CACHE_DIR, cache_fingerprint=self.cache_fingerprint
        )
        self.warn_non_utf8_docs(loaded_history)
        if not self.docs.is_docs_part_built and CODE_INDEX_DOC not in self.docs.latest_docs.by_path:
            warnings.warn(
                DocspecsiteWarning(
                    "no code reference entry page %s%s: the code-only site has no root page", DOCS_DIR, CODE_INDEX_DOC
                ),
                stacklevel=1,
            )
        if self.is_missing_source_url_reported:
            warnings.warn(
                DocspecsiteWarning(
                    "%s has no source-url: links to repository files cannot be made", ProjectConfig.CONFIG_FILE
                ),
                stacklevel=1,
            )

    @property
    def history(self) -> History:
        """Doc versions at the build ref, with the working-tree docs with :attr:`include_worktree`."""
        return self.docs.history

    @property
    def parts(self) -> frozenset[Part]:
        """The parts of the site this build produces."""
        return self.docs.parts

    @staticmethod
    def compute_repo_path_part(repo_path: str) -> Part:
        """Return the part of the site that a file or directory belongs to, by its repo path.

        A path under the code reference's directory ``docs/reference/code/``, such as an image its entry page shows,
        belongs to the code part, and so does a path outside ``docs/``, which is in the code directories; every other
        path under ``docs/`` belongs to the docs part.

        Docs: architecture/docs-tooling.md#parts

        Args:
            repo_path: Repo path of a doc, another file or a directory.
        """
        if repo_path.startswith(DOCS_DIR) and not repo_path.startswith(f"{DOCS_DIR}{CODE_PAGES_DIR}"):
            return Part.DOCS
        return Part.CODE

    def is_repo_path_part_built(self, repo_path: str) -> bool:
        """Return whether the part of the site that a file or directory belongs to is built.

        Args:
            repo_path: Repo path of a doc, another file or a directory.
        """
        return self.compute_repo_path_part(repo_path) in self.parts

    @staticmethod
    def is_doc_or_template(doc_path: str, *, is_symlink: bool) -> bool:
        """Return whether a file under ``docs/`` is a doc or a doc template, which the site never copies.

        Args:
            doc_path: Path of the file relative to ``docs/``.
            is_symlink: Whether the file is a symlink; a symlink is never a doc.
        """
        return is_template(doc_path) or is_doc(doc_path, is_symlink=is_symlink, is_under_symlinked_dir=False)

    def warn_left_out(self, path: str, reason: str) -> None:
        """Warn that input is left out of the site, when the part it belongs to is built.

        Docs: behavior/commands/build.md#what-the-build-does

        Args:
            path: Repo path of the doc, file or directory left out.
            reason: Why the build cannot use it.
        """
        if self.is_repo_path_part_built(path):
            warnings.warn(DocspecsiteWarning(self.LEFT_OUT_WARNING, path, reason), stacklevel=2)

    @staticmethod
    def leave_out_non_utf8_docs(history: History) -> History:
        """Return a history without the docs whose name is not valid UTF-8.

        No link can name such a doc, and its pages could not be linked to; :meth:`warn_non_utf8_docs` warns about them.

        Docs: behavior/commands/index.md#input-that-cannot-be-used

        Args:
            history: History whose docs are kept when their names are valid UTF-8.
        """
        return replace(
            history,
            versions_by_path=MappingProxyType(
                {path: versions for path, versions in history.versions_by_path.items() if is_utf8_name(path)}
            ),
        )

    def warn_non_utf8_docs(self, history: History) -> None:
        """Warn about each doc whose name is not valid UTF-8, which :meth:`leave_out_non_utf8_docs` leaves out.

        Docs: behavior/commands/index.md#input-that-cannot-be-used

        Args:
            history: History as loaded, before those docs are left out.
        """
        for path in history.versions_by_path:
            if not is_utf8_name(path):
                self.warn_left_out(f"{DOCS_DIR}{path}", NON_UTF8_NAME_MESSAGE)

    @cached_property
    def tree_symlink_follower(self) -> SymlinkFollower:
        """The rule for what a symlink leads to, applied to the built revision's tree."""
        # Every symlink's target is read at once: the follower reads one per symlink it passes, a git process each.
        link_texts_by_sha = self.git.read_blobs(
            entry.blob_sha for entry in self.history.tree.values() if entry.is_symlink
        )
        return SymlinkFollower(TreeFiles(self.history.tree, lambda _shas: link_texts_by_sha))

    @cached_property
    def worktree_symlink_follower(self) -> SymlinkFollower:
        """The rule for what a symlink leads to, applied to the files of the working tree that git sees."""
        seen_paths = frozenset(file.path for file in self.git.list_worktree_files("."))
        return SymlinkFollower(GitSeenFiles(self.root, seen_paths))

    @cached_property
    def docs_files(self) -> Mapping[str, DocsFile]:
        """The files under ``docs/`` that the site copies, by repo path; their site path is that path within ``docs/``.

        These are the files that are not docs or doc templates, from the built revision's tree, or with
        :attr:`include_worktree` from the working tree, where the files git sees count (a file only the tree has
        is read from it). A symlink counts by what it leads to, whatever its name: one to another file is that file,
        and one to a directory gives the files inside it at their paths below the symlink. One that leads to a doc is
        left out without a word, since ``check`` reports it; one that leads out of the repo or to nothing, and a file
        whose name is not valid UTF-8, are left out with a warning.

        Docs: architecture/docs-tooling.md#output-layout
        Docs: behavior/doc-symlinks.md#other-files-under-docs
        """
        # The working tree's file, else the built revision's, by repo path.
        sources_by_path: dict[str, WorktreeFile | TreeEntry] = {file.path: file for file in self.history.worktree_files}
        for path, entry in self.history.tree.items():
            if path.startswith(DOCS_DIR):
                sources_by_path.setdefault(path, entry)
        docs_files: dict[str, DocsFile] = {}
        for path, source in sorted(sources_by_path.items()):
            is_in_worktree = isinstance(source, WorktreeFile)
            if self.is_doc_or_template(path.removeprefix(DOCS_DIR), is_symlink=source.is_symlink):
                continue
            if not is_utf8_name(path):
                self.warn_left_out(path, NON_UTF8_NAME_MESSAGE)
            elif source.is_symlink:
                follower = self.worktree_symlink_follower if is_in_worktree else self.tree_symlink_follower
                docs_files.update(self.follow_docs_symlink(path, follower, is_in_worktree=is_in_worktree))
            else:
                docs_files[path] = DocsFile(path, is_in_worktree)
        return MappingProxyType(docs_files)

    def follow_docs_symlink(self, path: str, follower: SymlinkFollower, *, is_in_worktree: bool) -> dict[str, DocsFile]:
        """Return the files that a path under ``docs/`` gives the site through its symlinks, by repo path.

        A path that leads out of the repo or to nothing gives none, with a warning naming it; a path that leads to a
        doc gives none, without one.

        Docs: behavior/doc-symlinks.md#other-files-under-docs

        Args:
            path: Repo path of a symlink under ``docs/``, or of an entry below a symlinked directory there.
            follower: Rule for what the path leads to, applied where the build reads the path's contents.
            is_in_worktree: Whether the contents are read from the working tree; else from the built revision's tree.
        """
        target = follower.follow(path)
        match target.kind:
            case SymlinkKind.OUT_OF_REPO | SymlinkKind.NOTHING:
                self.warn_left_out(path, LEFT_OUT_SYMLINK_REASON)
                return {}
            case SymlinkKind.DOC:
                return {}
            case SymlinkKind.OTHER_FILE:
                return {path: DocsFile(target.found_path, is_in_worktree)}
            case SymlinkKind.DIRECTORY:
                docs_files: dict[str, DocsFile] = {}
                for name in follower.files.list_dir(target.found_path):
                    child = f"{path}/{name}"
                    if is_utf8_name(name):
                        docs_files.update(self.follow_docs_symlink(child, follower, is_in_worktree=is_in_worktree))
                    else:
                        self.warn_left_out(child, NON_UTF8_NAME_MESSAGE)
                return docs_files
            case _:
                assert_never(target.kind)

    @cached_property
    def built_docs_files(self) -> Mapping[str, DocsFile]:
        """The files of :attr:`docs_files` that belong to the parts being built, which the site copies, by repo path."""
        return MappingProxyType(
            {path: file for path, file in self.docs_files.items() if self.is_repo_path_part_built(path)}
        )

    @cached_property
    def unbuilt_part_files(self) -> frozenset[str]:
        """Repo paths of the files of :attr:`docs_files` that belong to a part not built.

        A link to one goes to the repository host, as the site does not copy it.

        Docs: architecture/docs-tooling.md#parts
        """
        return frozenset(path for path in self.docs_files if not self.is_repo_path_part_built(path))

    @cached_property
    def found_files(self) -> frozenset[str]:
        """Repo paths of the files that a link from a doc finds, besides the docs.

        They are the built revision's files and the files the site copies (:attr:`built_docs_files`), less what the
        site leaves out: under ``docs/``, a file of the tree that the site does not copy is found only when it is a doc
        template or a Markdown file, and never when it is a symlink or its name is not valid UTF-8. A file of a part
        that is not built is not copied but is found, as :attr:`unbuilt_part_files`.

        Docs: behavior/commands/build.md#what-the-build-does
        Docs: architecture/docs-tooling.md#parts
        """
        tree_paths = (
            path
            for path, entry in self.history.tree.items()
            if (doc_path := derive_doc_path(path)) is None
            or (not entry.is_symlink and is_utf8_name(path) and self.is_doc_or_template(doc_path, is_symlink=False))
        )
        return frozenset(tree_paths) | self.built_docs_files.keys() | self.unbuilt_part_files

    def find_changed_code_paths(self, codebase: Codebase) -> frozenset[str]:
        """Return the repo paths of the code files whose contents differ from the built revision's, or that it lacks.

        Without :attr:`include_worktree` the code is read from the built revision, so there are none. A file counts as
        changed as a working-tree doc does: git hashes it to a blob other than the one in the built revision's tree.

        Docs: architecture/docs-tooling.md#code-reference

        Args:
            codebase: Code loaded for the pages, whose module files are compared.
        """
        if not self.include_worktree:
            return frozenset()
        repo_paths: set[str] = set()
        for module in codebase.modules:
            if isinstance(module.filepath, list):
                continue  # a namespace package has no file, and no source link
            try:
                repo_paths.add(codebase.get_repo_path(module))
            except CodeError:
                continue  # its page reports the same error when it makes its source links
        sha_by_path = self.git.hash_files(sorted(repo_paths))
        return frozenset(
            path
            for path, sha in sha_by_path.items()
            if (entry := self.history.tree.get(path)) is None or entry.blob_sha != sha
        )

    def get_available_parts(self) -> frozenset[Part]:
        """Return every part the repo has the prerequisites for: the docs always, the code with ``code-dirs``."""
        return frozenset({Part.DOCS, Part.CODE} if self.config.code_dirs else {Part.DOCS})

    @property
    def is_missing_source_url_reported(self) -> bool:
        """Whether the build warns at its start that the code part is built but the settings have no ``source-url``.

        Then the resolver does not warn again about the links it turns into plain text.
        """
        return self.docs.is_code_part_built and not self.config.source_url

    def attempt[T](self, name: str, make: Callable[[], T]) -> T | None:
        """Call a function and return its result, or None if it raises.

        A :exc:`~docspecsite.errors.DocspecsiteError` (an error in the docs or code being built) is recorded as an error
        line for the page. Any other exception is a bug in docspecsite: an
        :exc:`~docspecsite.errors.InternalErrorWarning` is issued for it while it is being handled, so a warning filter
        that turns it into an exception keeps the original one as its context.
        Warnings that a filter turned into exceptions are not caught.

        Args:
            name: Name of the page or file in error lines and warnings, e.g. ``docs/<path>@<id>``; a failed name is
                counted once.
            make: Builds the page, its HTML or another site file.

        Raises:
            BuildError: In a strict build, for a :exc:`~docspecsite.errors.DocspecsiteError` instead of recording it.
        """
        try:
            return make()
        except DocspecsiteError as error:
            message = self.describe_error(error)
            if self.is_strict:
                raise BuildError("%s: %s", name, message) from error
            self.failed_names.add(name)
            error_line = f"{name}: {message}"
            if error_line not in self.errors:
                self.errors.append(error_line)
            return None
        except Warning:
            raise
        except Exception as error:  # noqa: BLE001 -- a bug in one page is warned about, other pages are still built
            warnings.warn(
                InternalErrorWarning("%s: internal error: %s", name, self.describe_error(error)), stacklevel=1
            )
            self.failed_names.add(name)
            return None

    @staticmethod
    @contextmanager
    def make_warnings_fatal() -> Generator[None]:
        """Turn docspecsite's warnings into exceptions in the block, and the first one raised into a ``BuildError``.

        Raises:
            BuildError: A warning of :data:`~docspecsite.errors.DOCSPECSITE_WARNINGS` was issued in the block.
        """
        with warnings.catch_warnings():
            for category in DOCSPECSITE_WARNINGS:
                warnings.simplefilter("error", category)
            try:
                yield
            except DOCSPECSITE_WARNINGS as warning:
                raise BuildError("strict: %s", warning) from warning

    def describe_error(self, error: Exception) -> str:
        """Return an exception's type and message on one line, without the absolute paths of the build's directories.

        Args:
            error: Exception raised while building a page.
        """
        message = " ".join(str(error).splitlines())
        for directory in self.hidden_dirs:
            message = message.replace(f"{directory}/", "")
        return f"{type(error).__name__}: {message}"

    def load_config(self) -> ProjectConfig:
        """Return the settings from the working tree's ``docspecsite.toml``, whatever ref is built.

        The file is read from disk, never through git, so an older ref is built with today's settings. Each unknown
        setting is ignored with a warning.

        Raises:
            BuildError: The file cannot be read, is not valid TOML, or a setting has an invalid value.
        """
        try:
            return ProjectConfig.load(self.root).require_valid()
        except ConfigError as error:
            raise BuildError(error.message, *error.values) from error

    def load_codebase(self, code_root: Path) -> Codebase | None:
        """Load the project's code from a directory, with a warning about each input it leaves out.

        Returns None, and issues a warning, when the code cannot be read.

        Docs: behavior/commands/index.md#input-that-cannot-be-used

        Args:
            code_root: Directory holding the code directories: the repository root, or the code directories
                extracted from the ref.
        """
        try:
            codebase = Codebase.load(code_root, self.config)
        except (CodeError, griffe.GriffeError) as error:
            warnings.warn(DocspecsiteWarning("cannot load code: %s", error), stacklevel=1)
            return None
        for left_out in codebase.left_out:
            self.warn_left_out(left_out.path, left_out.reason)
        return codebase

    def find_code_dirs(self) -> list[str]:
        """Return the code directories that exist in the ref's tree; ``.`` alone when the root is one of them.

        The settings' code directories (``code-dirs``) are matched against each file's parent directories, and
        against the symlinks, which can stand for a code directory.
        """
        if self.config.is_code_dir("."):
            return ["."]
        directories = {
            directory.as_posix()
            for path in self.history.tree
            for directory in PurePosixPath(path).parents
            if directory.name
        }
        directories.update(path for path, entry in self.history.tree.items() if entry.is_symlink)
        return sorted(directory for directory in directories if self.config.is_code_dir(directory))

    @contextmanager
    def prepare_code_root(self) -> Generator[Path | None]:
        """Provide the directory the code is read from, or None when the code part is not built.

        That is the working tree with :attr:`include_worktree`, or else the ref's code directories extracted to a
        temporary directory that is removed on exit (see :meth:`extract_code`).
        """
        if not self.docs.is_code_part_built:
            yield None
            return
        if self.include_worktree:
            yield self.root
            return
        with TemporaryDirectory(prefix="docspecsite-code-") as tmp:
            self.extract_code(Path(tmp))
            yield Path(tmp)

    def extract_code(self, code_root: Path) -> None:
        """Write the code directories of the built revision into a directory, at their repo paths.

        A code directory that is a symlink is followed within the built revision: the directory it leads to is written
        at its own path, with the symlink to it, so the code is found under the code directory and is at its real path
        for the source links. One that leads to an absolute path, out of the repo or to nothing is left out, and so is
        a symlink in a code directory that points to an absolute path or out of the code directories, each with a
        :class:`~docspecsite.errors.DocspecsiteWarning` naming it.

        Docs: behavior/commands/build.md#what-the-build-does

        Args:
            code_root: Empty directory that receives the code.
        """
        read_dirs: dict[str, None] = {}  # repo paths of the directories to write, each once
        targets_by_link: dict[str, str] = {}  # repo path a code directory symlink leads to, by the symlink's path
        for code_dir in self.find_code_dirs():
            entry = self.history.tree.get(code_dir)
            if entry is None or not entry.is_symlink:
                read_dirs[code_dir] = None
                continue
            target = self.tree_symlink_follower.follow(code_dir)
            match target.kind:
                case SymlinkKind.OUT_OF_REPO | SymlinkKind.NOTHING:
                    self.warn_left_out(code_dir, LEFT_OUT_SYMLINK_REASON)
                case SymlinkKind.DIRECTORY:
                    read_dirs[target.found_path] = None
                    targets_by_link[code_dir] = target.found_path
                case SymlinkKind.DOC | SymlinkKind.OTHER_FILE:
                    self.warn_left_out(code_dir, CODE_DIR_TO_FILE_REASON)
                case _:
                    assert_never(target.kind)
        if not read_dirs:
            return
        for path in self.git.write_files(self.history.head, list(read_dirs), code_root):
            if path in targets_by_link:
                continue  # a code directory inside another, followed by its own rule and linked below
            warnings.warn(
                DocspecsiteWarning("%s: symlink to an absolute path or out of the code directories, left out", path),
                stacklevel=1,
            )
        for link, target in targets_by_link.items():
            link_file = code_root / link
            if link_file.is_symlink():
                continue  # it lies in another code directory, and write_files wrote it there, as the ref has it
            link_file.parent.mkdir(parents=True, exist_ok=True)
            link_file.symlink_to(posixpath.relpath(target, posixpath.dirname(link) or "."))

    def use_known_code_components(self, vocabulary: Vocabulary) -> None:
        """Warn about each unknown ``code-components`` id and leave it out of the settings the code pages read.

        Docs: behavior/commands/build.md#what-the-build-does

        Args:
            vocabulary: The vocabulary of the latest docs, whose components are the known ids.
        """
        checked = self.config.check_code_components(vocabulary.components)
        for key, component in checked.unknown:
            warnings.warn(
                DocspecsiteWarning(self.UNKNOWN_CODE_COMPONENT_WARNING, ProjectConfig.CONFIG_FILE, key, component),
                stacklevel=1,
            )
        self.config = replace(self.config, code_components=checked.known)

    def collect_code_entries(self, codebase: Codebase | None) -> list[IndexEntry]:
        """Return the index entries of the code modules, for the component pages; none when the code is not loaded.

        Each module becomes an entry for its reference page, with its components from the settings'
        ``code-components``.

        Args:
            codebase: The loaded code; None when it is not loaded.
        """
        if codebase is None:
            return []
        return [
            IndexEntry(
                path=m.path,
                title=m.path,
                summary="",
                status=DocStatus((Status.IMPLEMENTED,)),
                layer=Layer.REFERENCE,
                tags=(),
                components=self.config.find_components(m.path),
                is_code_module=True,
            )
            for m in codebase.modules
        ]

    def collect_index_entries(self) -> list[IndexEntry]:
        """Return the index entries of the built latest docs that have front matter, ordered by doc path."""
        return [
            IndexEntry.from_front_matter(doc.path, doc.front_matter)
            for doc in sorted(self.docs.latest_docs, key=lambda doc: doc.path)
            if doc.front_matter is not None and self.docs.is_built_doc(doc.path)
        ]

    def make_site_index(self, codebase: Codebase | None, vocabulary: Vocabulary) -> SiteIndex:
        """Return the index of the site, with the index entries of the built docs and code.

        A warning is issued for each tag that cannot be a file name, and so gets no index page.

        Args:
            codebase: The loaded code, whose modules are listed on the component pages; None when it is not loaded.
            vocabulary: The vocabulary of the latest docs, which orders the status board's milestones.
        """
        entries = self.collect_index_entries()
        tags = sorted({tag for entry in entries for tag in entry.tags})
        for tag in tags:
            if not is_usable_tag(tag):
                warnings.warn(DocspecsiteWarning('tag "%s" cannot be a file name, no index page', tag), stacklevel=1)
        return SiteIndex(entries, self.collect_code_entries(codebase), self.config, self.docs.site_title, vocabulary)

    def stage_docs_files(self, staging_dir: Path) -> dict[str, Path]:
        """Return the file holding each file of :attr:`built_docs_files`, by repo path.

        A file read from the built revision's tree is staged in the staging directory; one read from the working tree
        is that file.

        Args:
            staging_dir: The build's staging directory.
        """
        built_docs_files = self.built_docs_files
        blobs = self.git.read_blobs(
            self.history.tree[docs_file.source_path].blob_sha
            for docs_file in built_docs_files.values()
            if not docs_file.is_in_worktree
        )
        staged_paths: dict[str, Path] = {}
        for path, docs_file in built_docs_files.items():
            if docs_file.is_in_worktree:
                staged_paths[path] = self.root / docs_file.source_path
            else:
                staged_paths[path] = stage_file(staging_dir, blobs[self.history.tree[docs_file.source_path].blob_sha])
        return staged_paths

    def prepare_site(self, code_root: Path | None, staging_dir: Path) -> PreparedSite:
        """Load the code and the links, and return everything the renderer needs.

        Args:
            code_root: Directory the code is read from; None when the code part is not built.
            staging_dir: The build's staging directory, where the renderer and the copied files are staged.
        """
        codebase = None
        if code_root is not None:
            self.hidden_dirs.append(code_root.resolve())
            codebase = self.load_codebase(code_root)
        resolver = Resolver(
            self.history,
            (codebase.index if codebase else MappingProxyType({})) if code_root is not None else None,
            self.config,
            self.docs.get_front_matter,
            doc_pages=self.docs,
            found_files=self.found_files,
            unbuilt_part_files=self.unbuilt_part_files,
            should_warn_on_dropped_repo_link=not self.is_missing_source_url_reported,
        )
        vocabulary = Vocabulary.parse(self.docs.read_latest_text)
        if self.docs.is_code_part_built:
            self.use_known_code_components(vocabulary)
        changed_code_paths = self.find_changed_code_paths(codebase) if codebase else frozenset[str]()
        return PreparedSite(
            docs=self.docs,
            config=self.config,
            resolver=resolver,
            codebase=codebase,
            changed_code_paths=changed_code_paths,
            site_index=self.make_site_index(codebase, vocabulary) if self.docs.is_docs_part_built else None,
            docs_files=self.stage_docs_files(staging_dir),
            vendor_dir=self.vendor_dir,
            cache_dir=self.root / self.CACHE_DIR,
            cache_fingerprint=self.cache_fingerprint,
            staging_dir=staging_dir,
            attempt=self.attempt,
        )

    def run(self, out: Path) -> BuildResult:
        """Build the pages and write the site; a builder builds its site once.

        A page that cannot be built or rendered is left out; see :func:`run_build`.

        Args:
            out: Output directory; its files from the previous build that are not rebuilt are deleted.

        Returns:
            What was built, with the errors of the pages that failed.

        Raises:
            BuildError: In a strict build, on the first :exc:`~docspecsite.errors.DocspecsiteError` of a page.
        """
        with self.prepare_code_root() as code_root, TemporaryDirectory(prefix="docspecsite-site-") as staging_dir:
            site = self.prepare_site(code_root, Path(staging_dir))
            rendered_site = SiteRenderer.load(RendererName.INTERNAL).render(site)
            writer = SiteWriter(out)
            refused_paths = writer.find_outside(rendered_site.files)
            for path in refused_paths:
                warnings.warn(DocspecsiteWarning("refusing to write outside --out: %s", path), stacklevel=1)
            writer.write({path: file.read_bytes() for path, file in rendered_site.files.items()})
        self.docs.front_matter_cache.prune()
        return BuildResult(
            page_count=len(rendered_site.page_paths - set(refused_paths)),
            counts=rendered_site.counts,
            errors=tuple(self.errors),
            failed_count=len(self.failed_names),
        )


def run_build(
    root: Path,
    ref: str,
    out: Path,
    *,
    include_worktree: bool = False,
    vendor_dir: Path | None = None,
    is_strict: bool = False,
    parts: frozenset[Part] | None = None,
) -> BuildResult:
    """Build the static site for a git ref.

    A page that cannot be built or rendered is left out. A :exc:`~docspecsite.errors.DocspecsiteError` is reported in
    :attr:`BuildResult.errors`; an internal error is issued as an :exc:`~docspecsite.errors.InternalErrorWarning` and
    only counted in :attr:`BuildResult.failed_count`. Problems that do not stop the build are issued as
    :exc:`~docspecsite.errors.DocspecsiteWarning`.

    Args:
        root: Repository root to build from.
        ref: Revision to build: its first-parent history gives the doc versions, its tree the code; the settings
            always come from the working tree's ``docspecsite.toml``.
        out: Output directory; its files from the previous build that are not rebuilt are deleted.
        include_worktree: Add working-tree docs that differ from ``ref`` as a newest version, and read the code and
            docs assets from the working tree.
        vendor_dir: Directory of the vendored third-party files the site uses; None reads ``$DOCSPECSITE_VENDOR_DIR``,
            and without either the site is built without them.
        is_strict: Fail on the first :exc:`~docspecsite.errors.DocspecsiteError` of a page, internal error or warning,
            before anything is written: ``error`` warning filters are set for
            :exc:`~docspecsite.errors.DocspecsiteWarning` and :exc:`~docspecsite.errors.InternalErrorWarning` during the
            build.
        parts: The parts of the site to build; None means the docs, and the code too when ``docspecsite.toml`` has
            ``code-dirs``.

    Returns:
        What was built, with the errors of the pages that failed.

    Raises:
        BuildError: The working tree's root ``docspecsite.toml`` cannot be read, is not valid TOML or has an invalid
            value; with ``is_strict``, also on the first :exc:`~docspecsite.errors.DocspecsiteError` of a page, internal
            error or warning; also when ``parts`` has the code part and the settings have no ``code-dirs``.
    """
    if vendor_dir is None and os.environ.get(VENDOR_ENV):
        vendor_dir = Path(os.environ[VENDOR_ENV])
    with SiteBuilder.make_warnings_fatal() if is_strict else nullcontext():
        builder = SiteBuilder(
            root, ref, include_worktree=include_worktree, vendor_dir=vendor_dir, is_strict=is_strict, parts=parts
        )
        return builder.run(out)
