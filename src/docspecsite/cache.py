"""The `internal` renderer's incremental-build cache of link hrefs and rendered page bodies.

Unchanged versions are not re-rendered: hrefs are cached per blob, body HTML per fingerprint, blob and link targets,
and diff HTML per fingerprint and the blobs of its two versions.

Docs: architecture/docs-tooling.md#incremental-builds
"""

import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path

from .diskcache import CacheRoot
from .markdown import RenderedLink


class BodyCache(CacheRoot):
    """On-disk cache of rendered page bodies.

    It has link hrefs per blob and body HTML per blob and rendering, with diff HTML per pair of blobs.
    Entries this instance did not use are removed by :meth:`~docspecsite.diskcache.CacheRoot.prune`.
    """

    # Constants
    DIFF_KEY_PREFIX = "diff\0"
    """Start of the :meth:`load_or_compute_body` key of a diff entry, before the older blob's SHA hash; body keys
    never start with it."""

    # Entry directories
    BODIES_DIR = "bodies"
    """Directory of a cache root holding the body and diff HTML entries."""

    HREFS_DIR = "hrefs"
    """Directory of a cache root holding the link hrefs, one JSON entry per blob."""

    ENTRY_DIRS = (HREFS_DIR, BODIES_DIR)
    """The entry directories :meth:`~docspecsite.diskcache.CacheRoot.prune` looks into."""

    # Cache state
    hit_count: int
    """Number of bodies taken from the cache."""

    miss_count: int
    """Number of bodies rendered because the cache did not have them."""

    def __init__(self, directory: Path, fingerprint: str, variant: str) -> None:
        """Prepare a cache in a directory.

        Args:
            directory: Directory holding the cache roots; one root per fingerprint and variant is made under it.
            fingerprint: Docspecsite version fingerprint; entries made under another one are never read.
            variant: Name of the set of built parts (:attr:`~docspecsite.sitedocs.SiteDocs.parts_label`);
                builds of different sets keep separate roots, so none throws away the entries of another.
        """
        super().__init__(directory, fingerprint, variant)
        self.hit_count = 0
        self.miss_count = 0

    @staticmethod
    def make_targets_key(resolved: Mapping[str, RenderedLink]) -> str:
        """Return a hash of how the links of a page are rendered.

        It covers each link's href, markers, code style and replaced text, and does not depend on their order.

        Args:
            resolved: Rendering of each link of the page, keyed by the href as written in the doc.
        """
        lines = sorted(
            f"{href}\0{out.href}\0{';'.join(f'{css}:{text}' for css, text in out.markers)}"
            f"\0{out.use_code_style}\0{out.code_text!r}"
            for href, out in resolved.items()
        )
        return hashlib.sha256("\n".join(lines).encode()).hexdigest()

    def load_or_compute_hrefs(self, blob_sha: str, compute: Callable[[], list[str]]) -> list[str]:
        """Return the link hrefs of a blob, from the cache or else computed (and cached).

        Args:
            blob_sha: Git blob SHA hash of the doc's text; names the entry, so all versions with the same text share it.
            compute: Called only on a miss or an unreadable entry to extract the hrefs; its result is stored.
        """
        return self.load_or_compute_json(
            self.root / self.HREFS_DIR / f"{blob_sha}.json", compute, parse=self._parse_hrefs, to_json=lambda h: h
        )

    @staticmethod
    def _parse_hrefs(cached: object) -> list[str] | None:
        """Return the hrefs a cache entry holds; None when it holds no list of strings.

        Args:
            cached: The entry's JSON value.
        """
        if isinstance(cached, list) and all(isinstance(item, str) for item in cached):
            return [str(item) for item in cached]
        return None

    def load_or_compute_body(self, blob_sha: str, key: str, compute: Callable[[], str]) -> str:
        """Return the body HTML of a blob rendered for given link targets.

        It comes from the cache or else is computed. Cache hits and misses are counted in :attr:`hit_count` and
        :attr:`miss_count`.

        Args:
            blob_sha: Git blob SHA hash of the doc's text; part of the entry name with ``key`` and the fingerprint.
            key: How the page's links and Contents list are rendered (:meth:`make_targets_key` plus the Contents
                threshold); a different key gives a separate entry.
            compute: Called only on a miss to render the body HTML; its result is stored.
        """
        entry_name = hashlib.sha256(f"{self.root.name}\0{blob_sha}\0{key}".encode()).hexdigest()
        path = self.root / self.BODIES_DIR / f"{entry_name}.html"
        self.used_paths.add(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError, ValueError:
            pass
        else:
            self.hit_count += 1
            return text
        self.miss_count += 1
        body_html = compute()
        self.store(path, body_html.encode())
        return body_html

    def load_or_compute_diff_body(self, old_blob_sha: str, new_blob_sha: str, compute: Callable[[], str]) -> str:
        """Return the diff HTML between two blobs, from the cache or else computed (and cached).

        It is counted like a page body in :attr:`hit_count` and :attr:`miss_count`.

        Args:
            old_blob_sha: Git blob SHA hash of the older version's text, the ``-`` side of the diff.
            new_blob_sha: Git blob SHA hash of the newer version's text, the ``+`` side.
            compute: Called only on a miss to diff the two texts; its result is stored.
        """
        return self.load_or_compute_body(new_blob_sha, f"{self.DIFF_KEY_PREFIX}{old_blob_sha}", compute)
