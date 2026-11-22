"""Command-line entry point of docspecsite.

Docs: behavior/commands.md
Docs: architecture/docs-tooling.md
"""

import argparse
import sys
import warnings
from collections.abc import Callable, Generator
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import TextIO, override

from . import __version__
from .build import BuildError, run_build
from .check import Checker, OptionalCheck
from .choices import Choice
from .config import ConfigError, ProjectConfig
from .docset import DocSet
from .errors import DOCSPECSITE_WARNINGS
from .git import Git, GitError, UnknownRefError
from .parts import Part
from .query import (
    Filters,
    format_backlinks,
    format_list,
    resolve_doc_path,
)
from .text import UnreadableTextError


class CommandParser:
    """Builder of the argument parser of the ``docspecsite`` command."""

    class HelpFormatter(argparse.ArgumentDefaultsHelpFormatter):
        """Help formatter of the command and its subcommands; it shows each option's default unless it is unset."""

        @override
        def _get_help_string(self, action: argparse.Action) -> str | None:
            if action.default is None or action.default == frozenset():
                return action.help
            return super()._get_help_string(action)

    @staticmethod
    def parse_choices[C: Choice](choice_type: type[C], text: str) -> frozenset[C]:
        """Return the options of a choice type named in a comma-separated command-line value.

        Args:
            choice_type: The kind of options the value names.
            text: Option names separated by commas, e.g. ``docs,code``.

        Raises:
            argparse.ArgumentTypeError: The text is empty or names an unknown option; the message is the one of
                :meth:`Choice.parse_list <docspecsite.choices.Choice.parse_list>`, so the usage error shows it.
        """
        try:
            return choice_type.parse_list(text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from exc

    @staticmethod
    def build() -> argparse.ArgumentParser:
        """Build the argument parser of the ``docspecsite`` command, with its subcommands."""
        parser = argparse.ArgumentParser(
            prog="docspecsite",
            description="Check docs and render every version of every doc from git history.",
            formatter_class=CommandParser.HelpFormatter,
        )
        parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
        parser.add_argument(
            "--repo",
            type=Path,
            default=Path("."),
            help="top level of the git repository containing docs/",
        )
        commands = parser.add_subparsers(dest="command", metavar="command")

        check_parser = commands.add_parser(
            "check", help="validate the docs", formatter_class=CommandParser.HelpFormatter
        )
        check_parser.add_argument(
            "--staged",
            action="store_true",
            help="also reject staged deletes and renames under docs/",
        )
        check_parser.add_argument(
            "--optional-checks",
            metavar="C,…",
            type=partial(CommandParser.parse_choices, OptionalCheck),
            default=frozenset(),
            help="optional checks to run as well, comma-separated: code (the references in the code: Docs: lines, "
            "roles and code: links in docstrings)",
        )
        check_parser.set_defaults(handler=run_check_command)

        list_parser = commands.add_parser(
            "list", help="list docs, filtered by front matter", formatter_class=CommandParser.HelpFormatter
        )
        for name in ("layer", "status", "component", "tag", "milestone", "priority"):
            list_parser.add_argument(f"--{name}", metavar=name[0].upper())
        CommandParser.add_format_option(list_parser)
        list_parser.set_defaults(handler=run_list_command)

        backlinks_parser = commands.add_parser(
            "backlinks", help="list the docs that link to a doc", formatter_class=CommandParser.HelpFormatter
        )
        backlinks_parser.add_argument(
            "path", help="the doc: docs/x.md (from the repo root), x.md (relative to docs/) or an absolute path"
        )
        CommandParser.add_format_option(backlinks_parser)
        backlinks_parser.set_defaults(handler=run_backlinks_command)

        build_parser = commands.add_parser(
            "build", help="render the static site from a ref's history", formatter_class=CommandParser.HelpFormatter
        )
        build_parser.add_argument("--ref", default="main", help="the git ref to build")
        build_parser.add_argument("--out", default="site", help="output directory, relative to the current directory")
        build_parser.add_argument(
            "--include-worktree",
            action="store_true",
            help="add uncommitted changes as a 'working copy' version, and read the code from the working tree",
        )
        build_parser.add_argument(
            "--strict",
            action="store_true",
            help="stop at the first page error without writing anything, and fail on warnings too (for CI)",
        )
        build_parser.add_argument(
            "--parts",
            type=partial(CommandParser.parse_choices, Part),
            help="parts to build, comma-separated: docs, code (default: all the repo has)",
        )
        build_parser.set_defaults(handler=run_build_command)
        return parser

    @staticmethod
    def add_format_option(parser: argparse.ArgumentParser) -> None:
        """Add the ``--format`` option (text or JSON output) to a command's parser.

        Args:
            parser: Parser of a command whose output can be printed as JSON.
        """
        parser.add_argument("--format", choices=["text", "json"], default="text", help="output format")


def run_check_command(args: argparse.Namespace) -> int:
    """Run the ``check`` command and print its problems.

    Returns exit status 1 when problems are found or ``staged`` is set outside git, else 0.

    Args:
        args: Parsed ``check`` options; ``repo``, ``staged`` and ``optional_checks`` (the set of
            :class:`~docspecsite.check.OptionalCheck` to run as well) are used.
    """
    try:
        problems = Checker(args.repo).run(include_staged=args.staged, optional_checks=args.optional_checks)
    except GitError as exc:
        print(f"docspecsite check --staged: {exc}", file=sys.stderr)
        return 1
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} problem(s)", file=sys.stderr)
        return 1
    return 0


def run_list_command(args: argparse.Namespace) -> int:
    """Run the ``list`` command and print the matching docs.

    Returns exit status 1 when ``docspecsite.toml`` is not valid TOML or has an invalid value, or when a doc cannot be
    read or is not valid UTF-8, else 0. Unknown settings are printed as warnings.

    Args:
        args: Parsed ``list`` options; ``repo``, the filters and ``format`` are used.
    """
    try:
        with WarningPrinter.print_warnings():
            config = ProjectConfig.load(args.repo).require_valid()
    except ConfigError as error:
        print(f"docspecsite list: {error}", file=sys.stderr)
        return 1
    filters = Filters(
        layer=args.layer,
        status=args.status,
        component=args.component,
        tag=args.tag,
        milestone=args.milestone,
        priority=args.priority,
    )
    try:
        doc_set = DocSet.load(args.repo).require_readable()
    except UnreadableTextError as error:
        print(f"docspecsite list: {error}", file=sys.stderr)
        return 1
    sys.stdout.write(format_list(doc_set.select(filters, config), args.format))
    return 0


def run_backlinks_command(args: argparse.Namespace) -> int:
    """Run the ``backlinks`` command and print the result.

    Returns exit status 1 when a doc cannot be read or is not valid UTF-8, 2 when the argument is not a doc, else 0.

    Args:
        args: Parsed ``backlinks`` options; ``repo``, ``path`` (the doc to find links to) and ``format`` are used.
    """
    try:
        doc_set = DocSet.load(args.repo).require_readable()
    except UnreadableTextError as error:
        print(f"docspecsite backlinks: {error}", file=sys.stderr)
        return 1
    target = resolve_doc_path(args.repo, args.path)
    if target is None:
        print(f"not a doc: {args.path}", file=sys.stderr)
        return 2
    sys.stdout.write(format_backlinks(doc_set.backlinks_by_target.get(target, ()), args.format))
    return 0


class WarningPrinter:
    """Printer of docspecsite's warnings as ``warning: <message>`` lines on stderr."""

    # Signature of ``warnings.showwarning``: message, category, filename, line number, file and source line.
    type ShowWarning = Callable[[Warning | str, type[Warning], str, int, TextIO | None, str | None], None]

    @staticmethod
    def show(
        show_other: ShowWarning,
        message: Warning | str,
        category: type[Warning],
        filename: str,
        lineno: int,
        file: TextIO | None = None,
        line: str | None = None,
    ) -> None:
        """Print docspecsite's warnings as ``warning: <message>`` on stderr, and pass any other warning on.

        Args:
            show_other: Shows the warnings of other categories; the ``warnings.showwarning`` in place before.
            message: The warning, or its text.
            category: Class of the warning; those in :data:`~docspecsite.errors.DOCSPECSITE_WARNINGS` are printed
                here.
            filename: File the warning was issued from, passed on for other warnings.
            lineno: Line the warning was issued from, passed on for other warnings.
            file: Stream to print to; None means stderr.
            line: Source line of the warning, passed on for other warnings.
        """
        if issubclass(category, DOCSPECSITE_WARNINGS):
            print(f"warning: {message}", file=file if file is not None else sys.stderr)
        else:
            show_other(message, category, filename, lineno, file, line)

    @staticmethod
    @contextmanager
    def print_warnings() -> Generator[None]:
        """Print docspecsite's warnings issued inside the block as ``warning: <message>`` on stderr."""
        with warnings.catch_warnings():
            warnings.showwarning = partial(WarningPrinter.show, warnings.showwarning)
            yield


def run_build_command(args: argparse.Namespace) -> int:
    """Run the ``build`` command and print its warnings, errors and summary.

    Warnings are printed as they are issued. Returns exit status 2 for an unknown ref, 1 for a failed build or failed
    pages, else 0.

    Args:
        args: Parsed ``build`` options; ``repo``, ``ref``, ``out``, ``include_worktree``, ``strict`` and ``parts`` (the
            set of :class:`~docspecsite.parts.Part` to build; None means every part the repo has) are used.
    """
    with WarningPrinter.print_warnings():
        try:
            build_result = run_build(
                args.repo,
                args.ref,
                Path(args.out),
                include_worktree=args.include_worktree,
                is_strict=args.strict,
                parts=args.parts,
            )
        except UnknownRefError:
            print(f"docspecsite build: unknown ref: {args.ref}", file=sys.stderr)
            return 2
        except (BuildError, GitError, OSError) as exc:
            print(f"docspecsite build: {exc}", file=sys.stderr)
            return 1
    for error in build_result.errors:
        print(f"error: {error}", file=sys.stderr)
    failed = f", {build_result.failed_count} failed" if build_result.failed_count else ""
    counts = f"{build_result.rendered_count} rendered, {build_result.cached_count} from cache{failed}"
    print(f"built {build_result.page_count} pages ({counts}) → {args.out}")
    return 1 if build_result.failed_count else 0


def main(argv: list[str] | None = None) -> int:
    """Run the ``docspecsite`` command line and return the exit status.

    Every command stops with exit status 1 when the checked repo is a subdirectory of a git repository.

    Args:
        argv: Arguments after the program name, e.g. ``["check", "--staged"]``; None reads ``sys.argv``.
    """
    parser = CommandParser.build()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_usage()
        return 0
    try:
        Git(args.repo).require_top_level()
    except GitError as error:
        print(f"docspecsite: {error}", file=sys.stderr)
        return 1
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
