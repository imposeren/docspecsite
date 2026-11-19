"""The front-matter rules of docs, and the file-name rule of ADRs.

They are described in ``docs/meta/front-matter.md``, ``docs/meta/lifecycle.md`` and ``docs/meta/structure.md``.

Docs: meta/front-matter.md
Docs: meta/structure.md#adr-ids
"""

import datetime
import posixpath
import re
from typing import TypeGuard

from .docs import Doc
from .problems import Problem
from .vocabulary import Vocabulary

REQUIRED_STRINGS = ("title", "summary")
REQUIRED_LISTS = ("components", "tags", "related")
REQUIRED = ("title", "summary", "layer", "status", *REQUIRED_LISTS)
TAG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ADR_DIR = "architecture/decisions/"
ADR_NAME = re.compile(r"^(?P<prefix>[A-Z]+)-\d{4}-[a-z0-9]+(-[a-z0-9]+)*\.md$")

LAYERS = (
    "root",
    "meta",
    "behavior",
    "scenarios",
    "architecture",
    "ui",
    "guides",
    "agents",
    "reference",
)
STATUSES = ("draft", "specified", "implemented", "deprecated", "redirect")
PRIORITIES = ("must", "should", "could")
REDIRECT_KINDS = (
    "renamed",
    "moved",
    "became-directory",
    "merged",
    "split",
    "replaced",
    "removed",
)
DECISIONS = ("proposed", "accepted", "superseded")


def is_adr(path: str) -> bool:
    """Return whether a path is an architecture decision record.

    Every doc under ``architecture/decisions/`` other than an ``index.md`` is one, whether or not its file name
    follows the ADR naming rule.

    Args:
        path: Doc path relative to ``docs/``.
    """
    return path.startswith(ADR_DIR) and posixpath.basename(path) != "index.md"


class FrontMatterValidator:
    """The validator of docs' front matter and ADR file names, holding what the rules depend on in one run.

    Attributes:
        vocab: Components and milestones that ``components`` and ``milestone`` may name.
        adr_prefixes: Prefixes an ADR file name may start with; None when the file-name rule is skipped.
    """

    def __init__(self, vocab: Vocabulary, adr_prefixes: tuple[str, ...] | None) -> None:
        """Prepare the validation of the docs of one run.

        Args:
            vocab: Components and milestones that ``components`` and ``milestone`` may name.
            adr_prefixes: Prefixes an ADR file name may start with: the external ones and the repository's own one;
                None skips the file-name rule, for when the repository's settings could not be read.
        """
        self.vocab = vocab
        self.adr_prefixes = adr_prefixes

    def validate(self, doc: Doc) -> list[Problem]:
        """Check the front matter and, for an ADR, the file name of a doc against the rules and return the problems.

        All problems are reported on line 1. The front matter of a doc whose front matter did not parse is not checked,
        but its file name is.

        Args:
            doc: Doc whose front matter is checked; its path decides the expected layer and whether ADR rules apply.
        """
        problems: list[Problem] = []
        adr_name_problem = self.describe_adr_name_problem(doc.path)
        if adr_name_problem is not None:
            problems.append(Problem(doc.path, 1, adr_name_problem))
        if doc.front_matter is not None:
            problems.extend(FrontMatterCheck(doc.path, doc.front_matter, self.vocab).find_problems())
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
        name_match = ADR_NAME.match(path.removeprefix(ADR_DIR))
        if name_match is not None and name_match["prefix"] in adr_prefixes:
            return None
        if adr_prefixes:
            return f"ADR file name must be <PREFIX>-NNNN-<slug>.md with PREFIX one of: {', '.join(adr_prefixes)}"
        return (
            "ADR file name must be <PREFIX>-NNNN-<slug>.md, and no ADR prefix is configured: "
            "set adr-prefix or external-adr-prefixes in docspecsite.toml"
        )


class FrontMatterCheck:
    """One check of a doc's parsed front matter, holding the messages of the rule violations it found.

    Attributes:
        path: Doc path relative to ``docs/``.
        front_matter: The doc's parsed front matter, by field name.
        vocab: Components and milestones that ``components`` and ``milestone`` may name.
        messages: Messages of the violations found so far, in the order they were found.
    """

    def __init__(self, path: str, front_matter: dict[str, object], vocab: Vocabulary) -> None:
        """Prepare the check of a doc's front matter.

        Args:
            path: Doc path relative to ``docs/``; decides the expected layer and whether ADR rules apply, and is the
                path the problems are reported on.
            front_matter: The doc's parsed front matter.
            vocab: Components and milestones that ``components`` and ``milestone`` may name.
        """
        self.path = path
        self.front_matter = front_matter
        self.vocab = vocab
        self.messages: list[str] = []

    @staticmethod
    def is_str(value: object) -> bool:
        """Return whether a value is a string with some non-blank text.

        Args:
            value: Front-matter value of a field that must be non-empty text, such as ``title`` or ``reason``.
        """
        return isinstance(value, str) and value.strip() != ""

    @staticmethod
    def is_str_list(value: object) -> TypeGuard[list[str]]:
        """Return whether a value is a list of strings.

        Args:
            value: Front-matter value of a list field such as ``components`` or ``redirect_to``; an empty list counts.
        """
        return isinstance(value, list) and all(isinstance(v, str) for v in value)

    @staticmethod
    def get_expected_layer(path: str) -> str:
        """Return the layer a doc must declare in its front matter.

        That is the top-level directory of the path, or ``root`` for a file directly in ``docs/``.

        Args:
            path: Doc path relative to ``docs/``, whose first directory names the layer.
        """
        return path.split("/")[0] if "/" in path else "root"

    def find_problems(self) -> list[Problem]:
        """Return the front matter's rule violations as problems, all on line 1 of the doc.

        A check covers one doc once: call this a single time per ``FrontMatterCheck``.
        """
        front_matter = self.front_matter
        for field in REQUIRED:
            if field not in front_matter:
                self.messages.append(f'missing required field "{field}"')
        for field in REQUIRED_STRINGS:
            if field in front_matter and not self.is_str(front_matter[field]):
                self.messages.append(f'"{field}" must be a non-empty string')
        for field in (*REQUIRED_LISTS, "code"):
            if field in front_matter and not self.is_str_list(front_matter[field]):
                self.messages.append(f'"{field}" must be a list of strings')

        self.check_enum("layer", LAYERS)
        self.check_enum("status", STATUSES)
        self.check_enum("priority", PRIORITIES)

        layer = front_matter.get("layer")
        expected_layer = self.get_expected_layer(self.path)
        if layer in LAYERS and layer != expected_layer:
            self.messages.append(f'layer "{layer}" does not match the directory (expected "{expected_layer}")')

        components = front_matter.get("components")
        if self.is_str_list(components):
            for component in components:
                if component not in self.vocab.components:
                    self.messages.append(f'unknown component "{component}" (add it to architecture/components.md)')
        tags = front_matter.get("tags")
        if self.is_str_list(tags):
            for tag in tags:
                if not TAG_PATTERN.match(tag):
                    self.messages.append(f'tag "{tag}" must be lowercase words separated by "-"')

        if "milestone" in front_matter and front_matter["milestone"] not in self.vocab.milestones:
            self.messages.append(
                f'unknown milestone "{front_matter["milestone"]}" (milestones are listed in roadmap.md)'
            )

        self.check_redirect_rules()
        self.check_adr_rules()
        return [Problem(self.path, 1, m) for m in self.messages]

    def check_enum(self, field: str, allowed: tuple[str, ...]) -> None:
        """Record a violation if the field is present with a value outside the allowed ones.

        Args:
            field: Name of the front-matter field to check; nothing is recorded when the doc lacks it.
            allowed: Values the field may take; the message lists them.
        """
        if field in self.front_matter and self.front_matter[field] not in allowed:
            self.messages.append(f'"{field}" must be one of: {", ".join(allowed)}')

    def check_redirect_rules(self) -> None:
        """Record any violations of the rules for ``redirect_*`` fields and ``reason``."""
        front_matter = self.front_matter
        if front_matter.get("status") != "redirect":
            for field in ("redirect_kind", "redirect_to"):
                if field in front_matter:
                    self.messages.append(f'"{field}" is only allowed with status: redirect')
            return
        kind = front_matter.get("redirect_kind")
        if kind is None:
            self.messages.append('status: redirect needs "redirect_kind"')
        elif kind not in REDIRECT_KINDS:
            self.messages.append(f'"redirect_kind" must be one of: {", ".join(REDIRECT_KINDS)}')
        if not self.is_str(front_matter.get("reason")):
            self.messages.append('status: redirect needs "reason" (one sentence)')
        target = front_matter.get("redirect_to")
        if kind == "removed":
            if target is not None:
                self.messages.append('redirect_kind: removed has no replacement, so no "redirect_to"')
        elif target is None:
            self.messages.append('status: redirect needs "redirect_to"')
        elif kind == "split" and not (self.is_str_list(target) and target):
            self.messages.append('"redirect_to" must be a list of paths for redirect_kind: split')
        elif not (self.is_str(target) or (self.is_str_list(target) and target)):
            self.messages.append('"redirect_to" must be a path or a list of paths')

    def check_adr_rules(self) -> None:
        """Record any violations of the ADR rules for ``decision``, ``date`` and ``superseded_by``.

        The doc's path decides whether it is an ADR.
        """
        front_matter = self.front_matter
        if not is_adr(self.path):
            if "decision" in front_matter:
                self.messages.append('"decision" is only for ADRs (architecture/decisions/<PREFIX>-NNNN-<slug>.md)')
            return
        decision = front_matter.get("decision")
        if decision is None:
            self.messages.append('ADR needs "decision"')
        elif decision not in DECISIONS:
            self.messages.append(f'"decision" must be one of: {", ".join(DECISIONS)}')
        date = front_matter.get("date")
        if date is None:
            self.messages.append('ADR needs "date" (YYYY-MM-DD)')
        elif not (isinstance(date, datetime.date) or (isinstance(date, str) and DATE_PATTERN.match(date))):
            self.messages.append('"date" must be YYYY-MM-DD')
        if decision == "superseded" and not self.is_str(front_matter.get("superseded_by")):
            self.messages.append('decision: superseded needs "superseded_by"')
