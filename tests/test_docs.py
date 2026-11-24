import pytest

from docspecsite.docs import Doc, DocStatus, is_doc, is_redirect
from docspecsite.problems import Problem


def test_problem_str() -> None:
    assert str(Problem("a/b.md", 3, "broken link")) == "docs/a/b.md:3: broken link"
    assert str(Problem("a", None, "no index.md")) == "docs/a: no index.md"


def test_problem_str_outside_docs() -> None:
    assert str(Problem("tools/x.py", 3, "m", under_docs=False)) == "tools/x.py:3: m"


def test_problem_with_hint() -> None:
    problem = Problem("import.md", 12, 'status note "Built." ("implemented") …', hint='set the doc\'s "status" instead')
    assert str(problem) == (
        'docs/import.md:12: status note "Built." ("implemented") …\n  hint: set the doc\'s "status" instead'
    )
    assert problem.format_report(show_hint=False) == 'docs/import.md:12: status note "Built." ("implemented") …'
    assert problem == Problem("import.md", 12, problem.message)


@pytest.mark.parametrize(
    ("raw", "values"),
    [
        ("specified", ("specified",)),
        (["specified"], ("specified",)),
        (["implemented", "specified"], ("implemented", "specified")),
        (5, ()),
        ({"a": 1}, ()),
        ([], ()),
        (["implemented", 1], ()),
        (None, ()),
    ],
)
def test_doc_status_from_front_matter(raw: object, values: tuple[str, ...]) -> None:
    front_matter: dict[str, object] = {} if raw is None else {"status": raw}
    assert DocStatus.from_front_matter(front_matter).values == values


def test_doc_status_edits() -> None:
    status = DocStatus(("implemented", "specified", "specified"))
    assert status.remove_duplicates().values == ("implemented", "specified")
    assert status.remove_value("specified").values == ("implemented",)
    assert DocStatus(("implemented",)).add_value("changed").values == ("implemented", "changed")


def test_doc_without_loaded_front_matter_has_no_status() -> None:
    assert Doc("x.md", None, "", 1, "no front matter").status == DocStatus(())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("redirect", True), (["redirect"], True), (["implemented", "redirect"], False), ("implemented", False)],
)
def test_is_redirect_reads_one_value_lists(raw: object, expected: bool) -> None:
    assert is_redirect({"status": raw}) is expected


@pytest.mark.parametrize(
    ("path", "is_symlink", "is_under_symlinked_dir", "expected"),
    [
        ("guides/setup.md", False, False, True),
        ("meta/templates/index.md", False, False, True),
        ("meta/templates/behavior.md", False, False, False),
        ("guides/alias.md", True, False, False),
        ("shared/page.md", False, True, False),
        ("img/logo.png", False, False, False),
    ],
    ids=["plain doc", "templates index", "template", "symlink", "under a symlinked dir", "not markdown"],
)
def test_is_doc(path: str, is_symlink: bool, is_under_symlinked_dir: bool, expected: bool) -> None:
    assert is_doc(path, is_symlink=is_symlink, is_under_symlinked_dir=is_under_symlinked_dir) is expected
