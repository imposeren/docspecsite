---
title: Doc templates
summary: Copy-and-fill starting points for each kind of doc; templates themselves are not part of the spec.
layer: meta
status: implemented
components: [docs-system]
tags: [meta, templates]
related:
  - meta/authoring.md
---

# Doc templates

Copy a template to its target path, then replace every `<placeholder>`.
Template files are excluded from indexes and checks for placeholder values (their `status` is `implemented` because the *template* is in use, not because its content is true).

## Children

- [index-doc.md](index-doc.md) — An `index.md` overview of any directory.
- [behavior-doc.md](behavior-doc.md) — A behavior-layer doc.
- [scenarios-doc.md](scenarios-doc.md) — A scenarios-layer doc with Gherkin.
- [architecture-doc.md](architecture-doc.md) — An architecture design doc.
- [adr.md](adr.md) — An architecture decision record; `<PREFIX>` is the repo's `adr-prefix`, `NNNN` the next number of that prefix ([ADR IDs](../structure.md#adr-ids)).
- [guide-doc.md](guide-doc.md) — A step-by-step guide.
- [redirect-doc.md](redirect-doc.md) — Replacing a moved or removed doc.
