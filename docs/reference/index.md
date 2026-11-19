---
title: Generated reference
summary: Entry point for precise lookup information — the generated code reference and HTTP (web) API reference, and hand-written facts about the external platforms the project depends on.
layer: reference
status: specified
components: [docs-system]
tags: [overview, reference, generated]
related:
  - architecture/docs-tooling.md
  - meta/linking.md
---

# Reference

Precise lookup information.
Two parts are **generated** during the docs build and never edited by hand; one is **hand-written**.

## Children

- [code/](code/index.md) — generated from docstrings and signatures; for developers and agents working inside the code.
- [web-api/](web-api/index.md) — generated from the committed schema of the web API; for frontend developers, API clients, agents.
- [external/](external/index.md) — hand-written from the platforms' own documentation: facts about the third-party platforms the project depends on (API capabilities, limits, terms).

How hand-written docs link here: `code:` links and `web-api:` links, see [meta/linking.md](../meta/linking.md#code-links).
