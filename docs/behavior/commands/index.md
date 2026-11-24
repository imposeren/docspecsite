---
title: Commands
summary: What the docspecsite commands share — the repo they work on, the start-up errors, the command table, input they cannot use and output into a pipe that closes early — with a doc for each of `check`, `list`, `backlinks` and `build`.
layer: behavior
status: [implemented, changed]
milestone: first-release
priority: must
code: [docspecsite.cli]
components: [cli, versioning, checks, queries, site]
tags: [cli, checks, rendering]
related:
  - scenarios/commands/index.md
  - behavior/commands/check.md
  - behavior/commands/list.md
  - behavior/commands/backlinks.md
  - behavior/commands/build.md
  - behavior/configuration.md
  - behavior/versioning-backends.md
  - behavior/repo-subdirectory.md
  - behavior/limits.md
  - behavior/requirements.md
  - architecture/docs-tooling.md
---

# Commands

docspecsite is used through one command line with four commands: `check` validates the docs, `list` and `backlinks` answer queries about them, and `build` renders the site.
This doc gives what the commands share: how they are run, the table of commands, input that cannot be used and output into a pipe that closes early.
Each command's options, output and exit codes are in a doc of its own.

## Running a command

> **Changed, not built yet.** Git is the only version control; `--optional-checks` knows only `code`, and deletes and renames are still rejected by `check --staged` ([check.md](check.md#what-the-check-reports)).

`docspecsite [--repo DIR] <command> [options]` works on the docs of one repo: the current directory, or `DIR` given with `--repo` (the [checked repo](../glossary.md)).
Every command reads `docspecsite.toml` from disk first ([configuration.md](../configuration.md)), then picks the [versioning backend](../glossary.md), the part of docspecsite that reads the project's version control ([versioning-backends.md](../versioning-backends.md)).
These stop every command with an error and exit code 1: a backend chosen by name that cannot read the checked repo (such as `git` outside a git repository), and `auto` finding more than one backend that recognizes it.
`list`, `build` and `backlinks` also stop when `backend` names no installed backend; `check` reports that as a problem ([configuration.md](../configuration.md#versioning)).
A subdirectory of a git repository stops every command with an error and exit code 1, also with `auto`, unless `backend = "none"` (for a docs project in a subdirectory, see [repo-subdirectory.md](../repo-subdirectory.md)).
`docspecsite --version` prints the installed version.
A command-line error (an unknown option, or an option value that is not valid, such as an unknown name in `--parts` or `--optional-checks`) stops the command before it starts, with a usage message on stderr (the command's error output) and exit code 2.

| Command | Does |
| -- | -- |
| `check [--optional-checks C,…] [--no-hints] [--strict]` | Runs every check ([DSR-20](check.md#requirements), [DSR-33](../docs-format.md#requirements)) on the working tree (the files as they are now on disk). `--no-hints` leaves out the hint lines under the problems ([DSR-51](check.md#requirements)). `--strict` makes warnings count as problems ([check](check.md#what-the-check-reports)). `--optional-checks` adds the optional checks it names: `code`, the code check ([DSR-36](check.md#requirements)), and the checks of the backend in use, such as `git:staged`, which reports docs marked in git as deleted or renamed in the next commit ("staged") ([DSR-6](../versioning-backends.md#versions-of-a-doc), [DSR-43](../versioning-backends.md#requirements)). |
| `list [--layer L] [--status S] [--component C] [--tag T] [--milestone M] [--priority P] [--format text\|json]` | Prints the docs whose front matter matches every given filter, from the working tree ([DSR-17](list.md#requirements)). |
| `backlinks <path> [--format text\|json]` | Prints the docs that link to `<path>` through body links, `related`, `redirect_to` or `superseded_by`, from the working tree ([DSR-28](backlinks.md#requirements)). |
| `build [--ref REF] [--out site] [--parts P,…] [--include-worktree] [--strict]` | Renders the static site; with version control, from the history of a [ref](../glossary.md), by default the commit that is checked out ([DSR-7](../site.md#rendering) … [DSR-19](../code-reference.md#requirements)). |

## Input that cannot be used

Input that docspecsite cannot use never ends a command with an error trace.
The cases below are the ones docspecsite handles; for text that is not UTF-8, anything else is outside what it supports ([limits.md](../limits.md#text-that-is-not-utf-8)).
`check` gives one problem and `build` one warning, each naming the file (with the line, when there is one) and the reason; that thing is left out, and the rest goes on:

```
<path>: <reason>
warning: <path>: <reason>; left out
```

The known cases:

- A package directory directly inside a code directory whose name Python cannot import (letters, digits and underscores, not starting with a digit, not a reserved word such as `class`), such as `src/a.b`: `directory name "a.b" is not a valid Python package name`. Only these top-level names are checked; subpackages are loaded as the code reference's reader handles them. With no valid package left, the code reference has no modules.
- A path in `code-dirs` that is a symlink pointing to a file instead of a directory: `symlink to a file, not a directory`. That path is left out.
- A link with nothing after `code:`, such as `[see](code:)`, in a doc's text or in a docstring: `empty code: target`. It is shown as its text, with no link and no marker. In a doc's text, `build` warns about it only for the doc's latest version, as for an unresolvable link.
- A file under `docs/`, a doc or any other file, whose name is not valid UTF-8: `name is not valid UTF-8, which breaks links to the rendered page`. The build gives it no page and does not copy it; `list` still lists such a doc, and `backlinks` finds no links to it, since a link is text and cannot name it. Wherever such a name is printed, each byte that is not UTF-8 shows as `\x` and two hex digits, such as `docs/guides/caf\xe9.md`. Outside `docs/`, such as in the code, a file is read under its name as it is.
- A commit subject that is not valid UTF-8: shown with `�` in place of each invalid byte sequence, with no problem or warning.

## Output into a pipe that closes early

When the program that reads the output of `list` or `backlinks` stops reading early, as in `docspecsite list | head -1`, the command stops writing, prints no error trace, and exits with the exit code it would have had anyway.

## Children

- [check.md](check.md) — The `check` command: what it validates, its problems, hints and warnings, its optional checks and exit codes (DSR-20, DSR-51, DSR-36).
- [list.md](list.md) — The `list` command: its filters, text and JSON output and exit codes (DSR-17).
- [backlinks.md](backlinks.md) — The `backlinks` command: which paths it takes, its output and exit codes (DSR-28).
- [build.md](build.md) — The `build` command: its options, docs-only and code-only builds, symlinks, links whose target is not found, its warnings and exit codes.

## See also

- [Scenarios](../../scenarios/commands/index.md) — exact cases for input that cannot be used and output into a pipe that closes early.
