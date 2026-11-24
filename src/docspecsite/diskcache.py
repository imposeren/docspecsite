"""On-disk cache roots under ``.docspecsite-cache/``, and the cache of the docs' front matter splits.

Each root belongs to one docspecsite version and variant; entries made by another version are never read, and a root
keeps only the entries its last user read or wrote.

Docs: architecture/docs-tooling.md#incremental-builds
"""

import contextlib
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import ClassVar

from . import __version__
from .markdown import FrontMatterSplit


class CacheRoot:
    """One cache root: a directory of entries for one docspecsite version and variant.

    Entries this instance did not use are removed by :meth:`prune`.
    """

    # Constants
    ENTRY_DIRS: ClassVar[tuple[str, ...]] = ()
    """Directories of a cache root holding this kind of cache's entries; :meth:`prune` looks only into these."""

    FINGERPRINT_PREFIX_LENGTH = 16
    """Number of hex digits of the fingerprint's hash that start each root name, :attr:`fingerprint_prefix`."""

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
            variant: Name of what the root holds, such as the set of built parts of a body cache; caches of different
                variants keep separate roots, so none throws away the entries of another.
        """
        self.directory = directory
        self.fingerprint_prefix = hashlib.sha256(fingerprint.encode()).hexdigest()[: self.FINGERPRINT_PREFIX_LENGTH]
        self.root = directory / f"{self.fingerprint_prefix}-{variant}"
        self.used_paths = set()

    @staticmethod
    def compute_fingerprint() -> str:
        """Return a string identifying this docspecsite version.

        It combines ``__version__``, the versions of the rendering dependencies and a hash of the package's files, so
        cache entries made by another version are not reused.
        """
        digest = hashlib.sha256(__version__.encode())
        for name in CacheRoot.RENDER_DISTRIBUTIONS:
            digest.update(f"{name}={CacheRoot.get_installed_version(name)}\0".encode())
        package_dir = CacheRoot.PACKAGE_DIR
        for path in sorted(p for p in package_dir.rglob("*") if p.is_file()):
            relative = path.relative_to(package_dir)
            if CacheRoot.SKIPPED_DIRS.intersection(relative.parts) or path.suffix == ".pyc":
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

    def load_or_compute_json[T](
        self,
        path: Path,
        compute: Callable[[], T],
        *,
        parse: Callable[[object], T | None],
        to_json: Callable[[T], object],
    ) -> T:
        """Return a value stored as JSON in a cache entry, or else computed and stored.

        Args:
            path: The entry's file; it counts as used, so :meth:`prune` keeps it.
            compute: Called on a miss, or when the entry cannot be read or holds no valid value; its result is stored.
            parse: Gives the value the entry's JSON holds; None when it holds no valid one.
            to_json: Gives the JSON form of a computed value.
        """
        self.used_paths.add(path)
        try:
            cached = parse(json.loads(path.read_text(encoding="utf-8")))
        except OSError, ValueError:
            cached = None
        if cached is not None:
            return cached
        value = compute()
        self.store(path, json.dumps(to_json(value)).encode())
        return value

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
        fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(temp_path, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temp_path)
            raise

    def prune(self) -> None:
        """Delete the entries not used since construction from this root, and the cache roots of other fingerprints.

        Roots of other variants of this fingerprint are kept. Only directories a cache root created are removed.
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
            for sub in self.ENTRY_DIRS:
                folder = self.root / sub
                if not folder.is_dir():
                    continue
                for path in folder.iterdir():
                    if path not in self.used_paths and path.is_file():
                        path.unlink()
        except OSError:
            pass


class FrontMatterCache(CacheRoot):
    """On-disk cache of the docs' front matter splits, one per blob, so a rebuild runs no markdown-it on them."""

    # Entry directories
    FRONT_MATTER_DIR = "front-matter"
    """Directory of a cache root holding the front matter splits, one JSON entry per blob."""

    ENTRY_DIRS = (FRONT_MATTER_DIR,)
    """The entry directories :meth:`~CacheRoot.prune` looks into."""

    # Variant
    VARIANT_PREFIX = "front-matter"
    """Start of the cache root's variant, before the label of the built parts; it keeps the root apart from the body
    cache's root of the same parts."""

    def __init__(self, directory: Path, fingerprint: str, parts_label: str) -> None:
        """Prepare the cache of the front matter splits in a directory.

        Args:
            directory: Directory holding the cache roots; this cache's root is made under it.
            fingerprint: Docspecsite version fingerprint; entries made under another one are never read.
            parts_label: Names of the parts built (:attr:`~docspecsite.sitedocs.SiteDocs.parts_label`); builds of
                different parts keep separate roots, so none throws away the entries of another.
        """
        super().__init__(directory, fingerprint, f"{self.VARIANT_PREFIX}-{parts_label}")

    def load_or_compute_front_matter_split(
        self, blob_sha: str, compute: Callable[[], FrontMatterSplit]
    ) -> FrontMatterSplit:
        """Return the front matter's YAML and the body's line of a blob, from the cache or else computed (and cached).

        Args:
            blob_sha: Git blob SHA hash of the doc's text; names the entry, so all versions with the same text share it.
            compute: Called only on a miss or an unreadable entry to split the text, as
                :meth:`~docspecsite.markdown.MarkdownText.split_front_matter` does; its result is stored.
        """
        return self.load_or_compute_json(
            self.root / self.FRONT_MATTER_DIR / f"{blob_sha}.json",
            compute,
            parse=self._parse_front_matter_split,
            to_json=list,
        )

    @staticmethod
    def _parse_front_matter_split(cached: object) -> FrontMatterSplit | None:
        """Return the front matter split a cache entry holds; None when it holds no valid one.

        Args:
            cached: The entry's JSON value, a list of the YAML text (or None) and the body's line number from 1.
        """
        if (
            isinstance(cached, list)
            and len(cached) == 2
            and (cached[0] is None or isinstance(cached[0], str))
            and type(cached[1]) is int
            and cached[1] >= 1
        ):
            return FrontMatterSplit(cached[0], cached[1])
        return None
