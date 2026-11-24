---
title: Docs project in a repo subdirectory
summary: docspecsite works on a docs project that lives in a subdirectory of a git repo, such as one service of a monorepo.
layer: behavior
status: specified
milestone: later
priority: could
components: [cli, checks, queries, site]
tags: [requirements, cli, versioning]
related:
  - behavior/commands.md
  - behavior/requirements.md
---

# Docs project in a repo subdirectory

A monorepo can hold several projects, each with its own `docs/`, `docspecsite.toml` and code.
docspecsite then works on one of them, given with `--repo` or as the current directory.
Until this is built, a subdirectory of a git repo stops every command with an error ([commands.md](commands.md)).

This requirement is part of the [DS-n](../meta/glossary.md#ds-n) numbering listed in [requirements.md](requirements.md):

- **DS-37** The checked repo can be a subdirectory of a git repository. Paths in settings and output stay relative to that subdirectory, and a doc's versions are the commits that touch it, as for a repo of its own.

## Not decided yet

- Whether settings and `source-url` links need the subdirectory's path in the repository, or docspecsite finds it from git.
