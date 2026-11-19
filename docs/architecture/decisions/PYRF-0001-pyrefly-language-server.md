---
title: "PYRF-0001: Pyrefly language server for agents"
summary: In Python projects that type-check with Pyrefly, agents look up code through Pyrefly's own language server, run by the pyrefly-lsp Claude Code plugin with Pyrefly at the project's pinned version on the PATH, so the type errors agents see while editing match the project's type check.
layer: architecture
status: implemented
milestone: foundation
priority: should
decision: accepted
date: 2026-11-19
components: [agents]
tags: [adr, agents, python, language-server]
related:
  - agents/code-lookup.md
---

# PYRF-0001: Pyrefly language server for agents

Agents look up Python code through Pyrefly's own language server, at the project's pinned Pyrefly version, so the type errors they see while editing are the ones the project's type check reports.

## Context

Agents look up code through a language server that a Claude Code plugin starts ([agents/code-lookup.md](../../agents/code-lookup.md)).
The template's default for Python is Anthropic's `pyright-lsp`.
A project that type-checks with Pyrefly would then see Pyright's type errors while editing and Pyrefly's in its checks, and the two disagree in places.

## Options considered

1. **Anthropic's `pyright-lsp`** (the default): mature, but a second type checker whose errors differ from the project's.
2. **A community Pyrefly plugin**: the existing ones are small single-author projects with little use.
3. **`pyrefly-lsp` from [imposeren/claude-pyrefly-lsp](https://github.com/imposeren/claude-pyrefly-lsp)**: built like Anthropic's language-server plugins; it only names the server (`pyrefly lsp`), and Pyrefly comes from the `PATH`.

## Decision

- Option 3: the project's `.claude/settings.json` adds the `claude-pyrefly-lsp` marketplace and enables `pyrefly-lsp@claude-pyrefly-lsp`.
- `pyrefly` on the `PATH` is the version the project pins, either:
  - the project's own virtual environment first on the `PATH`, through a local, git-ignored direnv `.envrc` (`source_up` and `PATH_add .venv/bin`), which applies when Claude Code starts in the project directory; or
  - a global `uv tool install pyrefly==<pinned version>`, also for sessions started elsewhere.
- Pyrefly finds the project's `.venv` on its own, which gives it the installed libraries; a virtual environment elsewhere is set with `python-interpreter-path` in the project's Pyrefly config.
- Find references works with Pyrefly's default background indexing.

## Consequences

- The type errors agents see after an edit are the project's own type check's.
- Contributors install Pyrefly, or use direnv with the project's synced `.venv`; `/.envrc` is in `.gitignore`.
- The plugin's README has the setup details.
- This ADR comes with the template's Pyrefly option: only projects that chose Pyrefly as their Python language server hold it.
