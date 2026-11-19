---
title: "BASE-0002: Quality gate — review before commit, prek on commit, CI after push"
summary: Changes are reviewed against their specs before they are committed, deterministic checks run as prek hooks on commit, and CI re-runs them after the push; no push gate (no-mistakes was considered and dropped).
layer: architecture
status: specified
milestone: foundation
priority: must
decision: accepted
date: 2026-11-16
components: [quality-gate]
tags: [adr, quality, agents]
related:
  - architecture/quality-gate.md
---

# BASE-0002: Quality gate — review before commit, prek on commit, CI after push

## Context

The project is documentation-driven and developed largely with AI agents.
We need (a) fast deterministic checks — especially docs integrity and no-delete/rename — and (b) review that understands intent, e.g. "does this code match its spec?", before code reaches the shared remote.

## Options considered

1. **pre-commit only** — deterministic only; Python-based, slower.
2. **prek** — drop-in `pre-commit` replacement (same config), single fast binary.
3. **CI-only review** (e.g. hosted PR review bots) — feedback arrives after pushing; ties review to a vendor.
4. **no-mistakes** — local git-proxy remote running review/test/docs/lint stages with a coding agent in a disposable worktree, auto-fixing mechanical issues, then pushing and opening the PR.
5. **Review before commit** — the change is reviewed against its specs (an agent review in a fresh context, then the maintainer) before it is committed, with prek on commit and CI after the push.

## Decision

prek (2) for commit-time hooks, and review before commit (5); CI re-runs prek as the backstop.
no-mistakes (4) was set up and tried on a throwaway branch, then dropped:

- every change is already reviewed against its specs before it is committed, so its review, test and docs stages repeated checks that had already run;
- what it added beyond that — checking a change live, and running in a clean worktree — is done without it: live checks are part of review, and agents use a git worktree or a fresh-context reviewer;
- it cost a background daemon, git 2.40+, workarounds for its handling of `CLAUDE_CONFIG_DIR`, and a script to get past its guard against rewritten history (amend, squash);
- it is not enforced anyway: pushing straight to `origin` skips it, so CI stays the real backstop. Design: [quality-gate.md](../quality-gate.md).

## Consequences

- Contributors install one host tool for the gate (prek).
- Review is a step of the workflow, not a mechanism: nothing technical stops an unreviewed push, and CI catches only what prek and the tests check.
- If agents later push without the maintainer reviewing each change, a push gate is reconsidered through a new ADR.
