---
title: The backlinks command
summary: The `backlinks` command (DSR-28) — the paths it takes, the links it counts, its text and JSON output and its exit codes.
layer: behavior
status: implemented
milestone: first-release
priority: must
code: [docspecsite.cli]
components: [queries, cli]
tags: [cli]
related:
  - scenarios/commands/backlinks.md
  - behavior/commands/index.md
  - behavior/commands/list.md
  - behavior/doc-symlinks.md
  - behavior/requirements.md
  - architecture/docs-tooling.md
---

# The backlinks command

`docspecsite backlinks <path>` prints the docs that link to a doc through body links, `related`, `redirect_to` or `superseded_by`, from the working tree, without rendering anything.
It is a query command for agents: its output is one line per linking doc, or JSON with `--format json`.

## Requirements

These requirements are part of the [DSR-n](../../meta/glossary.md#dsr-n) numbering listed in [requirements.md](../requirements.md).

- **DSR-28** A query command for agents: list the docs that link to a given doc (body links, `related`, `redirect_to`), without rendering.

## Options and output

`<path>` is `docs/x.md` (from the repo root), `x.md` (relative to `docs/`) or an absolute path.
It is read as written, without following symlinks; a path that leaves `docs/` through `..` is not a doc.
Each linking doc is printed on one line: its path, the kinds of its links (`body`, `related`, `redirect_to`, `superseded_by`) and its title, separated by tabs; `--format json` prints the same as a JSON list.
A link to a directory counts as a link to its `index.md`.
A doc that cannot be read, or that is not valid UTF-8, stops `backlinks` with an error naming the doc and exit code 1.
Otherwise the exit code is 2 when `<path>` is not a doc, with `not a doc: <path>` on stderr, else 0.
A doc template, a symlink and a path inside a symlinked directory are not docs ([DSR-39](../doc-symlinks.md#requirements)).
For output into a pipe that closes early, see [Output into a pipe that closes early](index.md#output-into-a-pipe-that-closes-early).

## See also

- [Scenarios](../../scenarios/commands/backlinks.md) — exact cases for the backlinks of a doc template.
