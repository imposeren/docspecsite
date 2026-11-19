---
title: "BASE-0004: mdformat for Markdown"
summary: mdformat formats Markdown with line breaks preserved and compact tables; it runs as a prek hook and in CI.
layer: architecture
status: implemented
milestone: foundation
priority: must
decision: accepted
date: 2026-11-16
components: [quality-gate]
tags: [adr, quality, markdown]
related:
  - architecture/quality-gate.md
---

# BASE-0004: mdformat for Markdown

## Context

The [quality gate](../quality-gate.md) runs deterministic checks as prek hooks and in CI.
The docs are the spec and many people and agents edit them, so Markdown formatting needs a concrete tool.
The constraints are few dependencies and everything runnable through prek or Docker.

## Options considered

1. **mdformat** (Python, with plugins for tables, front matter and GFM).
   It's a formatter, so it fixes files instead of just complaining.
2. **markdownlint-cli2** (Node).
   A linter with many rules, and it can fix some issues.
3. **Prettier** (Node).
   Formats Markdown among other things, and could also format a frontend later.
4. **None**.
   This relies on review alone.

## Decision

**mdformat** (option 1), with the `mdformat-gfm` plugin (tables and other GitHub-flavored Markdown) set to compact tables, and `mdformat-frontmatter` (front matter passes through unchanged).
mdformat normalizes Markdown formatting (lists, emphasis, spacing, tables) but **never re-wraps lines** (`wrap = "keep"`, its default).
Prettier was chosen first and dropped after its first run on these docs: it always pads tables to aligned columns, with no option to turn that off, so a change to one cell rewrites every row and table lines grow to hundreds of characters, against the per-sentence diffs this decision is for.
There is no line-length limit: authors rely on soft wrap in their editors and may put a line break after each sentence, so `git blame` and diffs work per sentence ([meta/authoring.md](../../meta/authoring.md#line-breaks)).
prek creates mdformat's environment itself, so the quality gate needs no Node and nothing on the host; formatters for other languages are chosen with those languages.

It runs as a prek hook and in CI.
Versions are pinned in `.pre-commit-config.yaml`.

## Consequences

- mdformat leaves almost no style options, which removes arguments about style.
- mdformat rewrites Markdown formatting (not line breaks), so its first run may cause a formatting-only change.
  That change goes in its own commit, separate from spec changes.
- mdformat and its plugins are three Python packages to pin; they run in an environment prek creates, so the host needs nothing more.
