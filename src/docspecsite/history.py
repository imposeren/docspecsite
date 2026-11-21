"""Per-document versions along the first-parent history of a ref.

Docs: meta/versioning.md
"""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Self

from .docs import DOCS, is_template
from .errors import DocspecsiteError
from .git import Git


@dataclass(frozen=True)
class Version:
    """One version of a doc, from one commit or from the uncommitted working copy."""

    WORKTREE: ClassVar[str] = "worktree"
    """Short id of the working-copy version, in place of a commit's short SHA hash."""

    WORKTREE_SUBJECT: ClassVar[str] = "working copy (uncommitted)"
    """Subject of the working-copy version, shown as its description."""

    path: str
    """POSIX path of the doc, relative to ``docs/``."""

    short_id: str
    """First 12 characters of the commit's SHA hash; :attr:`WORKTREE` for the working copy."""

    commit: str | None
    """Full SHA hash of the commit; None for the working copy."""

    commit_index: int
    """Position of the commit on the first-parent chain of the ref, 0 for the ref itself and higher for older ones;
    -1 for the working copy."""

    date: str
    """Committer date, ``YYYY-MM-DD``; empty for the working copy."""

    subject: str
    """Commit subject without a ``spec:`` or ``docs:`` prefix; :attr:`WORKTREE_SUBJECT` for the working copy."""

    blob: str
    """SHA hash of the doc's git blob, the key of its contents."""

    @property
    def is_worktree(self) -> bool:
        """Whether this is the version of the uncommitted working copy."""
        return self.short_id == self.WORKTREE


@dataclass(frozen=True)
class History:
    """Versions of all docs at a ref, newest first, with their contents."""

    SUBJECT_PREFIX: ClassVar[re.Pattern[str]] = re.compile(r"^(spec|docs):\s*")
    """Commit-subject prefix that :meth:`strip_subject` removes."""

    head: str
    """Full SHA hash of the commit the ref names."""

    docs: Mapping[str, tuple[Version, ...]]
    """Versions of each doc of the ref's tree, newest first, by doc path relative to ``docs/``."""

    texts: Mapping[str, str]
    """Decoded contents of the versions that are valid UTF-8, by blob SHA hash."""

    tree: frozenset[str]
    """Repository-relative paths of the files in the ref's tree."""

    undecodable: Mapping[str, tuple[str, str, int]] = field(default_factory=dict)
    """The blobs that are not valid UTF-8, by SHA hash: their doc path (relative to ``docs/``), the decoding error's
    reason and its byte offset."""

    def find_latest(self, path: str) -> Version:
        """Return the newest version of a doc.

        Args:
            path: Doc path relative to ``docs/``; it must be a doc of this history.
        """
        return self.docs[path][0]

    def find_previous(self, version: Version) -> Version | None:
        """Return the version just before another, or None when that is its doc's first.

        Args:
            version: Version of a doc in this history; the result is the next older version of the same doc.
        """
        versions = self.docs[version.path]
        index = versions.index(version)
        return versions[index + 1] if index + 1 < len(versions) else None

    def is_latest(self, version: Version) -> bool:
        """Return whether a version is the newest of its doc.

        Args:
            version: Version of a doc in this history, compared with its doc's newest version (the working copy if any).
        """
        return self.docs[version.path][0] == version

    def find_contemporary(self, path: str, at: Version) -> Version | None:
        """Return the version of a doc that was current when another version was written.

        The result is None when there is none. For the working copy it is the latest version.

        Args:
            path: Doc path relative to ``docs/`` whose version is wanted, e.g. the target of a link.
            at: Version of another doc, e.g. the one holding the link; its commit position is the point in time. The
                working copy stands for now.
        """
        if at.is_worktree:
            return self.find_latest(path)
        for version in self.docs[path]:
            if not version.is_worktree and version.commit_index >= at.commit_index:
                return version
        return None

    def is_decodable(self, version: Version) -> bool:
        """Return whether the contents of a version are valid UTF-8, so that the ``read_text`` method can return them.

        Args:
            version: Version whose blob is looked up among the undecodable ones.
        """
        return version.blob not in self.undecodable

    def read_text(self, version: Version) -> str:
        """Return the contents of a version.

        Args:
            version: Version whose blob's decoded text is returned.

        Raises:
            NotUtf8Error: The contents are not valid UTF-8.
        """
        if version.blob in self.undecodable:
            raise NotUtf8Error("docs/%s: not valid UTF-8 (%s at byte %d)", *self.undecodable[version.blob])
        return self.texts[version.blob]

    @classmethod
    def load(cls, git: Git, ref: str, *, worktree: Path | None = None) -> Self:
        """Return the history of every doc at a git ref, along its first-parent chain.

        Args:
            git: Repository whose commits, trees and blobs are read.
            ref: Revision whose history to load; a branch, tag or SHA hash. Its first-parent chain gives the versions,
                and its tree decides which docs exist.
            worktree: Repository root on disk; when given, working-tree docs that differ from ``ref`` (uncommitted,
                or untracked but not ignored) become a newest version. None reads git only.
        """
        head = git.resolve(ref)
        commits = git.list_first_parent(head)
        commit_index_by_sha = {c.sha: i for i, c in enumerate(commits)}
        tree = git.read_tree(head)
        doc_paths = {p.removeprefix(DOCS) for p in tree if p.startswith(DOCS) and cls.is_doc(p.removeprefix(DOCS))}

        versions: dict[str, list[Version]] = {path: [] for path in doc_paths}
        for change in git.list_changes(head, DOCS):
            path = change.path.removeprefix(DOCS)
            if path in doc_paths and change.blob is not None:
                commit = commits[commit_index_by_sha[change.commit]]
                versions[path].append(
                    Version(
                        path,
                        change.commit[:12],
                        change.commit,
                        commit_index_by_sha[change.commit],
                        commit.date,
                        cls.strip_subject(commit.subject),
                        change.blob,
                    )  # fmt: skip
                )

        extra: dict[str, bytes] = {}
        if worktree is not None:
            for repo_path in git.list_worktree_files(DOCS):
                path = repo_path.removeprefix(DOCS)
                if not cls.is_doc(path):
                    continue
                worktree_bytes = (worktree / repo_path).read_bytes()
                sha = cls.compute_blob_sha(worktree_bytes)
                if sha != tree.get(f"{DOCS}{path}"):
                    extra[sha] = worktree_bytes
                    version = Version(path, Version.WORKTREE, None, -1, "", Version.WORKTREE_SUBJECT, sha)
                    versions.setdefault(path, []).insert(0, version)

        blobs = git.read_blobs(v.blob for vs in versions.values() for v in vs if not v.is_worktree)
        paths = {v.blob: path for path, vs in versions.items() for v in vs}
        texts: dict[str, str] = {}
        undecodable: dict[str, tuple[str, str, int]] = {}
        for sha, data in {**blobs, **extra}.items():
            try:
                texts[sha] = data.decode("utf-8")
            except UnicodeDecodeError as error:
                undecodable[sha] = (paths[sha], error.reason, error.start)
        docs = {path: tuple(vs) for path, vs in versions.items()}
        return cls(head, docs, texts, frozenset(tree), undecodable)

    @staticmethod
    def strip_subject(subject: str) -> str:
        """Return a commit subject without a leading ``spec:`` or ``docs:`` prefix.

        Args:
            subject: Commit subject shown as a version's description; only the first such prefix is removed.
        """
        return History.SUBJECT_PREFIX.sub("", subject, count=1)

    @staticmethod
    def compute_blob_sha(data: bytes) -> str:
        """Return the git blob SHA hash of some contents.

        Args:
            data: Raw bytes of a working-tree file, hashed as git would so they can be compared with the tree's blob.
        """
        return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()

    @staticmethod
    def is_doc(path: str) -> bool:
        """Return whether a path is a Markdown doc rather than a template or other file.

        Args:
            path: Path relative to ``docs/`` from the git tree or working tree, of any file type.
        """
        return path.endswith(".md") and not is_template(path)


class NotUtf8Error(DocspecsiteError, ValueError):
    """Error for doc contents that are not valid UTF-8."""
