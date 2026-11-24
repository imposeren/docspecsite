---
title: Glossary — technical terms and tools
summary: Short definitions of technical terms and tools used in docspecsite's architecture docs (uv, prek, Sphinx, MyST-Parser, sphinx-autoapi, furo, griffe, markdown-it-py, Mermaid, site renderer, build context, entry point…).
layer: architecture
status: changed
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
| **astroid** | Python library that parses Python code into a tree without importing it; sphinx-autoapi reads the code with it. |
| **build context** | The files Docker builds an image from; docker compose can take it straight from a git URL and tag, such as `https://github.com/imposeren/docspecsite.git#v0.1.0`. |
| **build front** | The part of `docspecsite build` that loads the settings, history, docs, code and parts, hands them to the site renderer and writes its output ([site.md](site.md#build-front)). |
| **BuildKit** | Docker's default image builder; supports cache mounts that keep package caches between builds. |
| **CI** | Continuous Integration: automatic checks and builds on every push / pull request. |
| **content key** | A hash of a doc version's text that a versioning backend gives (git: the blob SHA); the `internal` renderer's build cache names entries by it. |
| **docker compose** | Tool that defines and runs multi-container setups from `compose.yaml`; projects run docspecsite's image through it. |
| **docutils** | Python library that Sphinx builds on: the document tree and the reStructuredText reader that docstrings go through. |
| **entry point** | Python packaging metadata by which an installed package offers a named object to another, in a group such as `docspecsite.versioning`; found with `importlib.metadata.entry_points`. |
| **first-parent history** | The commits reached from a ref by following only each merge commit's first parent: the main line, without the commits of merged branches. |
| **furo** | A Sphinx theme: sidebar with the doc tree and the page's Contents, search box, light and dark modes; the `sphinx` renderer's fixed theme. |
| **griffe** | Python library that extracts docstrings and signatures from code without importing it; feeds the code check's lookup and the `internal` renderer's code reference. |
| **Jinja** | Python template engine; renders the `internal` renderer's HTML pages, and Sphinx's and furo's templates. |
| **markdown-it-py** | Python Markdown parser used by docspecsite for links, headings and status notes, by the `internal` renderer for HTML, and by MyST-Parser. |
| **mdformat** | Markdown formatter (Python); normalizes formatting without re-wrapping lines. |
| **Mermaid** | JavaScript library that draws diagrams from text in `mermaid` code blocks, in the browser. |
| **MyST-Parser** | Sphinx extension that reads Markdown (CommonMark plus MyST's own syntax, which docspecsite switches off) as Sphinx source. |
| **napoleon** | Sphinx's reader of Google- and NumPy-style docstring sections; docspecsite calls its public classes from its own listener. |
| **prek** | Fast drop-in replacement for `pre-commit`: runs checks as git commit hooks, and installs hooks from other repos pinned by tag. |
| **Pyrefly** | Fast Python type checker from Meta; checks type hints without running the code. |
| **pytest** | Python test runner. |
| **Python optional dependencies** | A named, optional set of dependencies of a Python package, declared under `[project.optional-dependencies]` in its `pyproject.toml` and installed with `package[name]`, such as `docspecsite[<backend>]`. |
| **Ruff** | Fast Python linter and formatter (replaces flake8, isort, black). |
| **SemVer** | Semantic versioning: versions `MAJOR.MINOR.PATCH`, where MAJOR marks incompatible changes, MINOR new features, PATCH fixes. |
| **site renderer** | The part of `docspecsite build` that turns the prepared input into the site's files: `sphinx` (default) or the temporary `internal` one, chosen by `[site] renderer` or `build --renderer` ([site.md](site.md#the-renderer-seam)). |
| **Sphinx** | Python documentation generator; the `sphinx` renderer drives it in-process with its configuration given in code ([DSS-0008](decisions/DSS-0008-sphinx-site-renderer.md)). |
| **sphinx-autoapi** | Sphinx extension that generates API reference pages from source code it parses with astroid, without importing it; builds the `sphinx` renderer's code reference. |
| **uv** | Fast Python package and project manager; installs Python itself from `.python-version`. |
| **versioning backend** | A class that gives docspecsite the version history of the docs from one version control system, or from none ([versioning-backends.md](versioning-backends.md)). |
