---
title: "DSS-0007: git through its command line, not a git library"
summary: The git backend keeps running the git program through subprocess instead of using a Python git library, so it reads history exactly as the user's git does, with the same filters, attributes and configuration.
layer: architecture
status: specified
milestone: later
priority: should
decision: proposed
date: 2026-11-22
components: [versioning]
tags: [adr, git, versioning]
related:
  - architecture/versioning-backends.md
  - architecture/docs-tooling.md
  - architecture/decisions/DSS-0001-custom-per-doc-history-renderer.md
---

# DSS-0007: git through its command line, not a git library

## Context

[DSS-0001](DSS-0001-custom-per-doc-history-renderer.md) chose a custom renderer "using the git CLI for history", without weighing git libraries.
With git becoming one backend behind a contract ([DSS-0006](DSS-0006-history-level-backend-contract.md)), its low-level class is public and a library could replace the command line.
The git backend must see files exactly as the user's git does: line-ending conversion, clean filters such as Git LFS, attributes and the user's configuration (for example when deciding whether a working-tree file changed).
Bugs found in an earlier review all came from doing in Python what git already does.

## Options considered

1. **The `git` command line** through `subprocess` (today) — identical behavior to the user's git, including filters and attributes; no Python dependency; one process per call, mitigated by batched calls (`cat-file --batch`, one `log` per ref).
2. **GitPython** — a Python API, but it runs the `git` program for most operations anyway; one more dependency for little gain.
3. **pygit2 (libgit2)** — fast, in-process; runs no external filter drivers (such as LFS) and differs from git on line-ending and attribute edge cases; a compiled dependency.
4. **dulwich** — pure Python; limited support for filters and attributes.

## Decision

Proposed: option 1, as today; this records the reasons DSS-0001 did not.
`git for-each-ref` lists tags for `versions = "tags"`.
Another library can still be used by a separate package that replaces the low-level git class ([DSS-0006](DSS-0006-history-level-backend-contract.md)).

## Consequences

- The `git` program is required wherever the git backend runs: in the Docker image (installed) and on the host for the prek hook (where git already is).
- No new dependency ([DS-23](../../behavior/distribution.md#requirements)).
- Process start-up cost per call stays; calls are batched where git allows it.
