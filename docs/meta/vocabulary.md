---
title: Vocabulary — components and tags
summary: How components and tags work — where the project's component list lives, the components every project using this documentation system has, and conventional tags.
layer: meta
status: implemented
components: [docs-system]
tags: [meta, vocabulary, components, tags]
related:
  - meta/front-matter.md
  - meta/structure.md
---

# Vocabulary — components and tags

## Components

A **component** is a named part of the system.
Docs list the components they are about in the `components` front-matter field, and component names double as [mirrored path](structure.md#mirrored-paths) segments.

- **The project's own components** are listed in **`architecture/components.md`**: it is part of the project's architecture, not of these rules.
- **Every project** using this documentation system also has the components below, because they come with the documentation system itself.
- A doc may only use components from these two lists; checks fail on unknown ones.
  Add a new component to `architecture/components.md` in the same change that first uses it.

| Component | Meaning |
| -- | -- |
| `docs-system` | The documentation system: these rules, its tooling, rendering. |
| `agents` | Guidance and tooling for AI agents working in the project. |

## Tags

Tags are free-form keywords (lowercase, `-`-separated) for search and tag indexes.
Prefer these conventional tags where they fit:

| Tag | Use for |
| -- | -- |
| `overview` | `index.md` docs and other overviews. |
| `rules` | Docs that state rules others must follow. |
| `adr` | Architecture decision records. |
| `glossary` | Glossaries. |
| `security`, `privacy`, `performance` | Docs mainly about these qualities. |
| `ux` | User-experience aspects. |
| `integration` | Talking to external systems. |
| `data-model` | Data structures and storage. |
