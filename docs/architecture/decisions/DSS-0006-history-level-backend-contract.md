---
title: "DSS-0006: History-level backend contract with a layered git backend"
summary: A versioning backend returns the finished version history of the docs, not version-control primitives; the git backend is a history-level class built on today's low-level Git class, and both are public extension points.
layer: architecture
status: specified
milestone: later
priority: should
decision: proposed
date: 2026-11-22
components: [versioning, site]
tags: [adr, plugins, versioning, git]
related:
  - architecture/versioning-backends.md
  - architecture/docs-tooling.md
---

# DSS-0006: History-level backend contract with a layered git backend

## Context

docspecsite reads per-doc history from git through one class, `docspecsite.git.Git`, and builds `History` from its primitives ([docs-tooling.md](../docs-tooling.md#history-model)).
Versions must also come from no version control at all (`none`, [DSR-41](../../behavior/versioning-backends.md#requirements)) and from other systems in separate packages ([DSR-40](../../behavior/versioning-backends.md#requirements)), and git gains a choice of versions from commits or from tags ([DSR-38](../../behavior/versioning-backends.md#versions-from-tags-only)).
The contract between core and a backend decides how much of git's model leaks into core and into every other backend.

## Options considered

1. **Low-level contract** — a backend gives primitives (resolve a revision, a linear list of revisions, changes per path, contents, the working tree, staged changes, export of files); history, version selection and tags stay in core.
   Backends are small, but the contract is shaped by git (first-parent history, blobs, staging), `none` must fake revisions, and tag selection becomes a core feature that other systems must map to.
2. **History-level contract** — a backend returns the finished version history (versions with id, short id, date, message, label, position and content key; the texts; the files at the built revision), its capabilities, link patterns and optional checks.
   `none` is trivial, git-only options stay in git, and a plugin has full control; each plugin author writes their own version listing.
3. **History-level contract, with the git backend in two layers** — option 2 as the public contract; the git backend is a history-level class (settings, commits or tags) built on a low-level git class (today's `Git`), both documented, so a plugin can replace only the low-level part or subclass the history part.

## Decision

Proposed: option 3.
Core knows only the history-level contract; git's two layers follow the template-method pattern: version selection in the history class, primitives in the low-level class.

## Consequences

- Core loses its git calls; `History` and `Version` keep only backend-neutral fields, and the git-specific parts move into the git backend.
- Both git classes are public API: their signatures are part of the release rules ([versioning.md](../versioning.md#public-interface)) and need to stay stable.
- A git-like system (another git library, a store built on git) reuses git's version selection by providing only the low-level class.
- Other backends write their own version listing, a cost each plugin carries.
