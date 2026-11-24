---
title: The list command
summary: The `list` command (DSR-17) — its filters, its text and JSON output, its order and its exit codes.
layer: behavior
status: implemented
milestone: first-release
priority: must
code: [docspecsite.cli]
components: [queries, cli]
tags: [cli]
related:
  - behavior/commands/index.md
  - behavior/commands/backlinks.md
  - behavior/status-notes.md
  - behavior/site.md
  - behavior/requirements.md
  - architecture/docs-tooling.md
---

# The list command

`docspecsite list` prints the docs whose front matter matches every given filter, from the working tree, without rendering anything.
It is a query command for agents: its output is one line per doc, or JSON with `--format json`.

## Requirements

These requirements are part of the [DSR-n](../../meta/glossary.md#dsr-n) numbering listed in [requirements.md](../requirements.md).

- **DSR-17** A query command for agents: list docs filtered by tag / component / status / layer / milestone / priority, without rendering; a partly built doc matches each of its statuses ([DSR-47](../status-notes.md#requirements)).

## Options and output

`--status S` matches a doc that has `S` anywhere in its `status`, so a partly built doc is found under each of its statuses ([DSR-47](../status-notes.md#requirements)).
Text output has one line per doc: path, status, title and summary, separated by tabs; a list of statuses is shown comma-separated without spaces, in the doc's order (`implemented,specified`).
`--format json` prints a JSON list with the path and the fields `title`, `summary`, `layer`, `status`, `components`, `tags`, `milestone` and `priority`; `status` is a string for a single status and a list of strings for a list.
Docs are sorted as listings that include ADRs are ([site.md](../site.md#navigation-and-indexes)).
Docs whose front matter does not load are left out.
A `docspecsite.toml` that is not valid TOML or has an invalid value stops `list` with an error and exit code 1; an unknown setting is a warning.
A doc that cannot be read, or that is not valid UTF-8, stops `list` with an error naming the doc and exit code 1.

For a doc whose name is not valid UTF-8, see [Input that cannot be used](index.md#input-that-cannot-be-used).

For output into a pipe that closes early, as in `docspecsite list | head -1`, see [Output into a pipe that closes early](index.md#output-into-a-pipe-that-closes-early).

## See also

- [Commands](index.md) — what all commands share, such as input that cannot be used.
