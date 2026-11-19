"""Per-document versions along the first-parent history of a ref.

Docs: meta/versioning.md
"""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .docs import DOCS, is_template
from .errors import DocspecsiteError
from .git import Git

WORKTREE_SUBJECT = "working copy (uncommitted)"
SUBJECT_PREFIX = re.compile(r"^(spec|docs):\s*")
WORKTREE = "worktree"


def strip_subject(subject: str) -> str:
    """Return a commit subject without a leading ``spec:`` or ``docs:`` prefix.

    Args:
        subject: Commit subject shown as a version's description; only the first such prefix is removed.
    """
    return SUBJECT_PREFIX.sub("", subject, count=1)


def compute_blob_sha(data: bytes) -> str:
    """Return the git blob sha of some contents.

    Args:
        data: Raw bytes of a working-tree file, hashed as git would so they can be compared with the tree's blob.
    """
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


@dataclass(frozen=True)
class Version:
    """One version of a doc, from one commit or from the uncommitted working copy."""

    path: str
    short_id: str
    commit: str | None
    commit_index: int
    date: str
    subject: str
    blob: str


@dataclass(frozen=True)
class History:
    """Versions of all docs at a ref, newest first, with their contents.

    ``undecodable`` maps the blobs that are not valid UTF-8 to the doc path (relative to ``docs/``), the decoding
    error's reason and its byte offset.
    """

    head: str
    docs: Mapping[str, tuple[Version, ...]]
    texts: Mapping[str, str]
    tree: frozenset[str]
    undecodable: Mapping[str, tuple[str, str, int]] = field(default_factory=dict)

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
        if at.short_id == WORKTREE:
            return self.find_latest(path)
        for version in self.docs[path]:
            if version.short_id != WORKTREE and version.commit_index >= at.commit_index:
                return version
        return None

    def is_decodable(self, version: Version) -> bool:
        """Return whether the contents of a version are valid UTF-8, so that ``read_text`` can return them.

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


class NotUtf8Error(DocspecsiteError, ValueError):
    """Error for doc contents that are not valid UTF-8."""


def is_doc(path: str) -> bool:
    """Return whether a path is a Markdown doc rather than a template or other file.

    Args:
        path: Path relative to ``docs/`` from the git tree or working tree, of any file type.
    """
    return path.endswith(".md") and not is_template(path)


def load_history(git: Git, ref: str, *, worktree: Path | None = None) -> History:
    """Load the history of every doc at a git ref, along its first-parent chain.

    Args:
        git: Repository whose commits, trees and blobs are read.
        ref: Revision whose history to load; a branch, tag or sha. Its first-parent chain gives the versions, and its
            tree decides which docs exist.
        worktree: Repository root on disk; when given, working-tree docs that differ from ``ref`` (uncommitted, or
            untracked but not ignored) become a newest version. None reads git only.
    """
    head = git.resolve(ref)
    commits = git.list_first_parent(head)
    commit_index_by_sha = {c.sha: i for i, c in enumerate(commits)}
    tree = git.read_tree(head)
    doc_paths = {p.removeprefix(DOCS) for p in tree if p.startswith(DOCS) and is_doc(p.removeprefix(DOCS))}

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
                    strip_subject(commit.subject),
                    change.blob,
                )  # fmt: skip
            )

    extra: dict[str, bytes] = {}
    if worktree is not None:
        for repo_path in git.list_worktree_files(DOCS):
            path = repo_path.removeprefix(DOCS)
            if not is_doc(path):
                continue
            worktree_bytes = (worktree / repo_path).read_bytes()
            sha = compute_blob_sha(worktree_bytes)
            if sha != tree.get(f"{DOCS}{path}"):
                extra[sha] = worktree_bytes
                versions.setdefault(path, []).insert(0, Version(path, WORKTREE, None, -1, "", WORKTREE_SUBJECT, sha))

    blobs = git.read_blobs(v.blob for vs in versions.values() for v in vs if v.short_id != WORKTREE)
    paths = {v.blob: path for path, vs in versions.items() for v in vs}
    texts: dict[str, str] = {}
    undecodable: dict[str, tuple[str, str, int]] = {}
    for sha, data in {**blobs, **extra}.items():
        try:
            texts[sha] = data.decode("utf-8")
        except UnicodeDecodeError as error:
            undecodable[sha] = (paths[sha], error.reason, error.start)
    docs = {path: tuple(vs) for path, vs in versions.items()}
    return History(head, docs, texts, frozenset(tree), undecodable)
