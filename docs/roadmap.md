---
title: Roadmap
summary: docspecsite's milestones in order, each with its goal; docs refer to them in their `milestone` field.
layer: root
status: implemented
components: []
tags: [overview, roadmap]
related:
  - meta/lifecycle.md
  - architecture/versioning.md
---

# Roadmap

Milestones in the order they are reached.
A milestone is a target state, not a list of tasks: it is reached when every doc with that `milestone` and `priority: must` is `implemented` ([meta/lifecycle.md](meta/lifecycle.md#using-status-as-a-task-list)).
Milestone ids (the values used in the `milestone` field) never change once used.

| Id | Goal |
| -- | -- |
| `foundation` | **Reached.** The project's machinery works: its own docs follow the template's method, the quality gate and the development environment are in place. The template's own decisions belong to this milestone. |
| `first-release` | **Reached with v0.1.0.** docspecsite checks, lists and renders a project's docs with per-doc history and a generated code reference, reads its settings from `docspecsite.toml`, accepts prefixed ADR IDs, and other repos use it through its prek hook and its Docker image built from a release tag. |
| `web-api-reference` | The HTTP API reference: a project's committed web API schema rendered with per-version pages, and `web-api:` links resolved ([behavior/web-api-reference.md](behavior/web-api-reference.md)). |
| `later` | Features planned for after the HTTP API reference, in no set order: a docs project in a repo subdirectory ([behavior/repo-subdirectory.md](behavior/repo-subdirectory.md)), versions from tags only ([behavior/tag-versions.md](behavior/tag-versions.md)) and symlinked docs ([behavior/doc-symlinks.md](behavior/doc-symlinks.md)). |
