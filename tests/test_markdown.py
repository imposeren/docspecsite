from docspecsite.markdown import (
    Entry,
    Link,
    extract_links,
    extract_table_first_column_codes,
    list_entries,
    split_front_matter,
)

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
    assert extract_links(text) == [
        Link("x.md#s", 1),
        Link("../y.md", 2),
        Link("https://e.org", 4),
    ]


def test_extract_links_decodes_percent() -> None:
    assert extract_links("[a](my%20doc.md)\n") == [Link("my doc.md", 1)]


def test_table_first_column_codes_section() -> None:
    assert extract_table_first_column_codes(VOCABULARY, "Components") == [
        "docs-system",
        "agents",
        "nested",
    ]


def test_table_first_column_codes_all_tables() -> None:
    assert extract_table_first_column_codes(VOCABULARY) == [
        "docs-system",
        "agents",
        "nested",
        "overview",
    ]


def test_split_front_matter_with_block() -> None:
    text = "---\ntitle: X\nlayer: meta\n---\n\n# X\n"
    assert split_front_matter(text) == ("title: X\nlayer: meta\n", 5)


def test_split_front_matter_without_block() -> None:
    assert split_front_matter("# X\n") == (None, 1)


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
    entries = list_entries(text)
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
    assert [e.targets for e in list_entries(text, "Children")] == [("a.md",), ("b.md",)]
    assert list_entries("# T\n\n- [x.md](x.md) — x\n", "Children") == []


def test_extract_links_includes_images() -> None:
    assert extract_links("See ![diagram](img/d.png).\n") == [Link("img/d.png", 1)]
