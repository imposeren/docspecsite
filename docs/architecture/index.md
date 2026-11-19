---
title: Architecture overview
summary: Technical overview of the project — guiding principles, what is designed so far (docs tooling, quality gate, development environment, versioning), and where the application's own design goes.
layer: architecture
status: specified
components: []
tags: [overview, architecture]
related:
  - behavior/index.md
  - architecture/decisions/index.md
---

# Architecture overview

So far the architecture layer covers the **project's own machinery**: how documentation is checked and built, how quality is gated, how developers run things, and how releases are versioned.
The **application architecture** is added as behavior and scenario docs are written, at the same paths as the behavior it implements.

## Guiding principles

- **Documentation first.**
  Docs are the spec; code follows ([meta/index.md](../meta/index.md)).
- **Docker everywhere.**
  Every task — dev, tests, docs, CI steps — runs in containers defined in the repo ([dev-environment.md](dev-environment.md)).
- **Few dependencies in custom tooling.**
  Reach for an established library before writing code; keep custom scripts small.

## Children

- [docs-tooling.md](docs-tooling.md) — How docs are checked, rendered with per-doc history, and served, by docspecsite.
- [quality-gate.md](quality-gate.md) — review before commit, prek hooks on commit, CI after push.
- [dev-environment.md](dev-environment.md) — docker compose as the single entry point; host requirements.
- [versioning.md](versioning.md) — Release versions (SemVer tied to the public interface) and where they are defined.
- [decisions/index.md](decisions/index.md) — Architecture decision records ([ADRs](../meta/glossary.md#adr)).
- [components.md](components.md) — The list of components (front-matter values and path segments).
- [glossary.md](glossary.md) — Technical terms and tools.
