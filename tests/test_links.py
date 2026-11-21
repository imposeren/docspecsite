from conftest import make_doc

from docspecsite.links import CodeRef, DocLinks, Ref


def test_outgoing_refs_resolution() -> None:
    d = make_doc(
        "architecture/x.md",
        "[a](../meta/index.md#rules) [b](#local)\n[c](../../compose.yaml) [d](sub/)\n",
        10,
        related=["meta/linking.md"],
        redirect_to=["a.md", "b.md"],
        superseded_by="architecture/decisions/0002-y.md",
    )
    refs, problems = DocLinks(d).collect_outgoing_refs()
    assert problems == []
    assert refs == [
        Ref("docs/meta/index.md", "body", 10, "rules"),
        Ref("docs/architecture/x.md", "body", 10, "local"),
        Ref("compose.yaml", "body", 11, None),
        Ref("docs/architecture/sub", "body", 11, None),
        Ref("docs/meta/linking.md", "related", 1, None),
        Ref("docs/a.md", "redirect_to", 1, None),
        Ref("docs/b.md", "redirect_to", 1, None),
        Ref("docs/architecture/decisions/0002-y.md", "superseded_by", 1, None),
    ]


def test_outgoing_refs_skips_web_links() -> None:
    d = make_doc("x.md", "[a](https://e.org) [b](http://e.org) [c](mailto:a@e.org)\n", 10)
    assert DocLinks(d).collect_outgoing_refs() == ([], [])


def test_outgoing_refs_code_and_unknown_scheme() -> None:
    d = make_doc("x.md", "[a](code:m.f)\n[b](web-api:create_order)\n[c](ftp://e.org/x)\n[d](HTTP://E.org)\n", 10)
    refs, problems = DocLinks(d).collect_outgoing_refs()
    assert refs == []
    assert [(p.line_number, p.message.split(" ")[0]) for p in problems] == [
        (11, "web-api:"),
        (12, "unsupported"),
    ]
    assert "no API schema" in problems[0].message


def test_outgoing_refs_outside_repo_and_absolute() -> None:
    d = make_doc("x.md", "[a](../../etc/passwd) [b](/docs/x.md)\n", 10)
    refs, problems = DocLinks(d).collect_outgoing_refs()
    assert refs == []
    assert "outside the repository" in problems[0].message
    assert "relative" in problems[1].message


def test_outgoing_refs_ignores_query_and_non_string_front_matter() -> None:
    d = make_doc("x.md", "[a](y.md?plain=1#z)\n", 10, related=[3], redirect_to=None)
    refs, _ = DocLinks(d).collect_outgoing_refs()
    assert refs == [Ref("docs/y.md", "body", 10, "z")]


def test_outgoing_refs_empty_target() -> None:
    refs, problems = DocLinks(make_doc("x.md", "[e]() [h](#)\n", 10)).collect_outgoing_refs()
    assert refs == []
    assert [p.message for p in problems] == ["empty link target", "empty link target"]


def test_code_refs() -> None:
    d = make_doc("x.md", "[a](code:m.f) [w](https://e.org) [r](y.md)\n", 10, code=["m", "m.C"])
    assert DocLinks(d).collect_code_refs() == [
        CodeRef("m.f", "body", 10),
        CodeRef("m", "code", 1),
        CodeRef("m.C", "code", 1),
    ]
    refs, problems = DocLinks(d).collect_outgoing_refs()
    assert [r.target for r in refs] == ["docs/y.md"]
    assert problems == []
    _, problems = DocLinks(make_doc("x.md", "[e](code:)\n", 10)).collect_outgoing_refs()
    assert [p.message for p in problems] == ["empty code: target"]
