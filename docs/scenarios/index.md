---
title: Scenarios
summary: Overview of Given/When/Then scenarios that pin down docspecsite's exact behavior, written for new behavior; the behavior docs and the tests cover the rest.
layer: scenarios
status: draft
components: []
tags: [overview, gherkin]
related:
  - behavior/index.md
---

# Scenarios

Scenarios describe specific situations in Gherkin (Given / When / Then), one actor per scenario, at the same paths as the matching [behavior](../behavior/index.md) docs.
They are written to be checkable and can later become automated acceptance tests.

> Scenarios are written for new behavior; for the rest, [behavior/commands.md](../behavior/commands.md) and the tests pin it down.
> See [meta/layers.md](../meta/layers.md#scenarios) and [meta/templates/scenarios-doc.md](../meta/templates/scenarios-doc.md).

## Actors

Scenarios use these actor phrasings consistently:

- "a docs author" — a person or agent who writes or changes docs in a project and commits them.
- "a reader" — someone who reads a project's rendered site.

## Children

- [versioning-backends.md](versioning-backends.md) — Choosing where versions come from, building without version control, versions from tags only, link patterns and versioning backend checks.
- [status-notes.md](status-notes.md) — Partly built docs: status lists and status notes in the check, `list` and on the site.
- [requirements.md](requirements.md) — The index of the requirements' scenarios: a doc's title in docs-format.md, file names and links to a directory in commands.md.
- [docs-format.md](docs-format.md) — The docs check's rules on a doc's title, and the heading a page without one shows.
- [doc-symlinks.md](doc-symlinks.md) — Symlinks (files that only point to another file or directory) under `docs/`, judged by what they lead to: the check problem and its hints, how listings and the site leave symlinked docs out, and symlinked images on the site.
- [commands.md](commands.md) — The revision a build shows by default, source links of a preview and of a symlinked code directory, body links whose target is found or not found, unknown components in `code-components`, input that docspecsite cannot use, the backlinks of a doc template, output into a pipe that closes early, the characters that file names may not contain, and the anchors of links to a directory.
