import docspecsite
from docspecsite.errors import DocspecsiteError, DocspecsiteWarning, InternalErrorWarning


def test_str_fills_values_into_message() -> None:
    error = DocspecsiteError("%s is not a blob (%d)", "abc", 3)
    assert str(error) == "abc is not a blob (3)"
    assert error.message == "%s is not a blob (%d)"
    assert error.values == ("abc", 3)


def test_str_without_values_is_message() -> None:
    assert str(DocspecsiteError("100% static")) == "100% static"


def test_warning_categories_are_exported_with_filled_messages() -> None:
    assert docspecsite.DocspecsiteWarning is DocspecsiteWarning
    assert docspecsite.InternalErrorWarning is InternalErrorWarning
    assert issubclass(DocspecsiteWarning, UserWarning)
    assert issubclass(InternalErrorWarning, RuntimeWarning)
    assert str(DocspecsiteWarning("%s: unresolvable link", "a.md")) == "a.md: unresolvable link"
    assert str(InternalErrorWarning("100% internal")) == "100% internal"
