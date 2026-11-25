"""Shared fixtures: throwaway docs trees and git repositories."""

import os
import re
import subprocess
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import NamedTuple

import pytest
import yaml

from docspecsite.coderef import Codebase
from docspecsite.config import ProjectConfig
from docspecsite.docs import Doc

type WriteDoc = Callable[..., Path]


@pytest.fixture(autouse=True, scope="session")
def isolated_git_config(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Run every git command of the tests without the host's git config, such as commit signing or hooks."""
    config = tmp_path_factory.mktemp("git-config") / "gitconfig"
    config.touch()
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("GIT_CONFIG_GLOBAL", str(config))
        patch.setenv("GIT_CONFIG_NOSYSTEM", "1")
        yield


_VOCABULARY = """# Vocabulary

## Components

| Component | Meaning |
|---|---|
| `docs-system` | The documentation system. |
| `agents` | Agent guidance. |

## Tags

| Tag | Use for |
|---|---|
| `overview` | Overviews. |
"""
_COMPONENTS = """# Components

| Component | Meaning |
|---|---|
| `core` | The core. |
| `storage/files` | File storage. |
"""
_ROADMAP = """# Roadmap

| Id | Goal |
|---|---|
| `foundation` | Machinery works. |
| `first-release` | First release. |
"""
_SAMPLE_MOD = '''"""Sample module.

Docs: meta/vocabulary.md
"""

from sample.base import Base

type Alias = list[int]

LIMIT: int = 3
"""The limit."""


class Thing(Base):
    """A thing."""

    size: int
    """How big."""

    @property
    def name(self) -> str:
        """The name."""
        return "x"

    @classmethod
    def make(cls, n: int = 3) -> "Thing":
        """Make one."""
        return cls()

    def run(self, n: int, *, fast: bool = False) -> str:
        """Run it.

        Args:
            n: How many.
            fast: Skip checks.

        Returns:
            The result.

        Raises:
            ValueError: When n is negative.
        """
        return ""


def _helper() -> None:
    """Private."""
'''

GUIDES_INDEX = "# Guides\n\n## Setup\n\n## Children\n\n- [setup.md](setup.md) — Setup.\n"
ROOT_INDEX_WITH_GUIDES = (
    "## Children\n\n- [roadmap.md](roadmap.md) — M.\n- [meta/index.md](meta/index.md) — R.\n"
    "- [architecture/index.md](architecture/index.md) — A.\n- [guides/](guides/index.md) — G.\n"
)
SCENARIO_IMPLEMENTED_WARNING = (
    'warning: docs/scenarios/import.md:1: "implemented" in "status" is ignored: the "scenarios" layer has no build '
    "status, and the value can mislead a reader once the doc that owns the rules changes and nobody updates it"
)


class HistoryRepo(NamedTuple):
    """A test repository whose commits are known by name."""

    root: Path
    """Repository root; the docs tree is its ``docs/``."""
    commits: dict[str, str]
    """Full SHA hash of each named commit, by name: ``c1``..``c5``, plus ``code`` in the build tests."""


def _with_overrides(defaults: dict[str, object], overrides: dict[str, object]) -> dict[str, object]:
    """Return front-matter fields with some of them replaced, added or removed.

    Args:
        defaults: Front-matter fields to start from; left unchanged.
        overrides: Fields replacing or adding to them; a value of None removes the field.
    """
    merged = dict(defaults)
    for key, value in overrides.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def write_doc(root: Path, path: str, body: str = "", **front_matter: object) -> Path:
    """Write ``docs/<path>`` with valid default front matter and return the file.

    Args:
        root: Repo root holding the ``docs`` directory.
        path: Doc path relative to ``docs``.
        body: Markdown text after the front matter.
        **front_matter: Fields overriding the defaults; ``None`` removes that field.
    """
    parts = path.split("/")
    defaults: dict[str, object] = {
        "title": parts[-1].removesuffix(".md"),
        "summary": f"Test doc {path}.",
        "layer": parts[0] if len(parts) > 1 else "root",
        "status": "specified",
        "components": [],
        "tags": [],
        "related": [],
    }
    merged = _with_overrides(defaults, front_matter)
    text = "---\n" + yaml.safe_dump(merged, sort_keys=False) + "---\n\n" + body
    file = root / "docs" / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")
    return file


def make_doc(path: str = "meta/x.md", body: str = "", body_line: int = 1, /, **front_matter: object) -> Doc:
    """Build an in-memory ``Doc`` object with valid default front matter.

    All named parameters are positional-only so a front matter key such as ``path`` cannot bind to them.

    Args:
        path: Doc path relative to ``docs``; the title, summary and layer defaults derive from it.
        body: Markdown text of the doc body.
        body_line: Line number at which the body starts in the file.
        **front_matter: Fields overriding the defaults; ``None`` removes that field.
    """
    defaults: dict[str, object] = {
        "title": path,
        "summary": f"About {path}.",
        "layer": path.split("/")[0] if "/" in path else "root",
        "status": "specified",
        "components": [],
        "tags": [],
        "related": [],
    }
    return Doc(path, _with_overrides(defaults, front_matter), body, body_line, None)


@pytest.fixture
def docs_tree(tmp_path: Path) -> Path:
    """A repo root with a minimal docs tree on which ``docspecsite check`` is clean.

    Args:
        tmp_path: Fresh directory that becomes the repo root.
    """
    write_doc(
        tmp_path,
        "index.md",
        "# Docs\n\n## Children\n\n"
        "- [roadmap.md](roadmap.md) — Milestones.\n"
        "- [meta/index.md](meta/index.md) — Rules.\n"
        "- [architecture/index.md](architecture/index.md) — How it is built.\n",
    )
    write_doc(tmp_path, "roadmap.md", _ROADMAP)
    write_doc(
        tmp_path,
        "meta/index.md",
        "# Meta\n\n## Children\n\n- [vocabulary.md](vocabulary.md) — Components and tags.\n",
    )
    write_doc(tmp_path, "meta/vocabulary.md", _VOCABULARY)
    write_doc(
        tmp_path,
        "architecture/index.md",
        "# Architecture\n\n## Children\n\n- [components.md](components.md) — The components.\n",
    )
    write_doc(tmp_path, "architecture/components.md", _COMPONENTS)
    return tmp_path


def write_scenario_docs(root: Path, **front_matter: object) -> None:
    """Add a behavior doc and a scenario doc that gives cases for it to a ``docs_tree``, keeping its check clean.

    The scenario doc ``scenarios/import.md`` has no ``status`` and names ``behavior/import.md`` in ``related``.

    Args:
        root: Repo root of a ``docs_tree``.
        **front_matter: Fields of the scenario doc overriding these; ``None`` removes that field.
    """
    write_doc(
        root,
        "index.md",
        "# Docs\n\n## Children\n\n"
        "- [roadmap.md](roadmap.md) — Milestones.\n"
        "- [meta/index.md](meta/index.md) — Rules.\n"
        "- [architecture/index.md](architecture/index.md) — How it is built.\n"
        "- [behavior/](behavior/index.md) — What it does.\n"
        "- [scenarios/](scenarios/index.md) — Exact cases.\n",
    )
    write_doc(root, "behavior/index.md", "# Behavior\n\n## Children\n\n- [import.md](import.md) — Import.\n")
    write_doc(root, "behavior/import.md", "# Import\n")
    write_doc(root, "scenarios/index.md", "# Scenarios\n\n## Children\n\n- [import.md](import.md) — Import.\n")
    write_doc(
        root, "scenarios/import.md", "# Import\n", **{"status": None, "related": ["behavior/import.md"], **front_matter}
    )


def run_git(root: Path, *args: str, env: Mapping[str, str] | None = None, input: str | None = None) -> str:
    """Run ``git -C <root> <args>``, raise if it fails, and return its output without surrounding whitespace.

    Args:
        root: Repository the command runs in (``-C``).
        *args: Git subcommand and its arguments.
        env: Environment of the command, such as commit dates; None inherits the test process's environment.
        input: Text fed to the command's stdin, such as an object for ``hash-object --stdin``; None feeds none.
    """
    completed = subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True, env=env, input=input
    )
    return completed.stdout.strip()


def make_commit(root: Path, message: str, date: str = "2026-11-01T12:00:00+00:00") -> str:
    """Stage everything and commit it; return the full SHA hash of the commit.

    Args:
        root: Repository to commit in.
        message: Commit message.
        date: Author and committer date (ISO 8601) of the commit, so that histories are deterministic.
    """
    run_git(root, "add", "-A")
    run_git(
        root, "commit", "-q", "-m", message, env={**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    )
    return run_git(root, "rev-parse", "HEAD")


def init_git_repo(root: Path) -> None:
    """Make a directory a git repository on branch ``main``, with a committer identity and no commits.

    Args:
        root: Existing directory to make a repository.
    """
    run_git(root, "init", "-q", "-b", "main")
    run_git(root, "config", "user.name", "Test")
    run_git(root, "config", "user.email", "test@example.invalid")


def add_files(root: Path, files: Mapping[str, bytes | str]) -> None:
    """Write files and symlinks at repo paths, with the directories they lie in.

    Args:
        root: Repository root.
        files: Contents of each file by repo path; a str is a symlink's target instead.
    """
    for path, content in files.items():
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            file.symlink_to(content)
        else:
            file.write_bytes(content)


def write_guides(root: Path) -> None:
    """Write ``docs/guides/`` with its index and ``setup.md``, listed in a root index with its title heading.

    Args:
        root: Tree holding ``docs/``.
    """
    write_doc(root, "index.md", f"# Docs\n\n{ROOT_INDEX_WITH_GUIDES}")
    write_doc(root, "guides/index.md", GUIDES_INDEX)
    write_doc(root, "guides/setup.md", "# Setup\n")


def edit_text(file: Path, edit: Callable[[str], str]) -> None:
    """Replace the text of a UTF-8 file with what a function makes of it.

    Args:
        file: Existing file to rewrite.
        edit: Called with the current text; its result becomes the new text.
    """
    file.write_text(edit(file.read_text(encoding="utf-8")), encoding="utf-8")


def extract_aside(html: str, cls: str) -> str:
    """Return the inner HTML of the first ``<aside class="<cls>">`` in ``html``."""
    found = re.search(rf'<aside class="{cls}">(.*?)</aside>', html, re.DOTALL)
    assert found, cls
    return found.group(1)


def write_roles_module(root: Path, source: str) -> None:
    """Write ``source`` as the module ``sample.roles`` of the sample package under ``root``."""
    (root / "tools/sample/src/sample/roles.py").write_text(source, encoding="utf-8")


def load_sample_code(root: Path) -> Codebase:
    """Load the code of a tree from the code directories its ``docspecsite.toml`` names.

    Args:
        root: Tree holding the root ``docspecsite.toml`` and the code directories.
    """
    return Codebase.load(root, ProjectConfig.load(root))


@pytest.fixture
def git_repo(docs_tree: Path) -> Path:
    """``docs_tree`` as a git repository with everything in one commit.

    Args:
        docs_tree: Tree that is made a repository on branch ``main``.
    """
    init_git_repo(docs_tree)
    make_commit(docs_tree, "init")
    return docs_tree


def _write_meta_index(root: Path, children: list[str]) -> None:
    items = "".join(f"- [{name}]({name}) — Doc {name}.\n" for name in ["vocabulary.md", *children])
    write_doc(root, "meta/index.md", f"# Meta\n\n## Children\n\n{items}")


@pytest.fixture
def history_repo(git_repo: Path) -> HistoryRepo:
    """``git_repo`` plus five more commits ``c1``..``c5`` changing ``meta/a.md`` and ``meta/b.md``.

    Args:
        git_repo: Repository the commits are added to.
    """
    shas: dict[str, str] = {}
    _write_meta_index(git_repo, ["a.md", "c.md"])
    write_doc(git_repo, "meta/a.md", "See [b](b.md).\n")
    write_doc(git_repo, "meta/c.md", "Never changed.\n")
    shas["c1"] = make_commit(git_repo, "spec: add a", "2026-11-01T12:00:00+00:00")
    _write_meta_index(git_repo, ["a.md", "b.md", "c.md"])
    write_doc(git_repo, "meta/b.md", "No links.\n")
    shas["c2"] = make_commit(git_repo, "spec: add b", "2026-11-02T12:00:00+00:00")
    write_doc(git_repo, "meta/a.md", "See [b](b.md). Changed.\n")
    shas["c3"] = make_commit(git_repo, "docs: change a", "2026-11-03T12:00:00+00:00")
    write_doc(git_repo, "meta/b.md", "No links. Changed.\n")
    shas["c4"] = make_commit(git_repo, "fix: change b", "2026-11-04T12:00:00+00:00")
    write_doc(git_repo, "meta/a.md", "See [b](b.md). Changed again.\n")
    shas["c5"] = make_commit(git_repo, "change a again", "2026-11-05T12:00:00+00:00")
    return HistoryRepo(git_repo, shas)


@pytest.fixture
def code_tree(docs_tree: Path) -> Path:
    """``docs_tree`` plus a root ``docspecsite.toml`` and the package ``tools/sample/src/sample``.

    Args:
        docs_tree: Tree the project settings and the sample package are written into.
    """
    (docs_tree / ProjectConfig.CONFIG_FILE).write_text(
        'source-url = "https://github.com/o/r"\ncode-dirs = ["tools/*/src"]\n\n[code-components]\nsample = ["core"]\n',
        encoding="utf-8",
    )
    pkg = docs_tree / "tools/sample/src/sample"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text('"""Sample package."""\n', encoding="utf-8")
    (pkg / "base.py").write_text(
        'class Base:\n    """A base."""\n\n    def hello(self) -> str:\n'
        '        """Say hello."""\n        return "hi"\n',
        encoding="utf-8",
    )
    (pkg / "mod.py").write_text(_SAMPLE_MOD, encoding="utf-8")
    (pkg / "_private.py").write_text('"""Private module."""\n', encoding="utf-8")
    return docs_tree


def move_sample_package_to_root(root: Path) -> None:
    """Move ``code_tree``'s sample package to the repo root and name the root as the code directory.

    Args:
        root: Tree made by ``code_tree``; its ``docspecsite.toml`` is rewritten with ``code-dirs = ["."]``.
    """
    (root / "tools/sample/src/sample").rename(root / "sample")
    edit_text(
        root / ProjectConfig.CONFIG_FILE, lambda text: text.replace('code-dirs = ["tools/*/src"]', 'code-dirs = ["."]')
    )
