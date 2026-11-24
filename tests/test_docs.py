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


def test_a_warning_prints_without_its_hint() -> None:
    warning = Problem("scenarios/import.md", 1, "ignored", is_warning=True, hint="h")
    assert str(warning) == "warning: docs/scenarios/import.md:1: ignored"


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
    assert DocStatus.from_front_matter(front_matter, "meta/x.md").values == values


@pytest.mark.parametrize("path", ["scenarios/import.md", "scenarios/sub/import.md"])
def test_an_implemented_status_is_left_out_of_the_values(path: str) -> None:
    status = DocStatus.from_front_matter({"status": "implemented", "milestone": "later", "priority": "must"}, path)
    assert (status.values, status.ignored_values, status.milestone, status.priority) == (
        (),
        ("implemented",),
        None,
        None,
    )
    assert (status.is_written, status.is_build_tracked) == (False, False)


@pytest.mark.parametrize(
    ("raw", "values", "ignored_values"),
    [
        (["draft", "specified"], ("draft",), ("specified",)),
        (["implemented", "changed"], (), ("implemented", "changed")),
        ("deprecated", ("deprecated",), ()),
        (["draft"], ("draft",), ()),
    ],
)
def test_what_is_left_of_the_status_is_checked_as_in_any_doc(
    raw: object, values: tuple[str, ...], ignored_values: tuple[str, ...]
) -> None:
    status = DocStatus.from_front_matter({"status": raw}, "scenarios/import.md")
    assert (status.values, status.ignored_values) == (values, ignored_values)
    assert status.is_written is bool(values)


@pytest.mark.parametrize("raw", [[], None, 5])
def test_a_status_written_with_no_value_counts_as_written(raw: object) -> None:
    assert DocStatus.from_front_matter({"status": raw}, "scenarios/import.md").is_written is True


def test_the_directory_decides_the_layer() -> None:
    front_matter = {"status": "implemented", "layer": "behavior"}
    assert DocStatus.from_front_matter(front_matter, "scenarios/import.md").values == ()
    assert DocStatus.from_front_matter({**front_matter, "layer": "scenarios"}, "behavior/import.md").values == (
        "implemented",
    )


def test_docs_of_other_layers_keep_milestone_and_priority() -> None:
    status = DocStatus.from_front_matter(
        {"status": "specified", "milestone": "later", "priority": "must"}, "behavior/x.md"
    )
    assert (status.milestone, status.priority, status.is_build_tracked) == ("later", "must", True)


def test_a_null_milestone_is_kept_as_written_but_reads_as_none() -> None:
    status = DocStatus.from_front_matter({"status": "specified", "milestone": None}, "behavior/x.md")
    assert (dict(status.roadmap_front_matter), status.milestone) == ({"status": "specified", "milestone": None}, None)


def test_a_doc_status_is_hashable() -> None:
    front_matter = {"status": "specified", "milestone": "m"}
    assert hash(DocStatus.from_front_matter(front_matter, "behavior/x.md")) == hash(
        DocStatus.from_front_matter(dict(front_matter), "behavior/x.md")
    )


def test_doc_status_edits_keep_the_other_fields() -> None:
    status = DocStatus.from_front_matter({"status": ["draft", "specified"], "milestone": "m"}, "scenarios/x.md")
    assert status.remove_value("draft").ignored_values == ("specified",)
    assert (
        DocStatus.from_front_matter({"status": "draft", "milestone": "m"}, "meta/x.md").remove_value("draft").milestone
        == "m"
    )


def test_doc_status_edits_keep_the_ignored_values_in_place() -> None:
    status = DocStatus.from_front_matter({"status": ["implemented", "draft", "draft", "implemented"]}, "scenarios/x.md")
    assert status.remove_duplicates().format_yaml() == "[implemented, draft, implemented]"
    assert status.remove_value("draft").format_yaml() == "[implemented, implemented]"


def test_doc_status_edits() -> None:
    status = DocStatus(("implemented", "specified", "specified"))
    assert status.remove_duplicates().values == ("implemented", "specified")
    assert status.remove_value("specified").values == ("implemented",)
    assert DocStatus(("implemented",)).add_value("changed").values == ("implemented", "changed")


def test_doc_without_loaded_front_matter_has_no_status() -> None:
    status = Doc("x.md", None, "", 1, "no front matter").status
    assert (status.values, status.is_written) == ((), False)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("redirect", True), (["redirect"], True), (["implemented", "redirect"], False), ("implemented", False)],
)
def test_is_redirect_reads_one_value_lists(raw: object, expected: bool) -> None:
    assert is_redirect({"status": raw}, "meta/x.md") is expected


def test_a_redirect_scenario_doc_with_a_build_status_is_a_redirect() -> None:
    assert is_redirect({"status": ["redirect", "implemented"]}, "scenarios/old.md") is True


def test_status_yaml_and_json_forms() -> None:
    one, two, none = DocStatus(("implemented",)), DocStatus(("implemented", "specified")), DocStatus(())
    assert [s.format_yaml() for s in (one, two)] == ["implemented", "[implemented, specified]"]
    assert [s.make_json_value() for s in (one, two, none)] == ["implemented", ["implemented", "specified"], None]


@pytest.mark.parametrize(("values", "expected"), [(("deprecated",), True), (("redirect",), True), (("draft",), False)])
def test_retired_status(values: tuple[str, ...], expected: bool) -> None:
    assert DocStatus(values).is_retired is expected


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
