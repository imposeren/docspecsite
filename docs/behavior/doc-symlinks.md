---
title: Symlinked docs
summary: Planned — a symlink under docs/ that points to another file inside docs/ is read as that file, by check and in every built version.
layer: behavior
status: specified
milestone: later
priority: could
components: [checks, site]
tags: [requirements, checks, versioning]
related:
  - behavior/requirements.md
  - behavior/commands.md
---

# Symlinked docs

A project may want the same doc at two paths, for example while a section moves.
A relative symlink inside `docs/` makes that possible without copying the text.

This requirement continues the numbering of [requirements.md](requirements.md):

- **DS-39** A symlink under `docs/` with a relative target inside `docs/` is read as its target, by `check` and in every version the build renders. Its versions are the commits that change the link or its target. A symlink with an absolute target, or one that leaves `docs/`, is a check problem.

## Not decided yet

- Whether a symlinked doc gets its own page or links to its target's page.
- Whether symlinked directories are followed.
