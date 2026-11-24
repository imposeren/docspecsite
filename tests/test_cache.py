import hashlib
import json
import os
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

from docspecsite import diskcache
from docspecsite.cache import BodyCache
from docspecsite.diskcache import FrontMatterCache
from docspecsite.markdown import FrontMatterSplit, Marker, RenderedLink

FP = "a" * 64


def _make_cache_root(base: Path, fp: str, variant: str = "docs") -> Path:
    return base / f"{hashlib.sha256(fp.encode()).hexdigest()[:16]}-{variant}"


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
    first_cache = BodyCache(tmp_path, FP, "docs")
    assert first_cache.get_body("blob1", "k", compute) == "<p>x</p>"
    assert (first_cache.hit_count, first_cache.miss_count) == (0, 1)
    second_cache = BodyCache(tmp_path, FP, "docs")
    assert second_cache.get_body("blob1", "k", compute) == "<p>x</p>"
    assert len(calls) == 1
    assert (second_cache.hit_count, second_cache.miss_count) == (1, 0)


def test_key_change_rerenders(tmp_path: Path) -> None:
    compute, calls = _make_counting_compute("<p>x</p>")
    cache = BodyCache(tmp_path, FP, "docs")
    cache.get_body("blob1", "k1", compute)
    cache.get_body("blob1", "k2", compute)
    assert len(calls) == 2


def test_fingerprint_separates(tmp_path: Path) -> None:
    compute, calls = _make_counting_compute("<p>x</p>")
    BodyCache(tmp_path, FP, "docs").get_body("blob1", "k", compute)
    other = BodyCache(tmp_path, "b" * 64, "docs")
    other.get_body("blob1", "k", compute)
    assert len(calls) == 2
    other.prune()
    assert not (_make_cache_root(tmp_path, FP)).exists()
    assert (_make_cache_root(tmp_path, "b" * 64)).is_dir()


def test_variants_kept_by_prune(tmp_path: Path) -> None:
    compute, _ = _make_counting_compute("<p>x</p>")
    docs_cache = BodyCache(tmp_path, FP, "docs")
    docs_cache.get_body("blob1", "k", compute)
    code_and_docs_cache = BodyCache(tmp_path, FP, "code+docs")
    code_and_docs_cache.get_body("blob1", "k", compute)
    code_and_docs_cache.prune()
    assert _make_cache_root(tmp_path, FP, "docs").is_dir()
    assert _make_cache_root(tmp_path, FP, "code+docs").is_dir()
    other_fingerprint_cache = BodyCache(tmp_path, "b" * 64, "docs")
    other_fingerprint_cache.get_body("blob1", "k", compute)
    other_fingerprint_cache.prune()
    assert not _make_cache_root(tmp_path, FP, "docs").exists()
    assert not _make_cache_root(tmp_path, FP, "code+docs").exists()
    lookalike = tmp_path / f"{other_fingerprint_cache.fingerprint_prefix}x"
    lookalike.mkdir()
    (lookalike / BodyCache.MARKER_FILENAME).touch()
    other_fingerprint_cache.prune()
    assert not lookalike.exists()


def test_prune_unused(tmp_path: Path) -> None:
    compute, _ = _make_counting_compute("<p>x</p>")
    stale_cache = BodyCache(tmp_path, FP, "docs")
    stale_cache.get_body("blob1", "k", compute)
    stale_cache.get_body("blob2", "k", compute)
    stale_cache.get_hrefs("blob1", lambda: ["a.md"])
    stale_cache.get_hrefs("blob2", lambda: ["b.md"])
    fresh_cache = BodyCache(tmp_path, FP, "docs")
    fresh_cache.get_body("blob1", "k", compute)
    fresh_cache.get_hrefs("blob1", lambda: ["a.md"])
    fresh_cache.prune()
    base = _make_cache_root(tmp_path, FP)
    assert len(list((base / "bodies").iterdir())) == 1
    assert [p.name for p in (base / "hrefs").iterdir()] == ["blob1.json"]


def test_hrefs_cached_and_corrupt_is_miss(tmp_path: Path) -> None:
    BodyCache(tmp_path, FP, "docs").get_hrefs("blob1", lambda: ["a.md"])
    cache = BodyCache(tmp_path, FP, "docs")
    assert cache.get_hrefs("blob1", lambda: ["never"]) == ["a.md"]
    (_make_cache_root(tmp_path, FP) / "hrefs" / "blob1.json").write_text("{not json")
    assert BodyCache(tmp_path, FP, "docs").get_hrefs("blob1", lambda: ["b.md"]) == ["b.md"]
    compute, calls = _make_counting_compute("<p>y</p>")
    first_cache = BodyCache(tmp_path, FP, "docs")
    first_cache.get_body("blob1", "k", compute)
    for path in (_make_cache_root(tmp_path, FP) / "bodies").iterdir():
        path.write_bytes(b"\xff\xfe")
    assert BodyCache(tmp_path, FP, "docs").get_body("blob1", "k", compute) == "<p>y</p>"
    assert len(calls) == 2
    assert json.loads(next((_make_cache_root(tmp_path, FP) / "hrefs").iterdir()).read_text()) == ["b.md"]


def test_targets_key_order_independent() -> None:
    link_with_marker = RenderedLink("a.html", (Marker("marker newer", "newer doc"),))
    link_without_href = RenderedLink(None)
    assert BodyCache.make_targets_key(
        {"a.md": link_with_marker, "b.md": link_without_href}
    ) == BodyCache.make_targets_key({"b.md": link_without_href, "a.md": link_with_marker})
    assert BodyCache.make_targets_key({"a.md": link_with_marker}) != BodyCache.make_targets_key(
        {"a.md": link_without_href}
    )
    assert BodyCache.make_targets_key({"a.md": link_without_href}) != BodyCache.make_targets_key(
        {"a.md": RenderedLink(None, use_code_style=True)}
    )
    assert BodyCache.make_targets_key({"a.md": RenderedLink("a.html", code_text="x")}) != BodyCache.make_targets_key(
        {"a.md": RenderedLink("a.html", code_text="y")}
    )


def test_fingerprint_is_stable_hex() -> None:
    assert BodyCache.compute_fingerprint() == BodyCache.compute_fingerprint()
    assert len(BodyCache.compute_fingerprint()) > 16


def test_fingerprint_includes_rendering_dependency_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    before = BodyCache.compute_fingerprint()
    seen: list[str] = []

    def fake_installed_version(name: str) -> str:
        seen.append(name)
        if name == "griffelib":
            raise PackageNotFoundError(name)
        return "99.0"

    monkeypatch.setattr(diskcache, "version", fake_installed_version)
    assert BodyCache.compute_fingerprint() != before
    assert seen == ["markdown-it-py", "mdit-py-plugins", "jinja2", "griffelib"]


def test_prune_keeps_foreign_data(tmp_path: Path) -> None:
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "f.txt").write_text("x")
    (tmp_path / "foreign.txt").write_text("y")
    compute, _ = _make_counting_compute("<p>x</p>")
    BodyCache(tmp_path, FP, "docs").get_body("blob1", "k", compute)
    other_fingerprint_cache = BodyCache(tmp_path, "b" * 64, "docs")
    other_fingerprint_cache.get_body("blob1", "k", compute)
    other_fingerprint_cache.prune()
    assert (tmp_path / "keep" / "f.txt").read_text() == "x"
    assert (tmp_path / "foreign.txt").read_text() == "y"
    assert not _make_cache_root(tmp_path, FP).exists()


def test_prune_keeps_foreign_files_in_own_root(tmp_path: Path) -> None:
    compute, _ = _make_counting_compute("<p>x</p>")
    cache = BodyCache(tmp_path, FP, "docs")
    cache.get_body("blob1", "k", compute)
    (_make_cache_root(tmp_path, FP) / "bodies" / "sub").mkdir()
    cache.prune()
    assert (_make_cache_root(tmp_path, FP) / "bodies" / "sub").is_dir()


def test_write_failure_is_not_fatal(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    cache = BodyCache(blocker, FP, "docs")
    assert cache.get_hrefs("blob1", lambda: ["a.md"]) == ["a.md"]
    assert cache.get_body("blob1", "k", lambda: "<p>x</p>") == "<p>x</p>"
    cache.prune()
    assert os.path.isfile(blocker)


@pytest.mark.parametrize("split", [FrontMatterSplit("title: X\n", 4), FrontMatterSplit(None, 1)])
def test_front_matter_split_cached_across_instances(tmp_path: Path, split: FrontMatterSplit) -> None:
    calls: list[int] = []

    def compute() -> FrontMatterSplit:
        calls.append(1)
        return split

    assert FrontMatterCache(tmp_path, FP).get_front_matter_split("blob1", compute) == split
    assert FrontMatterCache(tmp_path, FP).get_front_matter_split("blob1", compute) == split
    assert len(calls) == 1


@pytest.mark.parametrize("content", ["not json", "[1, 2]", '["a", 0]', '["a", true]', '["a"]', '{"a": 1}'])
def test_front_matter_split_wrong_entry_is_recomputed(tmp_path: Path, content: str) -> None:
    cache = FrontMatterCache(tmp_path, FP)
    entry = cache.root / "front-matter" / "blob1.json"
    entry.parent.mkdir(parents=True)
    entry.write_text(content, encoding="utf-8")
    assert cache.get_front_matter_split("blob1", lambda: FrontMatterSplit("title: X\n", 4)) == ("title: X\n", 4)
    assert json.loads(entry.read_text(encoding="utf-8")) == ["title: X\n", 4]


def test_prune_removes_unused_front_matter_entries(tmp_path: Path) -> None:
    old_cache = FrontMatterCache(tmp_path, FP)
    old_cache.get_front_matter_split("old", lambda: FrontMatterSplit(None, 1))
    old_cache.get_front_matter_split("kept", lambda: FrontMatterSplit(None, 1))
    new_cache = FrontMatterCache(tmp_path, FP)
    new_cache.get_front_matter_split("kept", lambda: FrontMatterSplit(None, 1))
    new_cache.prune()
    assert not (new_cache.root / "front-matter" / "old.json").exists()
    assert (new_cache.root / "front-matter" / "kept.json").exists()
