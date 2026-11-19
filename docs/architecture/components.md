---
title: Components
summary: The list of the project's components — the allowed values of the `components` front-matter field and the path segments used across layers.
layer: architecture
status: implemented
components: []
tags: [overview, components]
related:
  - meta/vocabulary.md
  - architecture/index.md
---

# Components

The parts of the project, used in docs' `components` field and as [mirrored path](../meta/structure.md#mirrored-paths) segments in every layer.
How components work in general, and the components every project has (`docs-system`, `agents`): [meta/vocabulary.md](../meta/vocabulary.md).
Add a component here in the same change that first uses it.

A project adds its own components in sections, e.g. **Product** (the parts users see and talk about) and **Project infrastructure** (the machinery around the code), one table row per component: its name (lowercase, `-`-separated, `/` for a sub-part such as `payments/card`) and a one-line meaning.

## Project infrastructure

| Component | Meaning |
| -- | -- |
| `quality-gate` | Pre-commit checks, CI and review. |
| `dev-environment` | Local development setup (docker compose). |
| `deploy` | Releasing and deploying the project. |
