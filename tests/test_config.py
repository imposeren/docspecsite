import os
from pathlib import Path

import pytest

from docspecsite.config import ConfigError, ProjectConfig, ProjectConfigParser
from docspecsite.errors import DocspecsiteWarning
from docspecsite.schema import STATUS_NOTES

_STATUS_NOTE_TEXT_MESSAGE = (
    '"status-notes" text of "specified" must be non-empty text without leading or trailing spaces'
)


def test_from_bytes_reads_every_setting() -> None:
    text = """
adr-prefix = "DSS"
external-adr-prefixes = ["BASE", "PYRF"]
source-url = "https://example.org/r"
code-dirs = ["src", "services/*/src"]
toc-min-headings = 3

[code-components]
docspecsite = ["docs-system"]

[status-notes]
specified = "Ще не зроблено."
"""
    assert ProjectConfig.from_bytes(text.encode()) == ProjectConfig(
        code_dirs=("src", "services/*/src"),
        source_url="https://example.org/r",
        code_components={"docspecsite": ("docs-system",)},
        adr_prefix="DSS",
        external_adr_prefixes=("BASE", "PYRF"),
        toc_min_headings=3,
        status_notes={"Ще не зроблено.": "specified", "Changed, not built yet.": "changed", "Built.": "implemented"},
    )


def test_status_notes_replace_the_defaults_they_set() -> None:
    config = ProjectConfig.from_bytes('[status-notes]\nspecified = "Ще не зроблено."\n'.encode())
    assert config.status_notes == {
        "Ще не зроблено.": "specified",
        "Changed, not built yet.": "changed",
        "Built.": "implemented",
    }
    assert ProjectConfig.from_bytes(None).status_notes == STATUS_NOTES


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('status-notes = "x"', '"status-notes" must be a table of status note texts by status'),
        ('[status-notes]\ndone = "X."', '"status-notes" has an unknown status: "done"'),
        ('[status-notes]\nspecified = ""', _STATUS_NOTE_TEXT_MESSAGE),
        ('[status-notes]\nspecified = " X."', _STATUS_NOTE_TEXT_MESSAGE),
        ("[status-notes]\nspecified = 5", _STATUS_NOTE_TEXT_MESSAGE),
        (
            '[status-notes]\nspecified = "Built."',
            '"status-notes" gives "implemented" and "specified" the same text: "Built."',
        ),
    ],
)
def test_invalid_status_notes_keep_the_defaults(text: str, expected: str) -> None:
    config = ProjectConfig.from_bytes(text.encode())
    assert config.invalid_values == (expected,)
    assert config.status_notes == STATUS_NOTES


def test_every_invalid_status_note_is_reported_and_valid_texts_next_to_them_are_discarded() -> None:
    config = ProjectConfig.from_bytes(b'[status-notes]\nspecified = ""\nchanged = "Redo."\ndone = "X."\n')
    assert config.invalid_values == (
        _STATUS_NOTE_TEXT_MESSAGE,
        '"status-notes" has an unknown status: "done"',
    )
    assert config.status_notes == STATUS_NOTES


def test_from_bytes_defaults() -> None:
    expected = ProjectConfig((), "", {})
    assert ProjectConfig.from_bytes(None) == expected
    assert ProjectConfig.from_bytes(b"# no settings\n") == expected


def test_adr_prefixes() -> None:
    config = ProjectConfig.from_bytes(b'adr-prefix = "APP"\nexternal-adr-prefixes = ["BASE", "PYRF"]\n')
    assert config.adr_prefixes == ("BASE", "PYRF", "APP")
    assert ProjectConfig((), "", {}).adr_prefixes == ()
    assert ProjectConfig((), "", {}, adr_prefix="DSS").adr_prefixes == ("DSS",)
    assert ProjectConfig((), "", {}, external_adr_prefixes=("BASE",)).adr_prefixes == ("BASE",)


@pytest.mark.parametrize("value", ['"BASE"', "{ BASE = 1 }", "3"])
def test_external_adr_prefixes_must_be_a_list(value: str) -> None:
    config = ProjectConfig.from_bytes(f"external-adr-prefixes = {value}\n".encode())
    assert config.external_adr_prefixes == ()
    assert config.problems == ('"external-adr-prefixes" must be a list of capital-letter prefixes',)


def test_invalid_external_adr_prefixes_are_reported_and_left_out() -> None:
    config = ProjectConfig.from_bytes(
        b'adr-prefix = "APP"\nexternal-adr-prefixes = ["BASE", "pyrf", "APP", 3, "PYRF", "BASE"]\n'
    )
    assert config.external_adr_prefixes == ("BASE", "PYRF")
    assert config.problems == (
        '"external-adr-prefixes" entries must be capital letters only, e.g. "BASE": "pyrf"',
        '"external-adr-prefixes" must not list "adr-prefix": "APP"',
        '"external-adr-prefixes" entries must be capital letters only, e.g. "BASE": "3"',
        '"external-adr-prefixes" lists a prefix twice: "BASE"',
    )


@pytest.mark.parametrize("value", ['"dss"', '"D-S"', '""', "3", '"BASE1"', '"DSS\\n"'])
def test_invalid_adr_prefix_is_reported(value: str) -> None:
    config = ProjectConfig.from_bytes(f"adr-prefix = {value}\n".encode())
    assert config.adr_prefix == ""
    assert config.problems == ('"adr-prefix" must be capital letters only, e.g. "APP"',)


def test_unknown_setting_is_reported() -> None:
    config = ProjectConfig.from_bytes(b'adr_prefix = "DSS"\n')
    assert config.adr_prefix == ""
    assert config.problems == ('unknown setting "adr_prefix"',)
    assert config.unknown_settings == ('unknown setting "adr_prefix"',)
    assert config.invalid_values == ()


def test_problems_list_unknown_settings_before_invalid_values() -> None:
    config = ProjectConfig.from_bytes(b'source-url = 3\nadr_prefix = "DSS"\n')
    assert config.unknown_settings == ('unknown setting "adr_prefix"',)
    assert config.invalid_values == ('"source-url" must be a string',)
    assert config.problems == ('unknown setting "adr_prefix"', '"source-url" must be a string')


def test_parser_reports_problems_once_per_parse() -> None:
    parser = ProjectConfigParser({"adr_prefix": "DSS", "source-url": 3})
    parser.parse()
    config = parser.parse()
    assert config.unknown_settings == ('unknown setting "adr_prefix"',)
    assert config.invalid_values == ('"source-url" must be a string',)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('code-dirs = "src"', '"code-dirs" must be a list of strings'),
        ("code-dirs = [1]", '"code-dirs" must be a list of strings'),
        ('code-components = ["x"]', '"code-components" must be a table of lists of strings'),
        ('[code-components]\nx = "core"', '"code-components" must be a table of lists of strings'),
        ("[code-components]\nx = [1]", '"code-components" must be a table of lists of strings'),
        ("source-url = 3", '"source-url" must be a string'),
        ("toc-min-headings = -1", '"toc-min-headings" must be a whole number of 0 or more'),
        ('toc-min-headings = "x"', '"toc-min-headings" must be a whole number of 0 or more'),
        ("toc-min-headings = true", '"toc-min-headings" must be a whole number of 0 or more'),
    ],
)
def test_wrong_value_types_are_reported(text: str, expected: str) -> None:
    config = ProjectConfig.from_bytes(f"{text}\n".encode())
    assert config.problems == (expected,)
    assert config == ProjectConfig((), "", {}, invalid_values=(expected,))


@pytest.mark.parametrize("entry", ["/abs/src", "../src", "a/../src", ""])
def test_code_dirs_outside_the_repo_are_reported(entry: str) -> None:
    config = ProjectConfig.from_bytes(f'code-dirs = ["src", "{entry}"]\n'.encode())
    assert config.code_dirs == ("src",)
    assert config.problems == (
        f'"code-dirs" entries must be paths inside the repo, without ".." or a leading "/": "{entry}"',
    )


def test_code_dirs_are_normalized() -> None:
    assert ProjectConfig.from_bytes(b'code-dirs = ["./src", "./", ".", "a/*/src/"]\n').code_dirs == (
        "src",
        ".",
        ".",
        "a/*/src",
    )


@pytest.mark.parametrize(
    ("directory", "expected"),
    [(".", True), ("src", False), ("a/src", False)],
)
def test_is_code_dir_root(directory: str, expected: bool) -> None:
    assert ProjectConfig((".",), "", {}).is_code_dir(directory) is expected


@pytest.mark.parametrize(
    ("directory", "expected"),
    [(".", False), ("src", False), ("tools/a/src", True), ("tools/a/b/src", False)],
)
def test_is_code_dir_glob(directory: str, expected: bool) -> None:
    assert ProjectConfig(("tools/*/src",), "", {}).is_code_dir(directory) is expected


def test_find_components() -> None:
    config = ProjectConfig((), "", {"docspecsite": ("docs-system",), "docspecsite.cli": ("x",)})
    assert config.find_components("docspecsite.cli.main") == ("x",)
    assert config.find_components("docspecsite.check") == ("docs-system",)
    assert config.find_components("docspecsite") == ("docs-system",)
    assert config.find_components("docspecsitex") == ()


def test_toc_min_headings_values() -> None:
    def parse_toc_min(toc_min_headings: str) -> int:
        return ProjectConfig.from_bytes(f"toc-min-headings = {toc_min_headings}\n".encode()).toc_min_headings

    assert parse_toc_min("0") == 0
    assert parse_toc_min("7") == 7
    assert parse_toc_min("-1") == 5
    assert parse_toc_min('"x"') == 5
    assert parse_toc_min("true") == 5
    assert parse_toc_min("2.5") == 5
    assert ProjectConfig.from_bytes(None).toc_min_headings == 5


@pytest.mark.parametrize("newline", [b"\r\n", b"\r"])
def test_from_bytes_accepts_any_line_ending(newline: bytes) -> None:
    data = newline.join([b'adr-prefix = "APP"', b'source-url = "https://example.org/r"', b""])
    config = ProjectConfig.from_bytes(data)
    assert (config.adr_prefix, config.source_url) == ("APP", "https://example.org/r")


@pytest.mark.parametrize(("data", "detail"), [(b'source-url = "\xff"\n', "utf-8"), (b"[code-components\n", "")])
def test_from_bytes_records_invalid_toml(data: bytes, detail: str) -> None:
    config = ProjectConfig.from_bytes(data)
    assert config.read_error.startswith("not valid TOML: ")
    assert detail in config.read_error
    assert config.problems == (config.read_error,)
    assert config == ProjectConfig((), "", {}, read_error=config.read_error)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"[code-components\n", r"^docspecsite\.toml: not valid TOML: "),
        (b"source-url = 3\n", r'^docspecsite\.toml: "source-url" must be a string$'),
    ],
)
def test_require_valid_rejects_a_bad_file(data: bytes, expected: str) -> None:
    with pytest.raises(ConfigError, match=expected):
        ProjectConfig.from_bytes(data).require_valid()


def test_require_valid_warns_about_unknown_settings() -> None:
    config = ProjectConfig.from_bytes(b'adr_prefix = "DSS"\n')
    with pytest.warns(DocspecsiteWarning, match=r"^docspecsite\.toml: "):
        assert config.require_valid() is config


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_load_records_an_unreadable_file(tmp_path: Path) -> None:
    config_file = tmp_path / ProjectConfig.CONFIG_FILE
    config_file.write_text('adr-prefix = "APP"\n', encoding="utf-8")
    config_file.chmod(0)
    config = ProjectConfig.load(tmp_path)
    assert config.read_error.startswith("cannot be read: ")
    assert config.adr_prefix == ""
    with pytest.raises(ConfigError, match=r"^docspecsite\.toml: cannot be read: "):
        config.require_valid()


def test_source_url_without_trailing_slash() -> None:
    assert ProjectConfig.from_bytes(b'source-url = "https://example.org/r/"\n').source_url == "https://example.org/r"
