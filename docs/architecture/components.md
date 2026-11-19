---
title: Components
summary: The list of docspecsite's components — the allowed values of the `components` front-matter field and the path segments used across layers.
layer: architecture
status: specified
components: []
tags: [overview, components]
related:
  - meta/vocabulary.md
  - architecture/index.md
---

# Components

The parts of docspecsite, used in docs' `components` field and as [mirrored path](../meta/structure.md#mirrored-paths) segments in every layer.
How components work in general, and the components every project has (`docs-system`, `agents`): [meta/vocabulary.md](../meta/vocabulary.md).
Add a component here in the same change that first uses it.
`docspecsite.toml` maps the package's modules to these components for the code reference ([behavior/configuration.md](../behavior/configuration.md)).

## Product

| Component | Meaning |
| -- | -- |
| `cli` | The `docspecsite` command line, its settings file (`docspecsite.toml`) and how it reports errors. |
| `checks` | `docspecsite check`: front matter, ADR file names, links, indexes, names, staged deletes and renames. |
| `queries` | `docspecsite list` and `docspecsite backlinks`: answers about the docs without rendering. |
| `site` | `docspecsite build`: per-doc history from git, rendered pages, diffs, index pages, the machine listing and the build cache. |
| `code-reference` | Loading a project's Python code, its reference pages, and links between docs and code. |
| `distribution` | How other repos get docspecsite: the Docker image, the prek hook and release tags. |

## Project infrastructure

| Component | Meaning |
| -- | -- |
| `quality-gate` | Review, commit hooks and checks on docspecsite's own changes. |
| `dev-environment` | Setting up and running docspecsite from its source. |
| `deploy` | Releasing docspecsite: release tags. It runs nowhere itself; other repos build it from a tag. |
