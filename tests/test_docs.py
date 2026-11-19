from docspecsite.problems import Problem


def test_problem_str() -> None:
    assert str(Problem("a/b.md", 3, "broken link")) == "docs/a/b.md:3: broken link"
    assert str(Problem("a", None, "no index.md")) == "docs/a: no index.md"


def test_problem_str_outside_docs() -> None:
    assert str(Problem("tools/x.py", 3, "m", under_docs=False)) == "tools/x.py:3: m"
