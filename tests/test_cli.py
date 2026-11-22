import json
import os
import re
import subprocess
import sys
import tomllib
import warnings
from pathlib import Path

import pytest
from conftest import make_commit, run_git, write_doc, write_roles_module

from docspecsite.build import BuildResult
from docspecsite.cli import main
from docspecsite.config import ProjectConfig
from docspecsite.errors import DocspecsiteWarning, InternalErrorWarning
from docspecsite.git import Git, GitError


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
