"""Incremental-build cache of link hrefs and rendered page bodies.

Unchanged versions are not re-rendered: hrefs are cached per blob, body HTML per fingerprint, blob and link targets,
and diff HTML per fingerprint and the blobs of its two versions.

Docs: architecture/docs-tooling.md
"""

import contextlib
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from . import __version__
from .markdown import RenderedLink


class BodyCache:
    """On-disk cache of rendered page bodies.

    It has two levels: link hrefs per blob and body HTML per blob and rendering, with diff HTML per pair of blobs.
    Entries this instance did not use are removed by :meth:`prune`.
    """

    # Constants
    DIFF_KEY_PREFIX = "diff\0"
    """Start of the :meth:`get_body` key of a diff entry, before the older blob's SHA hash; body keys never start with
    it."""

    MARKER_FILENAME = ".docspecsite-cache-root"
    """Name of the file that marks a cache root as made by this cache, so :meth:`prune` may remove it."""

    # Fingerprint inputs
    PACKAGE_DIR = Path(__file__).parent
    """Directory of the docspecsite package, whose files :meth:`compute_fingerprint` hashes."""

    RENDER_DISTRIBUTIONS = ("markdown-it-py", "mdit-py-plugins", "jinja2", "griffelib")
    """Rendering dependencies whose installed versions :meth:`compute_fingerprint` includes."""

    SKIPPED_DIRS = frozenset({"__pycache__"})
    """Directories under :attr:`PACKAGE_DIR` whose files :meth:`compute_fingerprint` does not hash."""

    # Cache state
    fingerprint_prefix: str
    """Start of the hash of the fingerprint.

    Every root name under :attr:`directory` begins with it and a ``-``, so :meth:`prune` tells the roots of this
    docspecsite version from the others.
    """

    hit_count: int
    """Number of bodies taken from the cache."""

    miss_count: int
    """Number of bodies rendered because the cache did not have them."""

    root: Path
    """Cache root of this fingerprint and variant under :attr:`directory`: ``<fingerprint_prefix>-<variant>``."""

    used_paths: set[Path]
    """Entry files read or written by this instance; :meth:`prune` keeps only these."""

    # Arguments of __init__
    directory: Path
    """See :meth:`__init__`."""

    def __init__(self, directory: Path, fingerprint: str, variant: str) -> None:
        """Prepare a cache in a directory.

        Args:
            directory: Directory holding the cache roots; one root per fingerprint and variant is made under it.
            fingerprint: Docspecsite version fingerprint; entries made under another one are never read.
            variant: Name of the set of built parts (:attr:`~docspecsite.build.SiteBuilder.parts_label`); builds of
                different sets keep separate roots, so none throws away the entries of another.
        """
        self.directory = directory
        self.fingerprint_prefix = hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
        self.root = directory / f"{self.fingerprint_prefix}-{variant}"
        self.used_paths = set()
        self.hit_count = 0
        self.miss_count = 0

    @staticmethod
    def compute_fingerprint() -> str:
        """Return a string identifying this docspecsite version.

        It combines ``__version__``, the versions of the rendering dependencies and a hash of the package's files, so
        cache entries made by another version are not reused.
        """
        digest = hashlib.sha256(__version__.encode())
        for name in BodyCache.RENDER_DISTRIBUTIONS:
            digest.update(f"{name}={BodyCache.get_installed_version(name)}\0".encode())
        package_dir = BodyCache.PACKAGE_DIR
        for path in sorted(p for p in package_dir.rglob("*") if p.is_file()):
            relative = path.relative_to(package_dir)
            if BodyCache.SKIPPED_DIRS.intersection(relative.parts) or path.suffix == ".pyc":
                continue
            digest.update(relative.as_posix().encode() + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        return f"{__version__}-{digest.hexdigest()}"

    @staticmethod
    def get_installed_version(name: str) -> str:
        """Return the installed version of a distribution, or ``"none"`` if it is not installed.

        Args:
            name: Distribution to look up, under its package-index name (one of the rendering dependencies).
        """
        try:
            return version(name)
        except PackageNotFoundError:
            return "none"

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

    def get_hrefs(self, blob_sha: str, compute: Callable[[], list[str]]) -> list[str]:
        """Return the link hrefs of a blob, from the cache or else computed (and cached).

        Args:
            blob_sha: Git blob SHA hash of the doc's text; names the entry, so all versions with the same text share it.
            compute: Called only on a miss or an unreadable entry to extract the hrefs; its result is stored.
        """
        path = self.root / "hrefs" / f"{blob_sha}.json"
        self.used_paths.add(path)
        try:
            cached_hrefs = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(cached_hrefs, list) and all(isinstance(item, str) for item in cached_hrefs):
                return cached_hrefs
        except OSError, ValueError:
            pass
        hrefs = compute()
        self.store(path, json.dumps(hrefs).encode())
        return hrefs

    def get_body(self, blob_sha: str, key: str, compute: Callable[[], str]) -> str:
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
        path = self.root / "bodies" / f"{entry_name}.html"
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

    def get_diff_body(self, old_blob_sha: str, new_blob_sha: str, compute: Callable[[], str]) -> str:
        """Return the diff HTML between two blobs, from the cache or else computed (and cached).

        It is counted like a page body in :attr:`hit_count` and :attr:`miss_count`.

        Args:
            old_blob_sha: Git blob SHA hash of the older version's text, the ``-`` side of the diff.
            new_blob_sha: Git blob SHA hash of the newer version's text, the ``+`` side.
            compute: Called only on a miss to diff the two texts; its result is stored.
        """
        return self.get_body(new_blob_sha, f"{self.DIFF_KEY_PREFIX}{old_blob_sha}", compute)

    def store(self, path: Path, data: bytes) -> None:
        """Write a cache entry.

        A failing cache directory (read-only, full) only disables caching.

        Args:
            path: Entry file under this cache's fingerprint root; the root also gets the marker that lets :meth:`prune`
                remove it.
            data: Entry contents, written atomically.
        """
        try:
            marker_path = self.root / self.MARKER_FILENAME
            if not marker_path.exists():
                self.write_atomic(marker_path, b"")
            self.write_atomic(path, data)
        except OSError:
            pass

    @staticmethod
    def write_atomic(path: Path, data: bytes) -> None:
        """Write a file so that an interrupted write leaves no partial file.

        An interrupted build therefore leaves no corrupt entry.

        Args:
            path: Destination file; missing parent directories are created and the temporary file is made beside it, so
                the final rename is atomic.
            data: Bytes that replace the whole file.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def prune(self) -> None:
        """Delete the entries not used since construction from this root, and the cache roots of other fingerprints.

        Roots of other variants of this fingerprint are kept. Only directories this cache created are removed.
        """
        try:
            children = list(self.directory.iterdir())
            for child in children:
                if (
                    not child.name.startswith(f"{self.fingerprint_prefix}-")
                    and child.is_dir()
                    and (child / self.MARKER_FILENAME).is_file()
                ):
                    shutil.rmtree(child, ignore_errors=True)
            for sub in ("hrefs", "bodies"):
                folder = self.root / sub
                if not folder.is_dir():
                    continue
                for path in folder.iterdir():
                    if path not in self.used_paths and path.is_file():
                        path.unlink()
        except OSError:
            pass
