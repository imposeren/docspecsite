---
title: Architecture overview
summary: Technical overview of docspecsite — guiding principles, how the tool is built and shipped, its development environment, quality gate and releases, and the recorded decisions.
layer: architecture
status: [changed, implemented]
components: []
tags: [overview, architecture]
related:
  - behavior/index.md
  - architecture/decisions/index.md
---

# Architecture overview

docspecsite is one Python package that reads a repo's `docs/` and its history through a versioning backend (git by default); it ships to other repos as a Docker image and a prek hook, both taken from this repo at a release tag.

## Guiding principles

> **Built.**

- **Documentation first.**
  Docs are the spec; code follows ([meta/](../meta/index.md)).
  docspecsite's own docs follow the same method as the projects it checks.
- **The method's rules are not configuration.**
  docspecsite implements the rules of the template's `docs/meta/`; only project settings (ADR prefix, source URL, code location) are configurable ([behavior/configuration.md](../behavior/configuration.md)).
- **Established libraries, each for a reason.**
  Reach for an established library before writing docspecsite's own code; every dependency is listed with its reason in [docs-tooling.md](docs-tooling.md#dependencies), and a new one needs an ADR ([DSR-23](../behavior/distribution.md#requirements)).
- **Static output.**
  The site is plain files that need no server-side code ([DSR-25](../behavior/site.md#building)).
- **No registry.**
  Other repos build the image and install the hook straight from this repo's git tags ([docs-tooling.md](docs-tooling.md#how-other-repos-use-docspecsite)).

## Children

- [docs-tooling.md](docs-tooling.md) — How docspecsite works: modules, configuration, history model, rendering, code reference, Docker image and prek hook.
- [site.md](site.md) — How the site is built: the build front, the renderer seam, and the `sphinx` renderer on Sphinx, MyST-Parser, sphinx-autoapi and furo next to the temporary `internal` renderer.
- [versioning-backends.md](versioning-backends.md) — Pluggable versioning backends: the history-level contract, finding a backend, the git and none backends.
- [components.md](components.md) — The list of components (front-matter values and path segments).
- [dev-environment.md](dev-environment.md) — docker compose as the entry point for working on docspecsite; the dev and runtime images.
- [quality-gate.md](quality-gate.md) — Review before commit and the prek hooks; tests before releases.
- [versioning.md](versioning.md) — Release tags, what counts as an incompatible change, and how to release.
- [decisions/](decisions/index.md) — Architecture decision records ([ADRs](../meta/glossary.md#adr)), the template's and docspecsite's own.
- [glossary.md](glossary.md) — Technical terms and tools.
