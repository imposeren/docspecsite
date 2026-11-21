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
from typing import TextIO

from . import __version__
from .build import BuildError, run_build
from .check import Checker
from .config import ConfigError, ProjectConfig
from .docset import DocSet
from .errors import DocspecsiteWarning, InternalErrorWarning
from .git import GitError, UnknownRefError
from .parts import parse_parts
from .query import (
    Filters,
    format_backlinks,
    format_list,
    resolve_doc_path,
)

# Signature of ``warnings.showwarning``: message, category, filename, line number, file and source line.
type ShowWarning = Callable[[Warning | str, type[Warning], str, int, TextIO | None, str | None], None]

FORMATTER = argparse.ArgumentDefaultsHelpFormatter


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser of the ``docspecsite`` command, with its subcommands."""
    parser = argparse.ArgumentParser(
        prog="docspecsite",
        description="Check docs and render every version of every doc from git history.",
        formatter_class=FORMATTER,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path("."),
        help="repository root containing docs/",
    )
    commands = parser.add_subparsers(dest="command", metavar="command")

    check_parser = commands.add_parser("check", help="validate the docs", formatter_class=FORMATTER)
    check_parser.add_argument(
        "--staged",
        action="store_true",
        help="also reject staged deletes and renames under docs/",
    )
    check_parser.add_argument(
        "--code",
        action="store_true",
        help="also check the references in the code: Docs: lines, roles and code: links in docstrings",
    )
    check_parser.set_defaults(handler=run_check_command)

    list_parser = commands.add_parser("list", help="list docs, filtered by front matter", formatter_class=FORMATTER)
    for name in ("layer", "status", "component", "tag", "milestone", "priority"):
        list_parser.add_argument(f"--{name}", metavar=name[0].upper())
    add_format_option(list_parser)
    list_parser.set_defaults(handler=run_list_command)

    backlinks_parser = commands.add_parser(
        "backlinks", help="list the docs that link to a doc", formatter_class=FORMATTER
    )
    backlinks_parser.add_argument(
        "path", help="the doc: docs/x.md (from the repo root), x.md (relative to docs/) or an absolute path"
    )
    add_format_option(backlinks_parser)
    backlinks_parser.set_defaults(handler=run_backlinks_command)

    build_parser = commands.add_parser(
        "build", help="render the static site from a ref's history", formatter_class=FORMATTER
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
        help="parts to build, comma-separated: docs, code (default: all the repo has)",
    )
    build_parser.set_defaults(handler=run_build_command)
    return parser


def add_format_option(parser: argparse.ArgumentParser) -> None:
    """Add the ``--format`` option (text or JSON output) to a command's parser.

    Args:
        parser: Parser of a command whose output can be printed as JSON.
    """
    parser.add_argument("--format", choices=["text", "json"], default="text", help="output format")


def run_check_command(args: argparse.Namespace) -> int:
    """Run the ``check`` command and print its problems.

    Returns exit status 1 when problems are found or ``--staged`` is used outside git, else 0.

    Args:
        args: Parsed ``check`` options; ``repo``, ``staged`` and ``code`` are used.
    """
    try:
        problems = Checker(args.repo).run(staged=args.staged, code=args.code)
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

    Returns exit status 1 when ``docspecsite.toml`` is not valid TOML or has an invalid value, else 0. Unknown
    settings are printed as warnings.

    Args:
        args: Parsed ``list`` options; ``repo``, the filters and ``format`` are used.
    """
    try:
        with print_warnings():
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
    sys.stdout.write(format_list(DocSet.load(args.repo).select(filters, config), args.format))
    return 0


def run_backlinks_command(args: argparse.Namespace) -> int:
    """Run the ``backlinks`` command and print the result.

    Returns exit status 2 when the argument is not a doc, else 0.

    Args:
        args: Parsed ``backlinks`` options; ``repo``, ``path`` (the doc to find links to) and ``format`` are used.
    """
    target = resolve_doc_path(args.repo, args.path)
    if target is None:
        print(f"not a doc: {args.path}", file=sys.stderr)
        return 2
    sys.stdout.write(format_backlinks(DocSet.load(args.repo).backlinks_by_target.get(target, ()), args.format))
    return 0


def show_warning(
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
        category: Class of the warning; :exc:`~docspecsite.errors.DocspecsiteWarning` and
            :exc:`~docspecsite.errors.InternalErrorWarning` are printed here.
        filename: File the warning was issued from, passed on for other warnings.
        lineno: Line the warning was issued from, passed on for other warnings.
        file: Stream to print to; None means stderr.
        line: Source line of the warning, passed on for other warnings.
    """
    if issubclass(category, (DocspecsiteWarning, InternalErrorWarning)):
        print(f"warning: {message}", file=file if file is not None else sys.stderr)
    else:
        show_other(message, category, filename, lineno, file, line)


@contextmanager
def print_warnings() -> Generator[None]:
    """Print docspecsite's warnings issued inside the block as ``warning: <message>`` on stderr."""
    with warnings.catch_warnings():
        warnings.showwarning = partial(show_warning, warnings.showwarning)
        yield


def run_build_command(args: argparse.Namespace) -> int:
    """Run the ``build`` command and print its warnings, errors and summary.

    Warnings are printed as they are issued. Returns exit status 2 for an unknown ref, 1 for a failed build or failed
    pages, else 0.

    Args:
        args: Parsed ``build`` options; ``repo``, ``ref``, ``out``, ``include_worktree``, ``strict`` and ``parts`` are
            used.
    """
    with print_warnings():
        try:
            parts = None if args.parts is None else parse_parts(args.parts)
        except ValueError as exc:
            print(f"docspecsite build: {exc}", file=sys.stderr)
            return 1
        try:
            result = run_build(
                args.repo,
                args.ref,
                Path(args.out),
                include_worktree=args.include_worktree,
                strict=args.strict,
                parts=parts,
            )
        except UnknownRefError:
            print(f"docspecsite build: unknown ref: {args.ref}", file=sys.stderr)
            return 2
        except (BuildError, GitError, OSError) as exc:
            print(f"docspecsite build: {exc}", file=sys.stderr)
            return 1
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    failed = f", {result.failed_count} failed" if result.failed_count else ""
    counts = f"{result.rendered_count} rendered, {result.cached_count} from cache{failed}"
    print(f"built {result.page_count} pages ({counts}) → {args.out}")
    return 1 if result.failed_count else 0


def main(argv: list[str] | None = None) -> int:
    """Run the ``docspecsite`` command line and return the exit status.

    Args:
        argv: Arguments after the program name, e.g. ``["check", "--staged"]``; None reads ``sys.argv``.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_usage()
        return 0
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
