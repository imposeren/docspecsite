import json
from pathlib import Path

import pytest
from conftest import make_doc

from docspecsite.config import ProjectConfig
from docspecsite.docs import Doc
from docspecsite.docset import DocSet
from docspecsite.query import (
    Backlink,
    Filters,
    format_backlinks,
    format_list,
    resolve_doc_path,
)

_NO_CONFIG = ProjectConfig((), "", {})

DOCS = [
    make_doc("meta/b.md", status="implemented", components=["docs-system"], tags=["rules"]),
    make_doc("architecture/a.md", components=["core", "docs-system"], milestone="foundation", priority="must"),
    make_doc("architecture/c.md", tags=["rules", "adr"], milestone="foundation", priority="should"),
    Doc("meta/broken.md", None, "", 1, "no front matter"),
]


def select_paths(filters: Filters) -> list[str]:
    return [d.path for d in DocSet(DOCS).select(filters, _NO_CONFIG)]


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (Filters(), ["architecture/a.md", "architecture/c.md", "meta/b.md"]),
        (Filters(layer="meta"), ["meta/b.md"]),
        (Filters(status="specified"), ["architecture/a.md", "architecture/c.md"]),
        (Filters(component="docs-system"), ["architecture/a.md", "meta/b.md"]),
        (Filters(component="docs"), []),
        (Filters(tag="rules"), ["architecture/c.md", "meta/b.md"]),
        (Filters(milestone="foundation"), ["architecture/a.md", "architecture/c.md"]),
        (Filters(priority="must"), ["architecture/a.md"]),
        (Filters(status="specified", tag="rules"), ["architecture/c.md"]),
        (Filters(milestone="foundation", component="docs-system"), ["architecture/a.md"]),
    ],
)
def test_select_filters(filters: Filters, expected: list[str]) -> None:
    assert select_paths(filters) == expected


def test_select_skips_broken_docs() -> None:
    assert "meta/broken.md" not in select_paths(Filters())


def test_format_list_text() -> None:
    text = format_list(DocSet(DOCS).select(Filters(layer="meta"), _NO_CONFIG), "text")
    assert text == "meta/b.md\timplemented\tmeta/b.md\tAbout meta/b.md.\n"


def test_format_list_text_empty() -> None:
    assert format_list([], "text") == ""


def test_format_list_json_roundtrip() -> None:
    items = json.loads(format_list(DocSet(DOCS).select(Filters(), _NO_CONFIG), "json"))
    assert [i["path"] for i in items] == ["architecture/a.md", "architecture/c.md", "meta/b.md"]
    assert set(items[0]) == {
        "path",
        "title",
        "summary",
        "layer",
        "status",
        "components",
        "tags",
        "milestone",
        "priority",
    }
    assert items[0]["components"] == ["core", "docs-system"]
    assert items[2]["milestone"] is None


def test_backlinks_kinds() -> None:
    docs = [
        make_doc("meta/target.md", "[self](#x) [self2](target.md)\n"),
        make_doc("meta/a.md", "See [t](target.md).\n", title="T meta/a.md", related=["meta/target.md"]),
        make_doc("old.md", status="redirect", redirect_to="meta/target.md", title="T old.md"),
        make_doc("guides/g.md", "[t](../meta/target.md#section)\n", title="T guides/g.md"),
        make_doc("guides/other.md", "[o](g.md)\n"),
    ]
    backlinks = DocSet(docs).backlinks_by_target.get("meta/target.md", ())
    assert [(b.doc.path, b.title, b.kinds) for b in backlinks] == [
        ("guides/g.md", "T guides/g.md", ("body",)),
        ("meta/a.md", "T meta/a.md", ("body", "related")),
        ("old.md", "T old.md", ("redirect_to",)),
    ]


def test_backlinks_excludes_self_links() -> None:
    docs = [make_doc("a.md", "[me](a.md) [anchor](#top)\n")]
    assert DocSet(docs).backlinks_by_target.get("a.md", ()) == ()


def test_resolve_doc_path(tmp_path: Path) -> None:
    (tmp_path / "docs" / "meta").mkdir(parents=True)
    (tmp_path / "docs" / "meta" / "x.md").write_text("x")
    for arg in ("docs/meta/x.md", "./docs/meta/x.md", "meta/x.md"):
        assert resolve_doc_path(tmp_path, arg) == "meta/x.md"
    assert resolve_doc_path(tmp_path, "meta/missing.md") is None
    assert resolve_doc_path(tmp_path, "meta") is None


def test_format_backlinks() -> None:
    links = [Backlink(make_doc("a.md", title="A"), ("body", "related"))]
    assert format_backlinks(links, "text") == "a.md\tbody,related\tA\n"
    assert json.loads(format_backlinks(links, "json")) == [
        {"source": "a.md", "title": "A", "kinds": ["body", "related"]}
    ]


def test_backlinks_via_directory_link() -> None:
    docs = [
        make_doc("index.md", "- [sub/](sub/) — Sub.\n", title="T index.md"),
        make_doc("sub/index.md"),
        make_doc("sub/a.md", "[up](..)\n", title="T sub/a.md"),
    ]
    assert DocSet(docs).backlinks_by_target.get("sub/index.md", ()) == (Backlink(docs[0], ("body",)),)
    assert DocSet(docs).backlinks_by_target.get("index.md", ()) == (Backlink(docs[2], ("body",)),)


def test_backlinks_of_every_doc() -> None:
    docs = DocSet(
        [
            make_doc("meta/a.md", "[i](../)\n"),
            make_doc("guides/g.md", "[x](../../compose.yaml)\n"),
            make_doc("index.md"),
            make_doc("sub/a.md", "[nowhere](missing.md)\n"),
        ]
    )
    expected: dict[str, tuple[Backlink, ...]] = {
        "meta/a.md": (),
        "guides/g.md": (),
        "index.md": (Backlink(docs.by_path["meta/a.md"], ("body",)),),
        "sub/a.md": (),
        "sub/missing.md": (Backlink(docs.by_path["sub/a.md"], ("body",)),),
    }
    assert {path: docs.backlinks_by_target.get(path, ()) for path in expected} == expected


def test_resolve_doc_path_absolute_and_outside_paths(tmp_path: Path) -> None:
    (tmp_path / "docs" / "meta").mkdir(parents=True)
    (tmp_path / "docs" / "meta" / "x.md").write_text("x")
    assert resolve_doc_path(tmp_path, str(tmp_path / "docs" / "meta" / "x.md")) == "meta/x.md"
    assert resolve_doc_path(tmp_path, str(tmp_path / "README.md")) is None
    assert resolve_doc_path(tmp_path, "../README.md") is None


@pytest.mark.parametrize(
    ("config", "expected_adrs"),
    [
        (
            ProjectConfig((), "", {}, adr_prefix="APP", external_adr_prefixes=("BASE", "PYRF")),
            ["BASE-0001-x.md", "BASE-0002-x.md", "PYRF-0001-x.md", "XYZ-0001-x.md", "APP-0001-x.md"],
        ),
        (
            ProjectConfig((), "", {}, adr_prefix="APP", external_adr_prefixes=("PYRF", "BASE")),
            ["PYRF-0001-x.md", "BASE-0001-x.md", "BASE-0002-x.md", "XYZ-0001-x.md", "APP-0001-x.md"],
        ),
        (
            ProjectConfig((), "", {}, adr_prefix="APP"),
            ["BASE-0001-x.md", "BASE-0002-x.md", "PYRF-0001-x.md", "XYZ-0001-x.md", "APP-0001-x.md"],
        ),
    ],
)
def test_select_lists_adrs_by_prefix_order(config: ProjectConfig, expected_adrs: list[str]) -> None:
    adrs = [
        make_doc("architecture/decisions/index.md"),
        make_doc("architecture/decisions/APP-0001-x.md"),
        make_doc("architecture/decisions/XYZ-0001-x.md"),
        make_doc("architecture/decisions/BASE-0002-x.md"),
        make_doc("architecture/decisions/PYRF-0001-x.md"),
        make_doc("architecture/decisions/BASE-0001-x.md"),
        make_doc("architecture/decisions-x.md"),
        make_doc("architecture/z.md"),
    ]
    assert [d.path for d in DocSet(adrs).select(Filters(), config)] == [
        "architecture/decisions-x.md",
        *(f"architecture/decisions/{name}" for name in expected_adrs),
        "architecture/decisions/index.md",
        "architecture/z.md",
    ]
