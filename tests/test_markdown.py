import pytest

from docspecsite.markdown import Entry, HtmlRenderer, Link, MarkdownText, RenderedLink

VOCABULARY = """# Vocabulary

## Components

| Component | Meaning |
|---|---|
| `docs-system` | Docs. |
| `agents` | Agents. |

### Notes

| Component | Meaning |
|---|---|
| `nested` | Still under Components. |

## Tags

| Tag | Use for |
|---|---|
| `overview` | Overviews. |
"""


def test_extract_links_inline_reference_and_autolink() -> None:
    text = "Intro [a](x.md#s) here.\nSecond line [b][r]\n\n<https://e.org>\n\n[r]: ../y.md\n"
    assert MarkdownText(text).extract_links() == [
        Link("x.md#s", 1),
        Link("../y.md", 2),
        Link("https://e.org", 4),
    ]


def test_extract_links_decodes_percent() -> None:
    assert MarkdownText("[a](my%20doc.md)\n").extract_links() == [Link("my doc.md", 1)]


def test_table_first_column_codes_section() -> None:
    assert MarkdownText(VOCABULARY).extract_table_first_column_codes("Components") == [
        "docs-system",
        "agents",
        "nested",
    ]


def test_table_first_column_codes_all_tables() -> None:
    assert MarkdownText(VOCABULARY).extract_table_first_column_codes() == [
        "docs-system",
        "agents",
        "nested",
        "overview",
    ]


def test_split_front_matter_with_block() -> None:
    text = "---\ntitle: X\nlayer: meta\n---\n\n# X\n"
    assert MarkdownText(text).split_front_matter() == ("title: X\nlayer: meta\n", 5)


def test_split_front_matter_without_block() -> None:
    assert MarkdownText("# X\n").split_front_matter() == (None, 1)


def test_list_entries() -> None:
    text = (
        "- [a.md](a.md) — Does A.\n"
        "- [b.md](b.md)\n"
        "\n"
        "| Id | Title |\n"
        "|---|---|\n"
        "| [0001](0001-x.md) | Title |\n"
        "\n"
        "A paragraph with [c](c.md).\n"
    )
    entries = MarkdownText(text).list_entries()
    assert [(e.targets, e.line_number) for e in entries] == [(("a.md",), 1), (("b.md",), 2)]
    assert entries[0].text == "— Does A."
    assert entries[1].text == ""
    assert isinstance(entries[0], Entry)


def test_list_entries_section() -> None:
    text = (
        "# T\n\n- [x.md](x.md) — before\n\n"
        "## Children\n\n- [a.md](a.md) — A.\n\n### Sub\n\n- [b.md](b.md) — B.\n\n"
        "## See also\n\n- [y.md](y.md) — after\n"
    )
    assert [e.targets for e in MarkdownText(text).list_entries("Children")] == [("a.md",), ("b.md",)]
    assert MarkdownText("# T\n\n- [x.md](x.md) — x\n").list_entries("Children") == []


def test_extract_links_includes_images() -> None:
    assert MarkdownText("See ![diagram](img/d.png).\n").extract_links() == [Link("img/d.png", 1)]


def test_render_unlinked_code_style() -> None:
    renderer = HtmlRenderer(lambda href: RenderedLink(None, use_code_style=True))
    plain = renderer.render("[place](code:x.y)")
    assert "<code>place</code>" in plain
    assert "<a" not in plain
    assert renderer.render("[`place`](code:x.y)").count("<code>") == 1


def test_role_rule_tokens() -> None:
    assert [link.target for link in MarkdownText(":py:meth:`.x`", use_roles=True).extract_links()] == ["role:.x"]
    assert [link.target for link in MarkdownText("a :class:`~p.C` b", use_roles=True).extract_links()] == ["role:~p.C"]
    assert [link.target for link in MarkdownText(":meth:``a`b``", use_roles=True).extract_links()] == ["role:a`b"]
    assert MarkdownText(":ref:`x`", use_roles=True).extract_links() == []
    assert MarkdownText(":py:meth:`.x`").extract_links() == []
    spanning = MarkdownText(":meth:`a\nb` then\n[c](d)", use_roles=True).extract_links()
    assert [link.line_number for link in spanning] == [1, 3]


@pytest.mark.parametrize(
    "text",
    ["```\n:meth:`x`\n```\n", "`` :meth:`x` ``", "\\:meth:`x`", ":ref:`x`", "[see :meth:`x`](u)", ":meth:`x"],
    ids=["fence", "code-span", "escaped", "other-role", "in-link", "unclosed"],
)
def test_role_rule_leaves_code_alone(text: str) -> None:
    def keep(href: str) -> RenderedLink:
        return RenderedLink(href)

    assert HtmlRenderer(keep, use_roles=True).render(text) == HtmlRenderer(keep).render(text)
