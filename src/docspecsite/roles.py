"""Sphinx's Python roles in docstrings, such as `` :meth:`attempt` ``, read by the Markdown parser.

A role becomes a link around a code span whose target is the role's content under :data:`ROLE_SCHEME`; the code
reference resolves it later, with the docstring's object as context.

Docs: architecture/docs-tooling.md
"""

import re
from dataclasses import dataclass
from typing import ClassVar, Self
from urllib.parse import quote

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline

ROLE_SCHEME = "role:"
"""Scheme of the link a role becomes; the rest of the link's target is the role's content, percent-encoded."""

PYTHON_ROLES = frozenset({"mod", "class", "func", "meth", "attr", "data", "exc", "obj"})
"""Names of the Python roles that become links, each also with the ``py:`` domain; other roles stay as written."""


@dataclass(frozen=True)
class RoleRef:
    """What a role's content says: the target it refers to and how its link text is chosen."""

    # Constants
    TITLED_TARGET: ClassVar[re.Pattern[str]] = re.compile(r"^(?P<title>.*?)\s*<(?P<target>[^<>]+)>$", re.DOTALL)
    """A role's content in the ``Text <target>`` form."""

    # Fields
    target: str
    """Dotted path of the target as written, without ``~``; a leading ``.`` makes it relative to the docstring."""

    title: str | None
    """Text given in the ``Text <target>`` form, or None."""

    short: bool
    """Whether the target was written with ``~``, so that only the last part of its path is shown."""

    @classmethod
    def parse(cls, content: str) -> Self:
        """Read the content of a role.

        Args:
            content: Text between the role's backticks: a target such as ``~.attempt``, optionally in the
                ``Text <target>`` form.
        """
        titled = cls.TITLED_TARGET.match(content)
        title, target = (titled["title"], titled["target"]) if titled and titled["title"] else (None, content)
        target = target.strip()
        return cls(target.removeprefix("~"), title, target.startswith("~"))

    @property
    def written_text(self) -> str:
        """The text of the role as written: its title, else its target without ``~``."""
        return self.title if self.title is not None else self.target

    def display_text(self, dotted_path: str) -> str:
        """Return the link text of the role once its target is found.

        Args:
            dotted_path: Full dotted path of the code element the target leads to.
        """
        if self.title is not None:
            return self.title
        return dotted_path.rpartition(".")[2] if self.short else dotted_path


class RoleRule:
    """The inline rule of markdown-it, ``sphinx_role``, that reads Python roles as links around a code span."""

    # Constants
    BACKTICK_RUN = re.compile("`+")
    """A run of backticks, the delimiter of a role's content as of a code span."""

    NAME = "sphinx_role"
    """Name of the rule in the parser's inline rules."""

    ROLE_START = re.compile(r":(?:py:)?([a-z]+):(?=`)")
    """The start of a role, ``:name:`` or ``:py:name:`` right before a backtick; the group is the role's name."""

    @staticmethod
    def install(md: MarkdownIt) -> None:
        """Make a parser read Python roles, before it reads code spans; a markdown-it plugin.

        Args:
            md: Parser that gets the rule.
        """
        md.inline.ruler.before("backticks", RoleRule.NAME, RoleRule.parse)

    @staticmethod
    def parse(state: StateInline, silent: bool) -> bool:
        """Read a Python role at the parser's position, as markdown-it calls an inline rule.

        A role is ``:name:`` or ``:py:name:`` with a name in :data:`PYTHON_ROLES`, directly followed by content in
        backticks closed by a run of as many backticks. Inside a link's text a role is left as written, since links do
        not nest.

        Args:
            state: Inline parser state; on a match its position moves past the role and, unless ``silent``, the link
                tokens are pushed.
            silent: Only check for a role, as markdown-it does when it validates a construct, without pushing tokens.

        Returns:
            Whether a role was read.
        """
        start = RoleRule.ROLE_START.match(state.src, state.pos, state.posMax)
        if start is None or start[1] not in PYTHON_ROLES or state.linkLevel > 0:
            return False
        opening = RoleRule.BACKTICK_RUN.match(state.src, start.end(), state.posMax)
        if opening is None:
            return False
        closing = next(
            (
                run
                for run in RoleRule.BACKTICK_RUN.finditer(state.src, opening.end(), state.posMax)
                if len(run[0]) == len(opening[0])
            ),
            None,
        )
        if closing is None:
            return False
        content = state.src[opening.end() : closing.start()].replace("\n", " ").strip()
        if not content:
            return False
        if not silent:
            link_open = state.push("link_open", "a", 1)
            link_open.attrs = {"href": ROLE_SCHEME + quote(content, safe="")}
            link_open.meta = {"role_source": state.src[state.pos : closing.end()]}
            code = state.push("code_inline", "code", 0)
            code.markup = opening[0]
            code.content = RoleRef.parse(content).written_text
            state.push("link_close", "a", -1)
        state.pos = closing.end()
        return True
