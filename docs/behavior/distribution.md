---
title: How projects run docspecsite
summary: Projects run the docs check as the `docs-check` prek hook and build and serve their site with a Docker image, both pinned to a docspecsite release tag, with nothing else to install on the host and few dependencies.
layer: behavior
status: [implemented, changed]
milestone: first-release
priority: must
components: [distribution]
tags: [requirements]
related:
  - behavior/requirements.md
  - behavior/commands.md
  - behavior/site.md
  - guides/using-docspecsite.md
  - architecture/docs-tooling.md
---

# How projects run docspecsite

A project does not install docspecsite itself: the docs check runs as a prek hook before each commit and in CI, and the site is built and served in a Docker image, both taken from docspecsite's repo at a release tag.
How to set this up is in [guides/using-docspecsite.md](../guides/using-docspecsite.md).

## Requirements

> **Changed, not built yet.** The deletes-and-renames check is still `check --staged`, which the `docs-check` hook runs. Git is the only version control, and every build needs it.

These requirements are part of the [DS-n](../meta/glossary.md#ds-n) numbering listed in [requirements.md](requirements.md):

- **DS-21** The check runs automatically before code leaves a developer's machine and again in CI: docspecsite provides it, with the git backend's `git:staged` check, as a prek hook, `docs-check`, that a project pins to a release tag ([guides/using-docspecsite.md](../guides/using-docspecsite.md)).
- **DS-22** Building and serving docs run through Docker, in an image built from docspecsite's repo at a release tag; the check runs as a prek hook in an environment prek creates.
  Nothing beyond Docker, prek and the project's version control (git by default) is required on the host.
- **DS-23** docspecsite keeps its dependencies minimal.

## See also

- [commands.md](commands.md#checks) — what the check validates.
- [Architecture](../architecture/docs-tooling.md) — how it is built.
