from collections.abc import Callable, Mapping
from pathlib import Path

import pytest
from conftest import add_files, init_git_repo, make_commit

from docspecsite.git import Git
from docspecsite.symlinks import (
    DiskFiles,
    GitSeenFiles,
    RepoFiles,
    SymlinkFollower,
    SymlinkKind,
    SymlinkTarget,
    TreeFiles,
)

type LoadFiles = Callable[[Mapping[str, str], Mapping[str, str]], SymlinkFollower]
"""Make a repo from files (path to text) and symlinks (path to link text); return a follower over it."""


def _load_git_seen_files(root: Path) -> GitSeenFiles:
    return GitSeenFiles(root, frozenset(file.path for file in Git(root).list_worktree_files(".")))


@pytest.fixture(params=["disk", "tree", "git-seen"])
def load_files(request: pytest.FixtureRequest, tmp_path: Path) -> LoadFiles:
    root = tmp_path / "repo"
    root.mkdir()
    # Files outside the repo exist, so a follower that looked there would find them.
    (tmp_path / "srv").mkdir()
    (tmp_path / "srv/setup.md").write_text("outside", encoding="utf-8")

    def load(files: Mapping[str, str], links: Mapping[str, str]) -> SymlinkFollower:
        file_contents = {path: text.encode() for path, text in {"README.md": "root", **files}.items()}
        add_files(root, {**file_contents, **links})
        repo_files: RepoFiles
        if request.param == "disk":
            repo_files = DiskFiles(root)
        elif request.param == "git-seen":
            init_git_repo(root)
            repo_files = _load_git_seen_files(root)
        else:
            init_git_repo(root)
            git = Git(root)
            repo_files = TreeFiles(git.read_tree(make_commit(root, "init")), git.read_blobs)
        return SymlinkFollower(repo_files)

    return load


# One test per row of the kinds table in behavior/doc-symlinks.md.


def test_out_of_repo(load_files: LoadFiles) -> None:
    follower = load_files({}, {"docs/guides/notes.md": "/srv/notes/setup.md", "docs/up.md": "../../srv/setup.md"})
    assert follower.follow("docs/guides/notes.md") == SymlinkTarget(SymlinkKind.OUT_OF_REPO, None)
    assert follower.follow("docs/up.md") == SymlinkTarget(SymlinkKind.OUT_OF_REPO, None)
    assert follower.make_hint("docs/guides/notes.md") is None


def test_nothing(load_files: LoadFiles) -> None:
    follower = load_files({"docs/guides/setup.md": ""}, {"docs/guides/old.md": "gone.md", "docs/deep": "setup.md/x"})
    assert follower.follow("docs/guides/old.md") == SymlinkTarget(SymlinkKind.NOTHING, None)
    assert follower.follow("docs/deep") == SymlinkTarget(SymlinkKind.NOTHING, None)
    assert follower.make_hint("docs/guides/old.md") == "remove the symlink; its target does not exist"


def test_doc_inside_docs(load_files: LoadFiles) -> None:
    follower = load_files({"docs/guides/setup.md": ""}, {"docs/guides/alias.md": "setup.md"})
    assert follower.follow("docs/guides/alias.md") == SymlinkTarget(SymlinkKind.DOC, "docs/guides/setup.md")
    assert follower.make_hint("docs/guides/alias.md") == (
        'link to "docs/guides/setup.md" in the text instead, and remove the symlink'
    )


def test_doc_outside_docs_adds_md_to_the_new_place(load_files: LoadFiles) -> None:
    follower = load_files(
        {"vendor/shared.md": ""},
        {"docs/reference/shared.md": "../../vendor/shared.md", "docs/guides/setup-copy": "../../vendor/shared.md"},
    )
    assert follower.follow("docs/reference/shared.md") == SymlinkTarget(SymlinkKind.DOC, "vendor/shared.md")
    assert follower.make_hint("docs/reference/shared.md") == (
        'move "vendor/shared.md" to "docs/reference/shared.md", and put the symlink at "vendor/shared.md" instead'
    )
    assert follower.make_hint("docs/guides/setup-copy") == (
        'move "vendor/shared.md" to "docs/guides/setup-copy.md", and put the symlink at "vendor/shared.md" instead'
    )


def test_directory_with_a_doc_inside(load_files: LoadFiles) -> None:
    follower = load_files(
        {"vendor/shared/a/page.md": "", "docs/parts/b/page.md": ""},
        {"docs/shared": "../vendor/shared", "docs/guides/parts": "../parts"},
    )
    assert follower.follow("docs/shared") == SymlinkTarget(SymlinkKind.DIRECTORY, "vendor/shared")
    assert follower.has_doc_inside("docs/shared")
    assert follower.make_hint("docs/shared") == (
        'move "vendor/shared" to "docs/shared", and put the symlink at "vendor/shared" instead'
    )
    assert follower.make_hint("docs/guides/parts") == (
        'link to "docs/parts" in the text instead, and remove the symlink'
    )


def test_directory_with_no_doc_inside(load_files: LoadFiles) -> None:
    follower = load_files({"assets/img/logo.png": "png"}, {"docs/img": "../assets/img"})
    assert follower.follow("docs/img") == SymlinkTarget(SymlinkKind.DIRECTORY, "assets/img")
    assert not follower.has_doc_inside("docs/img")
    assert follower.make_hint("docs/img") is None


def test_other_file(load_files: LoadFiles) -> None:
    follower = load_files({"assets/logo.png": "png"}, {"docs/logo.png": "../assets/logo.png"})
    assert follower.follow("docs/logo.png") == SymlinkTarget(SymlinkKind.OTHER_FILE, "assets/logo.png")
    assert follower.make_hint("docs/logo.png") is None


def test_kind_comes_from_the_target_not_the_name(load_files: LoadFiles) -> None:
    follower = load_files(
        {"assets/notes.txt": "", "vendor/notes.md": ""},
        {"docs/a.md": "../assets/notes.txt", "docs/b.txt": "../vendor/notes.md"},
    )
    assert follower.follow("docs/a.md").kind is SymlinkKind.OTHER_FILE
    assert follower.follow("docs/b.txt").kind is SymlinkKind.DOC


def test_chain_inside_the_repo(load_files: LoadFiles) -> None:
    follower = load_files(
        {"vendor/real/shared.md": ""},
        {"docs/alias.md": "../vendor/link.md", "vendor/link.md": "dir/shared.md", "vendor/dir": "real"},
    )
    assert follower.follow("docs/alias.md") == SymlinkTarget(SymlinkKind.DOC, "vendor/real/shared.md")


def test_chain_that_leaves_the_repo(load_files: LoadFiles) -> None:
    follower = load_files({}, {"docs/alias.md": "../vendor/link.md", "vendor/link.md": "../../srv/setup.md"})
    assert follower.follow("docs/alias.md") == SymlinkTarget(SymlinkKind.OUT_OF_REPO, None)


def test_chain_to_an_absolute_target(load_files: LoadFiles) -> None:
    follower = load_files({}, {"docs/alias.md": "../vendor/link.md", "vendor/link.md": "/srv/setup.md"})
    assert follower.follow("docs/alias.md") == SymlinkTarget(SymlinkKind.OUT_OF_REPO, None)


@pytest.mark.parametrize(
    ("links", "path"),
    [
        ({"docs/self.md": "self.md"}, "docs/self.md"),
        ({"docs/a.md": "b.md", "docs/b.md": "a.md"}, "docs/a.md"),
        ({"docs/here": "."}, "docs/here"),
        ({"docs/guides/up": ".."}, "docs/guides/up"),
        ({"docs/root": ".."}, "docs/root"),
    ],
    ids=["one symlink", "two symlinks", "directory it lies in", "parent directory", "repo root"],
)
def test_loop_leads_to_nothing(load_files: LoadFiles, links: Mapping[str, str], path: str) -> None:
    follower = load_files({"docs/guides/setup.md": ""}, links)
    assert follower.follow(path) == SymlinkTarget(SymlinkKind.NOTHING, None)


def test_has_doc_inside_through_a_nested_symlink(load_files: LoadFiles) -> None:
    follower = load_files(
        {"vendor/shared/img/logo.png": "", "vendor/notes/setup.md": "", "vendor/pics/a.png": ""},
        {
            "docs/shared": "../vendor/shared",
            "vendor/shared/img/notes": "../../notes",
            "docs/pics": "../vendor/pics",
            "vendor/pics/more": "../shared/img/logo.png",
        },
    )
    assert follower.has_doc_inside("docs/shared")
    assert not follower.has_doc_inside("docs/pics")


def test_has_doc_inside_skips_loops(load_files: LoadFiles) -> None:
    follower = load_files(
        {"vendor/shared/a/logo.png": ""},
        {
            "docs/shared": "../vendor/shared",
            "vendor/shared/back": "../../docs",
            "vendor/shared/a/up": "..",
            "vendor/shared/a/top": "../../../vendor",
        },
    )
    assert follower.follow("docs/shared").kind is SymlinkKind.DIRECTORY
    assert not follower.has_doc_inside("docs/shared")


def test_follow_reads_below_a_symlinked_directory(load_files: LoadFiles) -> None:
    follower = load_files({"assets/img/logo.png": ""}, {"docs/img": "../assets/img", "assets/img/old.png": "gone.png"})
    assert follower.follow("docs/img/logo.png") == SymlinkTarget(SymlinkKind.OTHER_FILE, "assets/img/logo.png")
    assert follower.follow("docs/img/old.png") == SymlinkTarget(SymlinkKind.NOTHING, None)


def test_git_seen_files_count_an_ignored_target_as_missing(tmp_path: Path) -> None:
    add_files(
        tmp_path,
        {
            ".gitignore": b"build/\n",
            "build/flow.png": b"ignored",
            "static/flow.png": b"untracked",
            "docs/ignored.png": "../build/flow.png",
            "docs/seen.png": "../static/flow.png",
            "docs/build": "../build",
        },
    )
    init_git_repo(tmp_path)
    follower = SymlinkFollower(_load_git_seen_files(tmp_path))
    assert follower.follow("docs/ignored.png") == SymlinkTarget(SymlinkKind.NOTHING, None)
    assert follower.follow("docs/build") == SymlinkTarget(SymlinkKind.NOTHING, None)
    assert follower.follow("docs/seen.png") == SymlinkTarget(SymlinkKind.OTHER_FILE, "static/flow.png")
