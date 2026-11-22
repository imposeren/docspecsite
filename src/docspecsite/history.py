"""Per-document versions along the first-parent history of a ref.

Docs: meta/versioning.md
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Self

from .docs import DOCS_DIR, derive_doc_path, is_template, make_dir_index_path
from .errors import DocspecsiteError
from .git import Commit, Git
from .text import NOT_UTF8_MESSAGE, decode_text


@dataclass(frozen=True)
class Version:
    """One version of a doc, from one commit or from the uncommitted working copy."""

    SUBJECT_PREFIX: ClassVar[re.Pattern[str]] = re.compile(r"^(spec|docs):\s*")
    """Commit-subject prefix that :meth:`strip_subject` removes."""

    WORKTREE_SHORT_ID: ClassVar[str] = "worktree"
    """Short id of the working-copy version, in place of a commit's short SHA hash."""

    WORKTREE_SUBJECT: ClassVar[str] = "working copy (uncommitted)"
    """Subject of the working-copy version, shown as its description."""

    path: str
    """POSIX path of the doc, relative to ``docs/``."""

    commit: Commit | None
    """Commit that wrote this version; None for the working copy."""

    commit_index: int
    """Position of the commit on the first-parent chain of the ref, 0 for the ref itself and higher for older ones;
    -1 for the working copy."""

    blob_sha: str
    """SHA hash of the doc's git blob, the key of its contents."""

    @property
    def short_id(self) -> str:
        """First 12 characters of the commit's SHA hash; :attr:`WORKTREE_SHORT_ID` for the working copy."""
        return self.commit.sha[:12] if self.commit is not None else self.WORKTREE_SHORT_ID

    @property
    def date(self) -> str:
        """Committer date, ``YYYY-MM-DD``; empty for the working copy."""
        return self.commit.date if self.commit is not None else ""

    @property
    def subject(self) -> str:
        """Commit subject without a ``spec:`` or ``docs:`` prefix; :attr:`WORKTREE_SUBJECT` for the working copy."""
        return self.strip_subject(self.commit.subject) if self.commit is not None else self.WORKTREE_SUBJECT

    @property
    def is_worktree(self) -> bool:
        """Whether this is the version of the uncommitted working copy."""
        return self.commit is None

    @staticmethod
    def strip_subject(subject: str) -> str:
        """Return a commit subject without a leading ``spec:`` or ``docs:`` prefix.

        Args:
            subject: Commit subject shown as a version's description; only the first such prefix is removed.
        """
        return Version.SUBJECT_PREFIX.sub("", subject, count=1)


@dataclass(frozen=True)
class History:
    """Versions of all docs at a ref, newest first, with their contents."""

    head: str
    """Full SHA hash of the commit the ref names."""

    versions_by_path: Mapping[str, tuple[Version, ...]]
    """Versions of each doc of the ref's tree, newest first, by doc path relative to ``docs/``."""

    texts_by_sha: Mapping[str, str]
    """Decoded contents of the versions that are valid UTF-8, by blob SHA hash."""

    tree: frozenset[str]
    """Repository-relative paths of the files in the ref's tree."""

    decode_errors_by_sha: Mapping[str, tuple[str, int]] = field(default_factory=dict)
    """Decoding errors of the blobs that are not valid UTF-8, by blob SHA hash: the error's reason and its byte
    offset."""

    def find_latest(self, path: str) -> Version:
        """Return the newest version of a doc.

        Args:
            path: Doc path relative to ``docs/``; it must be a doc of this history.
        """
        return self.versions_by_path[path][0]

    def find_doc_path(self, path: str) -> str:
        """Return the doc a path stands for: a directory's index doc when it is a doc of this history, else the path.

        Args:
            path: Path relative to ``docs/`` of a doc or of a directory.
        """
        index_path = make_dir_index_path(path)
        return index_path if index_path in self.versions_by_path else path

    def is_latest(self, version: Version) -> bool:
        """Return whether a version is the newest of its doc.

        Args:
            version: Version of a doc in this history, compared with its doc's newest version (the working copy if any).
        """
        return self.versions_by_path[version.path][0] == version

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
        for version in self.versions_by_path[path]:
            if not version.is_worktree and version.commit_index >= at.commit_index:
                return version
        return None

    def is_decodable(self, version: Version) -> bool:
        """Return whether the contents of a version are valid UTF-8, so that the ``read_text`` method can return them.

        Args:
            version: Version whose blob is looked up among the ones that failed to decode.
        """
        return version.blob_sha not in self.decode_errors_by_sha

    def read_text(self, version: Version) -> str:
        """Return the contents of a version.

        Args:
            version: Version whose blob's decoded text is returned.

        Raises:
            NotUtf8Error: The contents are not valid UTF-8.
        """
        if not self.is_decodable(version):
            raise NotUtf8Error(
                f"{DOCS_DIR}%s: {NOT_UTF8_MESSAGE}", version.path, *self.decode_errors_by_sha[version.blob_sha]
            )
        return self.texts_by_sha[version.blob_sha]

    @classmethod
    def load(cls, git: Git, ref: str, *, worktree_root: Path | None = None) -> Self:
        """Return the history of every doc at a git ref, along its first-parent chain.

        Args:
            git: Repository whose commits, trees and blobs are read.
            ref: Revision whose history to load; a branch, tag or SHA hash. Its first-parent chain gives the versions,
                and its tree decides which docs exist.
            worktree_root: Repository root on disk; when given, working-tree docs that differ from ``ref`` (uncommitted,
                or untracked but not ignored) become a newest version. None reads git only.

        Raises:
            UnknownRefError: ``ref`` names no commit.
        """
        head = git.resolve(ref)
        commits = git.list_first_parent(head)
        commit_index_by_sha = {c.sha: i for i, c in enumerate(commits)}
        tree = git.read_tree(head)
        doc_paths = {
            path for repo_path in tree if (path := derive_doc_path(repo_path)) is not None and cls.is_doc(path)
        }

        versions: dict[str, list[Version]] = {path: [] for path in doc_paths}
        for change in git.list_changes(head, DOCS_DIR):
            path = change.path.removeprefix(DOCS_DIR)
            if path in doc_paths and change.blob_sha is not None:
                commit_index = commit_index_by_sha[change.commit_sha]
                versions[path].append(Version(path, commits[commit_index], commit_index, change.blob_sha))

        worktree_bytes_by_sha: dict[str, bytes] = {}
        if worktree_root is not None:
            worktree_doc_paths = [
                repo_path
                for repo_path in git.list_worktree_files(DOCS_DIR)
                if cls.is_doc(repo_path.removeprefix(DOCS_DIR))
            ]
            for repo_path, sha in git.hash_files(worktree_doc_paths).items():
                if sha != tree.get(repo_path):
                    path = repo_path.removeprefix(DOCS_DIR)
                    worktree_bytes_by_sha[sha] = (worktree_root / repo_path).read_bytes()
                    version = Version(path, None, -1, sha)
                    versions.setdefault(path, []).insert(0, version)

        committed_bytes_by_sha = git.read_blobs(v.blob_sha for vs in versions.values() for v in vs if not v.is_worktree)
        texts_by_sha: dict[str, str] = {}
        decode_errors_by_sha: dict[str, tuple[str, int]] = {}
        # A working-tree file whose filtered contents match a committed blob keeps the blob's bytes: the file's own
        # bytes may differ (such as in line endings), and committed versions show the committed text.
        for sha, data in {**worktree_bytes_by_sha, **committed_bytes_by_sha}.items():
            try:
                texts_by_sha[sha] = decode_text(data)
            except UnicodeDecodeError as error:
                decode_errors_by_sha[sha] = (error.reason, error.start)
        versions_by_path = {path: tuple(vs) for path, vs in versions.items()}
        return cls(head, versions_by_path, texts_by_sha, frozenset(tree), decode_errors_by_sha)

    @staticmethod
    def is_doc(path: str) -> bool:
        """Return whether a path is a Markdown doc rather than a template or other file.

        Args:
            path: Path relative to ``docs/`` from the git tree or working tree, of any file type.
        """
        return path.endswith(".md") and not is_template(path)


class NotUtf8Error(DocspecsiteError, ValueError):
    """Error for doc contents that are not valid UTF-8."""
