"""Project settings read from ``docspecsite.toml`` at the root of the checked repository.

Docs: behavior/configuration.md
Docs: architecture/docs-tooling.md#adr-ids
"""

import re
import tomllib
import warnings
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import ClassVar

from .docs import BUILD_STATUSES, is_str_list, make_string_tuple
from .errors import DocspecsiteError, DocspecsiteWarning
from .schema import ADR_DIR, ADR_NAME_PATTERN, STATUS_NOTES
from .text import decode_text


class ConfigError(DocspecsiteError):
    """Error for a ``docspecsite.toml`` that cannot be used: unreadable, not valid TOML, or with an invalid value."""


@dataclass(frozen=True)
class CodeComponentsCheck:
    """The ``[code-components]`` ids split into known and unknown ones.

    :meth:`ProjectConfig.check_code_components` splits them.

    Docs: architecture/docs-tooling.md#configuration
    """

    known: Mapping[str, tuple[str, ...]]
    """The known component ids of each key, in the order the settings give them; a key keeps its entry when none is
    known."""

    unknown: tuple[tuple[str, str], ...]
    """The unknown entries as ``(key, component)``, in the order the settings give them."""


@dataclass(frozen=True)
class ProjectConfig:
    """Docspecsite settings read from the project's ``docspecsite.toml``."""

    # Files
    CONFIG_FILE: ClassVar[str] = "docspecsite.toml"
    """Name of the settings file at the repository root."""

    # Defaults
    DEFAULT_TOC_MIN: ClassVar[int] = 5
    """Default of ``toc-min-headings``."""

    # Settings
    code_dirs: tuple[str, ...]
    """Globs of the directories holding the Python packages (``code-dirs``), relative to the repository root."""

    source_url: str
    """Base URL of the repository host (``source-url``), without a trailing ``/``; empty when unset."""

    code_components: Mapping[str, tuple[str, ...]]
    """Component ids by dotted-name prefix (``[code-components]``)."""

    adr_prefix: str = ""
    """The repository's own ADR prefix (``adr-prefix``); empty when unset, so only external ADRs are valid."""

    external_adr_prefixes: tuple[str, ...] = ()
    """Prefixes of ADRs taken from elsewhere (``external-adr-prefixes``), in the order listings show them."""

    toc_min_headings: int = DEFAULT_TOC_MIN
    """Number of ``##`` sections from which a doc gets a Contents list; 0 turns it off (``toc-min-headings``)."""

    status_notes: Mapping[str, str] = STATUS_NOTES
    """Status note labels, each with the status it announces (``[status-notes]``): the defaults, with the project's
    texts replacing those of the statuses it sets.

    Docs: behavior/configuration.md
    """

    # Problems found while reading
    unknown_settings: tuple[str, ...] = ()
    """Messages about settings docspecsite does not know; they are ignored."""

    invalid_values: tuple[str, ...] = ()
    """Messages about settings with an invalid value; those settings took their defaults."""

    read_error: str = ""
    """Why the file could not be read (unreadable, or not valid UTF-8 TOML); every setting then took its default.

    Empty when the file was read or is missing.
    """

    @property
    def problems(self) -> tuple[str, ...]:
        """Messages about a file that could not be read, then about unknown settings, then about invalid values."""
        return (*((self.read_error,) if self.read_error else ()), *self.unknown_settings, *self.invalid_values)

    @property
    def adr_prefixes(self) -> tuple[str, ...]:
        """The prefixes an ADR file name may start with, in listing order: the external ones, then the repo's own."""
        if not self.adr_prefix:
            return self.external_adr_prefixes
        return (*self.external_adr_prefixes, self.adr_prefix)

    @classmethod
    def from_bytes(cls, content: bytes | None) -> ProjectConfig:
        """Read the project settings from the content of ``docspecsite.toml``.

        A missing setting takes its default. An unknown setting is listed in :attr:`unknown_settings`; a setting with
        an invalid value is listed in :attr:`invalid_values` and also takes its default (an invalid ``code-dirs`` or
        ``external-adr-prefixes`` entry is left out). Content that is not valid UTF-8 TOML is described in
        :attr:`read_error`, and every setting takes its default.

        Args:
            content: Content of the root ``docspecsite.toml``, UTF-8 with an optional byte-order mark and any line
                endings; ``None`` or empty means the file is missing and every setting takes its default.
        """
        if not content:
            return ProjectConfigParser({}).parse()
        try:
            text = decode_text(content).replace("\r\n", "\n").replace("\r", "\n")
            settings = tomllib.loads(text)
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
            return replace(ProjectConfigParser({}).parse(), read_error=f"not valid TOML: {error}")
        return ProjectConfigParser(settings).parse()

    @classmethod
    def load(cls, root: Path) -> ProjectConfig:
        """Read the project settings from a working tree's ``docspecsite.toml``, as the ``from_bytes`` method does.

        A file that exists but cannot be read is described in :attr:`read_error`, and every setting takes its default.

        Args:
            root: Root of the working tree; without the file every setting takes its default.
        """
        config_file = root / cls.CONFIG_FILE
        if not config_file.is_file():
            return cls.from_bytes(None)
        try:
            content = config_file.read_bytes()
        except OSError as error:
            return replace(cls.from_bytes(None), read_error=f"cannot be read: {error}")
        return cls.from_bytes(content)

    def require_valid(self) -> ProjectConfig:
        """Return these settings if the file was read and every value is valid.

        Each unknown setting is ignored with a :exc:`~docspecsite.errors.DocspecsiteWarning`, so a setting of a newer
        release does not stop an older one.

        Raises:
            ConfigError: The file could not be read or is not valid UTF-8 TOML, or a setting has an invalid value.
        """
        if self.read_error:
            raise ConfigError("%s: %s", self.CONFIG_FILE, self.read_error)
        if self.invalid_values:
            raise ConfigError("%s: %s", self.CONFIG_FILE, "; ".join(self.invalid_values))
        for message in self.unknown_settings:
            warnings.warn(DocspecsiteWarning("%s: %s", self.CONFIG_FILE, message), stacklevel=2)
        return self

    def is_code_dir(self, directory: str) -> bool:
        """Return whether a directory is one of the ``code_dirs`` attribute's directories (``.`` matches only the root).

        Args:
            directory: POSIX path of the directory relative to the repo root; ``.`` is the root itself.
        """
        path = PurePosixPath(directory)
        return any(path.full_match(pattern) for pattern in self.code_dirs)

    def check_code_components(self, components: Collection[str]) -> CodeComponentsCheck:
        """Split the ``code-components`` ids into known and unknown ones; the one owner of whether an id is known.

        Docs: behavior/configuration.md#settings

        Args:
            components: The component vocabulary: the ids that have a page.
        """
        known = {key: tuple(c for c in ids if c in components) for key, ids in self.code_components.items()}
        unknown = tuple((key, c) for key, ids in self.code_components.items() for c in ids if c not in components)
        return CodeComponentsCheck(known, unknown)

    def find_components(self, dotted_path: str) -> tuple[str, ...]:
        """Return the component ids of a code element.

        They are those of the longest :attr:`code_components` prefix that matches ``dotted_path`` on whole dotted
        segments; the result is empty when no prefix matches.

        Args:
            dotted_path: Dotted path of the module or member to classify.
        """
        longest_prefix = ""
        for prefix in self.code_components:
            if (dotted_path == prefix or dotted_path.startswith(prefix + ".")) and len(prefix) > len(longest_prefix):
                longest_prefix = prefix
        return self.code_components[longest_prefix] if longest_prefix else ()

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
        name_match = ADR_NAME_PATTERN.match(name)
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
    """The parser of the settings read from ``docspecsite.toml``, holding the unknown settings and invalid values."""

    # Setting names
    KNOWN_SETTING_NAMES: ClassVar[tuple[str, ...]] = (
        "adr-prefix",
        "external-adr-prefixes",
        "source-url",
        "code-dirs",
        "code-components",
        "toc-min-headings",
        "status-notes",
    )
    """Names of the settings docspecsite knows; any other key is an unknown setting."""

    # Value patterns
    ADR_PREFIX_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"[A-Z]+")
    """Pattern of a valid ADR prefix: capital letters only."""

    # Found by the last parse
    invalid_values: list[str]
    """Messages about invalid values found by the last parse, in the order they were found."""

    unknown_settings: list[str]
    """Messages about unknown settings found by the last parse."""

    # Arguments of __init__
    settings: Mapping[str, object]
    """See :meth:`__init__`."""

    def __init__(self, settings: Mapping[str, object]) -> None:
        """Prepare a parse of the settings.

        Args:
            settings: The parsed TOML table of ``docspecsite.toml``, by setting name; empty when the file is missing.
        """
        self.settings = settings
        self.unknown_settings = []
        self.invalid_values = []

    def parse(self) -> ProjectConfig:
        """Return the project settings, recording each unknown setting and each invalid value.

        A missing setting takes its default, and so does one with an invalid value (an invalid ``code-dirs`` or
        ``external-adr-prefixes`` entry is left out). Each parse starts with no recorded messages.
        """
        settings = self.settings
        self.unknown_settings = [f'unknown setting "{key}"' for key in settings if key not in self.KNOWN_SETTING_NAMES]
        self.invalid_values = []
        source_url = settings.get("source-url", "")
        if not isinstance(source_url, str):
            self.invalid_values.append('"source-url" must be a string')
            source_url = ""
        adr_prefix = settings.get("adr-prefix", "")
        if (
            not (isinstance(adr_prefix, str) and self.ADR_PREFIX_PATTERN.fullmatch(adr_prefix))
            and "adr-prefix" in settings
        ):
            self.invalid_values.append('"adr-prefix" must be capital letters only, e.g. "APP"')
            adr_prefix = ""
        prefix_entries = settings.get("external-adr-prefixes", [])
        if isinstance(prefix_entries, list):
            external_adr_prefixes = self.parse_external_adr_prefixes(prefix_entries, str(adr_prefix))
        else:
            self.invalid_values.append('"external-adr-prefixes" must be a list of capital-letter prefixes')
            external_adr_prefixes = ()
        toc_min_headings = settings.get("toc-min-headings", ProjectConfig.DEFAULT_TOC_MIN)
        if not (isinstance(toc_min_headings, int) and not isinstance(toc_min_headings, bool) and toc_min_headings >= 0):
            self.invalid_values.append('"toc-min-headings" must be a whole number of 0 or more')
            toc_min_headings = ProjectConfig.DEFAULT_TOC_MIN
        code_dirs = self.parse_code_dirs(self.parse_string_list("code-dirs"))
        code_components = (
            self.parse_code_components(settings["code-components"]) if "code-components" in settings else {}
        )
        status_notes = self.parse_status_notes(settings["status-notes"]) if "status-notes" in settings else STATUS_NOTES
        return ProjectConfig(
            code_dirs=code_dirs,
            source_url=source_url.rstrip("/"),
            code_components=code_components,
            adr_prefix=str(adr_prefix),
            external_adr_prefixes=external_adr_prefixes,
            toc_min_headings=toc_min_headings,
            status_notes=status_notes,
            unknown_settings=tuple(self.unknown_settings),
            invalid_values=tuple(self.invalid_values),
        )

    def parse_string_list(self, key: str) -> tuple[str, ...]:
        """Return the strings of a setting that must be a list of strings; empty when it is missing or invalid.

        A value that is not a list of strings is recorded as invalid, so the setting takes its default.

        Args:
            key: Name of the setting that is looked up, and named in the message when its value is invalid.
        """
        if key not in self.settings:
            return ()
        value = self.settings[key]
        if not is_str_list(value):
            self.invalid_values.append(f'"{key}" must be a list of strings')
            return ()
        return make_string_tuple(value)

    def parse_code_dirs(self, entries: tuple[str, ...]) -> tuple[str, ...]:
        """Return the valid ``code-dirs`` entries, normalized, and record the invalid ones.

        An entry is normalized as a POSIX path, so ``./src`` becomes ``src`` and ``./`` becomes ``.`` (the repo root).

        Args:
            entries: Strings of the ``code-dirs`` setting; each is normalized or recorded as invalid.
        """
        valid_dirs: list[str] = []
        for entry in entries:
            path = PurePosixPath(entry)
            if not entry or path.is_absolute() or ".." in path.parts:
                self.invalid_values.append(
                    f'"code-dirs" entries must be paths inside the repo, without ".." or a leading "/": "{entry}"'
                )
            else:
                valid_dirs.append(path.as_posix())
        return tuple(valid_dirs)

    def parse_external_adr_prefixes(self, entries: list[object], adr_prefix: str) -> tuple[str, ...]:
        """Return the valid ``external-adr-prefixes`` entries and record the invalid ones.

        An entry is invalid when it is not a string of capital letters only, equals the repository's own prefix, or
        repeats an earlier entry.

        Args:
            entries: Entries of the ``external-adr-prefixes`` setting, of any type; each is checked on its own, so a
                string of capital letters is kept and any other entry, a non-string one included, is recorded as
                invalid.
            adr_prefix: The repository's own valid ADR prefix, which no entry may repeat; empty when unset.
        """
        prefixes: list[str] = []
        for entry in entries:
            if not (isinstance(entry, str) and self.ADR_PREFIX_PATTERN.fullmatch(entry)):
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
            value: The ``code-components`` value from the parsed TOML, of any type; kept when it is a table of string
                lists by dotted-name prefix, otherwise recorded as invalid and replaced by an empty table.
        """
        if isinstance(value, dict) and all(is_str_list(components) for components in value.values()):
            return {str(prefix): tuple(components) for prefix, components in value.items()}
        self.invalid_values.append('"code-components" must be a table of lists of strings')
        return {}

    def parse_status_notes(self, value: object) -> Mapping[str, str]:
        """Return the effective status notes, or the defaults, recording every problem, when an entry is invalid.

        The effective notes are the default ones with the texts of the statuses the table sets in place of theirs.

        Docs: behavior/configuration.md

        Args:
            value: The ``status-notes`` value from the parsed TOML, of any type; valid when it is a table of texts by
                status, each text non-empty without leading or trailing whitespace, and no two statuses share a text.
        """
        if not isinstance(value, dict):
            self.invalid_values.append('"status-notes" must be a table of status note texts by status')
            return STATUS_NOTES
        problems_before = len(self.invalid_values)
        texts_by_status = {status: label for label, status in STATUS_NOTES.items()}
        for status, text in value.items():
            if status not in BUILD_STATUSES:
                self.invalid_values.append(f'"status-notes" has an unknown status: "{status}"')
            elif not (isinstance(text, str) and text and text == text.strip()):
                self.invalid_values.append(
                    f'"status-notes" text of "{status}" must be non-empty text without leading or trailing spaces'
                )
            else:
                texts_by_status[status] = text
        if len(self.invalid_values) > problems_before:
            return STATUS_NOTES
        statuses_by_text: dict[str, str] = {}
        for status in BUILD_STATUSES:
            text = texts_by_status[status]
            if text in statuses_by_text:
                self.invalid_values.append(
                    f'"status-notes" gives "{statuses_by_text[text]}" and "{status}" the same text: "{text}"'
                )
            else:
                statuses_by_text[text] = status
        if len(self.invalid_values) > problems_before:
            return STATUS_NOTES
        return {text: status for status, text in texts_by_status.items()}
