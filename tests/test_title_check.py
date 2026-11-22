from pathlib import Path

import pytest
from conftest import make_doc, write_doc

from docspecsite.check import Checker, TitleCheck
from docspecsite.docs import Doc

_NOT_TITLE = "the doc does not start with its title heading"


def check_doc(body: str, **front_matter: object) -> list[tuple[int | None, str, str | None]]:
    """Check a doc ``import.md`` whose body starts on file line 8; return its problems as (line, message, hint)."""
    doc = make_doc("import.md", body, 8, title="Import", **front_matter)
    return [(p.line_number, p.message, p.hint) for p in TitleCheck().check(doc)]


@pytest.mark.parametrize("body", ["\n# Import\n\nText.\n", "\nImport\n===\n\nText.\n", "# Import\n"])
def test_title_right_after_front_matter_passes(body: str) -> None:
    assert check_doc(body) == []


def test_text_before_title() -> None:
    assert check_doc("\nSome text\n\n# Import\n") == [
        (9, _NOT_TITLE, 'move this text below "# Import", or remove it'),
    ]


def test_line_of_unicode_spaces_before_title_is_text() -> None:
    assert check_doc("\u00a0\n\n# Import\n") == [(8, _NOT_TITLE, 'move this text below "# Import", or remove it')]


@pytest.mark.parametrize("text", ["<!-- generated -->", "[ref]: https://example.com"])
def test_html_comment_or_link_definition_before_title_is_text(text: str) -> None:
    assert [line for line, _, _ in check_doc(f"\n{text}\n\n# Import\n")] == [9]


def test_text_before_setext_title_quotes_its_first_line() -> None:
    assert check_doc("Some text\n\nImport\n===\n") == [
        (8, _NOT_TITLE, 'move this text below "Import", or remove it'),
    ]


def test_doc_without_title_offers_front_matter_title() -> None:
    assert check_doc("\n## Details\n") == [
        (9, _NOT_TITLE, 'add the title "# Import" right after the front matter'),
    ]


def test_doc_without_title_offers_multi_line_front_matter_title_on_one_line() -> None:
    doc = make_doc("import.md", "\n## Details\n", 8, title="Import\n  data")
    assert [p.hint for p in TitleCheck().check(doc)] == ['add the title "# Import data" right after the front matter']


def test_doc_without_title_or_front_matter_title() -> None:
    doc = make_doc("import.md", "\n## Details\n", 8, title=None)
    assert [(p.line_number, p.hint) for p in TitleCheck().check(doc)] == [
        (9, 'add a "#" title heading right after the front matter'),
    ]


@pytest.mark.parametrize("body", ["", "\n\n"])
def test_empty_doc_has_no_title_on_first_line(body: str) -> None:
    assert check_doc(body) == [(1, _NOT_TITLE, 'add the title "# Import" right after the front matter')]


@pytest.mark.parametrize(
    ("heading", "quoted"),
    [("# Export", "# Export"), ("Export\n===", "Export"), ("# Export `x` [y](z.md) #", "# Export `x` [y](z.md) #")],
)
def test_second_level_one_heading(heading: str, quoted: str) -> None:
    content = quoted.removeprefix("# ").removesuffix(" #")
    assert check_doc(f"# Import\n\n{heading}\n") == [
        (10, f'"{quoted}" is a second level-1 heading; a doc has one, its title', f'write it as "## {content}"'),
    ]


def test_empty_second_level_one_heading() -> None:
    assert check_doc("# Import\n\n#\n") == [
        (10, '"#" is a second level-1 heading; a doc has one, its title', 'make it a "##" heading or remove it'),
    ]


def test_level_one_headings_in_quotes_lists_and_code_blocks_are_not_headings() -> None:
    assert check_doc("# Import\n\n> # Example\n\n- # Item\n\n```\n# x\n```\n") == []


def test_first_level_one_heading_is_title_even_after_text() -> None:
    assert [line for line, _, _ in check_doc("Some text\n\n# Import\n\n# Export\n")] == [8, 12]


def test_title_is_not_checked_when_front_matter_does_not_load() -> None:
    assert TitleCheck().check(Doc.parse("import.md", "---\n[\n---\n\nText.\n")) == []
    assert TitleCheck().check(Doc.parse("import.md", "Text.\n")) == []


def test_run_checks_titles(docs_tree: Path) -> None:
    write_doc(docs_tree, "meta/s.md", "Some text\n\n# S\n\n> **Not built yet.**\n", status="implemented")
    problems = [
        (p.line_number, p.message) for p in Checker(docs_tree).run(include_staged=False) if p.path == "meta/s.md"
    ]
    assert problems == [
        (11, _NOT_TITLE),
        (15, 'status note "Not built yet." ("specified") right under the doc\'s title "# S"'),
    ]


def test_run_skips_title_check_when_front_matter_does_not_load(docs_tree: Path) -> None:
    (docs_tree / "docs" / "meta" / "bad.md").write_text("---\n[\n---\n\nText.\n")
    messages = [p.message for p in Checker(docs_tree).run(include_staged=False) if p.path == "meta/bad.md"]
    assert len(messages) == 1
    assert messages[0].startswith("front matter is not valid YAML")
