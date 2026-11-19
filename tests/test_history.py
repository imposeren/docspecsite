from pathlib import Path

import pytest
from conftest import HistoryRepo, make_commit, run_git, write_doc

from docspecsite.git import Git, GitError, UnknownRefError
from docspecsite.history import WORKTREE, NotUtf8Error, load_history, strip_subject


def test_versions_per_doc(history_repo: HistoryRepo) -> None:
    root, commits = history_repo
    history = load_history(Git(root), "main")
    a_versions = history.docs["meta/a.md"]
    assert [v.short_id for v in a_versions] == [commits["c5"][:12], commits["c3"][:12], commits["c1"][:12]]
    assert [v.date for v in a_versions] == ["2026-11-05", "2026-11-03", "2026-11-01"]
    assert [v.subject for v in a_versions] == ["change a again", "change a", "add a"]
    assert [v.subject for v in history.docs["meta/b.md"]] == ["fix: change b", "add b"]


def test_contemporary(history_repo: HistoryRepo) -> None:
    root, commits = history_repo
    history = load_history(Git(root), "main")
    a_versions_by_commit = {v.commit: v for v in history.docs["meta/a.md"]}
    b_versions_by_commit = {v.commit: v for v in history.docs["meta/b.md"]}
    assert (
        history.find_contemporary("meta/b.md", a_versions_by_commit[commits["c3"]])
        == b_versions_by_commit[commits["c2"]]
    )
    assert history.find_contemporary("meta/b.md", a_versions_by_commit[commits["c1"]]) is None
    assert (
        history.find_contemporary("meta/b.md", a_versions_by_commit[commits["c5"]])
        == b_versions_by_commit[commits["c4"]]
    )


def test_previous_and_latest(history_repo: HistoryRepo) -> None:
    root, commits = history_repo
    history = load_history(Git(root), "main")
    newest, middle, oldest = history.docs["meta/a.md"]
    assert history.find_previous(oldest) is None
    assert history.find_previous(newest) == middle
    assert history.is_latest(newest)
    assert not history.is_latest(middle)
    assert history.find_latest("meta/a.md") == newest
    assert history.read_text(oldest) == run_git(root, "show", f"{commits['c1']}:docs/meta/a.md") + "\n"


def test_first_parent_merge(history_repo: HistoryRepo) -> None:
    root, commits = history_repo
    run_git(root, "checkout", "-q", "-b", "side")
    write_doc(root, "meta/b.md", "Side change.\n")
    side = make_commit(root, "side change", "2026-11-06T12:00:00+00:00")
    run_git(root, "checkout", "-q", "main")
    run_git(root, "merge", "--no-ff", "-q", "-m", "Merge side", "side")
    merge = run_git(root, "rev-parse", "HEAD")
    history = load_history(Git(root), "main")
    newest = history.docs["meta/b.md"][0]
    assert newest.commit == merge
    assert newest.subject == "Merge side"
    assert side[:12] not in [v.short_id for v in history.docs["meta/b.md"]]
    assert [v.commit for v in history.docs["meta/b.md"]] == [merge, commits["c4"], commits["c2"]]


def test_quoted_path_and_unusual_subject(history_repo: HistoryRepo) -> None:
    root, _ = history_repo
    write_doc(root, 'meta/notes "draft".md', "Draft.\n")
    sha = make_commit(root, "add notes \x85 draft", "2026-11-06T12:00:00+00:00")
    history = load_history(Git(root), "main")
    versions = history.docs['meta/notes "draft".md']
    assert [(v.commit, v.subject) for v in versions] == [(sha, "add notes \x85 draft")]
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


def test_not_utf8_message(history_repo: HistoryRepo) -> None:
    root, _ = history_repo
    (root / "docs/meta/bad.md").write_bytes(b"ok\xff")
    make_commit(root, "spec: add bad", "2026-11-06T12:00:00+00:00")
    history = load_history(Git(root), "main")
    [version] = history.docs["meta/bad.md"]
    assert not history.is_decodable(version)
    with pytest.raises(NotUtf8Error) as raised:
        history.read_text(version)
    assert raised.value.message == "docs/%s: not valid UTF-8 (%s at byte %d)"
    assert str(raised.value) == "docs/meta/bad.md: not valid UTF-8 (invalid start byte at byte 2)"


def test_templates_and_ref(history_repo: HistoryRepo) -> None:
    root, _ = history_repo
    write_doc(root, "meta/templates/x.md", "Template.\n")
    make_commit(root, "add template")
    git = Git(root)
    assert "meta/templates/x.md" not in load_history(git, "main").docs
    with pytest.raises(UnknownRefError):
        load_history(git, "nope")


def test_worktree_versions(history_repo: HistoryRepo) -> None:
    root, commits = history_repo
    write_doc(root, "meta/a.md", "Edited, not committed.\n")
    write_doc(root, "meta/new.md", "Brand new.\n")
    git = Git(root)
    history = load_history(git, "main", worktree=root)
    working_copy, newest_commit = history.docs["meta/a.md"][:2]
    assert (working_copy.short_id, working_copy.commit_index, working_copy.subject) == (
        WORKTREE,
        -1,
        "working copy (uncommitted)",
    )
    assert newest_commit.commit == commits["c5"]
    assert history.read_text(working_copy) == (root / "docs/meta/a.md").read_text()
    assert [v.short_id for v in history.docs["meta/new.md"]] == [WORKTREE]
    assert all(v.short_id != WORKTREE for v in history.docs["meta/b.md"])
    plain = load_history(git, "main")
    assert "meta/new.md" not in plain.docs
    assert all(v.short_id != WORKTREE for v in plain.docs["meta/a.md"])


def test_strip_subject() -> None:
    assert strip_subject("spec: x") == "x"
    assert strip_subject("docs:x") == "x"
    assert strip_subject("Spec: x") == "Spec: x"
    assert strip_subject("fix: spec: x") == "fix: spec: x"
