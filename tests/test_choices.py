import pytest

from docspecsite.check import OptionalCheck
from docspecsite.parts import Part


def test_parse_list() -> None:
    assert Part.parse_list("docs,code") == {Part.DOCS, Part.CODE}
    assert Part.parse_list("code") == {Part.CODE}
    assert OptionalCheck.parse_list("code") == {OptionalCheck.CODE}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "no parts given (available: docs, code)"),
        ("docs, code", "unknown part: ' code' (available: docs, code)"),
        ("web", "unknown part: 'web' (available: docs, code)"),
        ("docs,,code", "unknown part: '' (available: docs, code)"),
    ],
)
def test_parse_list_rejects(text: str, message: str) -> None:
    with pytest.raises(ValueError) as exc:
        Part.parse_list(text)
    assert str(exc.value) == message
