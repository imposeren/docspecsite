---
title: Glossary — technical terms and tools
summary: Short definitions of technical terms and tools used in docspecsite's architecture docs (uv, prek, griffe, markdown-it-py, Mermaid, build context…).
layer: architecture
status: specified
components: []
tags: [glossary]
related:
  - meta/glossary.md
  - behavior/glossary.md
---

# Glossary — technical terms and tools

Documentation terms (ADR, layer, status…) are in [meta/glossary.md](../meta/glossary.md); docspecsite's own terms in [behavior/glossary.md](../behavior/glossary.md).

| Term | Meaning |
| -- | -- |
| **build context** | The files Docker builds an image from; docker compose can take it straight from a git URL and tag, such as `https://github.com/imposeren/docspecsite.git#v0.1.0`. |
| **BuildKit** | Docker's default image builder; supports cache mounts that keep package caches between builds. |
| **CI** | Continuous Integration: automatic checks and builds on every push / pull request. |
| **docker compose** | Tool that defines and runs multi-container setups from `compose.yaml`; projects run docspecsite's image through it. |
| **first-parent history** | The commits reached from a ref by following only each merge commit's first parent: the main line, without the commits of merged branches. |
| **griffe** | Python library that extracts docstrings and signatures from code; feeds the code reference. |
| **Jinja** | Python template engine that renders the site's HTML pages. |
| **markdown-it-py** | Python Markdown-to-HTML library used by docspecsite. |
| **mdformat** | Markdown formatter (Python); normalizes formatting without re-wrapping lines. |
| **Mermaid** | JavaScript library that draws diagrams from text in `mermaid` code blocks, in the browser. |
| **prek** | Fast drop-in replacement for `pre-commit`: runs checks as git commit hooks, and installs hooks from other repos pinned by tag. |
| **Pyrefly** | Fast Python type checker from Meta; checks type hints without running the code. |
| **pytest** | Python test runner. |
| **Ruff** | Fast Python linter and formatter (replaces flake8, isort, black). |
| **SemVer** | Semantic versioning: versions `MAJOR.MINOR.PATCH`, where MAJOR marks incompatible changes, MINOR new features, PATCH fixes. |
| **uv** | Fast Python package and project manager; installs Python itself from `.python-version`. |
