import datetime

import pytest
from conftest import make_doc

from docspecsite.docs import Doc
from docspecsite.schema import FrontMatterValidator
from docspecsite.vocabulary import Vocabulary

VOCAB = Vocabulary(
    components=frozenset({"docs-system", "core"}),
    milestones=("foundation", "first-release"),
)

ADR = "architecture/decisions/DSS-0001-x.md"
ADR_PREFIXES = ("BASE", "DSS")


def collect_messages(checked: Doc) -> list[str]:
    problems = FrontMatterValidator(VOCAB, ADR_PREFIXES).validate(checked)
    assert all(p.path == checked.path and p.line_number == 1 for p in problems)
    return [p.message for p in problems]


def assert_one(checked: Doc, expected: str) -> None:
    found = collect_messages(checked)
    assert len(found) == 1, found
    assert expected in found[0]


def test_valid_doc_has_no_problems() -> None:
    assert collect_messages(make_doc()) == []
    assert collect_messages(make_doc("index.md")) == []


def test_doc_with_load_error_is_skipped() -> None:
    assert collect_messages(Doc("x.md", None, "", 1, "no front matter")) == []


@pytest.mark.parametrize("field", ["title", "summary", "layer", "status", "components", "tags", "related"])
def test_required_fields(field: str) -> None:
    assert_one(make_doc(**{field: None}), f'missing required field "{field}"')


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("title", "", '"title" must be a non-empty string'),
        ("summary", 3, '"summary" must be a non-empty string'),
        ("components", "core", '"components" must be a list of strings'),
        ("tags", [1], '"tags" must be a list of strings'),
        ("related", None, 'missing required field "related"'),
        ("code", "a.b", '"code" must be a list of strings'),
    ],
)
def test_field_types(field: str, value: object, expected: str) -> None:
    assert_one(make_doc(**{field: value}), expected)


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "done"), ("priority", "high")],
)
def test_enum_fields(field: str, value: str) -> None:
    assert_one(make_doc(**{field: value}), f'"{field}" must be one of')


def test_unknown_layer() -> None:
    found = collect_messages(make_doc(layer="nope"))
    assert any('"layer" must be one of' in m for m in found)


@pytest.mark.parametrize(
    ("path", "layer", "expected"),
    [
        ("x.md", "meta", 'expected "root"'),
        ("meta/a/b.md", "root", 'expected "meta"'),
    ],
)
def test_layer_matches_directory(path: str, layer: str, expected: str) -> None:
    assert_one(make_doc(path, layer=layer), expected)


def test_layer_in_subdirectory_ok() -> None:
    assert collect_messages(make_doc("meta/a/b.md", layer="meta")) == []


def test_unknown_component() -> None:
    assert_one(
        make_doc(components=["core", "nope"]),
        'unknown component "nope" (add it to architecture/components.md)',
    )


@pytest.mark.parametrize("tag", ["Bad", "two words", "x_y", "-x", "x--y"])
def test_tag_format(tag: str) -> None:
    assert_one(make_doc(tags=[tag]), f'tag "{tag}"')


def test_good_tags() -> None:
    assert collect_messages(make_doc(tags=["adr", "data-model", "pg18"])) == []


def test_milestone_and_priority() -> None:
    assert collect_messages(make_doc(milestone="foundation", priority="must")) == []
    assert_one(make_doc(milestone="later"), 'unknown milestone "later"')


def test_redirect_valid() -> None:
    moved = make_doc(status="redirect", redirect_kind="moved", redirect_to="a.md", reason="R.")
    assert collect_messages(moved) == []
    removed = make_doc(status="redirect", redirect_kind="removed", reason="R.")
    assert collect_messages(removed) == []
    split = make_doc(status="redirect", redirect_kind="split", redirect_to=["a.md", "b.md"], reason="R.")
    assert collect_messages(split) == []


@pytest.mark.parametrize(
    ("front_matter", "expected"),
    [
        ({"redirect_to": "a.md", "reason": "R."}, 'needs "redirect_kind"'),
        ({"redirect_kind": "gone", "redirect_to": "a.md", "reason": "R."}, '"redirect_kind" must be one of'),
        ({"redirect_kind": "moved", "redirect_to": "a.md"}, 'needs "reason"'),
        ({"redirect_kind": "moved", "reason": "R."}, 'needs "redirect_to"'),
        ({"redirect_kind": "split", "redirect_to": "a.md", "reason": "R."}, "must be a list"),
        ({"redirect_kind": "moved", "redirect_to": [1], "reason": "R."}, '"redirect_to" must be'),
        ({"redirect_kind": "removed", "redirect_to": "a.md", "reason": "R."}, "no replacement"),
    ],
)
def test_redirect_rules(front_matter: dict[str, object], expected: str) -> None:
    assert_one(make_doc(status="redirect", **front_matter), expected)


@pytest.mark.parametrize("field", ["redirect_kind", "redirect_to"])
def test_redirect_fields_need_redirect_status(field: str) -> None:
    assert_one(make_doc(**{field: "moved"}), "only allowed with status: redirect")


def test_adr_valid() -> None:
    assert collect_messages(make_doc(ADR, decision="accepted", date=datetime.date(2026, 11, 18))) == []
    assert collect_messages(make_doc(ADR, decision="proposed", date="2026-11-18")) == []
    superseded = make_doc(
        ADR, decision="superseded", date="2026-11-18", superseded_by="architecture/decisions/DSS-0002-y.md"
    )
    assert collect_messages(superseded) == []


@pytest.mark.parametrize(
    ("front_matter", "expected"),
    [
        ({"date": "2026-11-18"}, 'ADR needs "decision"'),
        ({"decision": "maybe", "date": "2026-11-18"}, '"decision" must be one of'),
        ({"decision": "accepted"}, 'ADR needs "date"'),
        ({"decision": "accepted", "date": "18.11.2026"}, '"date" must be'),
        ({"decision": "superseded", "date": "2026-11-18"}, 'needs "superseded_by"'),
    ],
)
def test_adr_rules(front_matter: dict[str, object], expected: str) -> None:
    assert_one(make_doc(ADR, **front_matter), expected)


def test_decision_only_on_adrs() -> None:
    assert_one(make_doc(decision="accepted"), '"decision" is only for ADRs')
    assert collect_messages(make_doc("architecture/decisions/index.md")) == []


@pytest.mark.parametrize("path", ["architecture/decisions/BASE-0002-y.md", "architecture/decisions/DSS-0123-a-b2.md"])
def test_adr_names_with_known_prefixes(path: str) -> None:
    assert collect_messages(make_doc(path, decision="accepted", date="2026-11-18")) == []


@pytest.mark.parametrize(
    "name",
    [
        "0001-x.md",
        "APP-0001-x.md",
        "dss-0001-x.md",
        "DSS-001-x.md",
        "DSS-00001-x.md",
        "DSS-0001.md",
        "DSS-0001-X.md",
        "DSS0001-x.md",
        "notes.md",
    ],
)
def test_adr_names_need_a_known_prefix(name: str) -> None:
    assert_one(
        make_doc(f"architecture/decisions/{name}", decision="accepted", date="2026-11-18"),
        "ADR file name must be <PREFIX>-NNNN-<slug>.md with PREFIX one of: BASE, DSS",
    )


def test_adr_name_rule_covers_subdirectories() -> None:
    assert_one(
        make_doc("architecture/decisions/old/0001-x.md", decision="accepted", date="2026-11-18"),
        "ADR file name must be",
    )
    assert collect_messages(make_doc("architecture/decisions/old/index.md")) == []


def test_adr_name_rule_runs_without_front_matter() -> None:
    adr = Doc("architecture/decisions/0001-x.md", None, "", 1, "no front matter")
    found = FrontMatterValidator(VOCAB, ADR_PREFIXES).validate(adr)
    assert [p.message for p in found] == ["ADR file name must be <PREFIX>-NNNN-<slug>.md with PREFIX one of: BASE, DSS"]
    found = FrontMatterValidator(VOCAB, ()).validate(adr)
    assert [p.message for p in found] == [
        (
            "ADR file name must be <PREFIX>-NNNN-<slug>.md, and no ADR prefix is configured: "
            "set adr-prefix or external-adr-prefixes in docspecsite.toml"
        )
    ]


def test_adr_name_rule_skipped_without_prefixes() -> None:
    adr = make_doc("architecture/decisions/APP-0001-x.md", decision="accepted", date="2026-11-18")
    assert FrontMatterValidator(VOCAB, None).validate(adr) == []
