---
title: "BASE-0001: Docs are checked and rendered by docspecsite"
summary: The docs are checked, listed and rendered with per-doc git history by docspecsite, a separate tool pinned to a git tag and used through a prek hook and docker compose services, so projects share one implementation of the method's rules.
layer: architecture
status: implemented
milestone: foundation
priority: must
decision: accepted
date: 2026-11-16
components: [docs-system]
tags: [adr, docs, tooling, versioning]
related:
  - architecture/docs-tooling.md
---

# BASE-0001: Docs are checked and rendered by docspecsite

## Context

The [meta rules](../../meta/index.md) need tooling: checks for front matter, links, indexes and the no-delete/no-rename rule on every commit, a status listing that works as the task list, and a site that shows the history of every doc, with loud old versions and links in old versions that lead to contemporary versions.
What such tooling must provide is specified in [docspecsite's docs](https://github.com/imposeren/docspecsite/blob/main/docs/behavior/index.md).
Several projects follow the same method, in different languages, and each should get rule changes without copying code.

## Options considered

1. **A general doc generator** (MkDocs, Sphinx, with multi-version plugins) — polished, but versions are whole-site snapshots per branch or tag: no per-doc history, no version-aware links, and the method's checks would still have to be written.
2. **A copy of the tool inside each project** — works offline and can be changed freely, but every fix and rule change has to be copied into every project, and the copies drift.
3. **docspecsite, a separate tool in its own repo, pinned per project** — one implementation of the rules; projects pin a git tag and use it through a prek hook (checks) and docker compose services built from its repo (list, build, serve); no package or container registry is needed.

## Decision

Option 3.
Each project pins one docspecsite version, the same in `.pre-commit-config.yaml` and `compose.yaml`, and keeps its settings in `docspecsite.toml`. Design: [docs-tooling.md](../docs-tooling.md).

## Consequences

- Projects in any language get the checks: prek installs the hook itself, and the site is built in a container.
- A change to a rule that the tool enforces lands in two places: the rule in the template, and its enforcement in docspecsite, followed by a version bump in each project.
- docspecsite's own design and decisions live in its repo.
