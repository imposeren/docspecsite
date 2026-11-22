import codecs
from pathlib import Path

import pytest
from conftest import HistoryRepo, edit_text, make_commit, run_git, write_doc

from docspecsite.git import Git, GitError, UnknownRefError
from docspecsite.history import History, NotUtf8Error, Version


def test_versions_per_doc(history_repo: HistoryRepo) -> None:
    root, commits = history_repo
    history = History.load(Git(root), "main")
    a_versions = history.versions_by_path["meta/a.md"]
    assert [v.short_id for v in a_versions] == [commits["c5"][:12], commits["c3"][:12], commits["c1"][:12]]
    assert [v.date for v in a_versions] == ["2026-11-05", "2026-11-03", "2026-11-01"]
    assert [v.subject for v in a_versions] == ["change a again", "change a", "add a"]
    assert [v.subject for v in history.versions_by_path["meta/b.md"]] == ["fix: change b", "add b"]


def test_contemporary(history_repo: HistoryRepo) -> None:
    root, commits = history_repo
    history = History.load(Git(root), "main")
    a_versions_by_commit = {v.commit.sha: v for v in history.versions_by_path["meta/a.md"] if v.commit is not None}
    b_versions_by_commit = {v.commit.sha: v for v in history.versions_by_path["meta/b.md"] if v.commit is not None}
    assert (
        history.find_contemporary("meta/b.md", a_versions_by_commit[commits["c3"]])
        == b_versions_by_commit[commits["c2"]]
    )
    assert history.find_contemporary("meta/b.md", a_versions_by_commit[commits["c1"]]) is None
    assert (
        history.find_contemporary("meta/b.md", a_versions_by_commit[commits["c5"]])
        == b_versions_by_commit[commits["c4"]]
    )


def test_latest(history_repo: HistoryRepo) -> None:
    root, commits = history_repo
    history = History.load(Git(root), "main")
    newest, middle, oldest = history.versions_by_path["meta/a.md"]
    assert history.is_latest(newest)
    assert not history.is_latest(middle)
    assert history.find_latest("meta/a.md") == newest
    assert history.read_text(oldest) == run_git(root, "show", f"{commits['c1']}:docs/meta/a.md") + "\n"


def test_find_doc_path_prefers_directory_index() -> None:
    version = Version("meta/index.md", None, -1, "0" * 40)
    history = History("0" * 40, {"meta/index.md": (version,), "meta/a.md": (version,)}, {}, frozenset())
    assert history.find_doc_path("meta") == "meta/index.md"
    assert history.find_doc_path("meta/a.md") == "meta/a.md"
    assert history.find_doc_path("other") == "other"


def test_first_parent_merge(history_repo: HistoryRepo) -> None:
    root, commits = history_repo
    run_git(root, "checkout", "-q", "-b", "side")
    write_doc(root, "meta/b.md", "Side change.\n")
    side = make_commit(root, "side change", "2026-11-06T12:00:00+00:00")
    run_git(root, "checkout", "-q", "main")
    run_git(root, "merge", "--no-ff", "-q", "-m", "Merge side", "side")
    merge = run_git(root, "rev-parse", "HEAD")
    history = History.load(Git(root), "main")
    newest = history.versions_by_path["meta/b.md"][0]
    assert newest.commit is not None
    assert newest.commit.sha == merge
    assert newest.subject == "Merge side"
    assert side[:12] not in [v.short_id for v in history.versions_by_path["meta/b.md"]]
    assert [v.commit.sha for v in history.versions_by_path["meta/b.md"] if v.commit is not None] == [
        merge,
        commits["c4"],
        commits["c2"],
    ]


def test_quoted_path_and_unusual_subject(history_repo: HistoryRepo) -> None:
    root, _ = history_repo
    write_doc(root, 'meta/notes "draft".md', "Draft.\n")
    sha = make_commit(root, "add notes \x85 draft", "2026-11-06T12:00:00+00:00")
    history = History.load(Git(root), "main")
    versions = history.versions_by_path['meta/notes "draft".md']
    assert [(v.commit.sha, v.subject) for v in versions if v.commit is not None] == [(sha, "add notes \x85 draft")]
    assert history.read_text(versions[0]).endswith("Draft.\n")


def test_blobs_missing_is_git_error(history_repo: HistoryRepo) -> None:
    root, _ = history_repo
    with pytest.raises(GitError) as raised:
        Git(root).read_blobs(["1" * 40])
    assert raised.value.message == "cannot read blob: %s"
    assert str(raised.value) == f"cannot read blob: {'1' * 40} missing"


def test_git_error_names_command_and_keeps_stderr(tmp_path: Path) -> None:
    with pytest.raises(GitError) as raised:
        Git(tmp_path).resolve("main")
    assert raised.value.message == "git %s failed: %s"
    assert str(raised.value).startswith("git rev-parse failed: fatal: not a git repository")


def test_unknown_ref_message(history_repo: HistoryRepo) -> None:
    root, _ = history_repo
    with pytest.raises(UnknownRefError) as raised:
        Git(root).resolve("nope")
    assert raised.value.message == "unknown ref: %s"
    assert str(raised.value) == "unknown ref: nope"


@pytest.mark.parametrize(("prefix", "offset"), [(b"", 2), (codecs.BOM_UTF8, 5)], ids=["plain", "bom"])
def test_not_utf8_message(history_repo: HistoryRepo, prefix: bytes, offset: int) -> None:
    root, _ = history_repo
    (root / "docs/meta/bad.md").write_bytes(prefix + b"ok\xff")
    make_commit(root, "spec: add bad", "2026-11-06T12:00:00+00:00")
    history = History.load(Git(root), "main")
    [version] = history.versions_by_path["meta/bad.md"]
    assert not history.is_decodable(version)
    with pytest.raises(NotUtf8Error) as raised:
        history.read_text(version)
    assert raised.value.message == "docs/%s: not valid UTF-8 (%s at byte %d)"
    assert str(raised.value) == f"docs/meta/bad.md: not valid UTF-8 (invalid start byte at byte {offset})"


def test_templates_and_ref(history_repo: HistoryRepo) -> None:
    root, _ = history_repo
    write_doc(root, "meta/templates/x.md", "Template.\n")
    make_commit(root, "add template")
    git = Git(root)
    assert "meta/templates/x.md" not in History.load(git, "main").versions_by_path
    with pytest.raises(UnknownRefError):
        History.load(git, "nope")


def test_worktree_versions(history_repo: HistoryRepo) -> None:
    root, commits = history_repo
    write_doc(root, "meta/a.md", "Edited, not committed.\n")
    write_doc(root, "meta/new.md", "Brand new.\n")
    git = Git(root)
    history = History.load(git, "main", worktree_root=root)
    working_copy, newest_commit = history.versions_by_path["meta/a.md"][:2]
    assert (working_copy.short_id, working_copy.commit_index, working_copy.subject) == (
        Version.WORKTREE_SHORT_ID,
        -1,
        "working copy (uncommitted)",
    )
    assert newest_commit.commit is not None
    assert newest_commit.commit.sha == commits["c5"]
    assert history.read_text(working_copy) == (root / "docs/meta/a.md").read_text()
    assert [v.short_id for v in history.versions_by_path["meta/new.md"]] == [Version.WORKTREE_SHORT_ID]
    assert all(not v.is_worktree for v in history.versions_by_path["meta/b.md"])
    plain = History.load(git, "main")
    assert "meta/new.md" not in plain.versions_by_path
    assert all(not v.is_worktree for v in plain.versions_by_path["meta/a.md"])


def test_strip_subject() -> None:
    assert Version.strip_subject("spec: x") == "x"
    assert Version.strip_subject("docs:x") == "x"
    assert Version.strip_subject("Spec: x") == "Spec: x"
    assert Version.strip_subject("fix: spec: x") == "fix: spec: x"


def _commit_with_fake_signature(root: Path, message: str) -> str:
    """Commit the staged tree on top of ``main`` with a signature header git cannot verify."""
    run_git(root, "add", "-A")
    tree = run_git(root, "write-tree")
    parent = run_git(root, "rev-parse", "HEAD")
    commit_object = (
        f"tree {tree}\nparent {parent}\n"
        "author Test <test@example.invalid> 1793880000 +0000\n"
        "committer Test <test@example.invalid> 1793880000 +0000\n"
        "gpgsig -----BEGIN SSH SIGNATURE-----\n U1NIU0lH\n -----END SSH SIGNATURE-----\n\n"
        f"{message}\n"
    )
    sha = run_git(root, "hash-object", "-t", "commit", "-w", "--stdin", input=commit_object)
    run_git(root, "update-ref", "refs/heads/main", sha)
    return sha


def test_signed_commits_with_show_signature(history_repo: HistoryRepo) -> None:
    root, _ = history_repo
    write_doc(root, "meta/a.md", "Signed change.\n")
    signed_sha = _commit_with_fake_signature(root, "spec: signed change")
    run_git(root, "config", "log.showSignature", "true")
    history = History.load(Git(root), "main")
    newest = history.find_latest("meta/a.md")
    assert newest.commit is not None
    assert (newest.commit.sha, newest.subject) == (signed_sha, "signed change")


@pytest.mark.parametrize("conversion", ["autocrlf", "gitattributes"])
def test_worktree_versions_follow_line_ending_conversion(history_repo: HistoryRepo, conversion: str) -> None:
    root, _ = history_repo
    if conversion == "autocrlf":
        run_git(root, "config", "core.autocrlf", "true")
    else:
        (root / ".gitattributes").write_text("* text eol=crlf\n", encoding="utf-8")
    for doc in (root / "docs").rglob("*.md"):
        doc.write_bytes(doc.read_bytes().replace(b"\n", b"\r\n"))
    write_doc(root, "meta/b.md", "Edited, not committed.\n")
    history = History.load(Git(root), "main", worktree_root=root)
    assert all(not v.is_worktree for v in history.versions_by_path["meta/a.md"])
    working_copy = history.find_latest("meta/b.md")
    assert working_copy.is_worktree
    assert history.read_text(working_copy) == (root / "docs/meta/b.md").read_bytes().decode()


def test_byte_order_mark_is_dropped(history_repo: HistoryRepo) -> None:
    root, _ = history_repo
    edit_text(root / "docs/meta/a.md", lambda text: f"\ufeff{text}")
    make_commit(root, "spec: a with a BOM", "2026-11-06T12:00:00+00:00")
    edit_text(root / "docs/meta/b.md", lambda text: f"\ufeff{text}")
    history = History.load(Git(root), "main", worktree_root=root)
    for path in ("meta/a.md", "meta/b.md"):
        latest = history.find_latest(path)
        assert history.read_text(latest).startswith("---\n"), path
    assert history.find_latest("meta/b.md").is_worktree


def test_extract_leaves_out_unsafe_symlinks(git_repo: Path, tmp_path: Path) -> None:
    pkg = git_repo / "src/pkg"
    pkg.mkdir(parents=True)
    (pkg / "a.py").write_text("x = 1\n", encoding="utf-8")
    (pkg / "inner.py").symlink_to("a.py")
    (pkg / "absolute").symlink_to("/usr/share")
    (pkg / "docs").symlink_to("../../docs")
    (pkg / "outside").symlink_to("../../../elsewhere")
    sha = make_commit(git_repo, "add code")
    dest = tmp_path / "extracted"
    dest.mkdir()
    skipped = Git(git_repo).extract(sha, ["src"], dest)
    assert skipped == ["src/pkg/absolute", "src/pkg/docs", "src/pkg/outside"]
    assert sorted(p.name for p in (dest / "src/pkg").iterdir()) == ["a.py", "inner.py"]
    assert (dest / "src/pkg/inner.py").read_text(encoding="utf-8") == "x = 1\n"


def test_extract_with_the_repo_root_as_path_leaves_out_links_out_of_the_repo(git_repo: Path, tmp_path: Path) -> None:
    (git_repo / "inner").symlink_to("docs")
    (git_repo / "lnk").symlink_to("../outside")
    sha = make_commit(git_repo, "add links")
    dest = tmp_path / "extracted"
    dest.mkdir()
    skipped_link_paths = Git(git_repo).extract(sha, ["."], dest)
    assert skipped_link_paths == ["lnk"]
    assert (dest / "inner").is_symlink()


def test_worktree_version_of_a_name_with_a_newline(history_repo: HistoryRepo) -> None:
    root, _ = history_repo
    write_doc(root, "meta/a\nb.md", "Untracked.\n")
    history = History.load(Git(root), "main", worktree_root=root)
    working_copy = history.find_latest("meta/a\nb.md")
    assert working_copy.is_worktree
    assert history.read_text(working_copy) == (root / "docs/meta/a\nb.md").read_text(encoding="utf-8")


def test_worktree_copy_of_an_older_blob_keeps_the_committed_text(history_repo: HistoryRepo) -> None:
    root, _ = history_repo
    run_git(root, "config", "core.autocrlf", "true")
    git = Git(root)
    oldest = History.load(git, "main").versions_by_path["meta/a.md"][-1]
    oldest_bytes = git.read_blobs([oldest.blob_sha])[oldest.blob_sha]
    (root / "docs/meta/a.md").write_bytes(oldest_bytes.replace(b"\n", b"\r\n"))
    history = History.load(git, "main", worktree_root=root)
    working_copy = history.find_latest("meta/a.md")
    assert working_copy.is_worktree
    assert working_copy.blob_sha == oldest.blob_sha
    assert history.read_text(history.versions_by_path["meta/a.md"][-1]) == oldest_bytes.decode()
