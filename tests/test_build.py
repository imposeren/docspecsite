import re
import warnings
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import griffe
import pytest
from conftest import HistoryRepo, edit_text, extract_aside, make_commit, move_sample_package_to_root, run_git, write_doc

from docspecsite.build import BuildError, BuildResult, SiteBuilder, run_build
from docspecsite.coderef import Codebase, CodeError, CodeReference
from docspecsite.config import ProjectConfig
from docspecsite.errors import DocspecsiteError, DocspecsiteWarning, InternalErrorWarning
from docspecsite.git import UnknownRefError
from docspecsite.history import Version
from docspecsite.indexes import IndexRenderer
from docspecsite.pages import Page, PageLink, Templates
from docspecsite.parts import Part

_LINK = re.compile(r'(?:href|src)="([^"]*)"')
_EXTERNAL = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_FIVE_SECTIONS = "Summary.\n\n" + "".join(f"## S{i}\n\n### Sub{i}\n\n" for i in range(1, 6))


@pytest.fixture
def repo(history_repo: HistoryRepo, code_tree: Path) -> HistoryRepo:
    """``history_repo`` with ``code_tree``'s package committed on top.

    Args:
        history_repo: Repository with the named commits; the commit of the code is added as ``code``.
        code_tree: The same tree with the sample package written, not yet committed.
    """
    root, shas = history_repo
    assert code_tree == root
    shas["code"] = make_commit(root, "add code", "2026-11-06T12:00:00+00:00")
    return HistoryRepo(root, shas)


def _read(site_dir: Path, path: str) -> str:
    return (site_dir / path).read_text(encoding="utf-8")


def _get_messages(recorded: Iterable[warnings.WarningMessage]) -> list[str]:
    return [str(w.message) for w in recorded if w.category is DocspecsiteWarning]


def _shorten_sha(sha: str) -> str:
    return sha[:12]


def test_build_layout(repo: HistoryRepo, tmp_path: Path) -> None:
    root, shas = repo
    site_dir = tmp_path / "site"
    build_result = run_build(root, "main", site_dir)
    for path in (
        "index.html",
        "meta/a.html",
        f"meta/a/v/{_shorten_sha(shas['c3'])}.diff.html",
        "status.html",
        "llms.txt",
        "assets/docspecsite.css",
        "assets/docspecsite.js",
        "reference/code/sample.mod.html",
        "components/core.html",
        ".docspecsite-manifest",
    ):
        assert (site_dir / path).is_file(), path
    for key in ("c1", "c3", "c5"):
        assert (site_dir / f"meta/a/v/{_shorten_sha(shas[key])}.html").is_file(), key
    assert not (site_dir / f"meta/a/v/{_shorten_sha(shas['c2'])}.html").exists()
    assert not (site_dir / f"meta/a/v/{_shorten_sha(shas['c1'])}.diff.html").exists()
    c_page = _read(site_dir, "meta/c.html")
    assert c_page.count("<option") == 1
    assert "diff-link" not in c_page
    assert not list((site_dir / "meta/c/v").glob("*.diff.html"))
    assert build_result.page_count == len(list(site_dir.rglob("*.html")))
    manifest = set(_read(site_dir, ".docspecsite-manifest").splitlines())
    assert "meta/a.html" in manifest
    assert "llms.txt" in manifest


def test_build_old_and_latest(repo: HistoryRepo, tmp_path: Path) -> None:
    root, shas = repo
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    old = _read(site_dir, f"meta/a/v/{_shorten_sha(shas['c1'])}.html")
    assert '<div class="old-banner">⚠ OLD VERSION — 2026-11-01, ' in old
    assert '<body class="old">' in old
    assert "<title>[OLD] a — " in old
    assert 'href="../../b.html"' in old
    assert '<span class="marker newer">newer doc</span>' in old
    middle = _read(site_dir, f"meta/a/v/{_shorten_sha(shas['c3'])}.html")
    assert f'href="../../b/v/{_shorten_sha(shas["c2"])}.html"' in middle
    latest = _read(site_dir, "meta/a.html")
    assert "old-banner" not in latest
    assert "marker" not in latest
    assert 'href="b.html"' in latest
    options = re.findall(r"<option[^>]*>([^<]*)</option>", latest)
    assert len(options) == 3
    newest_option, oldest_option = options[0], options[-1]  # the picker lists the newest version first
    assert oldest_option == f"2026-11-01 · {_shorten_sha(shas['c1'])} · add a"
    assert newest_option == f"2026-11-05 · {_shorten_sha(shas['c5'])} · change a again"
    assert 'class="diff-link" href="a/v/' in latest
    permalink = _read(site_dir, f"meta/a/v/{_shorten_sha(shas['c5'])}.html")
    assert "old-banner" not in permalink
    assert 'href="../../b.html"' in permalink


def test_build_is_incremental(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    site_dir = tmp_path / "site"
    first_build = run_build(root, "main", site_dir)
    assert first_build.rendered_count > 0
    second_build = run_build(root, "main", site_dir)
    assert second_build.rendered_count == 0
    assert second_build.cached_count == first_build.rendered_count + first_build.cached_count
    write_doc(root, "meta/b.md", "No links. Changed once more.\n")
    make_commit(root, "spec: change b again", "2026-11-07T12:00:00+00:00")
    third_build = run_build(root, "main", site_dir)
    assert third_build.rendered_count == 1
    assert third_build.rendered_count + third_build.cached_count == second_build.cached_count + 1


def test_build_relative_links_only(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    write_doc(
        root, "meta/d.md", "See [a](a.md#x), [dir](../architecture/), [img](pic.png) and [code](code:sample.mod).\n"
    )
    (root / "docs/meta/pic.png").write_bytes(b"\x89PNG")
    make_commit(root, "spec: add d", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    assert (site_dir / "meta/pic.png").read_bytes() == b"\x89PNG"
    pages = list(site_dir.rglob("*.html"))
    assert pages
    for page in pages:
        for url in _LINK.findall(page.read_text(encoding="utf-8")):
            assert not url.startswith("/"), (page, url)
            if _EXTERNAL.match(url) or url.startswith("#"):
                continue
            path = unquote(url.split("#", 1)[0].split("?", 1)[0])
            assert (page.parent / path).resolve().is_file(), (page.relative_to(site_dir), url)


def test_build_keeps_foreign_files(repo: HistoryRepo, tmp_path: Path) -> None:
    root, shas = repo
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "keep.txt").write_text("mine", encoding="utf-8")
    run_build(root, "main", site_dir)
    run_build(root, "main", site_dir)
    assert (site_dir / "keep.txt").read_text(encoding="utf-8") == "mine"
    c_version = site_dir / f"meta/c/v/{_shorten_sha(shas['c1'])}.html"
    assert c_version.is_file()
    (root / "docs/meta/c.md").unlink()
    make_commit(root, "spec: drop c", "2026-11-07T12:00:00+00:00")
    with pytest.warns(DocspecsiteWarning, match="unresolvable link"):
        run_build(root, "main", site_dir)
    assert not (site_dir / "meta/c.html").exists()
    assert not c_version.exists()
    assert (site_dir / "meta/a.html").is_file()
    assert (site_dir / "keep.txt").read_text(encoding="utf-8") == "mine"
    assert "meta/c.html" not in _read(site_dir, ".docspecsite-manifest").splitlines()


def test_diff_html() -> None:
    html = SiteBuilder.render_diff_html("a\nb <i>\n", "a\nc\n")
    assert html.startswith('<pre class="diff">')
    assert '<span class="del">-b &lt;i&gt;</span>' in html
    assert '<span class="add">+c</span>' in html
    assert '<span class="hunk">@@' in html


def test_write_site_writes_only_changed_files(tmp_path: Path) -> None:
    site_dir = tmp_path / "out"
    SiteBuilder.write_site(site_dir, {"a.html": b"a", "d/b.html": b"b"})
    stamp = (site_dir / "a.html").stat().st_mtime_ns
    (site_dir / "a.html").touch()
    touched = (site_dir / "a.html").stat().st_mtime_ns
    SiteBuilder.write_site(site_dir, {"a.html": b"a", "d/c.html": b"c"})
    assert (site_dir / "a.html").stat().st_mtime_ns == touched >= stamp
    assert not (site_dir / "d/b.html").exists()
    assert (site_dir / "d/c.html").read_bytes() == b"c"


def test_write_site_refuses_paths_outside_out(tmp_path: Path) -> None:
    site_dir = tmp_path / "out"
    (tmp_path / "elsewhere").mkdir()
    site_dir.mkdir()
    (site_dir / "link").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    refused = SiteBuilder.write_site(
        site_dir, {"a.html": b"a", "../x.html": b"x", "/abs.html": b"x", "": b"x", "link/y.html": b"y"}
    )
    assert sorted(refused) == ["", "../x.html", "/abs.html", "link/y.html"]
    assert not (tmp_path / "x.html").exists()
    assert not (tmp_path / "elsewhere/y.html").exists()
    assert (site_dir / "a.html").is_file()


def test_write_site_does_not_delete_through_symlinks(tmp_path: Path) -> None:
    site_dir = tmp_path / "out"
    (tmp_path / "elsewhere").mkdir()
    victim = tmp_path / "elsewhere/v.html"
    victim.write_text("v", encoding="utf-8")
    site_dir.mkdir()
    (site_dir / "link").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    (site_dir / ".docspecsite-manifest").write_text("link/v.html\n", encoding="utf-8")
    SiteBuilder.write_site(site_dir, {"a.html": b"a"})
    assert victim.is_file()


def test_build_odd_tags(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    write_doc(root, "meta/odd.md", "Odd.\n", tags=["../../x", "a b"], components=["../../y"])
    make_commit(root, "add odd", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site" / "out"
    with pytest.warns(DocspecsiteWarning) as recorded:
        run_build(root, "main", site_dir)
    messages = _get_messages(recorded)
    assert not list((tmp_path / "site").glob("[xy]*"))
    assert not (site_dir / "x.html").exists()
    assert not (site_dir / "y.html").exists()
    assert (site_dir / "tags/a b.html").is_file()
    odd = _read(site_dir, "meta/odd.html")
    assert 'href="../tags/a%20b.html"' in odd
    assert 'tag "../../x" cannot be a file name, no index page' in messages
    assert '<span class="tag">#../../x</span>' in odd
    assert "refusing to write outside --out: components/../../y.html" in messages
    assert "../../y.html" not in odd
    _assert_local_links_resolve(site_dir)


def test_build_one_h1_and_status_reachable(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    write_doc(root, "meta/h.md", "# Heading T\n\nText.\n", tags=["x"])
    make_commit(root, "add h", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    page_html = _read(site_dir, "meta/h.html")
    assert page_html.count("<h1") == 1
    assert page_html.index('<h1 id="heading-t">Heading T</h1>') < page_html.index('class="status')
    assert _read(site_dir, "meta/a.html").count("<h1") == 1
    assert _read(site_dir, "reference/code/sample.mod.html").count("<h1") == 1
    assert 'href="status.html"' in _read(site_dir, "index.html")
    assert re.search(r'<nav class="breadcrumb">\s*<a href="\.\./index\.html">', _read(site_dir, "tags/x.html"))
    _assert_local_links_resolve(site_dir)


def test_write_site_ignores_manifest_entries_outside_out(tmp_path: Path) -> None:
    site_dir = tmp_path / "out"
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    site_dir.mkdir()
    (site_dir / ".docspecsite-manifest").write_text("../outside.txt\n/etc/hostname\n", encoding="utf-8")
    SiteBuilder.write_site(site_dir, {"a.html": b"a"})
    assert outside.is_file()


def test_build_worktree(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    write_doc(root, "meta/a.md", "Edited in the working tree.\n")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    assert not (site_dir / "meta/a/v/worktree.html").exists()
    assert "Edited in the working tree." not in _read(site_dir, "meta/a.html")
    run_build(root, "main", site_dir, include_worktree=True)
    assert (site_dir / "meta/a/v/worktree.html").is_file()
    assert (site_dir / "meta/a/v/worktree.diff.html").is_file()
    latest = _read(site_dir, "meta/a.html")
    assert "Edited in the working tree." in latest
    assert "working copy (uncommitted)" in latest


def test_build_mermaid_assets(repo: HistoryRepo, tmp_path: Path, recwarn: pytest.WarningsRecorder) -> None:
    root, _ = repo
    write_doc(root, "meta/m.md", "```mermaid\ngraph TD; A-->B\n```\n")
    make_commit(root, "spec: add m", "2026-11-07T12:00:00+00:00")
    vendor = tmp_path / "vendor"
    (vendor / "mermaid").mkdir(parents=True)
    (vendor / "mermaid/mermaid.min.js").write_bytes(b"// mermaid")
    (vendor / "mermaid/LICENSE").write_bytes(b"MIT")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir, vendor_dir=vendor)
    assert (site_dir / "assets/mermaid.min.js").read_bytes() == b"// mermaid"
    assert (site_dir / "assets/mermaid.LICENSE.txt").read_bytes() == b"MIT"
    assert 'src="../assets/mermaid.min.js"' in _read(site_dir, "meta/m.html")
    assert "mermaid.min.js" not in _read(site_dir, "meta/a.html")
    assert not [m for m in _get_messages(recwarn) if "mermaid" in m]

    empty = tmp_path / "empty"
    empty.mkdir()
    site_dir2 = tmp_path / "site2"
    with pytest.warns(DocspecsiteWarning) as recorded:
        run_build(root, "main", site_dir2, vendor_dir=empty)
    assert [m for m in _get_messages(recorded) if "mermaid bundle not found" in m]
    assert not (site_dir2 / "assets/mermaid.min.js").exists()
    page_html = _read(site_dir2, "meta/m.html")
    assert '<pre class="mermaid">graph TD; A--&gt;B' in page_html
    assert "mermaid.min.js" not in page_html


def test_build_mermaid_default_vendor_dir_from_env(
    repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = repo
    write_doc(root, "meta/m.md", "```mermaid\ngraph TD; A-->B\n```\n")
    make_commit(root, "spec: add m", "2026-11-07T12:00:00+00:00")
    vendor = tmp_path / "vendor"
    (vendor / "mermaid").mkdir(parents=True)
    (vendor / "mermaid/mermaid.min.js").write_bytes(b"// mermaid")
    monkeypatch.setenv("DOCSPECSITE_VENDOR_DIR", str(vendor))
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    assert (site_dir / "assets/mermaid.min.js").is_file()


def test_build_code_links_in_docs(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    write_doc(root, "meta/x.md", "[t](code:sample.mod.Thing)\n", title="X doc", code=["sample.mod"])
    write_doc(root, "meta/y.md", "Other.\n", title="Y doc", code=["sample.mod.Thing"])
    write_doc(root, "meta/z.md", "Unrelated.\n", title="Z doc", code=["sample.base"])
    make_commit(root, "spec: add x", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    assert 'href="../reference/code/sample.mod.html#sample.mod.Thing"' in _read(site_dir, "meta/x.html")
    mod = _read(site_dir, "reference/code/sample.mod.html")
    described = mod.split('<aside class="described-in">', 1)[1].split("</aside>", 1)[0]
    assert '<a href="../../meta/x.html">X doc</a>' in described
    assert '<a href="../../meta/y.html">Y doc</a>' in described
    assert "Z doc" not in described
    package = _read(site_dir, "reference/code/sample.html")
    assert "X doc" not in package
    assert "Y doc" not in package


def test_build_code_index(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    write_doc(root, "reference/index.md", "Reference.\n", title="Reference")
    write_doc(root, "reference/code/index.md", "Generated.\n", title="Code reference")
    make_commit(root, "spec: add reference", "2026-11-07T12:00:00+00:00")
    write_doc(root, "reference/code/index.md", "Generated again.\n", title="Code reference")
    make_commit(root, "spec: edit code index", "2026-11-08T12:00:00+00:00")
    write_doc(root, "meta/a.md", "See [code](../reference/code/index.md).\n", title="A")
    old_sha = make_commit(root, "spec: link a to the code index", "2026-11-09T12:00:00+00:00")
    write_doc(root, "meta/a.md", "No link now.\n", title="A")
    make_commit(root, "spec: unlink", "2026-11-10T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    index = _read(site_dir, "reference/code/index.html")
    assert 'href="sample.html"' in index
    assert "<h2>Packages</h2>" in index
    assert "<h2>Submodules</h2>" not in index
    mod = _read(site_dir, "reference/code/sample.mod.html")
    assert 'href="index.html">Code reference</a>' in mod
    # The entry page is versionless: no /v/ or diff pages and no picker, though it has two versions.
    assert not (site_dir / "reference/code/index").exists()
    assert "<option" not in index
    assert "diff-link" not in index
    assert "<option" in _read(site_dir, "meta/a.html")  # a doc with versions does have a picker
    old = _read(site_dir, f"meta/a/v/{_shorten_sha(old_sha)}.html")
    assert 'href="../../../reference/code/index.html"' in old
    assert "current code" in old


def test_build_warns_about_unresolvable_links(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    write_doc(root, "meta/a.md", "See [gone](gone.md) and [c](code:sample.nope).\n")
    sha = make_commit(root, "spec: break a", "2026-11-07T12:00:00+00:00")
    with pytest.warns(DocspecsiteWarning) as recorded:
        run_build(root, "main", tmp_path / "site")
    messages = _get_messages(recorded)
    assert f"docs/meta/a.md@{sha[:12]}: unresolvable link: gone.md" in messages
    assert f"docs/meta/a.md@{sha[:12]}: unknown code element: code:sample.nope" in messages


def test_build_redirect_notice_and_moved_marker(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    write_doc(
        root,
        "meta/c.md",
        "Old body.\n",
        status="redirect",
        redirect_kind="renamed",
        redirect_to=["meta/a.md"],
        reason="Now <a>.",
    )
    write_doc(root, "meta/b.md", "See [c](c.md).\n", related=["meta/c.md"])
    make_commit(root, "spec: rename c", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    c_page = _read(site_dir, "meta/c.html")
    assert '<div class="redirect-notice">' in c_page
    assert "<strong>Renamed</strong>" in c_page
    assert '<a href="a.html">a</a>' in c_page
    assert '<p class="reason">Now &lt;a&gt;.</p>' in c_page
    assert "http-equiv" not in c_page
    b_page = _read(site_dir, "meta/b.html")
    assert '<span class="marker moved">→ moved</span>' in b_page
    related = extract_aside(b_page, "related")
    assert '<a href="c.html">c</a>' in related
    backlinks = extract_aside(_read(site_dir, "meta/c.html"), "backlinks")
    assert '<a href="b.html">b</a>' in backlinks


def test_build_escapes_titles_and_subjects(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    write_doc(root, "meta/e.md", "Body.\n", title='E <b> & "q"', summary="S <i> & more")
    make_commit(root, 'spec: add <e> & "quote"', "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    page_html = _read(site_dir, "meta/e.html")
    assert "<b>" not in page_html
    assert "<h1>E &lt;b&gt; &amp; &#34;q&#34;</h1>" in page_html
    assert "add &lt;e&gt; &amp; &#34;quote&#34;</option>" in page_html
    assert "<i>" not in _read(site_dir, "status.html")
    assert "<e>" not in page_html
    llms = _read(site_dir, "llms.txt")
    assert '[E <b> & "q"](meta/e.html): S <i> & more' in llms


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[code-components\n", "docspecsite.toml: not valid TOML: "),
        ("source-url = 3\n", 'docspecsite.toml: "source-url" must be a string'),
    ],
)
def test_build_invalid_config_fails(repo: HistoryRepo, tmp_path: Path, text: str, expected: str) -> None:
    root, _ = repo
    (root / ProjectConfig.CONFIG_FILE).write_text(text, encoding="utf-8")
    make_commit(root, "break the config", "2026-11-07T12:00:00+00:00")
    with pytest.raises(BuildError) as raised:
        run_build(root, "main", tmp_path / "site")
    assert str(raised.value).startswith(expected)


def test_build_code_error_is_a_warning(repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, _ = repo

    def raise_in_load(root: object, config: object) -> None:
        raise CodeError("cannot locate Docs: lines of %s", "sample.mod", file="tools/sample/src/sample/mod.py")

    monkeypatch.setattr(Codebase, "load", raise_in_load)
    site_dir = tmp_path / "site"
    with pytest.warns(DocspecsiteWarning) as recorded:
        run_build(root, "main", site_dir)
    assert (site_dir / "meta/a.html").is_file()
    assert not (site_dir / "reference/code/sample.mod.html").exists()
    assert "cannot load code: cannot locate Docs: lines of sample.mod" in _get_messages(recorded)


def test_build_code_page_error_is_local(repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, _ = repo
    original = CodeReference.build_page

    def raise_in_build_page(self: CodeReference, module: griffe.Module, described_in: Sequence[PageLink]) -> Page:
        if module.path == "sample.mod":
            raise CodeError("namespace package has no single file: %s", "sample.mod")
        return original(self, module, described_in)

    monkeypatch.setattr(CodeReference, "build_page", raise_in_build_page)
    site_dir = tmp_path / "site"
    build_result = run_build(root, "main", site_dir)
    assert (site_dir / "meta/a.html").is_file()
    assert (site_dir / "reference/code/sample.html").is_file()
    assert not (site_dir / "reference/code/sample.mod.html").exists()
    assert build_result.errors == (
        "reference/code/sample.mod: CodeError: namespace package has no single file: sample.mod",
    )


def test_build_code_template_error_is_local(repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, _ = repo

    def raise_in_create_environment() -> None:
        raise DocspecsiteError("no code template")

    monkeypatch.setattr("docspecsite.coderef.create_environment", raise_in_create_environment)
    site_dir = tmp_path / "site"
    build_result = run_build(root, "main", site_dir)
    assert (site_dir / "meta/a.html").is_file()
    assert not (site_dir / "reference/code/sample.html").exists()
    assert build_result.errors == (
        "reference/code/sample: DocspecsiteError: no code template",
        "reference/code/sample.base: DocspecsiteError: no code template",
        "reference/code/sample.mod: DocspecsiteError: no code template",
    )


def test_build_docs_files_colliding_with_generated_files(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    (root / "docs/meta/a.html").write_text("mine", encoding="utf-8")
    (root / "docs/meta/a").write_text("file where a version directory goes", encoding="utf-8")
    (root / "docs/llms.txt").write_text("mine", encoding="utf-8")
    (root / "docs/meta/ok.png").write_bytes(b"png")
    make_commit(root, "add colliding files", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    with pytest.warns(DocspecsiteWarning) as recorded:
        run_build(root, "main", site_dir)
    assert "<html" in _read(site_dir, "meta/a.html")
    assert (site_dir / "meta/a/v").is_dir()
    assert _read(site_dir, "llms.txt") != "mine"
    assert (site_dir / "meta/ok.png").read_bytes() == b"png"
    for path in ("meta/a.html", "meta/a", "llms.txt"):
        assert f"docs/{path}: collides with a generated file, not copied" in _get_messages(recorded)


def test_build_worktree_copies_docs_files(repo: HistoryRepo, tmp_path: Path, recwarn: pytest.WarningsRecorder) -> None:
    root, _ = repo
    (root / "docs/meta/new.png").write_bytes(b"new")
    write_doc(root, "meta/a.md", "See ![n](new.png).\n")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir, include_worktree=True)
    assert (site_dir / "meta/new.png").read_bytes() == b"new"
    assert 'src="new.png"' in _read(site_dir, "meta/a.html")
    assert "doc no longer exists" not in _read(site_dir, "meta/a.html")
    assert not any("new.png" in m for m in _get_messages(recwarn))


def test_build_doc_with_quoted_name(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    write_doc(root, 'meta/notes "draft".md', "Draft.\n")
    sha = make_commit(root, "add notes", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    assert (site_dir / 'meta/notes "draft".html').is_file()
    assert (site_dir / f'meta/notes "draft"/v/{_shorten_sha(sha)}.html').is_file()


def test_build_unknown_ref(git_repo: Path, tmp_path: Path) -> None:
    with pytest.raises(UnknownRefError):
        run_build(git_repo, "nope", tmp_path / "site")


def test_build_reads_ref_not_worktree(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    run_git(root, "checkout", "-q", "-b", "other")
    write_doc(root, "meta/a.md", "Only on other.\n")
    make_commit(root, "spec: other", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    assert "Only on other." not in _read(site_dir, "meta/a.html")


@pytest.mark.parametrize(
    ("config_text", "body", "expected_messages", "expected_html"),
    [
        ("", "No repository links.\n", [], "No repository links."),
        (
            'source-url = "https://github.com/o/r"\n',
            "See [compose](../compose.yaml).\n",
            [],
            'href="https://github.com/o/r/blob/{sha}/compose.yaml"',
        ),
        (
            'code-dirs = ["src"]\n',
            "No repository links.\n",
            ["links to repository files cannot be made"],
            "No repository",
        ),
        (
            'code-dirs = ["src"]\n',
            "See [compose](../compose.yaml).\n",
            ["links to repository files cannot be made"],
            "See compose.",
        ),
    ],
)
def test_build_warns_once_without_source_url(
    git_repo: Path, tmp_path: Path, config_text: str, body: str, expected_messages: list[str], expected_html: str
) -> None:
    (git_repo / ProjectConfig.CONFIG_FILE).write_text(config_text, encoding="utf-8")
    (git_repo / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    write_doc(git_repo, "a.md", body)
    sha = make_commit(git_repo, "set the config")
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        run_build(git_repo, "main", tmp_path / "site")
    messages = [m for m in _get_messages(recorded) if "source-url" in m]
    assert [m.rpartition("source-url: ")[2] for m in messages] == expected_messages
    assert expected_html.format(sha=sha) in _read(tmp_path / "site", "a.html")


def test_build_does_not_warn_about_repo_links_of_old_versions(git_repo: Path, tmp_path: Path) -> None:
    (git_repo / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    write_doc(git_repo, "a.md", "See [compose](../compose.yaml).\n")
    sha = make_commit(git_repo, "spec: add a", "2026-11-07T12:00:00+00:00")
    write_doc(git_repo, "a.md", "No repository links.\n")
    make_commit(git_repo, "spec: drop the link", "2026-11-08T12:00:00+00:00")
    site_dir = tmp_path / "site"
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        run_build(git_repo, "main", site_dir)
    assert not [m for m in _get_messages(recorded) if "source-url" in m]
    assert "See compose." in _read(site_dir, f"a/v/{_shorten_sha(sha)}.html")


def _assert_local_links_resolve(site_dir: Path) -> None:
    """Assert that every local link in the built pages points at a file of the site.

    Args:
        site_dir: Output directory of the built site; it must hold at least one page.
    """
    pages = list(site_dir.rglob("*.html"))
    assert pages
    for page in pages:
        for url in _LINK.findall(page.read_text(encoding="utf-8")):
            assert not url.startswith("/"), (page.relative_to(site_dir), url)
            if _EXTERNAL.match(url) or url.startswith("#"):
                continue
            path = unquote(url.split("#", 1)[0].split("?", 1)[0])
            assert (page.parent / path).resolve().is_file(), (page.relative_to(site_dir), url)


def test_build_without_source_url_has_no_root_links(history_repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = history_repo
    (root / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    write_doc(root, "meta/templates/t.md", "Template.\n")
    write_doc(root, "meta/d.md", "See [compose](../../compose.yaml) and [tpl](templates/t.md).\n")
    write_doc(root, "meta/e.md", "Also [compose](../../compose.yaml).\n")
    sha = make_commit(root, "spec: add d and e", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        run_build(root, "main", site_dir)
    _assert_local_links_resolve(site_dir)
    assert "See compose and tpl." in _read(site_dir, "meta/d.html")
    assert "Also compose." in _read(site_dir, "meta/e.html")
    assert [m for m in _get_messages(recorded) if "source-url" in m] == [
        (
            f"docs/meta/d.md@{_shorten_sha(sha)}: docspecsite.toml has no source-url: "
            "links to repository files, such as ../../compose.yaml, are plain text"
        )
    ]


def test_build_old_version_tag_without_index_is_plain_text(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    write_doc(root, "meta/b.md", "Tagged.\n", tags=["gone"], components=["core"])
    old = make_commit(root, "spec: tag b", "2026-11-07T12:00:00+00:00")
    write_doc(root, "meta/b.md", "Untagged.\n")
    make_commit(root, "spec: untag b", "2026-11-08T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    page_html = _read(site_dir, f"meta/b/v/{_shorten_sha(old)}.html")
    assert "tags/gone.html" not in page_html
    assert '<span class="tag">#gone</span>' in page_html
    assert 'href="../../../components/core.html"' in page_html
    _assert_local_links_resolve(site_dir)


def _break_doc(monkeypatch: pytest.MonkeyPatch, path: str, error: BaseException) -> None:
    """Make every page of a doc raise while it is built.

    Args:
        monkeypatch: Fixture that installs the failing patch.
        path: Doc path relative to ``docs/`` whose pages fail.
        error: Exception raised for each of its pages.
    """
    original = SiteBuilder.build_doc_page

    def raise_in_doc_page(self: SiteBuilder, v: Version, *args: Any) -> Page:
        if v.path == path:
            raise error
        return original(self, v, *args)

    monkeypatch.setattr(SiteBuilder, "build_doc_page", raise_in_doc_page)


def test_build_page_error_is_local(repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, shas = repo
    _break_doc(monkeypatch, "meta/b.md", DocspecsiteError("boom in %s", f"{root}/docs/meta/b.md\nsecond line"))
    site_dir = tmp_path / "site"
    build_result = run_build(root, "main", site_dir)
    assert (site_dir / "meta/a.html").is_file()
    assert (site_dir / "status.html").is_file()
    assert not (site_dir / "meta/b.html").exists()
    assert not (site_dir / f"meta/b/v/{_shorten_sha(shas['c2'])}.html").exists()
    assert (site_dir / f"meta/b/v/{_shorten_sha(shas['c4'])}.diff.html").is_file()
    assert build_result.errors == tuple(
        f"docs/meta/b.md@{_shorten_sha(shas[key])}: DocspecsiteError: boom in docs/meta/b.md second line"
        for key in ("c4", "c2")
    )
    assert build_result.page_count == len(list(site_dir.rglob("*.html")))


def test_build_keyboard_interrupt_is_not_a_page_error(
    repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = repo
    _break_doc(monkeypatch, "meta/b.md", KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        run_build(root, "main", tmp_path / "site")


def test_build_internal_error_is_warned_and_page_left_out(
    repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, shas = repo
    _break_doc(monkeypatch, "meta/b.md", RuntimeError(f"bug in {root}/docs/meta/b.md"))
    site_dir = tmp_path / "site"
    with pytest.warns(InternalErrorWarning) as recorded:
        build_result = run_build(root, "main", site_dir)
    assert [str(w.message) for w in recorded if w.category is InternalErrorWarning] == [
        f"docs/meta/b.md@{_shorten_sha(shas[key])}: internal error: RuntimeError: bug in docs/meta/b.md"
        for key in ("c4", "c4", "c2")
    ]
    assert (site_dir / "meta/a.html").is_file()
    assert not (site_dir / "meta/b.html").exists()
    assert build_result.errors == ()
    assert build_result.failed_count == 2


def test_build_internal_error_filter_raises_with_original_exception(
    repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = repo
    bug = RuntimeError("bug")
    _break_doc(monkeypatch, "meta/b.md", bug)
    with warnings.catch_warnings():
        warnings.filterwarnings("error", category=InternalErrorWarning)
        with pytest.raises(InternalErrorWarning) as raised:
            run_build(root, "main", tmp_path / "site")
    assert raised.value.__context__ is bug
    assert not (tmp_path / "site").exists()


def test_build_strict_stops_at_internal_error(
    repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, shas = repo
    _break_doc(monkeypatch, "meta/b.md", RuntimeError("bug"))
    site_dir = tmp_path / "site"
    filters = list(warnings.filters)
    with pytest.raises(BuildError) as raised:
        run_build(root, "main", site_dir, strict=True)
    assert str(raised.value) == f"strict: docs/meta/b.md@{_shorten_sha(shas['c4'])}: internal error: RuntimeError: bug"
    assert isinstance(raised.value.__cause__, InternalErrorWarning)
    assert not site_dir.exists()
    assert warnings.filters == filters


def test_build_render_and_index_errors_are_local(
    repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = repo
    original = Templates.render

    def render(self: Templates, page: Page, *args: Any, **kwargs: Any) -> str:
        if page.url == "status.html":
            raise DocspecsiteError("bad template")
        return original(self, page, *args, **kwargs)

    def render_no_llms(*args: object) -> str:
        raise DocspecsiteError("no llms")

    monkeypatch.setattr(Templates, "render", render)
    monkeypatch.setattr(IndexRenderer, "render_llms_txt", render_no_llms)
    site_dir = tmp_path / "site"
    build_result = run_build(root, "main", site_dir)
    assert (site_dir / "meta/a.html").is_file()
    assert not (site_dir / "status.html").exists()
    assert not (site_dir / "llms.txt").exists()
    assert build_result.errors == ("status.html: DocspecsiteError: bad template", "llms.txt: DocspecsiteError: no llms")


def test_build_old_version_not_utf8(repo: HistoryRepo, tmp_path: Path) -> None:
    root, shas = repo
    (root / "docs/meta/b.md").write_bytes(b"---\ntitle: \xff\n---\n")
    bad = make_commit(root, "spec: break b", "2026-11-07T12:00:00+00:00")
    write_doc(root, "meta/b.md", "Fixed.\n")
    fixed = make_commit(root, "spec: fix b", "2026-11-08T12:00:00+00:00")
    site_dir = tmp_path / "site"
    build_result = run_build(root, "main", site_dir)
    latest = _read(site_dir, "meta/b.html")
    assert "Fixed." in latest
    assert (site_dir / f"meta/b/v/{_shorten_sha(shas['c4'])}.html").is_file()
    assert (site_dir / f"meta/b/v/{_shorten_sha(fixed)}.html").is_file()
    assert not (site_dir / f"meta/b/v/{_shorten_sha(bad)}.html").exists()
    assert not (site_dir / f"meta/b/v/{_shorten_sha(bad)}.diff.html").exists()
    assert not (site_dir / f"meta/b/v/{_shorten_sha(fixed)}.diff.html").exists()
    assert "diff-link" not in latest
    assert _shorten_sha(bad) not in latest
    assert _shorten_sha(shas["c4"]) in latest
    message = "NotUtf8Error: docs/meta/b.md: not valid UTF-8 (invalid start byte at byte 11)"
    assert build_result.errors == (f"docs/meta/b.md@{_shorten_sha(bad)}: {message}",)
    assert build_result.failed_count == 1


def test_build_failed_counts_pages_not_lines(
    repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, shas = repo
    original_diff = SiteBuilder.build_diff_page

    def raise_in_diff_page(self: SiteBuilder, v: Version, previous: Version) -> Page:
        if v.path == "meta/b.md":
            raise DocspecsiteError("diff")
        return original_diff(self, v, previous)

    _break_doc(monkeypatch, "meta/b.md", DocspecsiteError("page"))
    monkeypatch.setattr(SiteBuilder, "build_diff_page", raise_in_diff_page)
    build_result = run_build(root, "main", tmp_path / "site")
    c4 = _shorten_sha(shas["c4"])
    assert f"docs/meta/b.md@{c4}: DocspecsiteError: page" in build_result.errors
    assert f"docs/meta/b.md@{c4}: DocspecsiteError: diff" in build_result.errors
    assert len(build_result.errors) == 3
    assert build_result.failed_count == 2


def test_build_pages_exclude_refused(repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, _ = repo
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (tmp_path / "elsewhere").mkdir()
    (site_dir / "meta").symlink_to(tmp_path / "elsewhere")
    with pytest.warns(DocspecsiteWarning) as recorded:
        build_result = run_build(root, "main", site_dir)
    assert any(m.startswith("refusing to write outside --out: meta/") for m in _get_messages(recorded))
    assert build_result.page_count == len(list(site_dir.rglob("*.html"))) - len(
        list((site_dir / "meta").rglob("*.html"))
    )


def test_build_worktree_copies_only_files_git_sees(
    repo: HistoryRepo, tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    root, _ = repo
    (root / ".gitignore").write_text("docs/meta/ignored.png\n", encoding="utf-8")
    (root / "docs/meta/ignored.png").write_bytes(b"x")
    (root / "docs/meta/new.png").write_bytes(b"new")
    secret = tmp_path_factory.mktemp("outside") / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    (root / "docs/meta/link.txt").symlink_to(secret)
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir, include_worktree=True)
    assert (site_dir / "meta/new.png").read_bytes() == b"new"
    assert not (site_dir / "meta/ignored.png").exists()
    assert not (site_dir / "meta/link.txt").exists()


def test_build_latest_version_not_utf8(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    (root / "docs/meta/b.md").write_bytes(b"---\ntitle: \xff\n---\n")
    bad = make_commit(root, "spec: break b", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    build_result = run_build(root, "main", site_dir)
    assert not (site_dir / "meta/b.html").exists()
    assert (site_dir / "meta/a.html").is_file()
    assert "meta/b.html" not in _read(site_dir, "status.html")
    assert [error.partition(":")[0] for error in build_result.errors] == [f"docs/meta/b.md@{_shorten_sha(bad)}"]


def test_build_strict_stops_at_first_error(repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, shas = repo
    _break_doc(monkeypatch, "meta/b.md", DocspecsiteError("boom"))
    site_dir = tmp_path / "site"
    with pytest.raises(BuildError) as raised:
        run_build(root, "main", site_dir, strict=True)
    assert str(raised.value) == f"docs/meta/b.md@{_shorten_sha(shas['c4'])}: DocspecsiteError: boom"
    assert raised.value.message == "%s: %s"
    assert not site_dir.exists()


def test_build_strict_fails_on_warnings(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    site_dir = tmp_path / "site"
    assert isinstance(run_build(root, "main", site_dir, strict=True), BuildResult)
    write_doc(root, "meta/a.md", "See [gone](gone.md).\n")
    sha = make_commit(root, "spec: break a", "2026-11-07T12:00:00+00:00")
    other = tmp_path / "other"
    with pytest.raises(BuildError) as raised:
        run_build(root, "main", other, strict=True)
    assert str(raised.value) == f"strict: docs/meta/a.md@{sha[:12]}: unresolvable link: gone.md"
    assert raised.value.message == "strict: %s"
    assert isinstance(raised.value.__cause__, DocspecsiteWarning)
    assert not other.exists()


def test_build_error_messages_keep_relative_paths(
    repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, shas = repo
    monkeypatch.chdir(root)
    _break_doc(
        monkeypatch, "meta/b.md", DocspecsiteError("cannot read %s", f"../../x.md (see ./notes) in {root}/docs/b.md")
    )
    build_result = run_build(Path("."), "main", tmp_path / "site")
    assert build_result.errors[0] == (
        f"docs/meta/b.md@{_shorten_sha(shas['c4'])}: DocspecsiteError: "
        "cannot read ../../x.md (see ./notes) in docs/b.md"
    )


def _set_toc_min(root: Path, value: int) -> None:
    edit_text(
        root / ProjectConfig.CONFIG_FILE,
        lambda text: f"toc-min-headings = {value}\n{text}",
    )


def test_build_contents_list_and_cache_follows_threshold(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    write_doc(root, "meta/long.md", _FIVE_SECTIONS, title="Long")
    make_commit(root, "spec: add long", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    page_html = _read(site_dir, "meta/long.html")
    assert '<nav class="toc"><h2 class="toc-title">Contents</h2>' in page_html
    assert page_html.index('class="toc"') < page_html.index('<h2 id="s1">')
    assert '<a href="#sub3">Sub3</a>' in page_html
    assert "<h2>Contents</h2>" not in page_html
    assert 'class="toc"' not in _read(site_dir, "meta/a.html")
    assert run_build(root, "main", site_dir).rendered_count == 0

    _set_toc_min(root, 6)
    make_commit(root, "config: raise toc threshold", "2026-11-08T12:00:00+00:00")
    build_result = run_build(root, "main", site_dir)
    assert build_result.rendered_count > 0
    assert 'class="toc"' not in _read(site_dir, "meta/long.html")


def test_build_children_panel_only_on_code_pages(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    write_doc(root, "meta/index.md", "Meta.\n\n## Children\n\n- [a](a.md)\n", title="Meta")
    make_commit(root, "spec: index with children", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    assert 'aside class="children"' not in _read(site_dir, "meta/index.html")
    package = _read(site_dir, "reference/code/sample.html")
    assert '<aside class="children">' in package
    assert "<h2>Submodules</h2>" in package
    assert "<h2>Contents</h2>" not in package


def test_build_warns_about_config_problems(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    edit_text(root / ProjectConfig.CONFIG_FILE, lambda text: f'adr_prefix = "DSS"\n{text}')
    make_commit(root, "misspell a setting", "2026-11-07T12:00:00+00:00")
    with pytest.warns(DocspecsiteWarning) as recorded:
        run_build(root, "main", tmp_path / "site")
    assert 'docspecsite.toml: unknown setting "adr_prefix"' in _get_messages(recorded)


@pytest.mark.parametrize("include_worktree", [False, True])
def test_build_accepts_a_byte_order_mark_in_the_config(
    repo: HistoryRepo, tmp_path: Path, *, include_worktree: bool
) -> None:
    root, _ = repo
    edit_text(root / ProjectConfig.CONFIG_FILE, lambda text: f'\ufeffexternal-adr-prefixes = ["PYRF"]\n{text}')
    for name in ("APP-0001-a.md", "PYRF-0001-b.md"):
        write_doc(root, f"architecture/decisions/{name}", decision="accepted", date="2026-11-18")
    make_commit(root, "add external ADR", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir, include_worktree=include_worktree)
    llms = _read(site_dir, "llms.txt")
    assert llms.index("PYRF-0001-b") < llms.index("APP-0001-a")


def test_build_reads_the_worktree_config_only_with_include_worktree(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    committed = (root / ProjectConfig.CONFIG_FILE).read_text(encoding="utf-8")
    (root / ProjectConfig.CONFIG_FILE).write_text(f"toc-min-headings = -1\n{committed}", encoding="utf-8")
    with pytest.raises(BuildError, match='"toc-min-headings" must be a whole number of 0 or more'):
        run_build(root, "main", tmp_path / "site", include_worktree=True)
    (root / ProjectConfig.CONFIG_FILE).write_text(f'adr_prefix = "DSS"\n{committed}', encoding="utf-8")
    with pytest.warns(DocspecsiteWarning) as recorded:
        run_build(root, "main", tmp_path / "site", include_worktree=True)
    assert 'docspecsite.toml: unknown setting "adr_prefix"' in _get_messages(recorded)
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        run_build(root, "main", tmp_path / "site")
    assert not [m for m in _get_messages(recorded) if m.startswith(ProjectConfig.CONFIG_FILE)]


def test_build_orders_adrs_by_configured_prefixes(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    edit_text(root / ProjectConfig.CONFIG_FILE, lambda text: f'external-adr-prefixes = ["PYRF"]\n{text}')
    for name in ("APP-0001-a.md", "PYRF-0001-b.md"):
        write_doc(root, f"architecture/decisions/{name}", decision="accepted", date="2026-11-18")
    make_commit(root, "add external ADR", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    llms = _read(site_dir, "llms.txt")
    assert llms.index("PYRF-0001-b") < llms.index("APP-0001-a")


def test_build_from_ref_finds_code_in_the_repo_root(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    move_sample_package_to_root(root)
    sha = make_commit(root, "move code to the root", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    page = _read(site_dir, "reference/code/sample.mod.html")
    assert f'href="https://github.com/o/r/blob/{sha}/sample/mod.py#L' in page


def test_build_default_parts(repo: HistoryRepo) -> None:
    root, _ = repo
    assert SiteBuilder(root, "main", include_worktree=False, vendor_dir=None, strict=False, parts=None).parts == {
        Part.DOCS,
        Part.CODE,
    }
    (root / ProjectConfig.CONFIG_FILE).write_text("", encoding="utf-8")
    make_commit(root, "drop code-dirs", "2026-11-07T12:00:00+00:00")
    assert SiteBuilder(root, "main", include_worktree=False, vendor_dir=None, strict=False, parts=None).parts == {
        Part.DOCS
    }


def test_build_code_part_needs_code_dirs(history_repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = history_repo
    with pytest.raises(BuildError, match="code-dirs"):
        run_build(root, "main", tmp_path / "site", parts=frozenset({Part.CODE}))


def test_build_parts_label(repo: HistoryRepo) -> None:
    root, _ = repo
    builder = SiteBuilder(root, "main", include_worktree=False, vendor_dir=None, strict=False, parts=None)
    assert builder.parts_label == "code+docs"


def test_build_docs_only(repo: HistoryRepo, tmp_path: Path) -> None:
    root, shas = repo
    write_doc(
        root, "meta/x.md", "[x](code:sample.mod.Thing)\n", title="X doc", code=["sample.mod"], components=["core"]
    )
    make_commit(root, "spec: add x", "2026-11-07T12:00:00+00:00")
    write_doc(root, "meta/x.md", "[x](code:sample.mod.Thing) again\n", title="X doc", code=["sample.mod"])
    old_sha = make_commit(root, "spec: edit x", "2026-11-08T12:00:00+00:00")
    write_doc(
        root,
        "meta/x.md",
        "[x](code:sample.mod.Thing) latest\n",
        title="X doc",
        code=["sample.mod"],
        components=["core"],
    )
    write_doc(root, "reference/index.md", "# Reference\n\n## Children\n\n- [code/index.md](code/index.md) — Code.\n")
    write_doc(
        root,
        "reference/code/index.md",
        "See [X](../../meta/x.md).\n",
        title="Code reference",
        tags=["x"],
        components=["core"],
    )
    write_doc(
        root,
        "meta/y.md",
        "See [the code](../reference/code/index.md).\n",
        related=["reference/code/index.md"],
    )
    make_commit(root, "spec: edit x again", "2026-11-09T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir, parts=frozenset({Part.DOCS}))
    assert not (site_dir / "reference/code").exists()
    assert "<code>x</code> latest" in _read(site_dir, "meta/x.html")
    assert "<code>x</code> again" in _read(site_dir, f"meta/x/v/{_shorten_sha(old_sha)}.html")
    assert "sample." not in _read(site_dir, "components/core.html")
    assert "reference/code/" not in _read(site_dir, "llms.txt")
    pages = list(site_dir.rglob("*.html"))
    y_page = _read(site_dir, "meta/y.html")
    assert "the code" in y_page
    assert "Code reference" not in y_page  # neither the related list nor a link names the entry page
    assert "Code reference" not in _read(site_dir, "meta/x.html")  # no backlink from the entry page
    for page in pages:
        for url in _LINK.findall(page.read_text(encoding="utf-8")):
            assert "reference/code/" not in url, (page, url)


def test_build_alternating_parts_reuses_cache(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    write_doc(root, "meta/x.md", "[t](code:sample.mod.Thing)\n", title="X doc", code=["sample.mod"])
    make_commit(root, "spec: add x", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    run_build(root, "main", site_dir, parts=frozenset({Part.DOCS}))
    assert not [path for path in (site_dir / "reference/code").rglob("*") if path.is_file()]
    third_build = run_build(root, "main", site_dir)
    assert third_build.rendered_count == 0


def test_build_docs_only_ignores_broken_code(
    repo: HistoryRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = repo

    def raise_in_load(root: object, config: object) -> None:
        raise CodeError("cannot locate Docs: lines of %s", "sample.mod")

    monkeypatch.setattr(Codebase, "load", raise_in_load)
    result = run_build(root, "main", tmp_path / "site", strict=True, parts=frozenset({Part.DOCS}))
    assert not result.errors


def test_build_docs_only_no_source_url_start_warning(git_repo: Path, tmp_path: Path) -> None:
    (git_repo / ProjectConfig.CONFIG_FILE).write_text('code-dirs = ["src"]\n', encoding="utf-8")
    (git_repo / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    write_doc(git_repo, "a.md", "See [compose](../compose.yaml).\n")
    make_commit(git_repo, "set the config")
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        run_build(git_repo, "main", tmp_path / "site", parts=frozenset({Part.DOCS}))
    messages = [m.rpartition("source-url: ")[2] for m in _get_messages(recorded) if "source-url" in m]
    assert messages == ["links to repository files, such as ../compose.yaml, are plain text"]


def _add_code_only_docs(root: Path) -> str:
    """Commit the code reference entry page and a doc describing ``sample.mod``; return the commit's SHA hash."""
    write_doc(root, "reference/index.md", "Reference.\n", title="Reference")
    write_doc(
        root,
        "reference/code/index.md",
        "See [the module](code:sample.mod) and [X](../../meta/x.md#s).\n\n![Diagram](diagram.png)\n",
        title="Code reference",
        related=["meta/x.md"],
    )
    (root / "docs/reference/code/diagram.png").write_bytes(b"\x89PNG")
    write_doc(root, "meta/x.md", "X.\n", title="X doc", code=["sample.mod"])
    return make_commit(root, "spec: add the code reference", "2026-11-07T12:00:00+00:00")


def _extract_docs_links(html: str) -> str:
    return html.split('<div class="docs-links">', 1)[1].split("</div>", 1)[0]


def test_build_code_only(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    head = _add_code_only_docs(root)
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir, parts=frozenset({Part.CODE}))
    files = {p.relative_to(site_dir).as_posix() for p in site_dir.rglob("*") if p.is_file()}
    written_files = {f for f in files if not f.startswith("assets/") and f != SiteBuilder.MANIFEST}
    assert written_files == {
        "reference/code/diagram.png",
        "index.html",
        "reference/code/index.html",
        "reference/code/sample.html",
        "reference/code/sample.base.html",
        "reference/code/sample.mod.html",
    }
    root_page = _read(site_dir, "index.html")
    assert "<h1>Code reference</h1>" in root_page
    assert 'href="reference/code/sample.html"' in root_page
    assert 'href="reference/code/sample.mod.html"' in root_page
    assert 'href="reference/index.html"' not in root_page
    blob = f"https://github.com/o/r/blob/{head}/docs"
    assert f'href="{blob}/meta/x.md#s"' in root_page
    assert 'src="reference/code/diagram.png"' in root_page
    entry = _read(site_dir, "reference/code/index.html")
    assert 'src="diagram.png"' in entry
    related = extract_aside(entry, "related")
    assert f'<a href="{blob}/meta/x.md">X doc</a>' in related
    mod = _read(site_dir, "reference/code/sample.mod.html")
    breadcrumb = mod.split('<nav class="breadcrumb">', 1)[1].split("</nav>", 1)[0]
    assert '\nindex<span class="sep">' in breadcrumb  # the home doc, titled by its file name
    assert '\nReference<span class="sep">' in breadcrumb
    assert 'href="index.html">Code reference</a>' in breadcrumb
    assert '<span class="component">core</span>' in mod
    assert '<span class="status status-implemented">implemented</span>' in mod
    for page in ("index.html", "reference/code/index.html", "reference/code/sample.mod.html"):
        hrefs = _LINK.findall(_read(site_dir, page))
        assert not [h for h in hrefs if "components/" in h or h.endswith("status.html")], page
    assert f'href="{blob}/meta/vocabulary.md"' in _extract_docs_links(mod)
    assert f'<a href="{blob}/meta/x.md">X doc</a>' in extract_aside(mod, "described-in")


def test_build_code_only_without_entry_page(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    site_dir = tmp_path / "site"
    with pytest.warns(DocspecsiteWarning, match="no code reference entry page docs/reference/code/index.md"):
        run_build(root, "main", site_dir, parts=frozenset({Part.CODE}))
    assert (site_dir / "reference/code/sample.mod.html").is_file()
    assert not (site_dir / "index.html").exists()


def test_build_code_only_without_source_url(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    edit_text(
        root / ProjectConfig.CONFIG_FILE, lambda text: text.replace('source-url = "https://github.com/o/r"\n', "")
    )
    _add_code_only_docs(root)
    site_dir = tmp_path / "site"
    with pytest.warns(DocspecsiteWarning, match="no source-url"):
        run_build(root, "main", site_dir, parts=frozenset({Part.CODE}))
    mod = _read(site_dir, "reference/code/sample.mod.html")
    docs_links = _extract_docs_links(mod)
    assert "meta/vocabulary.md" in docs_links
    assert "<a" not in docs_links
    described = extract_aside(mod, "described-in")
    assert "meta/x.md" in described
    assert "<a" not in described
    entry = _read(site_dir, "reference/code/index.html")
    assert "and X.</p>" in entry
    assert "meta/x.md" not in entry


def test_build_code_only_worktree_new_doc(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    head = _add_code_only_docs(root)
    write_doc(root, "meta/new.md", "New.\n", title="New doc")
    edit_text(
        root / "tools/sample/src/sample/mod.py",
        lambda text: text.replace("Docs: meta/vocabulary.md\n", "Docs: meta/vocabulary.md\nDocs: meta/new.md\n", 1),
    )
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir, include_worktree=True, parts=frozenset({Part.CODE}))
    docs_links = _extract_docs_links(_read(site_dir, "reference/code/sample.mod.html"))
    assert f'href="https://github.com/o/r/blob/{head}/docs/meta/vocabulary.md"' in docs_links
    new_item = docs_links.split("meta/new.md", 1)[0].rsplit("<li>", 1)[1]
    assert "<a" not in new_item


def test_build_docs_line_to_missing_doc_is_text(repo: HistoryRepo, tmp_path: Path) -> None:
    root, _ = repo
    edit_text(
        root / "tools/sample/src/sample/mod.py",
        lambda text: text.replace("Docs: meta/vocabulary.md\n", "Docs: meta/vocabulary.md\nDocs: meta/missing.md\n", 1),
    )
    make_commit(root, "name a missing doc", "2026-11-07T12:00:00+00:00")
    site_dir = tmp_path / "site"
    run_build(root, "main", site_dir)
    docs_links = _extract_docs_links(_read(site_dir, "reference/code/sample.mod.html"))
    missing_item = docs_links.split("meta/missing.md", 1)[0].rsplit("<li>", 1)[1]
    assert "<a" not in missing_item
