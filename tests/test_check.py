import codecs
import os
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import edit_text, move_sample_package_to_root, run_git, write_doc, write_roles_module

from docspecsite.check import Checker, CodeLinkCheck, LinkCheck
from docspecsite.config import ProjectConfig
from docspecsite.docset import DocSet
from docspecsite.git import GitError

ROOT_INDEX_WITH_GUIDES = (
    "## Children\n\n- [roadmap.md](roadmap.md) — M.\n- [meta/index.md](meta/index.md) — R.\n"
    "- [architecture/index.md](architecture/index.md) — A.\n- [guides/](guides/index.md) — G.\n"
)


def find_link_problems(root: Path) -> list[str]:
    link_check = LinkCheck(root)
    return [str(p) for doc in Checker(root).doc_set for p in link_check.check(doc)]


def find_index_problems(root: Path) -> list[str]:
    return [str(p) for p in Checker(root).check_indexes()]


def test_fixture_tree_is_clean(docs_tree: Path) -> None:
    assert find_link_problems(docs_tree) == []
    assert find_index_problems(docs_tree) == []


def test_check_links_missing_file(docs_tree: Path) -> None:
    write_doc(docs_tree, "meta/a.md", "See [b](b.md).\n")
    [problem] = find_link_problems(docs_tree)
    assert problem.startswith("docs/meta/a.md:")
    assert "docs/meta/b.md does not exist" in problem


def test_check_links_missing_anchor(docs_tree: Path) -> None:
    write_doc(docs_tree, "meta/a.md", "# A\n\n## Real\n\n[x](vocabulary.md#tags) [y](#real) [z](#fake)\n")
    [problem] = find_link_problems(docs_tree)
    assert 'no heading "#fake" in docs/meta/a.md' in problem


def test_check_links_directory_and_repo_file_targets_ok(docs_tree: Path) -> None:
    (docs_tree / "compose.yaml").write_text("services: {}\n")
    write_doc(docs_tree, "meta/a.md", "[d](../architecture/) [c](../../compose.yaml#x)\n")
    assert find_link_problems(docs_tree) == []


def test_check_links_front_matter_must_be_doc(docs_tree: Path) -> None:
    (docs_tree / "docs" / "meta" / "data.yaml").write_text("a: 1\n")
    write_doc(docs_tree, "meta/a.md", related=["meta/missing.md", "meta/data.yaml", "meta"])
    problems = find_link_problems(docs_tree)
    assert len(problems) == 3
    assert all(p.startswith("docs/meta/a.md:1: ") for p in problems)
    assert "docs/meta/missing.md does not exist" in problems[0]
    assert "must be a doc" in problems[1]
    assert "must be a doc" in problems[2]


def test_check_links_line_numbers(docs_tree: Path) -> None:
    file = write_doc(docs_tree, "meta/a.md", "# A\n\n[x](nope.md)\n")
    line = file.read_text().splitlines().index("[x](nope.md)") + 1
    [problem] = find_link_problems(docs_tree)
    assert problem.startswith(f"docs/meta/a.md:{line}: ")


def test_check_links_in_doc_with_broken_front_matter(docs_tree: Path) -> None:
    (docs_tree / "docs" / "meta" / "bad.md").write_text("# Bad\n\n[x](nope.md)\n")
    [problem] = find_link_problems(docs_tree)
    assert problem.startswith("docs/meta/bad.md:3: ")


def test_check_indexes_missing_index(docs_tree: Path) -> None:
    write_doc(docs_tree, "meta/sub/a.md")
    assert "docs/meta/sub: directory has no index.md" in find_index_problems(docs_tree)


def test_check_indexes_children(docs_tree: Path) -> None:
    write_doc(
        docs_tree,
        "guides/index.md",
        "# Guides\n\n"
        "Prose mentioning [prose.md](prose.md) does not count.\n\n"
        "- [early.md](early.md) — A list before the section does not count.\n\n"
        "## Children\n\n"
        "- [listed.md](listed.md) — Has a description.\n"
        "- [bare.md](bare.md)\n"
        "- [one/](one/) — A directory linked as a directory.\n"
        "- [two/](two/index.md) — Linked via its index.\n\n"
        "| Doc | About |\n|---|---|\n| [row.md](row.md) | A table row does not count. |\n\n"
        "### Notes\n\n- [sub.md](sub.md) — A subsection still belongs to Children.\n\n"
        "## See also\n\n- [after.md](after.md) — After the section does not count.\n",
    )
    for name in ("listed", "bare", "row", "prose", "early", "after", "sub", "unlisted"):
        write_doc(docs_tree, f"guides/{name}.md")
    write_doc(docs_tree, "guides/old.md", status="redirect", redirect_kind="removed", reason="R.")
    for sub in ("one", "two", "three"):
        write_doc(docs_tree, f"guides/{sub}/index.md")
    write_doc(
        docs_tree,
        "index.md",
        "## Children\n\n- [roadmap.md](roadmap.md) — M.\n- [meta/index.md](meta/index.md) — R.\n"
        "- [architecture/index.md](architecture/index.md) — A.\n- [guides/](guides/index.md) — G.\n",
    )
    problems = find_index_problems(docs_tree)
    file = docs_tree / "docs" / "guides" / "index.md"
    bare_line = file.read_text().splitlines().index("- [bare.md](bare.md)") + 1
    assert sorted(problems) == sorted(
        [
            f"docs/guides/index.md:{bare_line}: child bare.md is listed without a description",
            "docs/guides/index.md: child after.md is not listed",
            "docs/guides/index.md: child early.md is not listed",
            "docs/guides/index.md: child prose.md is not listed",
            "docs/guides/index.md: child row.md is not listed",
            "docs/guides/index.md: child unlisted.md is not listed",
            "docs/guides/index.md: child three/ is not listed",
        ]
    )


def test_check_indexes_without_children_section(docs_tree: Path) -> None:
    write_doc(docs_tree, "index.md", ROOT_INDEX_WITH_GUIDES)
    write_doc(docs_tree, "guides/index.md", "# Guides\n\n- [a.md](a.md) — Listed, but not under Children.\n")
    write_doc(docs_tree, "guides/a.md")
    assert find_index_problems(docs_tree) == ["docs/guides/index.md: child a.md is not listed"]


def test_check_indexes_empty_directory_needs_no_children_section(docs_tree: Path) -> None:
    write_doc(docs_tree, "index.md", ROOT_INDEX_WITH_GUIDES)
    write_doc(docs_tree, "guides/index.md", "# Guides\n\n## Children\n\n- [empty/](empty/index.md) — E.\n")
    write_doc(docs_tree, "guides/empty/index.md", "# Nothing below\n")
    assert find_index_problems(docs_tree) == []


def test_staged_delete_and_rename(git_repo: Path) -> None:
    run_git(git_repo, "rm", "-q", "docs/roadmap.md")
    run_git(git_repo, "mv", "docs/meta/vocabulary.md", "docs/meta/words.md")
    (git_repo / "docs" / "index.md").write_text("changed but not staged\n")
    problems = [str(p) for p in Checker(git_repo).find_staged_deletes_renames()]
    assert len(problems) == 2
    assert problems[0].startswith("docs/meta/vocabulary.md: renamed to docs/meta/words.md")
    assert problems[1].startswith("docs/roadmap.md: deleted")
    assert all("redirect doc" in p for p in problems)


def test_staged_rename_of_path_with_quote_and_delete_of_non_ascii(git_repo: Path) -> None:
    for name in ('meta/say "hi".md', "ü.md"):
        (git_repo / "docs" / name).write_text("x\n")
    run_git(git_repo, "add", "docs")
    run_git(git_repo, "commit", "-q", "-m", "add")
    run_git(git_repo, "mv", 'docs/meta/say "hi".md', 'docs/meta/say "bye".md')
    run_git(git_repo, "rm", "-q", "docs/ü.md")
    problems = [str(p) for p in Checker(git_repo).find_staged_deletes_renames()]
    assert len(problems) == 2
    assert problems[0].startswith('docs/meta/say "hi".md: renamed to docs/meta/say "bye".md; ')
    assert problems[1].startswith("docs/ü.md: deleted; ")


def test_staged_delete_of_non_utf8_name(git_repo: Path) -> None:
    name = os.fsdecode(b"\xff.md")
    (git_repo / "docs" / name).write_text("x\n")
    run_git(git_repo, "add", "docs")
    run_git(git_repo, "commit", "-q", "-m", "add")
    run_git(git_repo, "rm", "-q", f"docs/{name}")
    [problem] = Checker(git_repo).find_staged_deletes_renames()
    assert (problem.path, problem.message.split(";")[0]) == (name, "deleted")


def test_staged_nothing(git_repo: Path) -> None:
    assert Checker(git_repo).find_staged_deletes_renames() == []


def test_staged_outside_git(docs_tree: Path) -> None:
    with pytest.raises(GitError) as raised:
        Checker(docs_tree).find_staged_deletes_renames()
    assert raised.value.message == "git %s failed: %s"
    assert str(raised.value).startswith("git diff failed: ")


def test_run_clean_tree(docs_tree: Path) -> None:
    assert Checker(docs_tree).run(include_staged=False) == []


def test_run_bad_front_matter_still_checks_links(docs_tree: Path) -> None:
    (docs_tree / "docs" / "meta" / "bad.md").write_text("# Bad\n\n- [x](nope.md) — x\n")
    messages = [str(p) for p in Checker(docs_tree).run(include_staged=False)]
    assert "docs/meta/bad.md: no front matter" in messages
    assert any(m.startswith("docs/meta/bad.md:3: broken link") for m in messages)
    assert messages == sorted(messages)


def test_run_reports_invalid_config(docs_tree: Path) -> None:
    (docs_tree / ProjectConfig.CONFIG_FILE).write_text("[code-components\n")
    (docs_tree / "docs" / "meta" / "bad.md").write_text("# Bad\n")
    problems = Checker(docs_tree).run(include_staged=False)
    bad = [p for p in problems if p.path == ProjectConfig.CONFIG_FILE]
    assert len(bad) == 1
    assert not bad[0].under_docs
    assert str(bad[0]).startswith("docspecsite.toml: not valid TOML: ")
    assert "docs/meta/bad.md: no front matter" in [str(p) for p in problems]


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_run_reports_unreadable_config_naming_it_once(docs_tree: Path) -> None:
    (docs_tree / ProjectConfig.CONFIG_FILE).write_text('adr-prefix = "DSS"\n')
    (docs_tree / ProjectConfig.CONFIG_FILE).chmod(0)
    [bad] = [str(p) for p in Checker(docs_tree).run(include_staged=False) if p.path == ProjectConfig.CONFIG_FILE]
    assert bad.startswith("docspecsite.toml: cannot be read: ")
    assert bad.count(ProjectConfig.CONFIG_FILE) == 2  # the location, and the path in the OS error


def test_run_reports_undecodable_code_as_code_problem(code_tree: Path) -> None:
    (code_tree / "tools/sample/src/sample/__init__.py").write_bytes(b'"""Bad \xff."""\n')
    problems = Checker(code_tree).run(include_staged=False)
    assert not [p for p in problems if p.path == ProjectConfig.CONFIG_FILE]
    [bad] = [p for p in problems if "cannot load code" in p.message]
    assert bad.path in ("(code)", "tools/sample/src/sample/bad.py")
    assert not bad.under_docs


def test_run_reports_code_value_error_as_code_problem(code_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_value_error(*args: object, **kwargs: object) -> None:
        raise ValueError("bad code")

    monkeypatch.setattr("docspecsite.coderef.griffe.load", raise_value_error)
    [bad] = [p for p in Checker(code_tree).run(include_staged=False) if "cannot load code" in p.message]
    assert bad.message == "cannot load code: cannot load the code of package sample: bad code"


def test_run_reports_code_outside_its_package_dir_as_code_problem(code_tree: Path, tmp_path: Path) -> None:
    checker = Checker(code_tree)
    assert checker.codebase is not None
    package = checker.codebase.packages_by_name["sample"]
    checker.codebase.packages_by_name["sample"] = replace(package, package_dir=tmp_path / "elsewhere" / "sample")
    [bad] = [p for p in checker.run(include_staged=False, include_code=True) if "cannot load code" in p.message]
    assert "outside" in bad.message
    assert "sample" in bad.message


def test_run_reports_undecodable_doc_and_checks_the_others(docs_tree: Path) -> None:
    (docs_tree / "docs/meta/latin.md").write_bytes(b"---\ntitle: Caf\xe9\n---\n")
    _list_in_meta_index(docs_tree, "latin")
    write_doc(docs_tree, "meta/a.md", "# A\n\n[x](nope.md)\n")
    _list_in_meta_index(docs_tree, "a")
    messages = [str(p) for p in Checker(docs_tree).run(include_staged=False)]
    assert "docs/meta/latin.md: not valid UTF-8 (invalid continuation byte at byte 14)" in messages
    assert any(m.startswith("docs/meta/a.md:") and "nope.md does not exist" in m for m in messages)


def test_check_indexes_skips_undecodable_index(docs_tree: Path) -> None:
    index_file = docs_tree / "docs/meta/index.md"
    index_file.write_bytes(index_file.read_bytes() + b"\xff\n")
    assert find_index_problems(docs_tree) == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_run_reports_unreadable_doc(docs_tree: Path) -> None:
    write_doc(docs_tree, "meta/locked.md")
    _list_in_meta_index(docs_tree, "locked")
    (docs_tree / "docs/meta/locked.md").chmod(0)
    messages = [str(p) for p in Checker(docs_tree).run(include_staged=False)]
    assert messages == ["docs/meta/locked.md: cannot be read: Permission denied"]


def test_run_reports_undecodable_vocabulary_doc(docs_tree: Path) -> None:
    vocabulary_file = docs_tree / "docs/meta/vocabulary.md"
    vocabulary_file.write_bytes(vocabulary_file.read_bytes() + b"\xff\n")
    messages = [str(p) for p in Checker(docs_tree).run(include_staged=False)]
    assert any(m.startswith("docs/meta/vocabulary.md: not valid UTF-8 (invalid start byte at byte ") for m in messages)


@pytest.mark.parametrize(("prefix", "offset"), [(b"", 3), (codecs.BOM_UTF8, 6)], ids=["plain", "bom"])
def test_check_links_to_undecodable_target_with_anchor(docs_tree: Path, prefix: bytes, offset: int) -> None:
    (docs_tree / "docs/meta/templates").mkdir()
    (docs_tree / "docs/meta/templates/x.md").write_bytes(prefix + b"# T\xff\n")
    write_doc(docs_tree, "meta/a.md", "# A\n\n[t](templates/x.md#t)\n")
    [problem] = find_link_problems(docs_tree)
    assert problem.startswith("docs/meta/a.md:")
    assert problem.endswith(
        f': cannot check heading "#t": docs/meta/templates/x.md: not valid UTF-8 (invalid start byte at byte {offset})'
    )


def test_run_reports_a_package_in_two_code_dirs(code_tree: Path) -> None:
    other = code_tree / "tools/other/src/sample"
    other.mkdir(parents=True)
    (other / "__init__.py").write_text('"""Other sample."""\n', encoding="utf-8")
    messages = [str(p) for p in Checker(code_tree).run(include_staged=False, include_code=True)]
    assert messages == [
        "(code): cannot load code: package sample is in more than one code directory: tools/other/src, tools/sample/src"
    ]


def test_run_reports_docs_at_reserved_paths(docs_tree: Path) -> None:
    write_doc(docs_tree, "status.md")
    write_doc(docs_tree, "meta/a.md")
    write_doc(docs_tree, "meta/a/v/x.md")
    write_doc(docs_tree, "reference/code/index.md")
    message = "reserved path: the doc's page would take the URL of"
    reserved = [str(p) for p in Checker(docs_tree).run(include_staged=False) if "reserved path" in p.message]
    assert reserved == [
        f"docs/meta/a/v/x.md: {message} the version pages of docs/meta/a.md",
        f"docs/status.md: {message} the status page",
    ]


def test_run_reports_schema_problems(docs_tree: Path) -> None:
    write_doc(docs_tree, "meta/a.md", components=["nope"])
    messages = [str(p) for p in Checker(docs_tree).run(include_staged=False)]
    assert any('unknown component "nope"' in m for m in messages)


def test_templates_are_not_docs(docs_tree: Path) -> None:
    write_doc(
        docs_tree,
        "meta/index.md",
        "## Children\n\n- [vocabulary.md](vocabulary.md) — Words.\n- [templates/](templates/index.md) — Templates.\n",
    )
    write_doc(docs_tree, "meta/templates/index.md", "## Children\n\n- [x.md](x.md) — A template.\n")
    (docs_tree / "docs" / "meta" / "templates" / "x.md").write_text(
        "---\ntitle: <Name>\nsummary: <One sentence: what.>\nlayer: behavior\n---\n\n[s](<same/path>.md)\n"
    )
    assert Checker(docs_tree).run(include_staged=False) == []
    assert "meta/templates/x.md" not in [d.path for d in DocSet.load(docs_tree)]
    assert "meta/templates/index.md" in [d.path for d in DocSet.load(docs_tree)]


def _list_in_meta_index(root: Path, name: str) -> None:
    edit_text(root / "docs/meta/index.md", lambda text: text + f"- [{name}]({name}.md) — A test doc.\n")


def test_run_resolves_code_links(code_tree: Path) -> None:
    write_doc(code_tree, "meta/x.md", "See [t](code:sample.mod.Thing).\n", code=["sample.mod"])
    _list_in_meta_index(code_tree, "x")
    assert [str(p) for p in Checker(code_tree).run(include_staged=False)] == []


def test_check_code_links_unknown(code_tree: Path) -> None:
    write_doc(code_tree, "meta/x.md", "# X\n\nSee [t](code:sample.nope).\n", code=["sample.gone"])
    checker = Checker(code_tree)
    assert checker.codebase is not None
    problems = [str(p) for p in CodeLinkCheck(checker.codebase).check(checker.doc_set.by_path["meta/x.md"])]
    assert "docs/meta/x.md:15: code: link to unknown code element: sample.nope" in problems
    assert 'docs/meta/x.md:1: "code" entry is not a code element: sample.gone' in problems


def _break_docs_line(code_tree: Path) -> str:
    """Point the ``Docs:`` line of ``sample.mod`` to a missing doc; return the problem a check reports for it."""
    mod = code_tree / "tools/sample/src/sample/mod.py"
    source = mod.read_text(encoding="utf-8")
    mod.write_text(source.replace("Docs: meta/vocabulary.md", "Docs: meta/missing.md"), encoding="utf-8")
    line = mod.read_text(encoding="utf-8").splitlines().index("Docs: meta/missing.md") + 1
    return f"tools/sample/src/sample/mod.py:{line}: Docs: line points to a missing doc: meta/missing.md"


def test_check_docs_lines(code_tree: Path) -> None:
    expected = _break_docs_line(code_tree)
    assert expected in [str(p) for p in Checker(code_tree).check_docs_lines()]


def test_check_ignores_docs_lines(code_tree: Path) -> None:
    expected = _break_docs_line(code_tree)
    assert expected not in [str(p) for p in Checker(code_tree).run(include_staged=False)]


def test_check_code_reports_docs_lines(code_tree: Path) -> None:
    expected = _break_docs_line(code_tree)
    assert expected in [str(p) for p in Checker(code_tree).run(include_staged=False, include_code=True)]


def test_check_code_reports_unknown_references(code_tree: Path) -> None:
    write_roles_module(
        code_tree,
        "class Thing:\n"
        "    def go(self) -> None:\n"
        '        """Go.\n'
        "\n"
        "        Known :meth:`.go`, unknown :meth:`.nope`, and [x](code:sample.gone).\n"
        '        """\n',
    )
    problems = [str(p) for p in Checker(code_tree).run(include_staged=False, include_code=True)]
    file = "tools/sample/src/sample/roles.py"
    assert f"{file}:{5}: unknown code element: :meth:`.nope`" in problems
    assert f"{file}:{5}: unknown code element: code:sample.gone" in problems
    assert not any(".go`" in p for p in problems)


def test_run_reports_unknown_code_link(code_tree: Path) -> None:
    write_doc(code_tree, "meta/x.md", "See [t](code:sample.nope).\n")
    _list_in_meta_index(code_tree, "x")
    [problem] = Checker(code_tree).run(include_staged=False)
    assert str(problem).endswith("code: link to unknown code element: sample.nope")


def test_check_docs_lines_missing_anchor(code_tree: Path) -> None:
    mod = code_tree / "tools/sample/src/sample/mod.py"
    mod.write_text(
        mod.read_text(encoding="utf-8").replace("meta/vocabulary.md", "meta/vocabulary.md#nope"), encoding="utf-8"
    )
    problems = [str(p) for p in Checker(code_tree).check_docs_lines()]
    assert 'tools/sample/src/sample/mod.py:3: no heading "#nope" in docs/meta/vocabulary.md' in problems


def test_check_docs_lines_to_undecodable_doc(code_tree: Path) -> None:
    module_file = code_tree / "tools/sample/src/sample/mod.py"
    module_file.write_text(
        module_file.read_text(encoding="utf-8").replace("meta/vocabulary.md", "meta/vocabulary.md#nope"),
        encoding="utf-8",
    )
    vocabulary_file = code_tree / "docs/meta/vocabulary.md"
    vocabulary_file.write_bytes(vocabulary_file.read_bytes() + b"\xff\n")
    assert [str(p) for p in Checker(code_tree).check_docs_lines()] == []


def test_run_reports_unlocatable_docs_line(code_tree: Path) -> None:
    mod = code_tree / "tools/sample/src/sample/mod.py"
    mod.write_text(
        mod.read_text(encoding="utf-8") + "\n\ndef f() -> None:\n    'Title.\\n\\nDocs: meta/vocabulary.md'\n",
        encoding="utf-8",
    )
    problems = [str(p) for p in Checker(code_tree).run(include_staged=False, include_code=True)]
    assert any(p.startswith("tools/sample/src/sample/mod.py") and "cannot locate Docs: lines" in p for p in problems)


def test_check_docs_lines_with_relative_root(code_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(code_tree)
    root = Path()
    checker = Checker(root)
    assert checker.codebase is not None
    assert checker.loading_problems == []
    assert checker.check_docs_lines() == []


def test_check_names_file_and_directory(docs_tree: Path) -> None:
    (docs_tree / "docs" / "meta" / "c#sharp").mkdir()
    (docs_tree / "docs" / "meta" / "c#sharp" / "a.md").write_text("x\n")
    (docs_tree / "docs" / "meta" / "100%.md").write_text("x\n")
    (docs_tree / "docs" / "meta" / "fine.md").write_text("x\n")
    assert [str(p) for p in Checker(docs_tree).check_names()] == [
        f"docs/meta/100%.md: {Checker.FORBIDDEN_NAME_MESSAGE}",
        f"docs/meta/c#sharp: {Checker.FORBIDDEN_NAME_MESSAGE}",
    ]


def test_check_names_clean_tree(docs_tree: Path) -> None:
    assert Checker(docs_tree).check_names() == []


def test_run_takes_adr_prefix_from_config(docs_tree: Path) -> None:
    (docs_tree / ProjectConfig.CONFIG_FILE).write_text('adr-prefix = "DSS"\nexternal-adr-prefixes = ["BASE", "PYRF"]\n')
    for name in ("BASE-0001-a.md", "DSS-0001-b.md", "APP-0001-c.md", "PYRF-0001-d.md"):
        write_doc(docs_tree, f"architecture/decisions/{name}", decision="accepted", date="2026-11-18")
    found = [p for p in Checker(docs_tree).run(include_staged=False) if "ADR file name" in p.message]
    assert [(p.path, p.message) for p in found] == [
        (
            "architecture/decisions/APP-0001-c.md",
            "ADR file name must be <PREFIX>-NNNN-<slug>.md with PREFIX one of: BASE, PYRF, DSS",
        )
    ]


def test_run_reports_config_problems(docs_tree: Path) -> None:
    (docs_tree / ProjectConfig.CONFIG_FILE).write_text('adr_prefix = "DSS"\ncode-dirs = ["/abs/src"]\n')
    found = [p for p in Checker(docs_tree).run(include_staged=False) if p.path == ProjectConfig.CONFIG_FILE]
    assert [(p.message, p.under_docs) for p in found] == [
        ('"code-dirs" entries must be paths inside the repo, without ".." or a leading "/": "/abs/src"', False),
        ('unknown setting "adr_prefix"', False),
    ]


def test_run_skips_adr_names_when_config_is_invalid(docs_tree: Path) -> None:
    (docs_tree / ProjectConfig.CONFIG_FILE).write_text("[code-components\n")
    write_doc(docs_tree, "architecture/decisions/DSS-0001-b.md", decision="accepted", date="2026-11-18")
    assert not [p for p in Checker(docs_tree).run(include_staged=False) if "ADR file name" in p.message]


def test_run_finds_code_in_the_repo_root(code_tree: Path) -> None:
    move_sample_package_to_root(code_tree)
    write_doc(code_tree, "meta/x.md", "See [t](code:sample.mod.Thing).\n", code=["sample.mod"])
    _list_in_meta_index(code_tree, "x")
    assert [str(p) for p in Checker(code_tree).run(include_staged=False)] == []
