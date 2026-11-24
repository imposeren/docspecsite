from pathlib import Path

from docspecsite.docset import DocSet


def test_load_paths_and_front_matter(docs_tree: Path) -> None:
    doc_set = DocSet.load(docs_tree)
    assert [d.path for d in doc_set] == [
        "architecture/components.md",
        "architecture/index.md",
        "index.md",
        "meta/index.md",
        "meta/vocabulary.md",
        "roadmap.md",
    ]
    front_matter = doc_set.by_path["meta/vocabulary.md"].front_matter
    assert front_matter is not None and front_matter["layer"] == "meta"
    assert doc_set.by_path["meta/vocabulary.md"].body.lstrip().startswith("# Vocabulary")
    assert all(d.error is None for d in doc_set)


def test_load_body_line(docs_tree: Path) -> None:
    (docs_tree / "docs" / "x.md").write_text("---\ntitle: X\n---\n\n# X\n")
    doc = DocSet.load(docs_tree).by_path["x.md"]
    assert doc.body_line == 4
    assert doc.body.splitlines()[1] == "# X"


def test_load_reports_bad_front_matter(docs_tree: Path) -> None:
    docs_dir = docs_tree / "docs"
    (docs_dir / "none.md").write_text("# No front matter\n")
    (docs_dir / "broken.md").write_text("---\ntitle: [\n---\n")
    (docs_dir / "list.md").write_text("---\n- a\n---\n")
    errors = {d.path: d.error for d in DocSet.load(docs_tree) if d.error}
    assert errors["none.md"] == "no front matter"
    assert errors["broken.md"] is not None
    assert errors["broken.md"].startswith("front matter is not valid YAML: ")
    assert errors["list.md"] == "front matter is not a mapping"
    assert all(d.front_matter is None for d in DocSet.load(docs_tree) if d.error)


def test_load_accepts_bom_and_crlf(docs_tree: Path) -> None:
    raw = "﻿---\r\ntitle: X\r\n---\r\n\r\n# X\r\n".encode()
    (docs_tree / "docs" / "crlf.md").write_bytes(raw)
    doc = DocSet.load(docs_tree).by_path["crlf.md"]
    assert doc.error is None and doc.front_matter == {"title": "X"}


def test_load_reports_impossible_date(docs_tree: Path) -> None:
    (docs_tree / "docs" / "bad-date.md").write_text("---\ntitle: X\ndate: 2026-02-31\n---\n")
    doc = DocSet.load(docs_tree).by_path["bad-date.md"]
    assert doc.front_matter is None
    assert doc.error is not None and doc.error.startswith("front matter is not valid YAML: ")


def test_front_matter_with_line_separator_keeps_body(docs_tree: Path) -> None:
    # U+2028 and U+0085 are valid in YAML and split lines for str.splitlines, but not for Markdown.
    text = '---\ntitle: "A\u2028B\u0085C"\n---\n\n# X\n\nText.\n'
    (docs_tree / "docs" / "sep.md").write_text(text, encoding="utf-8")
    doc = DocSet.load(docs_tree).by_path["sep.md"]
    assert doc.error is None
    assert doc.body_line == 4
    assert doc.body == "\n# X\n\nText.\n"
    assert doc.get_file_line_number(2) == 5


def test_docset_skips_symlinks_and_symlinked_dirs(docs_tree: Path) -> None:
    (docs_tree / "docs/alias.md").symlink_to("roadmap.md")
    (docs_tree / "docs/linked").symlink_to("meta")
    (docs_tree / "docs/dangling.md").symlink_to("nowhere.md")
    paths = [d.path for d in DocSet.load(docs_tree)]
    assert paths == [
        "architecture/components.md",
        "architecture/index.md",
        "index.md",
        "meta/index.md",
        "meta/vocabulary.md",
        "roadmap.md",
    ]
