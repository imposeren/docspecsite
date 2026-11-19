from pathlib import Path

from docspecsite.vocabulary import Vocabulary, load_vocabulary, parse_vocabulary


def test_load_vocabulary(docs_tree: Path) -> None:
    vocab = load_vocabulary(docs_tree)
    assert vocab.components == {"docs-system", "agents", "core", "storage/files"}
    assert vocab.milestones == ("foundation", "first-release")


def test_load_vocabulary_without_project_components(docs_tree: Path) -> None:
    (docs_tree / "docs" / "architecture" / "components.md").unlink()
    assert load_vocabulary(docs_tree).components == {"docs-system", "agents"}


def test_parse_vocabulary_from_reader(docs_tree: Path) -> None:
    def read(path: str) -> str | None:
        file = docs_tree / "docs" / path
        return file.read_text(encoding="utf-8") if file.is_file() else None

    assert parse_vocabulary(read) == load_vocabulary(docs_tree)
    assert parse_vocabulary(lambda _: None) == Vocabulary(frozenset(), ())
