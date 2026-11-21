from pathlib import Path

from docspecsite.vocabulary import Vocabulary


def test_load_vocabulary(docs_tree: Path) -> None:
    vocab = Vocabulary.load(docs_tree)
    assert vocab.components == {"docs-system", "agents", "core", "storage/files"}
    assert vocab.milestones == ("foundation", "first-release")


def test_load_vocabulary_without_project_components(docs_tree: Path) -> None:
    (docs_tree / "docs" / "architecture" / "components.md").unlink()
    assert Vocabulary.load(docs_tree).components == {"docs-system", "agents"}


def test_parse_vocabulary_from_reader(docs_tree: Path) -> None:
    def read(path: str) -> str | None:
        file = docs_tree / "docs" / path
        return file.read_text(encoding="utf-8") if file.is_file() else None

    assert Vocabulary.parse(read) == Vocabulary.load(docs_tree)
    assert Vocabulary.parse(lambda _: None) == Vocabulary(frozenset(), ())
