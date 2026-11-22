---
title: How documentation works
summary: Overview of the documentation system — layers, depth, front matter, linking, versioning and lifecycle — and the rules every doc follows.
layer: meta
status: implemented
components: [docs-system]
tags: [overview, meta, rules]
related:
  - architecture/docs-tooling.md
  - agents/reading-strategy.md
---

# How documentation works

This project is **documentation-driven**.
The docs are a finished, current specification of the system.
They double as the project's task list: anything the docs describe that the code does not yet do is work to be done.

This meta layer defines *how* docs are written, organized, linked and versioned.
It is deliberately **tool-agnostic**: it states rules and requirements, never which renderer or script implements them.
What any docs tooling must provide is specified in [docspecsite's docs](https://github.com/imposeren/docspecsite/blob/main/docs/behavior/index.md), the tool that checks and renders these docs; this project's tooling choices live in [architecture/docs-tooling.md](../architecture/docs-tooling.md).

## The rules in one screen

1. **Markdown only**, each file starting with YAML front matter → [front-matter.md](front-matter.md).
2. **Layers** are parallel views of the same system; **depth** is how detailed a doc is → [layers.md](layers.md), [structure.md](structure.md).
3. **Every directory has an `index.md`** that summarizes what is below it.
4. **Same part of the system ⇒ same relative path** in every layer that covers it → [structure.md](structure.md#mirrored-paths).
5. **Link down and across** (up is implied by the path); links must work in raw Markdown → [linking.md](linking.md).
6. **A commit is a version** (in the project's version control, usually git).
   Edit freely, commit deliberately → [versioning.md](versioning.md).
7. **Never delete or rename a doc** — turn it into a redirect doc instead → [versioning.md](versioning.md#no-delete-no-rename).
8. **Docs describe the target state**, not changes or bugs; `status` tracks how far the code has caught up → [lifecycle.md](lifecycle.md).
9. **Summary first.**
   A reader (human or agent) should be able to stop after the document brief, the first paragraph → [authoring.md](authoring.md).

## Children

- [layers.md](layers.md) — What each layer is for and what does *not* belong in it.
- [structure.md](structure.md) — Directory layout, depth, `index.md`, mirrored paths, growing a doc into a folder.
- [front-matter.md](front-matter.md) — Required and optional fields and their meaning.
- [linking.md](linking.md) — Link kinds (up/down/across/code), link syntax, backlinks.
- [versioning.md](versioning.md) — Commits (revisions) as versions, no-delete/no-rename, redirect docs.
- [lifecycle.md](lifecycle.md) — `status` values and how docs act as a task list.
- [authoring.md](authoring.md) — Writing style per layer and the doc [templates](templates/index.md).
- [templates/](templates/index.md) — Copy-and-fill starting points for each kind of doc.
- [vocabulary.md](vocabulary.md) — How `components` and `tags` work; where the project's component list lives; conventional tags.
- [glossary.md](glossary.md) — Documentation terms and abbreviations (ADR, layer, depth…); pointers to the product and technical glossaries.

## Forking only this layer

If you copy this layer into another project: keep or edit the rules above, replace [vocabulary.md](vocabulary.md), and record your tooling choice in your own architecture layer.
The requirements for the tooling are part of [docspecsite's docs](https://github.com/imposeren/docspecsite/blob/main/docs/behavior/index.md); check them against your own constraints.
