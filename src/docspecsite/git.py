"""Read-only access to a git repository through the ``git`` command line.

Docs: meta/versioning.md
"""

import os
import posixpath
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .errors import DocspecsiteError


class GitError(DocspecsiteError):
    """Error for a failed git command, including a path that is no git repository."""

    @property
    def is_no_repository(self) -> bool:
        """Whether git failed because the directory it ran in is not inside a git repository."""
        return "not a git repository" in str(self)


class UnknownRefError(GitError):
    """Error for a ref that names no commit."""


@dataclass(frozen=True)
class Commit:
    """Commit on the first-parent chain of a ref."""

    sha: str
    """Full SHA hash of the commit."""

    date: str
    """Committer date, ``YYYY-MM-DD``."""

    subject: str
    """First line of the commit message."""


@dataclass(frozen=True)
class TreeEntry:
    """File of a commit's tree.

    Docs: architecture/docs-tooling.md#history-model
    """

    blob_sha: str
    """SHA hash of the file's blob."""

    mode: str
    """The file mode git gives the file, such as ``100644``."""

    @property
    def is_symlink(self) -> bool:
        """Whether the file is a symlink, whose blob holds the link's target."""
        return self.mode == Git.SYMLINK_MODE


@dataclass(frozen=True)
class TreeFile:
    """File of a commit's tree, with its path."""

    path: str
    """Repository-relative path of the file."""

    entry: TreeEntry
    """The file's blob and mode."""


@dataclass(frozen=True)
class WorktreeFile:
    """File that git lists in the working tree and that exists on disk.

    Docs: architecture/docs-tooling.md#history-model
    """

    path: str
    """Repository-relative path of the file."""

    is_symlink: bool
    """Whether the path is a symlink; it is never followed."""


@dataclass(frozen=True)
class Change:
    """Change of one file by a commit."""

    commit_sha: str
    """Full SHA hash of the commit."""

    path: str
    """Repository-relative path of the file."""

    blob_sha: str | None
    """SHA hash of the file's blob after the change; None when the file was deleted."""

    is_symlink: bool
    """Whether the file is a symlink after the change; false when it was deleted."""


@dataclass(frozen=True)
class StagedChange:
    """Change of one file staged in the git index."""

    status: str
    """The ``--name-status`` letter, with the similarity score for a rename or copy, e.g. ``D`` or ``R100``."""

    old_path: str
    """Repository-relative path of the file, before the change for a rename or copy."""

    new_path: str | None
    """Repository-relative path of the renamed or copied file; None for any other change."""

    @staticmethod
    def has_new_path(status: str) -> bool:
        """Return whether a ``--name-status`` letter marks a rename or copy, which has a new path.

        Args:
            status: The ``--name-status`` letter, with the similarity score for a rename or copy, e.g. ``R100``.
        """
        return status[0] in "RC"

    @property
    def is_deleted(self) -> bool:
        """Whether the change deletes the file."""
        return self.status == "D"

    @property
    def is_renamed(self) -> bool:
        """Whether the change renames the file (a copy is not a rename)."""
        return self.status.startswith("R")


class Git:
    """Read-only queries on the git repository at its ``root`` attribute."""

    # Constants
    EXECUTABLE_MODE = "100755"
    """The file mode git gives an executable regular file."""

    GITLINK_MODE = "160000"
    """The file mode git gives a submodule."""

    HASH_CHUNK_SIZE = 1000
    """Most paths given to one ``git hash-object`` call, so that its command line stays within the system's limits."""

    NULL_SHA = "0" * 40
    """The all-zero SHA hash git shows for the missing side of an added or deleted file."""

    SYMLINK_MODE = "120000"
    """The file mode git gives a symlink."""

    # Arguments of __init__
    root: Path
    """See :meth:`__init__`."""

    def __init__(self, root: Path) -> None:
        """Prepare queries on a repository.

        Args:
            root: The repository root; git runs in it.
        """
        self.root = root

    def run(self, *args: str, stdin: bytes | None = None) -> bytes:
        """Run ``git`` in the repository and return its stdout.

        Git runs in the C locale, so that its error messages are in English.

        Args:
            *args: Git subcommand and its arguments, run with ``-C`` at the repository root; the first one names the
                command in the error message.
            stdin: Bytes to feed on stdin, such as the SHA hash list for ``cat-file --batch``; None passes no input.

        Raises:
            GitError: The command fails or the ``git`` program is not found; the message names the command and includes
                git's error output.
        """
        try:
            result = subprocess.run(
                ["git", "-C", str(self.root), "-c", "core.quotePath=false", *args],
                input=stdin,
                capture_output=True,
                check=False,
                env={**os.environ, "LC_ALL": "C"},
            )
        except FileNotFoundError as error:
            raise GitError("git %s failed: git not found (%s)", args[0], error.strerror) from error
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            if stderr:
                raise GitError("git %s failed: %s", args[0], stderr)
            raise GitError("git %s failed", args[0])
        return result.stdout

    def resolve(self, ref: str) -> str:
        """Return the full SHA hash of the commit that a ref names.

        Args:
            ref: Branch, tag, SHA hash or other revision expression given by the user; it must name a commit.

        Raises:
            UnknownRefError: ``ref`` names no commit.
        """
        try:
            return self.run("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").decode().strip()
        except GitError as error:
            if error.is_no_repository:
                raise
            raise UnknownRefError("unknown ref: %s", ref) from error

    def require_top_level(self) -> None:
        """Check that the repository root is not a subdirectory of a git repository.

        The check passes whenever git cannot tell: outside any git repository, when git refuses the repository or is
        not installed. Commands that need git report such a failure themselves.

        Raises:
            GitError: The root is a subdirectory of a git repository.
        """
        try:
            prefix = self.run("rev-parse", "--show-prefix").decode().strip()
        except GitError:
            return
        if prefix:
            raise GitError(
                "%s must be the top level of its git repo (subdirectories are not supported yet)", self.root.resolve()
            )

    def list_first_parent(self, sha: str) -> list[Commit]:
        """Return the commits on the first-parent chain from a commit, newest first.

        Args:
            sha: Commit whose first-parent history is listed, starting with the commit itself.
        """
        log_output = self.run("log", "--first-parent", "--no-show-signature", "-z", "--format=%H%x00%cI%x00%s", sha)
        fields = log_output.decode(errors="replace").split("\0")
        return [
            Commit(commit_sha, date[:10], subject)
            for commit_sha, date, subject in zip(fields[0::3], fields[1::3], fields[2::3], strict=False)
        ]

    def list_changes(self, sha: str, prefix: str) -> list[Change]:
        """Return the changes to files under a path prefix along the first-parent chain from a commit.

        A merge commit is compared against its first parent.

        Args:
            sha: Commit whose first-parent history is scanned, newest first.
            prefix: Repo-relative pathspec limiting the changes, e.g. ``docs/``; returned paths stay repo-relative.
        """
        log_output = self.run(
            "log", "--first-parent", "--no-show-signature", "--diff-merges=first-parent", "--no-renames", "--raw",
            "--no-abbrev", "-z", "--format=%H", sha, "--", prefix,
        )  # fmt: skip
        changes: list[Change] = []
        commit_sha = ""
        tokens = iter(log_output.split(b"\0"))
        for token in tokens:
            field = token.lstrip(b"\n")
            if field.startswith(b":"):
                _old_mode, new_mode, _old_blob_sha, new_blob_sha, _status = field[1:].decode().split()
                # The file's path follows as the next NUL-separated token.
                path = os.fsdecode(next(tokens))
                is_deleted = new_blob_sha == self.NULL_SHA
                changes.append(
                    Change(
                        commit_sha,
                        path,
                        None if is_deleted else new_blob_sha,
                        is_symlink=new_mode == self.SYMLINK_MODE,
                    )
                )
            elif field:
                commit_sha = field.decode()
        return changes

    def read_tree(self, sha: str) -> dict[str, TreeEntry]:
        """Return every file at a commit, by file path.

        Args:
            sha: Commit whose whole tree is listed, recursively and with repo-relative paths.
        """
        return {file.path: file.entry for file in self.list_tree(sha, None)}

    def list_tree(self, sha: str, paths: Sequence[str] | None) -> list[TreeFile]:
        """Return the files at a commit under some paths, in path order.

        Args:
            sha: Commit whose tree is listed, recursively.
            paths: Repo-relative paths (files or directories) limiting the listing; an empty sequence lists nothing,
                None the whole tree.
        """
        if paths is not None and not paths:
            return []
        tree_output = self.run("ls-tree", "-r", "-z", sha, *(["--", *paths] if paths is not None else []))
        listing: list[TreeFile] = []
        for line in tree_output.split(b"\0"):
            if line:
                fields, path = line.split(b"\t", 1)
                mode, _kind, blob_sha = fields.decode().split()
                listing.append(TreeFile(os.fsdecode(path), TreeEntry(blob_sha, mode)))
        return listing

    def list_worktree_files(self, prefix: str) -> list[WorktreeFile]:
        """Return the files under a prefix that git sees in the working tree, sorted by path.

        Tracked files and untracked files that are not ignored count. Files missing from the working tree, and
        directories (such as a submodule's), are left out. Symlinks are listed and never followed.

        Args:
            prefix: Repo-relative pathspec limiting the files, e.g. ``docs/``; returned paths stay repo-relative.
        """
        file_list_output = self.run("ls-files", "-z", "-co", "--exclude-standard", "--", prefix)
        found: dict[str, WorktreeFile] = {}
        for raw_path in file_list_output.split(b"\0"):
            path = os.fsdecode(raw_path)
            full_path = self.root / path
            if path and os.path.lexists(full_path):
                is_symlink = os.path.islink(full_path)
                if is_symlink or not os.path.isdir(full_path):
                    found[path] = WorktreeFile(path, is_symlink=is_symlink)
        return [found[path] for path in sorted(found)]

    def hash_files(self, paths: list[str]) -> dict[str, str]:
        """Return the blob SHA hash that git gives each of some working-tree files, by path.

        The files are hashed as ``git add`` would store them: with their line-ending conversion and clean filters
        applied, so an unchanged file gets the blob SHA hash it has in the tree.

        Args:
            paths: Repo-relative paths of existing files, any characters allowed; none gives an empty result without
                running git.
        """
        sha_by_path: dict[str, str] = {}
        for start in range(0, len(paths), self.HASH_CHUNK_SIZE):
            chunk = paths[start : start + self.HASH_CHUNK_SIZE]
            hash_output = self.run("hash-object", "--", *chunk)
            sha_by_path.update(zip(chunk, hash_output.decode().split(), strict=True))
        return sha_by_path

    def list_staged_changes(self, prefix: str) -> list[StagedChange]:
        """Return the changes staged under a path prefix, compared with ``HEAD``, with renames detected.

        Paths are decoded as file names are (undecodable bytes kept as surrogate escapes), never quoted.

        Args:
            prefix: Repo-relative pathspec limiting the changes, e.g. ``docs/``; returned paths stay repo-relative.

        Raises:
            GitError: The repository root is not a git working tree, or git fails otherwise.
        """
        diff_output = self.run("diff", "--cached", "--name-status", "-M", "-z", "--", prefix)
        changes: list[StagedChange] = []
        tokens = iter(diff_output.split(b"\0"))
        for token in tokens:
            if not token:
                continue
            status = token.decode()
            old_path = os.fsdecode(next(tokens))
            # A rename or copy is followed by its new path.
            new_path = os.fsdecode(next(tokens)) if StagedChange.has_new_path(status) else None
            changes.append(StagedChange(status, old_path, new_path))
        return changes

    def read_blobs(self, shas: Iterable[str]) -> dict[str, bytes]:
        """Return the contents of blobs, by blob SHA hash.

        Args:
            shas: Blob SHA hashes whose contents are wanted; duplicates are read once, and none gives an empty result
                without running git.

        Raises:
            GitError: A SHA hash is unknown or is not a blob.
        """
        wanted = list(dict.fromkeys(shas))
        if not wanted:
            return {}
        batch_output = self.run("cat-file", "--batch", stdin="".join(f"{sha}\n" for sha in wanted).encode())
        blob_by_sha: dict[str, bytes] = {}
        offset = 0
        for _ in wanted:
            end = batch_output.index(b"\n", offset)
            header = batch_output[offset:end].decode().split()
            if len(header) != 3:
                raise GitError("cannot read blob: %s", " ".join(header))
            sha, kind, size = header
            if kind != "blob":
                raise GitError("%s is not a blob", sha)
            start = end + 1
            blob_by_sha[sha] = batch_output[start : start + int(size)]
            offset = start + int(size) + 1
        return blob_by_sha

    def write_files(self, sha: str, paths: Sequence[str], dest: Path) -> list[str]:
        """Write files as they are committed at a commit into a directory, leaving out unsafe symlinks.

        The files are the committed bytes: no checkout filters, line-ending conversion or export attributes apply. A
        symlink that points to an absolute path, or to a path outside ``paths``, is not written.

        Docs: architecture/docs-tooling.md#code-reference

        Args:
            sha: Commit whose version of the files is written.
            paths: Repo-relative paths (files or directories) to write; directories are written with their contents.
            dest: Existing directory that receives the files at their repo-relative paths.

        Returns:
            The repo-relative paths of the symlinks left out, in path order.
        """
        listing = [file for file in self.list_tree(sha, paths) if file.entry.mode != self.GITLINK_MODE]
        blob_by_sha = self.read_blobs(file.entry.blob_sha for file in listing)
        skipped_link_paths: list[str] = []
        for tree_file in listing:
            dest_file = dest / tree_file.path
            blob_bytes = blob_by_sha[tree_file.entry.blob_sha]
            if tree_file.entry.is_symlink:
                target = os.fsdecode(blob_bytes)
                if not self.is_link_inside(tree_file.path, target, paths):
                    skipped_link_paths.append(tree_file.path)
                    continue
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                dest_file.symlink_to(target)
            else:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                dest_file.write_bytes(blob_bytes)
                if tree_file.entry.mode == self.EXECUTABLE_MODE:
                    dest_file.chmod(0o755)
        return skipped_link_paths

    @staticmethod
    def is_link_inside(link_path: str, target: str, paths: Sequence[str]) -> bool:
        """Return whether a symlink points to a relative path inside some repo paths.

        A link that leaves the repository is never inside, even when a path is the repository root ``.``.

        Args:
            link_path: Repo-relative path of the symlink.
            target: The path the symlink stores.
            paths: Repo-relative paths (files or directories) that the link's target must lie in.
        """
        if posixpath.isabs(target):
            return False
        resolved = PurePosixPath(posixpath.normpath(posixpath.join(posixpath.dirname(link_path), target)))
        if resolved.parts[:1] == ("..",):
            return False
        return any(resolved.is_relative_to(path) for path in paths)
