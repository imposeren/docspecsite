import hashlib
import json
import os
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

from docspecsite import cache
from docspecsite.cache import BodyCache, compute_fingerprint, make_targets_key
from docspecsite.markdown import Marker, RenderedLink

FP = "a" * 64


def _make_cache_root(base: Path, fp: str) -> Path:
    return base / hashlib.sha256(fp.encode()).hexdigest()[:16]


def _make_counting_compute(value: str):
    """Return a ``compute`` callback that records its calls, and the list it records them in.

    Args:
        value: Result the callback returns.
    """
    calls: list[int] = []

    def compute() -> str:
        calls.append(1)
        return value

    return compute, calls


def test_body_cached_across_instances(tmp_path: Path) -> None:
    compute, calls = _make_counting_compute("<p>x</p>")
    first_cache = BodyCache(tmp_path, FP)
    assert first_cache.get_body("blob1", "k", compute) == "<p>x</p>"
    assert (first_cache.hit_count, first_cache.miss_count) == (0, 1)
    second_cache = BodyCache(tmp_path, FP)
    assert second_cache.get_body("blob1", "k", compute) == "<p>x</p>"
    assert len(calls) == 1
    assert (second_cache.hit_count, second_cache.miss_count) == (1, 0)


def test_key_change_rerenders(tmp_path: Path) -> None:
    compute, calls = _make_counting_compute("<p>x</p>")
    cache = BodyCache(tmp_path, FP)
    cache.get_body("blob1", "k1", compute)
    cache.get_body("blob1", "k2", compute)
    assert len(calls) == 2


def test_fingerprint_separates(tmp_path: Path) -> None:
    compute, calls = _make_counting_compute("<p>x</p>")
    BodyCache(tmp_path, FP).get_body("blob1", "k", compute)
    other = BodyCache(tmp_path, "b" * 64)
    other.get_body("blob1", "k", compute)
    assert len(calls) == 2
    other.prune()
    assert not (_make_cache_root(tmp_path, FP)).exists()
    assert (_make_cache_root(tmp_path, "b" * 64)).is_dir()


def test_prune_unused(tmp_path: Path) -> None:
    compute, _ = _make_counting_compute("<p>x</p>")
    old = BodyCache(tmp_path, FP)
    old.get_body("blob1", "k", compute)
    old.get_body("blob2", "k", compute)
    old.get_hrefs("blob1", lambda: ["a.md"])
    old.get_hrefs("blob2", lambda: ["b.md"])
    new = BodyCache(tmp_path, FP)
    new.get_body("blob1", "k", compute)
    new.get_hrefs("blob1", lambda: ["a.md"])
    new.prune()
    base = _make_cache_root(tmp_path, FP)
    assert len(list((base / "bodies").iterdir())) == 1
    assert [p.name for p in (base / "hrefs").iterdir()] == ["blob1.json"]


def test_hrefs_cached_and_corrupt_is_miss(tmp_path: Path) -> None:
    BodyCache(tmp_path, FP).get_hrefs("blob1", lambda: ["a.md"])
    cache = BodyCache(tmp_path, FP)
    assert cache.get_hrefs("blob1", lambda: ["never"]) == ["a.md"]
    (_make_cache_root(tmp_path, FP) / "hrefs" / "blob1.json").write_text("{not json")
    assert BodyCache(tmp_path, FP).get_hrefs("blob1", lambda: ["b.md"]) == ["b.md"]
    compute, calls = _make_counting_compute("<p>y</p>")
    first_cache = BodyCache(tmp_path, FP)
    first_cache.get_body("blob1", "k", compute)
    for path in (_make_cache_root(tmp_path, FP) / "bodies").iterdir():
        path.write_bytes(b"\xff\xfe")
    assert BodyCache(tmp_path, FP).get_body("blob1", "k", compute) == "<p>y</p>"
    assert len(calls) == 2
    assert json.loads(next((_make_cache_root(tmp_path, FP) / "hrefs").iterdir()).read_text()) == ["b.md"]


def test_targets_key_order_independent() -> None:
    link_with_marker = RenderedLink("a.html", (Marker("marker newer", "newer doc"),))
    link_without_href = RenderedLink(None)
    assert make_targets_key({"a.md": link_with_marker, "b.md": link_without_href}) == make_targets_key(
        {"b.md": link_without_href, "a.md": link_with_marker}
    )
    assert make_targets_key({"a.md": link_with_marker}) != make_targets_key({"a.md": link_without_href})


def test_fingerprint_is_stable_hex() -> None:
    assert compute_fingerprint() == compute_fingerprint()
    assert len(compute_fingerprint()) > 16


def test_fingerprint_includes_rendering_dependency_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    before = compute_fingerprint()
    seen: list[str] = []

    def fake_installed_version(name: str) -> str:
        seen.append(name)
        if name == "griffelib":
            raise PackageNotFoundError(name)
        return "99.0"

    monkeypatch.setattr(cache, "version", fake_installed_version)
    assert compute_fingerprint() != before
    assert seen == ["markdown-it-py", "mdit-py-plugins", "jinja2", "griffelib"]


def test_prune_keeps_foreign_data(tmp_path: Path) -> None:
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "f.txt").write_text("x")
    (tmp_path / "foreign.txt").write_text("y")
    compute, _ = _make_counting_compute("<p>x</p>")
    BodyCache(tmp_path, FP).get_body("blob1", "k", compute)
    new = BodyCache(tmp_path, "b" * 64)
    new.get_body("blob1", "k", compute)
    new.prune()
    assert (tmp_path / "keep" / "f.txt").read_text() == "x"
    assert (tmp_path / "foreign.txt").read_text() == "y"
    assert not _make_cache_root(tmp_path, FP).exists()


def test_prune_keeps_foreign_files_in_own_root(tmp_path: Path) -> None:
    compute, _ = _make_counting_compute("<p>x</p>")
    cache = BodyCache(tmp_path, FP)
    cache.get_body("blob1", "k", compute)
    (_make_cache_root(tmp_path, FP) / "bodies" / "sub").mkdir()
    cache.prune()
    assert (_make_cache_root(tmp_path, FP) / "bodies" / "sub").is_dir()


def test_write_failure_is_not_fatal(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    cache = BodyCache(blocker, FP)
    assert cache.get_hrefs("blob1", lambda: ["a.md"]) == ["a.md"]
    assert cache.get_body("blob1", "k", lambda: "<p>x</p>") == "<p>x</p>"
    cache.prune()
    assert os.path.isfile(blocker)
