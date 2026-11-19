"""Project settings read from ``docspecsite.toml`` at the root of the checked repository.

Docs: behavior/configuration.md
Docs: architecture/docs-tooling.md#adr-ids
"""

import re
import tomllib
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .errors import DocspecsiteError, DocspecsiteWarning
from .schema import ADR_DIR, ADR_NAME

ADR_PREFIX = re.compile(r"[A-Z]+")
SETTINGS = (
    "adr-prefix",
    "external-adr-prefixes",
    "source-url",
    "code-dirs",
    "code-components",
    "toc-min-headings",
)

CONFIG_FILE = "docspecsite.toml"
DEFAULT_TOC_MIN = 5


class ConfigError(DocspecsiteError):
    """Error for a ``docspecsite.toml`` that cannot be used: not valid TOML, or with an invalid value of a setting."""


@dataclass(frozen=True)
class ProjectConfig:
    """Docspecsite settings read from the project's ``docspecsite.toml``."""

    code_dirs: tuple[str, ...]
    """Globs of the directories holding the Python packages (``code-dirs``), relative to the repository root."""
    source_url: str
    """Base URL of the repository host (``source-url``); empty when unset."""
    code_components: Mapping[str, tuple[str, ...]]
    """Component ids by dotted-name prefix (``[code-components]``)."""
    adr_prefix: str = ""
    """The repository's own ADR prefix (``adr-prefix``); empty when unset, so only external ADRs are valid."""
    external_adr_prefixes: tuple[str, ...] = ()
    """Prefixes of ADRs taken from elsewhere (``external-adr-prefixes``), in the order listings show them."""
    toc_min_headings: int = DEFAULT_TOC_MIN
    """Number of ``##`` sections from which a doc gets a Contents list; 0 turns it off (``toc-min-headings``)."""
    unknown_settings: tuple[str, ...] = ()
    """Messages about settings docspecsite does not know; they are ignored."""
    invalid_values: tuple[str, ...] = ()
    """Messages about settings with an invalid value; those settings took their defaults."""

    @property
    def problems(self) -> tuple[str, ...]:
        """Messages about unknown settings, then about invalid values."""
        return (*self.unknown_settings, *self.invalid_values)

    @property
    def adr_prefixes(self) -> tuple[str, ...]:
        """The prefixes an ADR file name may start with, in listing order: the external ones, then the repo's own."""
        if not self.adr_prefix:
            return self.external_adr_prefixes
        return (*self.external_adr_prefixes, self.adr_prefix)

    @classmethod
    def from_text(cls, text: str | None) -> ProjectConfig:
        """Read the project settings from the text of ``docspecsite.toml``.

        A missing setting takes its default. An unknown setting is listed in ``unknown_settings``; a setting with an
        invalid value is listed in ``invalid_values`` and also takes its default (an invalid ``code-dirs`` or
        ``external-adr-prefixes`` entry is left out).

        Args:
            text: Text of the root ``docspecsite.toml``; ``None`` or empty means the file is missing and every
                setting takes its default.

        Raises:
            tomllib.TOMLDecodeError: The text is not valid TOML.
        """
        return ProjectConfigParser(tomllib.loads(text) if text else {}).parse()

    @classmethod
    def from_bytes(cls, data: bytes | None) -> ProjectConfig:
        """Read the project settings from the content of ``docspecsite.toml``, as ``from_text`` does.

        Args:
            data: Content of the root ``docspecsite.toml``, UTF-8 with an optional byte-order mark and any line
                endings; ``None`` means the file is missing and every setting takes its default.

        Raises:
            tomllib.TOMLDecodeError: The content is not valid TOML.
            UnicodeDecodeError: The content is not UTF-8.
        """
        if data is None:
            return cls.from_text(None)
        text = data.decode("utf-8-sig")
        return cls.from_text(text.replace("\r\n", "\n").replace("\r", "\n"))

    @classmethod
    def from_valid_bytes(cls, data: bytes | None) -> ProjectConfig:
        """Read the project settings from the content of ``docspecsite.toml``, which must be valid.

        Each unknown setting is ignored with a ``DocspecsiteWarning``, so a setting of a newer release does not stop
        an older one.

        Args:
            data: Content of the root ``docspecsite.toml``; ``None`` means the file is missing and every setting
                takes its default.

        Raises:
            ConfigError: The content is not valid UTF-8 TOML, or a setting has an invalid value.
        """
        try:
            config = cls.from_bytes(data)
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
            raise ConfigError("%s is not valid TOML: %s", CONFIG_FILE, error) from error
        if config.invalid_values:
            raise ConfigError("%s: %s", CONFIG_FILE, "; ".join(config.invalid_values))
        for message in config.unknown_settings:
            warnings.warn(DocspecsiteWarning("%s: %s", CONFIG_FILE, message), stacklevel=2)
        return config

    @classmethod
    def load(cls, root: Path) -> ProjectConfig:
        """Read the project settings from the ``docspecsite.toml`` of a working tree, as ``from_bytes`` does.

        Args:
            root: Root of the working tree; without the file every setting takes its default.

        Raises:
            ConfigError: The file exists but cannot be read.
            tomllib.TOMLDecodeError: The file is not valid TOML.
            UnicodeDecodeError: The file is not UTF-8.
        """
        return cls.from_bytes(cls.read_file(root))

    @classmethod
    def load_valid(cls, root: Path) -> ProjectConfig:
        """Read the project settings from the ``docspecsite.toml`` at the root of a working tree, which must be valid.

        Each unknown setting is ignored with a warning, as ``from_valid_bytes`` does.

        Args:
            root: Root of the working tree; without the file every setting takes its default.

        Raises:
            ConfigError: The file cannot be read or is not valid UTF-8 TOML, or a setting has an invalid value.
        """
        return cls.from_valid_bytes(cls.read_file(root))

    @staticmethod
    def read_file(root: Path) -> bytes | None:
        """Return the content of the ``docspecsite.toml`` at the root of a working tree, or None if there is none.

        Args:
            root: Root of the working tree whose ``docspecsite.toml`` is read; without the file the result is None.

        Raises:
            ConfigError: The file exists but cannot be read.
        """
        config_file = root / CONFIG_FILE
        if not config_file.is_file():
            return None
        try:
            return config_file.read_bytes()
        except OSError as error:
            raise ConfigError("%s cannot be read: %s", CONFIG_FILE, error) from error

    def is_code_dir(self, directory: str) -> bool:
        """Return whether a directory is one of the code directories (``code_dirs``; ``.`` matches only the root).

        Args:
            directory: POSIX path of the directory relative to the repo root; ``.`` is the root itself.
        """
        path = PurePosixPath(directory)
        return any(path.full_match(pattern) for pattern in self.code_dirs)

    def get_components(self, dotted: str) -> tuple[str, ...]:
        """Return the component ids of a code element.

        They are those of the longest ``code_components`` prefix that matches ``dotted`` on whole dotted segments;
        the result is empty when no prefix matches.

        Args:
            dotted: Dotted path of the module or member to classify.
        """
        best = ""
        for prefix in self.code_components:
            if (dotted == prefix or dotted.startswith(prefix + ".")) and len(prefix) > len(best):
                best = prefix
        return self.code_components[best] if best else ()

    def make_sort_key(self, path: str) -> tuple[str, int, str]:
        """Return the key that sorts doc paths alphabetically, except that ADRs are ordered by prefix first.

        The key is ``(path, 0, "")`` for a path outside the decisions directory, and ``(ADR_DIR, prefix rank, rest of
        the path)`` inside it, so the decisions directory keeps its place among the other paths. ADRs come in this
        order: the external prefixes in their configured order, then other prefixes alphabetically (such as ``BASE``
        in a version from before it was listed), then the repository's own prefix; files that are not named like ADRs
        come last.

        Args:
            path: Doc path relative to ``docs/``, or a site path that keeps the doc's directories and file name.
        """
        if not path.startswith(ADR_DIR):
            return (path, 0, "")
        name = path.removeprefix(ADR_DIR)
        external_count = len(self.external_adr_prefixes)
        name_match = ADR_NAME.match(name)
        if name_match is None:
            prefix_rank = external_count + 2
        elif name_match["prefix"] == self.adr_prefix:
            prefix_rank = external_count + 1
        elif name_match["prefix"] in self.external_adr_prefixes:
            prefix_rank = self.external_adr_prefixes.index(name_match["prefix"])
        else:
            prefix_rank = external_count
        return (ADR_DIR, prefix_rank, name)


class ProjectConfigParser:
    """The parser of the settings read from ``docspecsite.toml``, holding the unknown settings and invalid values.

    Attributes:
        settings: The parsed TOML table, by setting name.
        unknown_settings: Messages about unknown settings found by the last parse.
        invalid_values: Messages about invalid values found by the last parse, in the order they were found.
    """

    def __init__(self, settings: Mapping[str, object]) -> None:
        """Prepare a parse of the settings.

        Args:
            settings: The parsed TOML table of ``docspecsite.toml``; empty when the file is missing.
        """
        self.settings = settings
        self.unknown_settings: list[str] = []
        self.invalid_values: list[str] = []

    def parse(self) -> ProjectConfig:
        """Return the project settings, recording each unknown setting and each invalid value.

        A missing setting takes its default, and so does one with an invalid value (an invalid ``code-dirs`` or
        ``external-adr-prefixes`` entry is left out). Each parse starts with no recorded messages.
        """
        settings = self.settings
        self.unknown_settings = [f'unknown setting "{key}"' for key in settings if key not in SETTINGS]
        self.invalid_values = []
        url = settings.get("source-url", "")
        if not isinstance(url, str):
            self.invalid_values.append('"source-url" must be a string')
            url = ""
        prefix = settings.get("adr-prefix", "")
        if not (isinstance(prefix, str) and ADR_PREFIX.fullmatch(prefix)) and "adr-prefix" in settings:
            self.invalid_values.append('"adr-prefix" must be capital letters only, e.g. "APP"')
            prefix = ""
        external_prefixes = (
            self.parse_external_adr_prefixes(settings["external-adr-prefixes"], str(prefix))
            if "external-adr-prefixes" in settings
            else ()
        )
        toc_min_headings = settings.get("toc-min-headings", DEFAULT_TOC_MIN)
        if not (isinstance(toc_min_headings, int) and not isinstance(toc_min_headings, bool) and toc_min_headings >= 0):
            self.invalid_values.append('"toc-min-headings" must be a whole number of 0 or more')
            toc_min_headings = DEFAULT_TOC_MIN
        code_dirs = self.parse_code_dirs(settings["code-dirs"]) if "code-dirs" in settings else ()
        code_components = (
            self.parse_code_components(settings["code-components"]) if "code-components" in settings else {}
        )
        return ProjectConfig(
            code_dirs=code_dirs,
            source_url=url,
            code_components=code_components,
            adr_prefix=str(prefix),
            external_adr_prefixes=external_prefixes,
            toc_min_headings=toc_min_headings,
            unknown_settings=tuple(self.unknown_settings),
            invalid_values=tuple(self.invalid_values),
        )

    def parse_code_dirs(self, value: object) -> tuple[str, ...]:
        """Return the valid ``code-dirs`` entries, normalized, and record the invalid ones.

        An entry is normalized as a POSIX path, so ``./src`` becomes ``src`` and ``./`` becomes ``.`` (the repo root).

        Args:
            value: Parsed ``code-dirs`` value; anything but a list of strings is reported and gives no entries.
        """
        if not (isinstance(value, list) and all(isinstance(item, str) for item in value)):
            self.invalid_values.append('"code-dirs" must be a list of strings')
            return ()
        entries: list[str] = []
        for entry in value:
            path = PurePosixPath(entry)
            if not entry or path.is_absolute() or ".." in path.parts:
                self.invalid_values.append(
                    f'"code-dirs" entries must be paths inside the repo, without ".." or a leading "/": "{entry}"'
                )
            else:
                entries.append(path.as_posix())
        return tuple(entries)

    def parse_external_adr_prefixes(self, value: object, adr_prefix: str) -> tuple[str, ...]:
        """Return the valid ``external-adr-prefixes`` entries and record the invalid ones.

        An entry is invalid when it is not capital letters only, equals the repository's own prefix, or repeats an
        earlier entry.

        Args:
            value: Parsed ``external-adr-prefixes`` value; anything but a list is reported and gives no entries.
            adr_prefix: The repository's own valid ADR prefix, which no entry may repeat; empty when unset.
        """
        if not isinstance(value, list):
            self.invalid_values.append('"external-adr-prefixes" must be a list of capital-letter prefixes')
            return ()
        prefixes: list[str] = []
        for entry in value:
            if not (isinstance(entry, str) and ADR_PREFIX.fullmatch(entry)):
                self.invalid_values.append(
                    f'"external-adr-prefixes" entries must be capital letters only, e.g. "BASE": "{entry}"'
                )
            elif entry == adr_prefix:
                self.invalid_values.append(f'"external-adr-prefixes" must not list "adr-prefix": "{entry}"')
            elif entry in prefixes:
                self.invalid_values.append(f'"external-adr-prefixes" lists a prefix twice: "{entry}"')
            else:
                prefixes.append(entry)
        return tuple(prefixes)

    def parse_code_components(self, value: object) -> dict[str, tuple[str, ...]]:
        """Return the ``code-components`` table; an empty one, recorded as invalid, when it is not one of string lists.

        Args:
            value: Parsed ``code-components`` value.
        """
        if isinstance(value, dict) and all(
            isinstance(components, list) and all(isinstance(c, str) for c in components)
            for components in value.values()
        ):
            return {str(prefix): tuple(components) for prefix, components in value.items()}
        self.invalid_values.append('"code-components" must be a table of lists of strings')
        return {}
