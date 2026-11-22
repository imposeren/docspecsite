---
title: "DSS-0005: Entry points for versioning backends"
summary: Versioning backends, built-in and third-party, are found through the Python entry-point group docspecsite.versioning, with a package.module:Class path as a way to load one without registering it.
layer: architecture
status: specified
milestone: later
priority: should
decision: proposed
date: 2026-11-22
components: [versioning]
tags: [adr, plugins, versioning]
related:
  - architecture/versioning-backends.md
  - behavior/versioning-backends.md
---

# DSS-0005: Entry points for versioning backends

## Context

Versions can come from more than one kind of version control ([DS-40](../../behavior/versioning-backends.md#requirements)).
Backends other than `git` and `none`, such as a Mercurial one, live in their own packages and repos, and a project picks one by a short name in `docspecsite.toml`.
docspecsite keeps its dependencies minimal ([DS-23](../../behavior/requirements.md#running)), and a backend must be found before any history is read, from the settings on disk alone.

## Options considered

1. **Python entry points** (`importlib.metadata.entry_points(group="docspecsite.versioning")`), declared by each package in `[project.entry-points."docspecsite.versioning"]` — the standard packaging mechanism (pytest, Sphinx and Flake8 plugins use it); standard library only; a name maps to a class without importing every plugin.
   A package must be installed to register; a typo in a name shows up only at run time.
2. **Only an import path** (`backend = "package.module:Class"`) — no registration at all, but long, implementation-shaped values in settings; built-in backends would need the same form or a special case.
3. **A plugin framework** (pluggy, stevedore) — hooks and plugin management docspecsite does not need; one more dependency.
4. **Namespace packages** (`docspecsite_backends.<name>` modules found by import) — no metadata, but fragile across install layouts and unusual for plugins today.

## Decision

Proposed: option 1, with option 2 as a second way to name a backend.
Built-in `git` and `none` register in docspecsite's own `pyproject.toml` the same way, so there is one lookup for every backend.
`package.module:Class` is resolved with `pkgutil.resolve_name`, which handles the same `module:attribute` form entry points use.
`auto` asks each registered backend whether it can handle the checked repo.

## Consequences

- A new version control is added by a separate package, without changing docspecsite (open–closed principle).
- Only installed packages register: the prek hook needs the backend in `additional_dependencies`, the Docker image a derived project image.
- A broken or missing backend is a settings problem named after `backend`, found when the command starts.
- Two installed backends that both recognize a repo make `auto` stop and ask for `backend`.
