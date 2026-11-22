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
- [requirements.md](requirements.md) — The docs check's rules on a doc's title, and the heading a page without one shows.
