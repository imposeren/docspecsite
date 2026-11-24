"""The front-matter rules of docs, and the file-name rule of ADRs.

Docs: meta/front-matter.md
Docs: meta/lifecycle.md
Docs: meta/structure.md#adr-ids
"""

import datetime
import re
from collections.abc import Mapping
from types import MappingProxyType

from .docs import LIST_STATUSES, ROOT_LAYER, Doc, DocStatus, derive_dir_layer, is_dir_index, is_str_list
from .problems import DocCheck, Problem
from .vocabulary import Vocabulary

ADR_DIR = "architecture/decisions/"
ADR_NAME_PATTERN = re.compile(r"^(?P<prefix>[A-Z]+)-\d{4}-[a-z0-9]+(-[a-z0-9]+)*\.md$")

LAYERS = (
    ROOT_LAYER,
    "meta",
    "behavior",
    "scenarios",
    "architecture",
    "ui",
    "guides",
    "agents",
    "reference",
)
STATUSES = ("draft", "specified", "changed", "implemented", "deprecated", "redirect")
"""All statuses, in the order of the status board.

Docs: meta/lifecycle.md
"""
STATUS_NOTES: Mapping[str, str] = MappingProxyType(
    {"Not built yet.": "specified", "Changed, not built yet.": "changed", "Built.": "implemented"}
)
"""Status note labels, each with the status it announces.

Docs: behavior/status-notes.md#requirements
"""
PRIORITIES = ("must", "should", "could")


def is_valid_status(status: DocStatus) -> bool:
    """Return whether a status is one known value, or a list of two or more distinct values that may be combined.

    The known values are :data:`STATUSES`, those that may be combined :data:`~docspecsite.docs.LIST_STATUSES`.

    Docs: behavior/status-notes.md#requirements

    Args:
        status: Status of a doc to validate.
    """
    values = status.values
    if status.is_single:
        return values[0] in STATUSES
    return bool(values) and len(set(values)) == len(values) and all(value in LIST_STATUSES for value in values)


def make_status_edit_hint(edit: str, status: DocStatus) -> str:
    """Return a hint that changes the ``status`` field, naming the change and the whole field as it then reads.

    For example ``add "changed" to "status" so it reads "status: [implemented, changed]"``.

    Docs: architecture/docs-tooling.md#problems-and-hints

    Args:
        edit: The change, as the words that come before ``"status"``, such as ``remove "draft" from``.
        status: Status the doc has after the change.
    """
    return f'{edit} "status" so it reads "status: {status.format_yaml()}"'


def is_adr(path: str) -> bool:
    """Return whether a path is an architecture decision record.

    Every doc under ``architecture/decisions/`` other than an ``index.md`` is one, whether or not its file name
    follows the ADR naming rule.

    Args:
        path: Doc path relative to ``docs/``.
    """
    return path.startswith(ADR_DIR) and not is_dir_index(path)


class FrontMatterValidator(DocCheck):
    """The validator of docs' front matter and ADR file names, holding what the rules depend on in one run."""

    vocab: Vocabulary
    """See :meth:`__init__`."""

    adr_prefixes: tuple[str, ...] | None
    """See :meth:`__init__`."""

    def __init__(self, vocab: Vocabulary, adr_prefixes: tuple[str, ...] | None) -> None:
        """Prepare the validation of the docs of one run.

        Args:
            vocab: Components and milestones that ``components`` and ``milestone`` may name.
            adr_prefixes: Prefixes an ADR file name may start with: the external ones and the repository's own one;
                None skips the file-name rule, for when the repository's settings could not be read.
        """
        self.vocab = vocab
        self.adr_prefixes = adr_prefixes

    def check(self, doc: Doc) -> list[Problem]:
        """Check the front matter and, for an ADR, the file name of a doc against the rules and return the problems.

        A doc whose front matter did not load gets its loading error as a problem, first, without a line number; its
        front matter is not checked, but its file name is. All other problems are reported on line 1.

        Args:
            doc: Doc whose front matter is checked; its path decides the expected layer and whether ADR rules apply.
        """
        problems = [Problem(doc.path, None, doc.error)] if doc.error else []
        adr_name_message = self.describe_adr_name_problem(doc.path)
        if adr_name_message is not None:
            problems.append(Problem(doc.path, 1, adr_name_message))
        if doc.front_matter is not None:
            problems.extend(FrontMatterCheck(doc, self.vocab).find_problems())
        return problems

    def describe_adr_name_problem(self, path: str) -> str | None:
        """Return the message for an ADR whose path is not ``architecture/decisions/<PREFIX>-NNNN-<slug>.md``.

        The prefix must be one of the known ADR prefixes. Return None for a valid name, for a doc that is not an ADR,
        and when the file-name rule is skipped.

        Args:
            path: Doc path relative to ``docs/``.
        """
        adr_prefixes = self.adr_prefixes
        if adr_prefixes is None or not is_adr(path):
            return None
        name_match = ADR_NAME_PATTERN.match(path.removeprefix(ADR_DIR))
        if name_match is not None and name_match["prefix"] in adr_prefixes:
            return None
        if adr_prefixes:
            return f"ADR file name must be <PREFIX>-NNNN-<slug>.md with PREFIX one of: {', '.join(adr_prefixes)}"
        return (
            "ADR file name must be <PREFIX>-NNNN-<slug>.md, and no ADR prefix is configured: "
            "set adr-prefix or external-adr-prefixes in docspecsite.toml"
        )


class FrontMatterCheck:
    """One check of a doc's parsed front matter, holding the problems of the rule violations it found."""

    # Required fields
    REQUIRED_LISTS = ("components", "tags", "related")
    """Required fields whose value must be a list of strings."""

    REQUIRED_FIELDS = ("title", "summary", "layer", "status", *REQUIRED_LISTS)
    """Fields every doc's front matter must have; ``status`` only in a layer with a build status."""

    REQUIRED_STRINGS = ("title", "summary")
    """Required fields whose value must be non-empty text."""

    # Value patterns
    DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    """Pattern of a ``date`` given as text: ``YYYY-MM-DD``."""

    TAG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
    """Pattern of a valid tag: lowercase words joined by hyphens."""

    # Messages
    IGNORED_IMPLEMENTED_MESSAGE = (
        '"implemented" in "status" is ignored: the "{layer}" layer has no build status, and the value can mislead a '
        "reader once the doc that owns the rules changes and nobody updates it"
    )

    # Allowed values
    DECISIONS = ("proposed", "accepted", "superseded")
    """Values ``decision`` may have."""

    REDIRECT_KINDS = (
        "renamed",
        "moved",
        "became-directory",
        "merged",
        "split",
        "replaced",
        "removed",
    )
    """Values ``redirect_kind`` may have."""

    # Found so far
    problems: list[Problem]
    """Problems of the violations found so far, in the order they were found."""

    # Arguments of __init__
    doc: Doc
    """See :meth:`__init__`."""

    vocab: Vocabulary
    """See :meth:`__init__`."""

    def __init__(self, doc: Doc, vocab: Vocabulary) -> None:
        """Prepare the check of a doc's front matter.

        Args:
            doc: Doc whose front matter parsed; its path decides the expected layer and whether ADR rules apply, and
                is the path the problems are reported on.
            vocab: Components and milestones that ``components`` and ``milestone`` may name.
        """
        self.doc = doc
        self.vocab = vocab
        self.problems = []

    @property
    def front_matter(self) -> dict[str, object]:
        """The doc's parsed front matter, by field name; empty for a doc whose front matter did not parse."""
        return self.doc.front_matter or {}

    @staticmethod
    def is_non_blank_str(value: object) -> bool:
        """Return whether a value is a string with some non-blank text.

        Args:
            value: Front-matter value of a field that must be non-empty text, such as ``title`` or ``reason``.
        """
        return isinstance(value, str) and value.strip() != ""

    def get_required_fields(self) -> tuple[str, ...]:
        """Return the fields the doc's front matter must have: :attr:`REQUIRED_FIELDS`, without ``status`` in a layer
        without a build status."""
        if self.doc.status.is_build_tracked:
            return self.REQUIRED_FIELDS
        return tuple(field for field in self.REQUIRED_FIELDS if field != "status")

    def find_problems(self) -> list[Problem]:
        """Return the front matter's rule violations as problems, all on line 1 of the doc.

        A check covers one doc once: call this a single time per :class:`FrontMatterCheck`.
        """
        front_matter = self.front_matter
        status = self.doc.status
        for field in self.get_required_fields():
            if field not in front_matter:
                self.report(f'missing required field "{field}"')
        for field in self.REQUIRED_STRINGS:
            if field in front_matter and not self.is_non_blank_str(front_matter[field]):
                self.report(f'"{field}" must be a non-empty string')
        for field in (*self.REQUIRED_LISTS, "code"):
            if field in front_matter and not is_str_list(front_matter[field]):
                self.report(f'"{field}" must be a list of strings')

        self.check_enum("layer", LAYERS, front_matter)
        self.check_status()
        self.check_enum("priority", PRIORITIES, status.roadmap_front_matter)

        layer = front_matter.get("layer")
        expected_layer = derive_dir_layer(self.doc.path)
        if layer in LAYERS and layer != expected_layer:
            self.report(f'layer "{layer}" does not match the directory (expected "{expected_layer}")')

        components = front_matter.get("components")
        if is_str_list(components):
            for component in components:
                if component not in self.vocab.components:
                    self.report(f'unknown component "{component}" (add it to architecture/components.md)')
        tags = front_matter.get("tags")
        if is_str_list(tags):
            for tag in tags:
                if not self.TAG_PATTERN.match(tag):
                    self.report(f'tag "{tag}" must be lowercase words separated by "-"')

        roadmap_front_matter = status.roadmap_front_matter
        if "milestone" in roadmap_front_matter and roadmap_front_matter["milestone"] not in self.vocab.milestones:
            self.report(
                f'unknown milestone "{roadmap_front_matter["milestone"]}" (milestones are listed in roadmap.md)'
            )

        self.check_redirect_rules()
        self.check_adr_rules()
        self.check_ignored_statuses()
        return self.problems

    def report(self, message: str, hint: str | None = None, *, is_warning: bool = False) -> None:
        """Record a violation, or a warning, as a problem on line 1 of the doc.

        Args:
            message: What is wrong, for the user.
            hint: How to fix this particular case; None for no hint.
            is_warning: Whether it is a warning rather than a broken rule.
        """
        self.problems.append(Problem(self.doc.path, 1, message, is_warning=is_warning, hint=hint))

    def check_enum(self, field: str, allowed: tuple[str, ...], fields: Mapping[str, object]) -> None:
        """Record a violation if the field is present with a value outside the allowed ones.

        Args:
            field: Name of the front-matter field to check; nothing is recorded when the doc lacks it.
            allowed: Values the field may take; the message lists them.
            fields: The fields to read it from: the front matter, or the one the doc's status reads the milestone
                and the priority from.
        """
        if field in fields and fields[field] not in allowed:
            self.report(f'"{field}" must be one of: {", ".join(allowed)}')

    def check_status(self) -> None:
        """Record the violations of the ``status`` rules, with hints that fix them where a fix is clear.

        A missing ``status`` is left to the required-field rule, and one whose values were all left out, in a layer
        without a build status, counts as not written. A status with no values or a value outside
        :data:`STATUSES` is one violation without a hint. Otherwise each single-only value combined with other values
        is one violation, then each value listed more than once, in doc order.
        """
        status = self.doc.status
        if not status.is_written or is_valid_status(status):
            return
        if not status.values or any(value not in STATUSES for value in status.values):
            self.report(
                f'"status" must be one of: {", ".join(STATUSES)}, '
                f"or a list of distinct values from: {', '.join(LIST_STATUSES)}"
            )
            return
        distinct_status = status.remove_duplicates()
        if not distinct_status.is_single:
            for value in distinct_status.values:
                if value not in LIST_STATUSES:
                    removal = make_status_edit_hint(f'remove "{value}" from', distinct_status.remove_value(value))
                    self.report(
                        f'"{value}" is combined with other statuses in "status"',
                        hint=f'write "status: {value}", or {removal}',
                    )
        for value in distinct_status.values:
            if status.values.count(value) > 1:
                self.report(
                    f'"{value}" is listed twice in "status"',
                    hint=make_status_edit_hint(f'remove the duplicate "{value}" from', distinct_status),
                )

    def check_ignored_statuses(self) -> None:
        """Record the warning about an ignored ``implemented`` status, once, in a layer without a build status.

        Docs: behavior/docs-format.md#layers-without-a-build-status
        Docs: behavior/commands.md#docs-without-a-build-status
        """
        if "implemented" in self.doc.status.ignored_values:
            layer = derive_dir_layer(self.doc.path)
            self.report(self.IGNORED_IMPLEMENTED_MESSAGE.format(layer=layer), is_warning=True)

    def check_redirect_rules(self) -> None:
        """Record any violations of the rules for ``redirect_*`` fields and ``reason``."""
        front_matter = self.front_matter
        if not self.doc.is_redirect:
            for field in ("redirect_kind", "redirect_to"):
                if field in front_matter:
                    self.report(f'"{field}" is only allowed with status: redirect')
            return
        kind = front_matter.get("redirect_kind")
        if kind is None:
            self.report('status: redirect needs "redirect_kind"')
        elif kind not in self.REDIRECT_KINDS:
            self.report(f'"redirect_kind" must be one of: {", ".join(self.REDIRECT_KINDS)}')
        if not self.is_non_blank_str(front_matter.get("reason")):
            self.report('status: redirect needs "reason" (one sentence)')
        target = front_matter.get("redirect_to")
        if kind == "removed":
            if target is not None:
                self.report('redirect_kind: removed has no replacement, so no "redirect_to"')
        elif target is None:
            self.report('status: redirect needs "redirect_to"')
        elif kind == "split" and not (is_str_list(target) and target):
            self.report('"redirect_to" must be a list of paths for redirect_kind: split')
        elif not (self.is_non_blank_str(target) or (is_str_list(target) and target)):
            self.report('"redirect_to" must be a path or a list of paths')

    def is_iso_date(self, value: object) -> bool:
        """Return whether a value is a calendar date: a ``date`` (not a ``datetime``) or ``YYYY-MM-DD`` text.

        Args:
            value: A front-matter value as YAML loaded it, such as an ADR's ``date``.
        """
        if isinstance(value, datetime.datetime):
            return False
        if isinstance(value, datetime.date):
            return True
        if not (isinstance(value, str) and self.DATE_PATTERN.match(value)):
            return False
        try:
            datetime.date.fromisoformat(value)
        except ValueError:
            return False
        return True

    def check_adr_rules(self) -> None:
        """Record any violations of the ADR rules for ``decision``, ``date`` and ``superseded_by``.

        The doc's path decides whether it is an ADR.
        """
        front_matter = self.front_matter
        if not is_adr(self.doc.path):
            for field in ("decision", "date", "superseded_by"):
                if field in front_matter:
                    self.report(f'"{field}" is only for ADRs (architecture/decisions/<PREFIX>-NNNN-<slug>.md)')
            return
        decision = front_matter.get("decision")
        if decision is None:
            self.report('ADR needs "decision"')
        elif decision not in self.DECISIONS:
            self.report(f'"decision" must be one of: {", ".join(self.DECISIONS)}')
        date = front_matter.get("date")
        if date is None:
            self.report('ADR needs "date" (YYYY-MM-DD)')
        elif not self.is_iso_date(date):
            self.report('"date" must be YYYY-MM-DD')
        superseded_by = front_matter.get("superseded_by")
        if decision == "superseded":
            if not self.is_non_blank_str(superseded_by):
                self.report('decision: superseded needs "superseded_by"')
        elif superseded_by is not None:
            self.report('"superseded_by" is only for ADRs with decision: superseded')
