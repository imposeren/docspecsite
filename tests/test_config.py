import os
from pathlib import Path

import pytest

from docspecsite.config import CONFIG_FILE, ConfigError, ProjectConfig, ProjectConfigParser


def test_from_text() -> None:
    text = """
adr-prefix = "DSS"
external-adr-prefixes = ["BASE", "PYRF"]
source-url = "https://example.org/r"
code-dirs = ["src", "services/*/src"]
toc-min-headings = 3

[code-components]
docspecsite = ["docs-system"]
"""
    assert ProjectConfig.from_text(text) == ProjectConfig(
        code_dirs=("src", "services/*/src"),
        source_url="https://example.org/r",
        code_components={"docspecsite": ("docs-system",)},
        adr_prefix="DSS",
        external_adr_prefixes=("BASE", "PYRF"),
        toc_min_headings=3,
    )


def test_from_text_defaults() -> None:
    expected = ProjectConfig((), "", {})
    assert ProjectConfig.from_text(None) == expected
    assert ProjectConfig.from_text("# no settings\n") == expected


def test_adr_prefixes() -> None:
    config = ProjectConfig.from_text('adr-prefix = "APP"\nexternal-adr-prefixes = ["BASE", "PYRF"]\n')
    assert config.adr_prefixes == ("BASE", "PYRF", "APP")
    assert ProjectConfig((), "", {}).adr_prefixes == ()
    assert ProjectConfig((), "", {}, adr_prefix="DSS").adr_prefixes == ("DSS",)
    assert ProjectConfig((), "", {}, external_adr_prefixes=("BASE",)).adr_prefixes == ("BASE",)


@pytest.mark.parametrize("value", ['"BASE"', "{ BASE = 1 }", "3"])
def test_external_adr_prefixes_must_be_a_list(value: str) -> None:
    config = ProjectConfig.from_text(f"external-adr-prefixes = {value}\n")
    assert config.external_adr_prefixes == ()
    assert config.problems == ('"external-adr-prefixes" must be a list of capital-letter prefixes',)


def test_invalid_external_adr_prefixes_are_reported_and_left_out() -> None:
    config = ProjectConfig.from_text(
        'adr-prefix = "APP"\nexternal-adr-prefixes = ["BASE", "pyrf", "APP", 3, "PYRF", "BASE"]\n'
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
    config = ProjectConfig.from_text(f"adr-prefix = {value}\n")
    assert config.adr_prefix == ""
    assert config.problems == ('"adr-prefix" must be capital letters only, e.g. "APP"',)


def test_unknown_setting_is_reported() -> None:
    config = ProjectConfig.from_text('adr_prefix = "DSS"\n')
    assert config.adr_prefix == ""
    assert config.problems == ('unknown setting "adr_prefix"',)
    assert config.unknown_settings == ('unknown setting "adr_prefix"',)
    assert config.invalid_values == ()


def test_problems_list_unknown_settings_before_invalid_values() -> None:
    config = ProjectConfig.from_text('source-url = 3\nadr_prefix = "DSS"\n')
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
    config = ProjectConfig.from_text(text + "\n")
    assert config.problems == (expected,)
    assert config == ProjectConfig((), "", {}, invalid_values=(expected,))


@pytest.mark.parametrize("entry", ["/abs/src", "../src", "a/../src", ""])
def test_code_dirs_outside_the_repo_are_reported(entry: str) -> None:
    config = ProjectConfig.from_text(f'code-dirs = ["src", "{entry}"]\n')
    assert config.code_dirs == ("src",)
    assert config.problems == (
        f'"code-dirs" entries must be paths inside the repo, without ".." or a leading "/": "{entry}"',
    )


def test_code_dirs_are_normalized() -> None:
    assert ProjectConfig.from_text('code-dirs = ["./src", "./", ".", "a/*/src/"]\n').code_dirs == (
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


def test_get_components() -> None:
    config = ProjectConfig((), "", {"docspecsite": ("docs-system",), "docspecsite.cli": ("x",)})
    assert config.get_components("docspecsite.cli.main") == ("x",)
    assert config.get_components("docspecsite.check") == ("docs-system",)
    assert config.get_components("docspecsite") == ("docs-system",)
    assert config.get_components("docspecsitex") == ()


def test_toc_min_headings_values() -> None:
    def parse_toc_min(toc_min_headings: str) -> int:
        return ProjectConfig.from_text(f"toc-min-headings = {toc_min_headings}\n").toc_min_headings

    assert parse_toc_min("0") == 0
    assert parse_toc_min("7") == 7
    assert parse_toc_min("-1") == 5
    assert parse_toc_min('"x"') == 5
    assert parse_toc_min("true") == 5
    assert parse_toc_min("2.5") == 5
    assert ProjectConfig.from_text(None).toc_min_headings == 5


@pytest.mark.parametrize("newline", [b"\r\n", b"\r"])
def test_from_bytes_accepts_any_line_ending(newline: bytes) -> None:
    data = newline.join([b'adr-prefix = "APP"', b'source-url = "https://example.org/r"', b""])
    config = ProjectConfig.from_bytes(data)
    assert (config.adr_prefix, config.source_url) == ("APP", "https://example.org/r")


def test_from_valid_bytes_rejects_invalid_utf8() -> None:
    with pytest.raises(ConfigError, match=r"^docspecsite\.toml is not valid TOML: .*utf-8"):
        ProjectConfig.from_valid_bytes(b'source-url = "\xff"\n')


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_read_file_reports_an_unreadable_file(tmp_path: Path) -> None:
    config_file = tmp_path / CONFIG_FILE
    config_file.write_text('adr-prefix = "APP"\n', encoding="utf-8")
    config_file.chmod(0)
    with pytest.raises(ConfigError, match=r"^docspecsite\.toml cannot be read: "):
        ProjectConfig.read_file(tmp_path)
