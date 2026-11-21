from docspecsite.markdown import Entry, Link, MarkdownText

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
