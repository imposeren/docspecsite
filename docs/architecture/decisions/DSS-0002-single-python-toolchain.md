---
title: "DSS-0002: One Python version and one uv project"
summary: docspecsite is one uv project at the repo root, with its Python version pinned once in .python-version and one lockfile; the Docker image gets Python through uv from the same pin.
layer: architecture
status: implemented
milestone: first-release
priority: must
decision: accepted
date: 2026-11-17
components: [dev-environment, distribution]
tags: [adr, python, uv]
related:
  - architecture/dev-environment.md
  - architecture/docs-tooling.md
---

# DSS-0002: One Python version and one uv project

## Context

docspecsite is written in Python.
Its Python version is needed in several places: on contributors' machines, in the Docker image other repos build, and in the environment prek creates for the `docs-check` hook.
The version should be declared in one place, and the dependencies locked, so that every place runs the same code.

## Options considered

1. **One uv project** (`pyproject.toml` at the repo root), **one `uv.lock`**, and a root **`.python-version`** as the single pin. uv uses `.python-version` both on the host and in the image.
2. **Option 1, but the image based on `python:X.Y-slim`.**
   The version would then be repeated in the `Dockerfile` (or passed as a build argument kept in sync by hand).
3. **pip with a `requirements.txt`** — no lockfile with hashes for every platform, no Python installation, and a second tool for the virtual environment.

## Decision

Option 1:

- **`.python-version`** at the repo root is the single source of truth for the version: **3.14**, the newest release that has been stable for about a year.
- `pyproject.toml` declares the package with `requires-python = ">=3.14,<3.15"`, its runtime dependencies, and a `dev` dependency group for the development tools; `uv.lock` locks them all.
- The `Dockerfile` starts from an official **uv** base image and runs `uv sync --frozen`, which installs the Python version from `.python-version`.
  No Python version appears in the `Dockerfile`.
- The package is the repo itself (`src/docspecsite/`), not a member of a workspace.

## Consequences

- Upgrading Python is a one-line change plus a lockfile refresh, and it applies everywhere at once.
- The image installs exactly the locked dependencies; the `docs-check` hook, installed by prek, resolves them from `pyproject.toml` within the same bounds.
- Projects that use docspecsite need no Python of their own: the image and prek provide it.
