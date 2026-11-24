---
title: "DSS-0004: pytest for tests"
summary: docspecsite is tested with pytest, a development-only dependency, with tests in tests/ at the repo root that build throwaway docs trees and git repositories.
layer: architecture
status: implemented
milestone: first-release
priority: must
decision: accepted
date: 2026-11-17
components: [quality-gate, dev-environment]
tags: [adr, testing, python]
related:
  - architecture/decisions/DSS-0002-single-python-toolchain.md
  - architecture/docs-tooling.md
  - architecture/quality-gate.md
  - agents/working-from-specs.md
---

# DSS-0004: pytest for tests

## Context

docspecsite is built test-first ([agents/working-from-specs.md](../../agents/working-from-specs.md#implementing-a-specified-doc)), so it needs a test framework.
It must keep its runtime dependencies minimal ([DS-23](../../behavior/distribution.md#requirements)).
Most tests need a docs tree on disk, and many need a git repository with a known history.

## Options considered

1. **pytest** — the de facto standard Python test runner: plain `assert`, fixtures (e.g. `tmp_path` for throwaway docs trees and git repositories), parametrized tests, a large plugin ecosystem.
   It is one more dependency, but only for development.
2. **stdlib `unittest`** — no dependency at all, but more verbose (test classes, `self.assert…` methods), no fixtures, weaker parametrization.

## Decision

Option 1, **pytest**:

- it is in the `dev` dependency group of `pyproject.toml`, so it is locked in `uv.lock` but is never a runtime dependency, and the image installs without it;
- tests live in `tests/` at the repo root, named in pytest's `testpaths`;
- tests run with `docker compose run --rm test` ([dev-environment.md](../dev-environment.md#services)).

## Consequences

- Test-only helpers (fixtures that write docs trees and make commits) live in `tests/conftest.py`, not in the package.
- Tests that need git run the real `git` CLI, as docspecsite does, so git must be installed wherever the tests run.
