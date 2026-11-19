---
title: "DSS-0003: Ruff for linting and formatting, strict Pyrefly for types"
summary: docspecsite's Python is linted and formatted with Ruff and type-checked with Pyrefly in strict mode; both run as prek hooks.
layer: architecture
status: implemented
milestone: first-release
priority: must
decision: accepted
date: 2026-11-17
components: [quality-gate]
tags: [adr, quality, python]
related:
  - architecture/quality-gate.md
  - architecture/decisions/DSS-0002-single-python-toolchain.md
---

# DSS-0003: Ruff for linting and formatting, strict Pyrefly for types

## Context

The [quality gate](../quality-gate.md) runs deterministic checks as prek hooks.
For docspecsite's Python code it needs a linter, a formatter and a type checker.
The constraints are few dependencies, everything installable through uv or prek, and one Python toolchain ([DSS-0002](DSS-0002-single-python-toolchain.md)).
Markdown formatting is the template's decision ([BASE-0004](BASE-0004-mdformat-for-markdown.md)).

## Options considered

**Lint + format**

1. **Ruff** (from Astral, the makers of uv).
   One fast tool that replaces flake8 (with most of its plugins), isort, pyupgrade and black-style formatting. Configured in `pyproject.toml`. Very widely adopted.
2. **black + flake8 + isort**.
   The classic setup: proven, but three tools and three configs, and much slower.
3. **pylint**.
   Very thorough, but slow and noisy, and it doesn't format code.

**Type checking**

1. **mypy**.
   The reference type checker, mature, with a big plugin ecosystem.
2. **Pyright**.
   Fast and strict, and powers VS Code's Pylance.
   Needs Node, or the `pyright` PyPI wrapper, which downloads Node.
3. **Pyrefly** (from Meta).
   A fast Rust type checker, stable (1.0), that installs as a Python package.
4. **ty** (from Astral).
   A very fast Rust type checker, but still pre-release (0.0.x).
5. **No type checking**.
   This forgoes a cheap and valuable check.

## Decision

- **Lint + format: Ruff.**
  It's the current standard: one tool, fast, and it has the fewest dependencies of the options.
- **Type checking: Pyrefly, strict from day one.**
  It's mature (1.0), fast enough to run on every commit and in every agent loop, and installs through uv.
  The code starts out fully typed, so strict mode costs almost nothing now and would be painful to turn on later. mypy is the fallback if Pyrefly falls short; ty can be reconsidered once it is stable, through a new ADR.

Both are pinned in the `dev` dependency group of `pyproject.toml`; the Ruff hook in `.pre-commit-config.yaml` is pinned to the same version.
The rule sets and settings: [quality-gate.md](../quality-gate.md#prek-on-commit).

## Consequences

- Ruff leaves almost no style options, which removes arguments about style.
- Every function and attribute is annotated; code that a strict checker cannot follow is rewritten rather than silenced.
