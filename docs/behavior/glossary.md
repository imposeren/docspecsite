---
title: Glossary — docspecsite terms
summary: Plain-language definitions of the terms docspecsite's docs and output use — checked repo, problem, ref, site, page, version, code reference, ADR prefix.
layer: behavior
status: specified
components: []
tags: [glossary]
related:
  - meta/glossary.md
  - architecture/glossary.md
---

# Glossary — docspecsite terms

Documentation terms (layer, status, redirect doc, version of a doc…) are in [meta/glossary.md](../meta/glossary.md); technical terms and tools in [architecture/glossary.md](../architecture/glossary.md).

| Term | Meaning |
| -- | -- |
| **ADR prefix** | The letters before the number in an ADR ID, such as `BASE` in `BASE-0002`. A repo has its own prefix (`adr-prefix` in `docspecsite.toml`) and may hold external ADRs, taken from elsewhere with their IDs, whose prefixes `external-adr-prefixes` lists, such as the template's `BASE` ([configuration.md](configuration.md)). |
| **checked repo** | The git repository whose `docs/` docspecsite works on: the current directory, or the one given with `--repo`. |
| **code reference** | Pages generated from a project's Python code and its docstrings, one per module, for the latest code only. |
| **problem** | One thing `docspecsite check` found wrong, printed as `path:line: message`. |
| **ref** | A git branch, tag or commit; `docspecsite build` renders the history of one ref. |
| **site** | The static HTML files `docspecsite build` writes: one page per doc version, diffs, index pages and a machine listing. |
| **working copy version** | Uncommitted changes to a doc, shown as an extra newest version when the site is built with `--include-worktree`. |
