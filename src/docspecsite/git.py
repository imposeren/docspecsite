"""Read-only access to a git repository through the ``git`` command line.

Docs: meta/versioning.md
"""

import io
import os
import subprocess
import tarfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .errors import DocspecsiteError


class GitError(DocspecsiteError):
    """Error for a failed git command, including a path that is no git repository."""


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
class Change:
    """Change of one file by a commit."""

    commit_sha: str
    """Full SHA hash of the commit."""

    path: str
    """Repository-relative path of the file."""

    blob_sha: str | None
    """SHA hash of the file's blob after the change; None when the file was deleted."""


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
    NULL_SHA = "0" * 40
    """The all-zero SHA hash git shows for the missing side of an added or deleted file."""

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

        Args:
            *args: Git subcommand and its arguments, run with ``-C`` at the repository root; the first one names the
                command in the error message.
            stdin: Bytes to feed on stdin, such as the SHA hash list for ``cat-file --batch``; None passes no input.

        Raises:
            GitError: The command fails; the message names it and includes git's error output.
        """
        result = subprocess.run(
            ["git", "-C", str(self.root), "-c", "core.quotePath=false", *args],
            input=stdin,
            capture_output=True,
            check=False,
        )
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
            if "not a git repository" in str(error):
                raise
            raise UnknownRefError("unknown ref: %s", ref) from error

    def list_first_parent(self, sha: str) -> list[Commit]:
        """Return the commits on the first-parent chain from a commit, newest first.

        Args:
            sha: Commit whose first-parent history is listed, starting with the commit itself.
        """
        fields = self.run("log", "--first-parent", "-z", "--format=%H%x00%cI%x00%s", sha).decode().split("\0")
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
            "log", "--first-parent", "--diff-merges=first-parent", "--no-renames", "--raw", "--no-abbrev", "-z",
            "--format=%H", sha, "--", prefix,
        ).decode()  # fmt: skip
        changes: list[Change] = []
        commit_sha = ""
        tokens = iter(log_output.split("\0"))
        for token in tokens:
            field = token.lstrip("\n")
            if field.startswith(":"):
                new_blob_sha = field[1:].split()[3]
                # The file's path follows as the next NUL-separated token.
                path = next(tokens)
                changes.append(Change(commit_sha, path, None if new_blob_sha == self.NULL_SHA else new_blob_sha))
            elif field:
                commit_sha = field
        return changes

    def read_tree(self, sha: str) -> dict[str, str]:
        """Return the blob SHA hash of every file at a commit, by file path.

        Args:
            sha: Commit whose whole tree is listed, recursively and with repo-relative paths.
        """
        tree_output = self.run("ls-tree", "-r", "-z", sha).decode()
        tree = {}
        for entry in tree_output.split("\0"):
            if entry:
                fields, path = entry.split("\t", 1)
                _mode, _kind, blob_sha = fields.split()
                tree[path] = blob_sha
        return tree

    def list_worktree_files(self, prefix: str) -> list[str]:
        """Return the sorted paths of files under a prefix that git sees in the working tree.

        Tracked files and untracked files that are not ignored count. Files missing from the working tree, and symlinks
        pointing outside the repository, are left out.

        Args:
            prefix: Repo-relative pathspec limiting the files, e.g. ``docs/``; returned paths stay repo-relative.
        """
        file_list_output = self.run("ls-files", "-z", "-co", "--exclude-standard", "--", prefix).decode()
        base = self.root.resolve()
        found: set[str] = set()
        for path in file_list_output.split("\0"):
            file = self.root / path
            if path and file.is_file() and file.resolve().is_relative_to(base):
                found.add(path)
        return sorted(found)

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

    def extract(self, sha: str, paths: list[str], dest: Path) -> None:
        """Extract files as they are at a commit into a directory.

        Args:
            sha: Commit whose version of the files is extracted.
            paths: Repo-relative paths (files or directories) to extract; directories are extracted with their contents.
            dest: Existing directory that receives the files at their repo-relative paths.
        """
        archive_bytes = self.run("archive", "--format=tar", sha, "--", *paths)
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
            archive.extractall(dest, filter="data")
