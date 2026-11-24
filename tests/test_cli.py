import json
import os
import re
import subprocess
import sys
import tomllib
import warnings
from pathlib import Path

import pytest
from conftest import make_commit, run_git, write_doc, write_guides, write_roles_module

from docspecsite.build import BuildResult
from docspecsite.cli import main
from docspecsite.config import ProjectConfig
from docspecsite.errors import DocspecsiteWarning, InternalErrorWarning
from docspecsite.git import Git, GitError

_SUBPROCESS_TIMEOUT_S = 60
_STRICT_UTF8_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8:strict"}
# The command prints docspecsite's warnings, which these tests check; as errors they would stop it before it prints.
_SHOW_DOCSPECSITE_WARNINGS = pytest.mark.filterwarnings("default::docspecsite.errors.DocspecsiteWarning")


def _extract_doc_output(out: str, path: str) -> str:
    """Return the problem lines of ``path`` in ``check`` output, each with the hint lines under it."""
    kept: list[str] = []
    is_doc_problem = False
    for line in out.splitlines(keepends=True):
        if not line.startswith("  hint: "):
            is_doc_problem = line.startswith(f"{path}:")
        if is_doc_problem:
            kept.append(line)
    return "".join(kept)


def test_version_prints_name_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert capsys.readouterr().out.strip() == f"docspecsite {project['version']}"


@pytest.mark.parametrize("command", ["check", "build"])
def test_help_shows_set_defaults_only(capsys: pytest.CaptureFixture[str], command: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main([command, "--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "(default: False)" in help_text
    assert "(default: None)" not in help_text
    assert "(default: frozenset())" not in help_text


def test_docs_tree_fixture_is_valid_layout(docs_tree: Path) -> None:
    docs = docs_tree / "docs"
    assert (docs / "roadmap.md").is_file()
    assert (docs / "meta" / "vocabulary.md").is_file()
    for directory in [docs, *(p for p in docs.rglob("*") if p.is_dir())]:
        assert (directory / "index.md").is_file(), directory


def test_cli_check_exit_codes(docs_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--repo", str(docs_tree), "check"]) == 0
    capsys.readouterr()
    write_doc(docs_tree, "meta/a.md", "# A\n\n[x](nope.md)\n")
    assert main(["--repo", str(docs_tree), "check"]) == 1
    captured = capsys.readouterr()
    assert captured.out.startswith("docs/meta/a.md:")
    assert "nope.md does not exist" in captured.out
    assert "problem" in captured.err


def test_cli_check_no_hints(docs_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_doc(docs_tree, "meta/a.md", "# A\n", status=["draft", "specified"])
    assert main(["--repo", str(docs_tree), "check"]) == 1
    assert '  hint: write "status: draft"' in capsys.readouterr().out
    file = write_doc(docs_tree, "import.md", "# Import\n\n## Import\n\n> **Not built yet.**\n", status="implemented")
    line = file.read_text(encoding="utf-8").splitlines().index("> **Not built yet.**") + 1
    assert main(["--repo", str(docs_tree), "check", "--no-hints"]) == 1
    out = capsys.readouterr().out
    assert "hint:" not in out
    assert _extract_doc_output(out, "docs/import.md") == (
        f'docs/import.md:{line}: status note "Not built yet." ("specified") '
        'in a doc with the single status "implemented"\n'
    )


def test_cli_check_prints_status_note_hints(docs_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    body = "# Import\n\n## Import\n\n> **Not built yet.**\n"
    file = write_doc(docs_tree, "import.md", body, status="implemented")
    line = file.read_text(encoding="utf-8").splitlines().index("> **Not built yet.**") + 1
    assert main(["--repo", str(docs_tree), "check"]) == 1
    assert _extract_doc_output(capsys.readouterr().out, "docs/import.md") == (
        f'docs/import.md:{line}: status note "Not built yet." ("specified") '
        'in a doc with the single status "implemented"\n'
        '  hint: add "specified" to "status" so it reads "status: [implemented, specified]", '
        'or remove the status note from the section "## Import"\n'
    )
    write_doc(docs_tree, "import.md", body, status=["implemented", "specified", "changed"])
    assert main(["--repo", str(docs_tree), "check"]) == 1
    assert _extract_doc_output(capsys.readouterr().out, "docs/import.md") == (
        'docs/import.md:1: "changed" is in "status", but no section has a "Changed, not built yet." status note\n'
        '  hint: add a "> **Changed, not built yet.**" status note to a section, '
        'or remove "changed" from "status" so it reads "status: [implemented, specified]"\n'
    )


def test_cli_check_staged_outside_git(
    docs_tree: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(docs_tree.parent))
    assert main(["--repo", str(docs_tree), "check", "--staged"]) == 1
    assert capsys.readouterr().err.startswith("docspecsite check --staged: git diff failed")


def test_cli_check_staged_prints_non_utf8_names_on_strict_stdout(git_repo: Path) -> None:
    for name in (b"\xff.md", b"r\xfe.md"):
        (git_repo / "docs" / os.fsdecode(name)).write_text("x\n")
    make_commit(git_repo, "add")
    run_git(git_repo, "rm", "-q", f"docs/{os.fsdecode(b'\xff.md')}")
    run_git(git_repo, "mv", f"docs/{os.fsdecode(b'r\xfe.md')}", f"docs/{os.fsdecode(b'n\xfd.md')}")
    completed = subprocess.run(
        [sys.executable, "-m", "docspecsite.cli", "--repo", str(git_repo), "check", "--staged"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8:strict"},
        check=False,
    )
    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert "docs/\\xff.md: deleted; " in completed.stdout
    assert "docs/r\\xfe.md: renamed to docs/n\\xfd.md; " in completed.stdout


def test_cli_list(docs_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_doc(docs_tree, "meta/a.md", status="implemented", tags=["x"])
    assert main(["--repo", str(docs_tree), "list", "--status", "implemented", "--format", "json"]) == 0
    [item] = json.loads(capsys.readouterr().out)
    assert item["path"] == "meta/a.md"
    assert item["tags"] == ["x"]


def test_cli_list_status_list(docs_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_doc(docs_tree, "meta/p.md", status=["implemented", "specified"])
    assert main(["--repo", str(docs_tree), "list", "--status", "specified", "--format", "json"]) == 0
    items = json.loads(capsys.readouterr().out)
    assert [i["status"] for i in items if i["path"] == "meta/p.md"] == [["implemented", "specified"]]


def test_cli_list_orders_adrs_by_configured_prefixes(docs_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (docs_tree / ProjectConfig.CONFIG_FILE).write_text('adr-prefix = "APP"\nexternal-adr-prefixes = ["PYRF"]\n')
    for name in ("APP-0001-a.md", "PYRF-0001-b.md"):
        write_doc(docs_tree, f"architecture/decisions/{name}", decision="accepted", date="2026-11-18")
    assert main(["--repo", str(docs_tree), "list", "--format", "json"]) == 0
    adr_paths = [item["path"] for item in json.loads(capsys.readouterr().out) if "/decisions/" in item["path"]]
    assert adr_paths[:2] == ["architecture/decisions/PYRF-0001-b.md", "architecture/decisions/APP-0001-a.md"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[code-components\n", "docspecsite list: docspecsite.toml: not valid TOML: "),
        ("source-url = 3\n", 'docspecsite list: docspecsite.toml: "source-url" must be a string\n'),
    ],
)
def test_cli_list_stops_on_invalid_config(
    docs_tree: Path, capsys: pytest.CaptureFixture[str], text: str, expected: str
) -> None:
    (docs_tree / ProjectConfig.CONFIG_FILE).write_text(text)
    assert main(["--repo", str(docs_tree), "list"]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith(expected)
    assert captured.out == ""


@_SHOW_DOCSPECSITE_WARNINGS
def test_cli_list_warns_about_unknown_settings(docs_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (docs_tree / ProjectConfig.CONFIG_FILE).write_text('adr_prefix = "APP"\nexternal-adr-prefixes = ["PYRF"]\n')
    for name in ("APP-0001-a.md", "PYRF-0001-b.md"):
        write_doc(docs_tree, f"architecture/decisions/{name}", decision="accepted", date="2026-11-18")
    assert main(["--repo", str(docs_tree), "list", "--format", "json"]) == 0
    captured = capsys.readouterr()
    assert captured.err == 'warning: docspecsite.toml: unknown setting "adr_prefix"\n'
    adr_paths = [item["path"] for item in json.loads(captured.out) if "/decisions/" in item["path"]]
    assert adr_paths[:2] == ["architecture/decisions/PYRF-0001-b.md", "architecture/decisions/APP-0001-a.md"]


def test_cli_list_accepts_a_byte_order_mark(docs_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (docs_tree / ProjectConfig.CONFIG_FILE).write_bytes(b'\xef\xbb\xbfexternal-adr-prefixes = ["PYRF"]\n')
    for name in ("APP-0001-a.md", "PYRF-0001-b.md"):
        write_doc(docs_tree, f"architecture/decisions/{name}", decision="accepted", date="2026-11-18")
    assert main(["--repo", str(docs_tree), "list", "--format", "json"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    adr_paths = [item["path"] for item in json.loads(captured.out) if "/decisions/" in item["path"]]
    assert adr_paths[:2] == ["architecture/decisions/PYRF-0001-b.md", "architecture/decisions/APP-0001-a.md"]


@pytest.mark.parametrize("command", [["list"], ["backlinks", "index.md"], ["backlinks", "nope.md"]])
def test_cli_list_and_backlinks_stop_on_undecodable_doc(
    docs_tree: Path, capsys: pytest.CaptureFixture[str], command: list[str]
) -> None:
    (docs_tree / "docs/meta/latin.md").write_bytes(b"---\ntitle: Caf\xe9\n---\n")
    assert main(["--repo", str(docs_tree), *command]) == 1
    captured = capsys.readouterr()
    assert captured.err == (
        f"docspecsite {command[0]}: docs/meta/latin.md: not valid UTF-8 (invalid continuation byte at byte 14)\n"
    )
    assert captured.out == ""


def test_cli_backlinks_unknown_path_exit_2(docs_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--repo", str(docs_tree), "backlinks", "nope.md"]) == 2
    assert "not a doc: nope.md" in capsys.readouterr().err


def test_backlinks_of_template_exits_2(docs_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_doc(docs_tree, "meta/templates/behavior-doc.md", "Template.\n")
    path = "docs/meta/templates/behavior-doc.md"
    assert main(["--repo", str(docs_tree), "backlinks", path]) == 2
    assert capsys.readouterr().err == f"not a doc: {path}\n"


def test_backlinks_of_symlink_exits_2(docs_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (docs_tree / "docs/alias.md").symlink_to("roadmap.md")
    (docs_tree / "docs/linked").symlink_to("meta")
    for path in ("docs/alias.md", "docs/linked/index.md"):
        assert main(["--repo", str(docs_tree), "backlinks", path]) == 2
        assert capsys.readouterr().err == f"not a doc: {path}\n"


def test_cli_backlinks(docs_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--repo", str(docs_tree), "backlinks", "docs/meta/index.md"]) == 0
    assert capsys.readouterr().out == "index.md\tbody\tindex\n"


def test_cli_build_unknown_ref_exit_2(git_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--repo", str(git_repo), "build", "--ref", "nope", "--out", str(tmp_path / "site")]) == 2
    assert capsys.readouterr().err.strip() == "docspecsite build: unknown ref: nope"


def test_cli_build_not_a_git_repo_exit_1(docs_tree: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--repo", str(docs_tree), "build", "--out", str(tmp_path / "site")]) == 1
    assert capsys.readouterr().err.startswith("docspecsite build: ")


def test_cli_build_unwritable_out_exit_1(git_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "file").write_text("x", encoding="utf-8")
    assert main(["--repo", str(git_repo), "build", "--out", str(tmp_path / "file" / "site")]) == 1
    assert capsys.readouterr().err.splitlines()[-1].startswith("docspecsite build: ")


def test_cli_build_page_error_exit_1(git_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (git_repo / "docs/meta/bad.md").write_bytes(b"---\ntitle: \xff\n---\n")
    sha = make_commit(git_repo, "spec: add bad")
    site_dir = tmp_path / "site"
    assert main(["--repo", str(git_repo), "build", "--out", str(site_dir)]) == 1
    captured = capsys.readouterr()
    assert f"error: docs/meta/bad.md@{sha[:12]}: NotUtf8Error: docs/meta/bad.md: not valid UTF-8" in captured.err
    page_count = len(list(site_dir.rglob("*.html")))
    assert re.fullmatch(
        rf"built {page_count} pages \(\d+ rendered, \d+ from cache, 1 failed\) → {re.escape(str(site_dir))}\n",
        captured.out,
    )
    assert (site_dir / "meta/index.html").is_file()
    assert not (site_dir / "meta/bad.html").exists()


def test_cli_build_strict_error(git_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (git_repo / ProjectConfig.CONFIG_FILE).write_text('source-url = "https://github.com/o/r"\n', encoding="utf-8")
    (git_repo / "docs/meta/bad.md").write_bytes(b"---\ntitle: \xff\n---\n")
    sha = make_commit(git_repo, "spec: add bad")
    site_dir = tmp_path / "site"
    assert main(["--repo", str(git_repo), "build", "--strict", "--out", str(site_dir)]) == 1
    captured = capsys.readouterr()
    assert (
        f"docspecsite build: docs/meta/bad.md@{sha[:12]}: NotUtf8Error: docs/meta/bad.md: not valid UTF-8"
        in captured.err
    )
    assert captured.out == ""
    assert not site_dir.exists()


def test_cli_build_strict_warning(git_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_doc(git_repo, "meta/a.md", "See [gone](gone.md).\n")
    sha = make_commit(git_repo, "spec: add a")
    site_dir = tmp_path / "site"
    assert main(["--repo", str(git_repo), "build", "--strict", "--out", str(site_dir)]) == 1
    err = capsys.readouterr().err
    assert err == f"docspecsite build: strict: docs/meta/a.md@{sha[:12]}: unresolvable link: gone.md\n"
    assert not site_dir.exists()


@_SHOW_DOCSPECSITE_WARNINGS
def test_cli_build_summary_and_warnings(git_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_doc(git_repo, "meta/a.md", "See [gone](gone.md).\n")
    sha = make_commit(git_repo, "spec: add a")
    site_dir = tmp_path / "site"
    assert main(["--repo", str(git_repo), "build", "--out", str(site_dir)]) == 0
    captured = capsys.readouterr()
    page_count = len(list(site_dir.rglob("*.html")))
    assert re.fullmatch(
        rf"built {page_count} pages \(\d+ rendered, \d+ from cache\) → {re.escape(str(site_dir))}\n", captured.out
    )
    assert f"warning: docs/meta/a.md@{sha[:12]}: unresolvable link: gone.md\n" in captured.err


def test_cli_build_shows_docspecsite_warnings_in_own_format(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def warn_and_return(*args: object, **kwargs: object) -> BuildResult:
        warnings.warn(DocspecsiteWarning("%s: unresolvable link: gone.md", "docs/a.md"), stacklevel=1)
        warnings.warn(InternalErrorWarning("%s: internal error: KeyError: 'x'", "docs/b.md"), stacklevel=1)
        warnings.warn("from a library", UserWarning, stacklevel=1)
        return BuildResult(page_count=0, rendered_count=0, cached_count=0, errors=(), failed_count=0)

    monkeypatch.setattr("docspecsite.cli.run_build", warn_and_return)
    with pytest.warns(UserWarning, match="from a library"):
        assert main(["--repo", str(git_repo), "build", "--out", str(tmp_path / "site")]) == 0
    assert capsys.readouterr().err == (
        "warning: docs/a.md: unresolvable link: gone.md\nwarning: docs/b.md: internal error: KeyError: 'x'\n"
    )


def test_cli_build_pythonwarnings_error_shows_internal_error_traceback(git_repo: Path, tmp_path: Path) -> None:
    script = (
        "import sys\n"
        "from docspecsite import build\n"
        "from docspecsite.cli import main\n"
        "def build_broken_page(*args, **kwargs):\n"
        "    raise RuntimeError('injected bug')\n"
        "build.SiteBuilder.build_doc_page = build_broken_page\n"
        "sys.exit(main(sys.argv[1:]))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, "--repo", str(git_repo), "build", "--out", str(tmp_path / "site")],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONWARNINGS": "error::RuntimeWarning:docspecsite.build"},
        check=False,
    )
    assert completed.returncode != 0
    assert "Invalid -W option" not in completed.stderr
    assert "in build_broken_page\n" in completed.stderr
    assert "RuntimeError: injected bug\n" in completed.stderr
    assert "docspecsite.errors.InternalErrorWarning: docs/" in completed.stderr
    assert not (tmp_path / "site").exists()


def test_cli_build_value_error_inside_build_is_not_a_build_error(
    git_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_value_error(*args: object, **kwargs: object) -> BuildResult:
        raise ValueError("a bug")

    monkeypatch.setattr("docspecsite.cli.run_build", raise_value_error)
    with pytest.raises(ValueError, match="a bug"):
        main(["--repo", str(git_repo), "build", "--out", str(tmp_path / "site")])


def test_cli_check_optional_checks_code(code_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_roles_module(code_tree, 'def f() -> None:\n    """Go.\n\n    See :func:`.nope`.\n    """\n')
    assert main(["--repo", str(code_tree), "check"]) == 0
    assert main(["--repo", str(code_tree), "check", "--optional-checks", "code"]) == 1
    assert "unknown code element: :func:`.nope`" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("command", "message"),
    [
        (["check", "--optional-checks", "web"], "unknown optional check: 'web' (available: code)"),
        (["check", "--optional-checks", ""], "no optional checks given (available: code)"),
        (["build", "--parts", "web"], "unknown part: 'web' (available: docs, code)"),
        (["build", "--parts", ""], "no parts given (available: docs, code)"),
    ],
    ids=["unknown-check", "no-checks", "unknown-part", "no-parts"],
)
def test_cli_bad_option_list_is_a_usage_error(
    git_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: list[str],
    message: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["--repo", str(git_repo), *command])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert err.startswith(f"usage: docspecsite {command[0]} ")
    assert err.endswith(f"docspecsite {command[0]}: error: argument {command[1]}: {message}\n")
    assert not (tmp_path / "site").exists()


def test_cli_check_has_no_code_flag(docs_tree: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--repo", str(docs_tree), "check", "--code"])
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "command", [["check"], ["list"], ["backlinks", "index.md"], ["build", "--out", "site"]], ids=lambda c: c[0]
)
def test_cli_stops_at_a_subdirectory_of_a_git_repo(
    git_repo: Path, capsys: pytest.CaptureFixture[str], command: list[str]
) -> None:
    subdirectory = git_repo / "docs"
    assert main(["--repo", str(subdirectory), *command]) == 1
    assert capsys.readouterr().err == (
        f"docspecsite: {subdirectory} must be the top level of its git repo (subdirectories are not supported yet)\n"
    )


def test_cli_stops_in_a_subdirectory_of_a_git_repo_by_default(
    git_repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(git_repo / "docs")
    assert main(["check"]) == 1
    assert "must be the top level of its git repo" in capsys.readouterr().err


def test_cli_list_without_git(
    docs_tree: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(docs_tree / "no-bin"))
    assert main(["--repo", str(docs_tree), "list", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("command", [["check"], ["list"], ["backlinks", "index.md"]], ids=lambda c: c[0])
def test_cli_runs_when_git_cannot_tell_the_top_level(
    docs_tree: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], command: list[str]
) -> None:
    def refuse(_git: Git, *args: str, stdin: bytes | None = None) -> bytes:
        raise GitError("git %s failed: %s", args[0], "fatal: detected dubious ownership in repository")

    monkeypatch.setattr(Git, "run", refuse)
    assert main(["--repo", str(docs_tree), *command]) == 0
    assert capsys.readouterr().err == ""


def _commit_guides_with_symlink(root: Path, target: str) -> None:
    write_guides(root)
    (root / "static").mkdir()
    (root / "static" / "flow.png").write_text("x\n")
    (root / "docs" / "guides" / "alias.md").symlink_to(target)
    make_commit(root, "add guides")


def test_staged_delete_of_symlink_passes(git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _commit_guides_with_symlink(git_repo, "setup.md")
    run_git(git_repo, "rm", "-q", "docs/guides/alias.md")
    assert main(["--repo", str(git_repo), "check", "--staged"]) == 0
    assert capsys.readouterr().out == ""


def test_staged_rename_of_symlink_passes(git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _commit_guides_with_symlink(git_repo, "../../static/flow.png")
    run_git(git_repo, "mv", "docs/guides/alias.md", "docs/guides/flow.png")
    assert main(["--repo", str(git_repo), "check", "--staged"]) == 0
    assert capsys.readouterr().out == ""


def _start_feature_branch(root: Path) -> list[str]:
    """Add ``docs/guides/setup.md`` on ``main``, then check out ``feat/x`` with two commits that change it.

    Returns:
        The full SHA hashes of the two commits of ``feat/x``.
    """
    write_doc(root, "guides/setup.md", "Setup.\n")
    make_commit(root, "spec: add setup", "2026-11-02T12:00:00+00:00")
    run_git(root, "checkout", "-q", "-b", "feat/x")
    shas: list[str] = []
    for day, text in ((3, "Setup, first change.\n"), (4, "Setup, second change.\n")):
        write_doc(root, "guides/setup.md", text)
        shas.append(make_commit(root, "spec: change setup", f"2026-11-0{day}T12:00:00+00:00"))
    return shas


def _list_worktree_pages(site_dir: Path) -> list[str]:
    return sorted(file.relative_to(site_dir).as_posix() for file in site_dir.rglob("v/worktree.html"))


def test_cli_build_defaults_to_head(git_repo: Path, tmp_path: Path) -> None:
    shas = _start_feature_branch(git_repo)
    site_dir = tmp_path / "site"
    assert main(["--repo", str(git_repo), "build", "--out", str(site_dir)]) == 0
    page = (site_dir / "guides/setup.html").read_text(encoding="utf-8")
    for sha in shas:
        assert sha[:12] in page


def test_cli_build_worktree_without_changes_has_no_working_copy(git_repo: Path, tmp_path: Path) -> None:
    shas = _start_feature_branch(git_repo)
    site_dir = tmp_path / "site"
    assert main(["--repo", str(git_repo), "build", "--include-worktree", "--out", str(site_dir)]) == 0
    page = (site_dir / "guides/setup.html").read_text(encoding="utf-8")
    for sha in shas:
        assert sha[:12] in page
    assert _list_worktree_pages(site_dir) == []


def test_cli_build_worktree_shows_only_uncommitted_changes(git_repo: Path, tmp_path: Path) -> None:
    _start_feature_branch(git_repo)
    write_doc(git_repo, "guides/setup.md", "Setup, not committed.\n")
    site_dir = tmp_path / "site"
    assert main(["--repo", str(git_repo), "build", "--include-worktree", "--out", str(site_dir)]) == 0
    assert _list_worktree_pages(site_dir) == ["guides/setup/v/worktree.html"]
    assert "Setup, not committed." in (site_dir / "guides/setup/v/worktree.html").read_text(encoding="utf-8")


def test_cli_build_detached_head(git_repo: Path, tmp_path: Path) -> None:
    write_doc(git_repo, "guides/setup.md", "Setup, checked out.\n")
    make_commit(git_repo, "spec: add setup", "2026-11-02T12:00:00+00:00")
    write_doc(git_repo, "guides/setup.md", "Setup, later.\n")
    make_commit(git_repo, "spec: change setup", "2026-11-03T12:00:00+00:00")
    run_git(git_repo, "checkout", "-q", "--detach", "HEAD~1")
    site_dir = tmp_path / "site"
    assert main(["--repo", str(git_repo), "build", "--out", str(site_dir)]) == 0
    page = (site_dir / "guides/setup.html").read_text(encoding="utf-8")
    assert "Setup, checked out." in page
    assert "Setup, later." not in page


def test_cli_build_no_commits_unknown_ref(docs_tree: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_git(docs_tree, "init", "-q", "-b", "main")
    assert main(["--repo", str(docs_tree), "build", "--out", str(tmp_path / "site")]) == 2
    assert capsys.readouterr().err == "docspecsite build: unknown ref: HEAD\n"


def test_build_help_include_worktree_text(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["build", "--help"])
    help_text = " ".join(capsys.readouterr().out.split())
    assert "read the code and the files under docs/ from the working tree" in help_text
    assert "(default: HEAD, the one checked out)" in help_text


@_SHOW_DOCSPECSITE_WARNINGS
def test_non_utf8_doc_and_file_left_out_with_warning(
    git_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (git_repo / os.fsdecode(b"docs/meta/caf\xe9.png")).write_bytes(b"png")
    (git_repo / os.fsdecode(b"docs/meta/caf\xe9.md")).write_text("# Caf\n", encoding="utf-8")
    make_commit(git_repo, "add names that are not UTF-8", "2026-11-02T12:00:00+00:00")
    site_dir = tmp_path / "site"
    assert main(["--repo", str(git_repo), "build", "--out", str(site_dir)]) == 0
    err = capsys.readouterr().err
    message = "name is not valid UTF-8, which breaks links to the rendered page; left out"
    assert f"warning: docs/meta/caf\\xe9.png: {message}\n" in err
    assert f"warning: docs/meta/caf\\xe9.md: {message}\n" in err
    assert not [file for file in (site_dir / "meta").rglob("*") if file.name.startswith("caf")]


def test_cli_build_code_only_gives_no_docs_warnings(
    git_repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (git_repo / ProjectConfig.CONFIG_FILE).write_text(
        'source-url = "https://github.com/o/r"\ncode-dirs = ["src"]\n', encoding="utf-8"
    )
    (git_repo / "src/pkg").mkdir(parents=True)
    (git_repo / "src/pkg/__init__.py").write_text('"""Package."""\n', encoding="utf-8")
    write_doc(git_repo, "reference/code/index.md", "Code.\n")
    (git_repo / "docs/guides").mkdir()
    (git_repo / "docs/guides/flow.png").symlink_to("/srv/img/flow.png")
    (git_repo / os.fsdecode(b"docs/meta/caf\xe9.md")).write_text("# Caf\n", encoding="utf-8")
    make_commit(git_repo, "add code and odd docs files", "2026-11-02T12:00:00+00:00")
    site_dir = tmp_path / "site"
    assert main(["--repo", str(git_repo), "build", "--parts", "code", "--strict", "--out", str(site_dir)]) == 0
    err = capsys.readouterr().err
    assert "left out" not in err
    assert not (site_dir / "guides").exists()


def _start_cli(repo: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.Popen[bytes]:
    """Start the command line on a repo in a child process, with its stdout and stderr as byte pipes."""
    return subprocess.Popen(
        [sys.executable, "-m", "docspecsite.cli", "--repo", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def _run_into_closed_pipe(repo: Path, *args: str) -> tuple[bytes, str, int]:
    """Run a command whose reader takes one line and closes the pipe; return that line, stderr and the exit code."""
    process = _start_cli(repo, *args)
    assert process.stdout is not None
    assert process.stderr is not None
    first_line = process.stdout.readline()
    process.stdout.close()
    stderr = process.stderr.read().decode()
    process.stderr.close()
    return first_line, stderr, process.wait(timeout=_SUBPROCESS_TIMEOUT_S)


def _run_with_strict_utf8_output(repo: Path, *args: str) -> tuple[str, str, int]:
    """Run a command whose stdout and stderr refuse text that is not valid UTF-8; return them and the exit code."""
    process = _start_cli(repo, *args, env=_STRICT_UTF8_ENV)
    stdout, stderr = process.communicate(timeout=_SUBPROCESS_TIMEOUT_S)
    return stdout.decode(), stderr.decode(), process.returncode


@pytest.fixture
def big_docs_tree(docs_tree: Path) -> Path:
    """A docs tree whose listing and backlinks of ``guides/setup.md`` exceed the pipe buffer."""
    write_doc(docs_tree, "guides/setup.md", "Setup.\n")
    for number in range(1000):
        write_doc(
            docs_tree,
            f"guides/many/doc-{number:04}.md",
            "See [setup](../setup.md).\n",
            title="A long title " * 20,
            summary="A long summary. " * 20,
        )
    return docs_tree


@pytest.mark.parametrize("fmt", ["text", "json"])
@pytest.mark.parametrize("command", [["list"], ["backlinks", "docs/guides/setup.md"]])
def test_cli_output_into_a_pipe_that_closes_early(big_docs_tree: Path, command: list[str], fmt: str) -> None:
    first_line, stderr, code = _run_into_closed_pipe(big_docs_tree, *command, "--format", fmt)
    assert first_line
    assert "Traceback" not in stderr
    assert "BrokenPipeError" not in stderr
    assert code == 0


def _add_non_utf8_doc(docs_tree: Path, text: bytes) -> None:
    """Write the doc ``docs/guides/café.md`` with its name in Latin-1, so not valid UTF-8."""
    (docs_tree / "docs" / "guides").mkdir(exist_ok=True)
    (docs_tree / "docs" / "guides" / os.fsdecode(b"caf\xe9.md")).write_bytes(text)


@pytest.mark.parametrize("fmt", ["text", "json"])
@pytest.mark.parametrize("command", [["list"], ["backlinks", "index.md"]], ids=lambda c: c[0])
def test_cli_shows_bytes_of_non_utf8_names(docs_tree: Path, command: list[str], fmt: str) -> None:
    index_text = (docs_tree / "docs" / "index.md").read_bytes()
    _add_non_utf8_doc(docs_tree, index_text + b"\nSee [the index](../index.md).\n")
    stdout, stderr, code = _run_with_strict_utf8_output(docs_tree, *command, "--format", fmt)
    assert code == 0, stderr
    assert "Traceback" not in stderr
    expected = "guides/caf\\xe9.md" if fmt == "text" else "guides/caf\\\\xe9.md"
    assert expected in stdout


def test_cli_backlinks_shows_bytes_of_a_non_utf8_argument(docs_tree: Path) -> None:
    _, stderr, code = _run_with_strict_utf8_output(docs_tree, "backlinks", os.fsdecode(b"docs/caf\xe9.md"))
    assert code == 2
    assert stderr == "not a doc: docs/caf\\xe9.md\n"


@pytest.mark.parametrize("command", [["list"], ["backlinks", "index.md"]], ids=lambda c: c[0])
def test_cli_read_error_shows_bytes_of_a_non_utf8_name(docs_tree: Path, command: list[str]) -> None:
    _add_non_utf8_doc(docs_tree, b"caf\xe9\n")
    _, stderr, code = _run_with_strict_utf8_output(docs_tree, *command)
    assert code == 1
    assert stderr.startswith(f"docspecsite {command[0]}: docs/guides/caf\\xe9.md: "), stderr


def _run_with_reader_gone(repo: Path, *args: str) -> tuple[str, int]:
    """Run a command whose stdout reader closed the pipe before the command wrote; return stderr and the exit code."""
    process = _start_cli(repo, *args)
    assert process.stdout is not None
    assert process.stderr is not None
    process.stdout.close()
    stderr = process.stderr.read().decode()
    process.stderr.close()
    return stderr, process.wait(timeout=_SUBPROCESS_TIMEOUT_S)


def test_cli_small_output_into_a_closed_pipe_gives_no_flush_error(docs_tree: Path) -> None:
    stderr, code = _run_with_reader_gone(docs_tree, "list")
    assert stderr == ""
    assert code == 0


def test_cli_check_problems_into_a_closed_pipe_keep_exit_code_1(docs_tree: Path) -> None:
    write_doc(docs_tree, "guides/broken.md", title=None)
    stderr, code = _run_with_reader_gone(docs_tree, "check")
    assert "Traceback" not in stderr
    assert "BrokenPipeError" not in stderr
    assert code == 1


def test_cli_build_summary_into_a_closed_pipe(git_repo: Path, tmp_path: Path) -> None:
    stderr, code = _run_with_reader_gone(git_repo, "build", "--out", str(tmp_path / "site"))
    assert "Traceback" not in stderr
    assert "BrokenPipeError" not in stderr
    assert code == 0
    assert (tmp_path / "site" / "index.html").is_file()
