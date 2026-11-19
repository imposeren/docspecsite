"""Incremental-build cache of link hrefs and rendered page bodies.

Covers DS-24. Hrefs are cached per blob and body HTML per fingerprint, blob and link targets.

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

PACKAGE_DIR = Path(__file__).parent
SKIPPED_DIRS = {"__pycache__"}
MARKER = ".docspecsite-cache-root"
RENDER_DISTRIBUTIONS = ("markdown-it-py", "mdit-py-plugins", "jinja2", "griffelib")


def compute_fingerprint() -> str:
    """Return a string identifying this docspecsite version.

    It combines ``__version__``, the versions of the rendering dependencies and a hash of the package's files, so
    cache entries made by another version are not reused.
    """
    digest = hashlib.sha256(__version__.encode())
    for name in RENDER_DISTRIBUTIONS:
        digest.update(f"{name}={get_installed_version(name)}\0".encode())
    for path in sorted(p for p in PACKAGE_DIR.rglob("*") if p.is_file()):
        relative = path.relative_to(PACKAGE_DIR)
        if SKIPPED_DIRS.intersection(relative.parts) or path.suffix == ".pyc":
            continue
        digest.update(relative.as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return f"{__version__}-{digest.hexdigest()}"


def get_installed_version(name: str) -> str:
    """Return the installed version of a distribution, or ``"none"`` if it is not installed.

    Args:
        name: Distribution to look up, under its package-index name (one of the rendering dependencies).
    """
    try:
        return version(name)
    except PackageNotFoundError:
        return "none"


def make_targets_key(resolved: Mapping[str, RenderedLink]) -> str:
    """Return a hash of how the links of a page are rendered.

    It covers each link's href and markers and does not depend on their order.

    Args:
        resolved: Rendering of each link of the page, keyed by the href as written in the doc; only the output href
            and markers enter the hash.
    """
    lines = sorted(
        f"{href}\0{out.href}\0{';'.join(f'{css}:{text}' for css, text in out.markers)}"
        for href, out in resolved.items()
    )
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


class BodyCache:
    """On-disk cache of rendered page bodies.

    It has two levels: link hrefs per blob and body HTML per blob and rendering. Entries this instance did not use are
    removed by ``prune``.

    Attributes:
        directory: Directory holding the cache roots, one per docspecsite version fingerprint.
        root: This fingerprint's cache root under ``directory``.
        used_paths: Entry files read or written by this instance; ``prune`` keeps only these.
        hit_count: Number of bodies taken from the cache.
        miss_count: Number of bodies rendered because the cache did not have them.
    """

    def __init__(self, directory: Path, fingerprint: str) -> None:
        """Prepare a cache in a directory.

        Args:
            directory: Directory holding the cache roots; one root per fingerprint is made under it.
            fingerprint: Docspecsite version fingerprint; entries made under another one are never read.
        """
        self.directory = directory
        self.root = directory / hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
        self.used_paths: set[Path] = set()
        self.hit_count = 0
        self.miss_count = 0

    def get_hrefs(self, blob: str, compute: Callable[[], list[str]]) -> list[str]:
        """Return the link hrefs of a blob, from the cache or else computed (and cached).

        Args:
            blob: Git blob sha of the doc's text; names the entry, so every version with the same text shares it.
            compute: Called only on a miss or an unreadable entry to extract the hrefs; its result is stored.
        """
        path = self.root / "hrefs" / f"{blob}.json"
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

    def get_body(self, blob: str, key: str, compute: Callable[[], str]) -> str:
        """Return the body HTML of a blob rendered for given link targets.

        It comes from the cache or else is computed. Cache hits and misses are counted in ``hit_count`` and
        ``miss_count``.

        Args:
            blob: Git blob sha of the doc's text; part of the entry name with ``key`` and the fingerprint.
            key: How the page's links and Contents list are rendered (``make_targets_key`` plus the Contents
                threshold); a different key gives a separate entry.
            compute: Called only on a miss to render the body HTML; its result is stored.
        """
        entry_name = hashlib.sha256(f"{self.root.name}\0{blob}\0{key}".encode()).hexdigest()
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

    def store(self, path: Path, data: bytes) -> None:
        """Write a cache entry.

        A failing cache directory (read-only, full) only disables caching.

        Args:
            path: Entry file under this cache's fingerprint root; the root also gets the marker that lets ``prune``
                remove it.
            data: Entry contents, written atomically.
        """
        try:
            marker = self.root / MARKER
            if not marker.exists():
                self.write_atomic(marker, b"")
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
        """Delete the entries not used since construction, and the cache roots of other fingerprints.

        Only directories this cache created are removed.
        """
        try:
            children = list(self.directory.iterdir())
            for child in children:
                if child != self.root and child.is_dir() and (child / MARKER).is_file():
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
