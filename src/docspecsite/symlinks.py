"""What a symlink in the repo leads to: one rule for the check and the build.

Docs: behavior/doc-symlinks.md#how-a-symlink-is-followed
Docs: architecture/docs-tooling.md#history-model
"""

import os
import posixpath
from abc import ABC, abstractmethod
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Protocol, override

from .docs import DOC_SUFFIX, DOCS_DIR
from .git import TreeEntry

CODE_DIR_TO_FILE_REASON = "symlink to a file, not a directory"

LEFT_OUT_SYMLINK_REASON = "symlink to an absolute path, outside the repo or to a missing file"


class SymlinkKind(StrEnum):
    """What a symlink leads to at the end of its chain, which alone decides how it is treated.

    Docs: behavior/doc-symlinks.md#the-kinds-of-symlink
    """

    OUT_OF_REPO = "out of the repo"
    NOTHING = "nothing"
    DOC = "a doc"
    DIRECTORY = "a directory"
    OTHER_FILE = "another file"


class RepoFiles(Protocol):
    """The files of the repo where symlinks are looked up, by repo-relative POSIX path (empty for the root).

    No method follows a symlink: each looks at the entry at the path itself.
    """

    def is_symlink(self, path: str) -> bool:
        """Return whether the entry at a path is a symlink.

        Args:
            path: Path of an existing entry.
        """
        ...

    def read_link(self, path: str) -> str:
        """Return the target a symlink stores, as written.

        Args:
            path: Path of a symlink.
        """
        ...

    def is_dir(self, path: str) -> bool:
        """Return whether the entry at a path is a directory (not a symlink to one).

        Args:
            path: Path of any entry; a missing one is no directory.
        """
        ...

    def exists(self, path: str) -> bool:
        """Return whether a file, directory or symlink stands at a path.

        Args:
            path: Path to look up; the directories it lies in are real directories, not symlinks.
        """
        ...

    def list_dir(self, path: str) -> list[str]:
        """Return the names of the entries of a directory, sorted.

        Args:
            path: Path of a directory.
        """
        ...


@dataclass(frozen=True)
class DiskFiles:
    """The files of a working tree on disk; only paths inside the repo are read, and no symlink is followed."""

    root: Path
    """Root directory of the repo."""

    def is_symlink(self, path: str) -> bool:
        """Return whether the entry at a path is a symlink."""
        return (self.root / path).is_symlink()

    def read_link(self, path: str) -> str:
        """Return the target a symlink stores."""
        return str((self.root / path).readlink())

    def is_dir(self, path: str) -> bool:
        """Return whether the entry at a path is a directory."""
        return (self.root / path).is_dir(follow_symlinks=False)

    def exists(self, path: str) -> bool:
        """Return whether anything stands at a path."""
        return (self.root / path).exists(follow_symlinks=False)

    def list_dir(self, path: str) -> list[str]:
        """Return the names of a directory's entries, sorted."""
        return sorted(entry.name for entry in (self.root / path).iterdir())


class _PathSetFiles(ABC):
    """Files known as a set of file paths: a directory exists when it holds one of them."""

    @property
    @abstractmethod
    def _file_paths(self) -> Collection[str]:
        """The repo paths of the files (symlinks included)."""

    @cached_property
    def _names_by_dir(self) -> dict[str, set[str]]:
        """The names of the entries of each directory that holds a file, by directory path; the root is always there."""
        names_by_dir: dict[str, set[str]] = {"": set()}
        # A listing names files only: each file registers its parent directories, up to the first one already known.
        for path in self._file_paths:
            parent, name = posixpath.split(path)
            while name and name not in names_by_dir.setdefault(parent, set()):
                names_by_dir[parent].add(name)
                parent, name = posixpath.split(parent)
        return names_by_dir

    def is_dir(self, path: str) -> bool:
        """Return whether the entry at a path is a directory that holds one of the files."""
        return path in self._names_by_dir

    def exists(self, path: str) -> bool:
        """Return whether one of the files, or a directory holding one, stands at a path."""
        return path in self._file_paths or self.is_dir(path)

    def list_dir(self, path: str) -> list[str]:
        """Return the names of a directory's entries among the files, sorted."""
        return sorted(self._names_by_dir[path])


@dataclass(frozen=True)
class GitSeenFiles(_PathSetFiles, DiskFiles):
    """The files of a working tree that git sees: tracked files, and untracked files that git does not ignore.

    A file that git ignores counts as missing, and so does a directory that holds none of the files git sees.

    Docs: behavior/doc-symlinks.md#how-a-symlink-is-followed
    """

    paths: frozenset[str]
    """Repo paths of the files (symlinks included) that git sees in the working tree."""

    @property
    @override
    def _file_paths(self) -> Collection[str]:
        """The files git sees."""
        return self.paths


@dataclass(frozen=True)
class TreeFiles(_PathSetFiles):
    """The files of a revision's tree; the target a symlink stores is the contents of its blob."""

    tree: Mapping[str, TreeEntry]
    """Every file of the revision (symlinks included), by repo path; directories are the paths' parents."""

    read_blobs: Callable[[Iterable[str]], Mapping[str, bytes]]
    """The reader of blob contents by blob SHA hash, such as ``Git.read_blobs``."""

    @property
    @override
    def _file_paths(self) -> Collection[str]:
        """The files of the tree."""
        return self.tree.keys()

    def is_symlink(self, path: str) -> bool:
        """Return whether the entry at a path is a symlink."""
        return path in self.tree and self.tree[path].is_symlink

    def read_link(self, path: str) -> str:
        """Return the target a symlink stores."""
        blob_sha = self.tree[path].blob_sha
        return os.fsdecode(self.read_blobs([blob_sha])[blob_sha])


@dataclass(frozen=True)
class SymlinkTarget:
    """What a path leads to after its symlinks are followed."""

    kind: SymlinkKind
    """What stands at the end of the chain."""

    path: str | None
    """Repo path at the end of the chain; None when the chain leads out of the repo or to nothing."""

    @property
    def found_path(self) -> str:
        """The repo path at the end of a chain that ends inside the repo, at a doc, directory or other file.

        Raises:
            ValueError: The chain leads out of the repo or to nothing.
        """
        if self.path is None:
            raise ValueError(f"a symlink chain that leads {self.kind} has no path")
        return self.path


class _ChainEndError(Exception):
    """The end of a chain of symlinks that leads out of the repo or to nothing."""

    kind: SymlinkKind
    """``SymlinkKind.OUT_OF_REPO`` or ``SymlinkKind.NOTHING``."""

    def __init__(self, kind: SymlinkKind) -> None:
        super().__init__("symlink chain ends", kind)
        self.kind = kind


@dataclass(frozen=True)
class SymlinkFollower:
    """The rule for what a symlink leads to, and the check's hint for it.

    A chain of symlinks is followed while every step stays inside the repo; a path that following has already
    passed (a directory the symlink lies in, a symlink already followed, or a place one of them led to) ends it as
    leading to nothing, so no loop of symlinks is followed forever.

    Docs: behavior/doc-symlinks.md#how-a-symlink-is-followed
    Docs: behavior/commands/check.md#what-the-check-reports
    """

    # Hints
    LINK_HINT = 'link to "{target}" in the text instead, and remove the symlink'
    MOVE_HINT = 'move "{target}" to "{new_place}", and put the symlink at "{target}" instead'
    NOTHING_HINT = "remove the symlink; its target does not exist"

    files: RepoFiles
    """Where the targets are looked up: the working tree or a revision's tree."""

    def follow(self, path: str) -> SymlinkTarget:
        """Return what a path leads to, following every symlink on the way, also in the directories it lies in.

        Args:
            path: Repo path, usually of a symlink; it may lie below a symlinked directory (``docs/img/logo.png`` is
                ``logo.png`` in the directory that ``docs/img`` leads to).
        """
        try:
            end_path = _SymlinkWalk(self.files).walk_path(path)
        except _ChainEndError as chain_end:
            return SymlinkTarget(chain_end.kind, None)
        return SymlinkTarget(self._classify(end_path), end_path)

    def has_doc_inside(self, dir_path: str) -> bool:
        """Return whether a directory has a doc inside: a ``.md`` file in it or below it, or a symlink there to one.

        A symlink inside it is followed by the same rule, so a symlink there that leads to a doc or to a directory
        with a doc inside counts; one that leads back to a path already passed leads to nothing.

        Args:
            dir_path: Repo path of a directory, or of a symlink; False when it does not lead to a directory.
        """
        walk = _SymlinkWalk(self.files)
        try:
            end_path = walk.walk_path(dir_path)
        except _ChainEndError:
            return False
        return self.files.is_dir(end_path) and walk.find_doc_inside(end_path)

    def make_hint(self, path: str) -> str | None:
        """Return the check's hint for a symlink, by where it leads.

        A doc's new place in the hint to move it is the symlink's path, with ``.md`` added when its name lacks it.

        Args:
            path: Repo path of a symlink.

        Returns:
            The hint; None when the symlink leads out of the repo (whose problem has no hint), and when it is allowed
            (it leads to another file or to a directory with no doc inside).
        """
        walk = _SymlinkWalk(self.files)
        try:
            end_path = walk.walk_path(path)
        except _ChainEndError as chain_end:
            return self.NOTHING_HINT if chain_end.kind is SymlinkKind.NOTHING else None
        kind = self._classify(end_path)
        if kind is SymlinkKind.OTHER_FILE or (kind is SymlinkKind.DIRECTORY and not walk.find_doc_inside(end_path)):
            return None
        if end_path.startswith(DOCS_DIR):
            return self.LINK_HINT.format(target=end_path)
        new_place = path if kind is SymlinkKind.DIRECTORY or path.endswith(DOC_SUFFIX) else path + DOC_SUFFIX
        return self.MOVE_HINT.format(target=end_path, new_place=new_place)

    def _classify(self, path: str) -> SymlinkKind:
        """Return the kind of what stands at an existing real repo path.

        Args:
            path: Real repo path, at the end of a chain of symlinks.
        """
        if self.files.is_dir(path):
            return SymlinkKind.DIRECTORY
        return SymlinkKind.DOC if path.endswith(DOC_SUFFIX) else SymlinkKind.OTHER_FILE


@dataclass
class _SymlinkWalk:
    """One walk through the symlinks of the repo, which remembers the paths it has passed to stop at a loop."""

    files: RepoFiles
    """Where the targets are looked up."""

    passed_paths: set[str] = field(default_factory=lambda: {""})
    """Paths passed so far: the symlinks followed, where they lead, and the directories a walked path lies in; the
    repo root from the start."""

    def walk_path(self, path: str) -> str:
        """Return the real repo path a path leads to, passing the directories it lies in.

        Args:
            path: Repo path, of a symlink or of an entry below a symlinked directory.

        Raises:
            _ChainEndError: The path leads out of the repo or to nothing.
        """
        return self.walk("", path.split("/"), mark_passed=True)

    def walk(self, start_dir: str, parts: Iterable[str], *, mark_passed: bool) -> str:
        """Return the real repo path that path parts lead to from a real directory, following symlinks on the way.

        Args:
            start_dir: Real directory the parts start from; empty for the repo root.
            parts: Path components, such as a link text split at ``/``; ``.`` and ``..`` are worked out as the file
                system does, after the symlinks before them.
            mark_passed: Also pass every directory walked through, as for the directories a symlink lies in.

        Raises:
            _ChainEndError: The parts lead out of the repo or to nothing.
        """
        current_path = start_dir
        for part in parts:
            if part in ("", "."):
                continue
            if not self.files.is_dir(current_path):
                raise _ChainEndError(SymlinkKind.NOTHING)
            if part == "..":
                if not current_path:
                    raise _ChainEndError(SymlinkKind.OUT_OF_REPO)
                current_path = posixpath.dirname(current_path)
                continue
            candidate = posixpath.join(current_path, part)
            if not self.files.exists(candidate):
                raise _ChainEndError(SymlinkKind.NOTHING)
            current_path = self.follow_link(candidate) if self.files.is_symlink(candidate) else candidate
            if mark_passed:
                self.passed_paths.add(current_path)
        return current_path

    def follow_link(self, link_path: str) -> str:
        """Return the real repo path a symlink leads to, passing the symlink and that path.

        Args:
            link_path: Repo path of a symlink whose directory is real.

        Raises:
            _ChainEndError: The symlink leads out of the repo or to nothing, also by coming back to a passed path.
        """
        if link_path in self.passed_paths:
            raise _ChainEndError(SymlinkKind.NOTHING)
        self.passed_paths.add(link_path)
        link_text = self.files.read_link(link_path)
        if posixpath.isabs(link_text):
            raise _ChainEndError(SymlinkKind.OUT_OF_REPO)
        # The symlinks inside the link text add their own targets on the way; only a path passed before this
        # symlink is a loop, not one that two routes through the link text share.
        passed_before = frozenset(self.passed_paths)
        end_path = self.walk(posixpath.dirname(link_path), link_text.split("/"), mark_passed=False)
        if end_path in passed_before:
            raise _ChainEndError(SymlinkKind.NOTHING)
        self.passed_paths.add(end_path)
        return end_path

    def find_doc_inside(self, dir_path: str) -> bool:
        """Return whether a real directory has a doc inside, following its symlinks from the paths passed so far.

        Each entry is walked on its own copy of the passed paths, since passing a sibling is no loop.

        Args:
            dir_path: Real repo path of a directory.
        """
        for name in self.files.list_dir(dir_path):
            child_path = posixpath.join(dir_path, name)
            branch_walk = _SymlinkWalk(self.files, set(self.passed_paths))
            if self.files.is_symlink(child_path):
                try:
                    end_path = branch_walk.follow_link(child_path)
                except _ChainEndError:
                    continue
            else:
                end_path = child_path
                branch_walk.passed_paths.add(child_path)
            if self.files.is_dir(end_path):
                if branch_walk.find_doc_inside(end_path):
                    return True
            elif end_path.endswith(DOC_SUFFIX):
                return True
        return False
