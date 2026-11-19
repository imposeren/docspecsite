---
title: Glossary — technical terms and tools
summary: Short definitions of technical terms, tools and services used in the architecture docs (docspecsite, prek, mdformat, compose, Caddy, SemVer…).
layer: architecture
status: implemented
components: []
tags: [glossary]
related:
  - meta/glossary.md
  - behavior/glossary.md
---

# Glossary — technical terms and tools

Documentation terms (ADR, layer, status…) are in [meta/glossary.md](../meta/glossary.md); product terms in [behavior/glossary.md](../behavior/glossary.md).

| Term | Meaning |
| -- | -- |
| **Caddy** | Web server and reverse proxy; serves the built docs site locally (`docs-serve`). |
| **CI** | Continuous Integration: automatic checks and builds on every push / pull request. |
| **docker compose** | Tool that defines and runs multi-container setups from `compose.yaml`; our single entry point for running anything. |
| **docspecsite** | The docs tool: checks, lists and renders docs with per-doc history. Its own repo, pinned to a version here. See [docs-tooling.md](docs-tooling.md). |
| **mdformat** | Markdown formatter (Python); normalizes formatting without re-wrapping lines. |
| **prek** | Fast drop-in replacement for `pre-commit`: runs checks as git commit hooks. |
| **SemVer** | Semantic versioning: versions `MAJOR.MINOR.PATCH`, where MAJOR marks incompatible changes, MINOR new features, PATCH fixes. |
