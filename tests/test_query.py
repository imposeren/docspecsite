import json
from pathlib import Path

import pytest
from conftest import make_doc

from docspecsite.config import ProjectConfig
from docspecsite.docs import Doc, DocStatus
from docspecsite.docset import DocSet
from docspecsite.query import (
    Backlink,
    Filters,
    format_backlinks,
    format_list,
    format_text_field,
    make_status_json_value,
    resolve_doc_path,
)

_NO_CONFIG = ProjectConfig((), "", {})

DOCS = [
    make_doc("meta/b.md", status="implemented", components=["docs-system"], tags=["rules"]),
    make_doc("architecture/a.md", components=["core", "docs-system"], milestone="foundation", priority="must"),
    make_doc("architecture/c.md", tags=["rules", "adr"], milestone="foundation", priority="should"),
    make_doc("guides/p.md", status=["implemented", "specified"]),
    make_doc("guides/q.md", status=["specified"]),
    Doc("meta/broken.md", None, "", 1, "no front matter"),
]


def select_paths(filters: Filters) -> list[str]:
    return [d.path for d in DocSet(DOCS).select(filters, _NO_CONFIG)]


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (Filters(), ["architecture/a.md", "architecture/c.md", "guides/p.md", "guides/q.md", "meta/b.md"]),
        (Filters(layer="meta"), ["meta/b.md"]),
        (Filters(status="specified"), ["architecture/a.md", "architecture/c.md", "guides/p.md", "guides/q.md"]),
        (Filters(status="implemented"), ["guides/p.md", "meta/b.md"]),
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
    assert [i["path"] for i in items] == [
        "architecture/a.md",
        "architecture/c.md",
        "guides/p.md",
        "guides/q.md",
        "meta/b.md",
    ]
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


def test_format_list_text_status_list() -> None:
    line = format_list([make_doc("guides/p.md", status=["implemented", "specified"])], "text")
    assert line.split("\t")[1] == "implemented,specified"


def test_format_list_text_status_with_tab_or_newline_stays_one_column() -> None:
    line = format_list([make_doc("guides/p.md", status=["imple\tmented", "speci\nfied"])], "text")
    assert line.count("\n") == 1
    assert line.split("\t")[1] == "imple mented,speci fied"


def test_format_list_text_status_of_wrong_shape_is_empty() -> None:
    assert format_list([make_doc("guides/d.md", status=5)], "text").split("\t")[1] == ""


def test_format_list_json_status_shapes() -> None:
    docs = [
        make_doc("a.md", status=["implemented", "specified"]),
        make_doc("b.md", status="implemented"),
        make_doc("c.md", status=["specified"]),
        make_doc("d.md", status=5),
    ]
    assert [i["status"] for i in json.loads(format_list(docs, "json"))] == [
        ["implemented", "specified"],
        "implemented",
        "specified",
        None,
    ]


def test_status_text_and_json_forms() -> None:
    one, two, none = DocStatus(("implemented",)), DocStatus(("implemented", "specified")), DocStatus(())
    assert [format_text_field(make_status_json_value(s)) for s in (one, two, none)] == [
        "implemented",
        "implemented,specified",
        "",
    ]
    assert [make_status_json_value(s) for s in (one, two, none)] == ["implemented", ["implemented", "specified"], None]


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


def test_resolve_doc_path_in_directory_whose_name_starts_with_two_dots(tmp_path: Path) -> None:
    (tmp_path / "docs" / "..notes").mkdir(parents=True)
    (tmp_path / "docs" / "..notes" / "x.md").write_text("x")
    assert resolve_doc_path(tmp_path, "..notes/x.md") == "..notes/x.md"


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


def test_resolve_doc_path_does_not_follow_links(tmp_path: Path) -> None:
    (tmp_path / "docs" / "meta" / "templates").mkdir(parents=True)
    (tmp_path / "docs" / "meta" / "x.md").write_text("x")
    (tmp_path / "docs" / "meta" / "templates" / "t.md").write_text("t")
    (tmp_path / "docs" / "alias.md").symlink_to("meta/x.md")
    (tmp_path / "docs" / "linked").symlink_to("meta")
    (tmp_path / "docs" / "meta" / "up").symlink_to("..")
    (tmp_path / "outside.md").write_text("o")
    assert resolve_doc_path(tmp_path, "docs/alias.md") is None
    assert resolve_doc_path(tmp_path, "linked/x.md") is None
    assert resolve_doc_path(tmp_path, "meta/templates/t.md") is None
    assert resolve_doc_path(tmp_path, "docs/meta/x.md") == "meta/x.md"
    assert resolve_doc_path(tmp_path, "meta/../meta/x.md") == "meta/x.md"
    # ".." is worked out on the text, so a directory symlink is not walked through it.
    assert resolve_doc_path(tmp_path, "meta/up/../x.md") == "meta/x.md"
    assert resolve_doc_path(tmp_path, "../outside.md") is None
    assert resolve_doc_path(tmp_path, str(tmp_path / "docs" / "alias.md")) is None


def test_resolve_doc_path_absolute_through_a_symlinked_parent_of_the_repo(tmp_path: Path) -> None:
    repo = tmp_path / "real" / "repo"
    (repo / "docs" / "meta").mkdir(parents=True)
    (repo / "docs" / "meta" / "x.md").write_text("x")
    (repo / "docs" / "alias.md").symlink_to("meta/x.md")
    (repo / "docs" / "root").symlink_to("..")
    (tmp_path / "link").symlink_to("real")
    linked_repo = tmp_path / "link" / "repo"
    assert resolve_doc_path(repo, str(linked_repo / "docs" / "meta" / "x.md")) == "meta/x.md"
    assert resolve_doc_path(linked_repo, str(repo / "docs" / "meta" / "x.md")) == "meta/x.md"
    # Below the repo root no link is followed.
    assert resolve_doc_path(repo, str(linked_repo / "docs" / "alias.md")) is None
    assert resolve_doc_path(repo, str(linked_repo / "docs" / "root" / "docs" / "meta" / "x.md")) is None
