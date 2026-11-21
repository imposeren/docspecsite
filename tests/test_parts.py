import pytest

from docspecsite.parts import Part, parse_parts


def test_parse_parts() -> None:
    assert parse_parts("docs,code") == {Part.DOCS, Part.CODE}
    assert parse_parts("code") == {Part.CODE}


@pytest.mark.parametrize("text", ["", "docs, code", "web", "docs,,code"])
def test_parse_parts_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        parse_parts(text)
