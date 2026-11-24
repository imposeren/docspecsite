---
title: "DSS-0001: Custom static renderer with per-doc git history"
summary: docspecsite is a small custom Python tool (markdown-it-py) that pre-renders every git version of every doc as static HTML, because existing doc generators only version whole sites.
layer: architecture
status: implemented
milestone: first-release
priority: must
decision: accepted
date: 2026-11-17
components: [docs-system, site]
tags: [adr, docs, tooling, versioning]
related:
  - architecture/docs-tooling.md
  - behavior/requirements.md
---

# DSS-0001: Custom static renderer with per-doc git history

## Context

The [docs system requirements](../../behavior/requirements.md) ask for **per-doc** history from git commits ([DSR-5](../../behavior/versioning-backends.md#versions-of-a-doc)), a version picker on each page ([DSR-8](../../behavior/site.md#rendering)), loud old-version warnings ([DSR-9](../../behavior/site.md#rendering)), and links in old versions that resolve to contemporary versions ([DSR-11](../../behavior/site.md#rendering)) — with minimal dependencies ([DSR-23](../../behavior/distribution.md#requirements)), running in Docker ([DSR-22](../../behavior/distribution.md#requirements)).

## Options considered

1. **MkDocs-Material / Zensical + `mike`** — polished, tags plugin, search.
   Versions are whole-site snapshots per branch/tag; no per-doc history, no version-aware links.
2. **Sphinx + MyST + `sphinx-multiversion`** — powerful cross-referencing, autodoc.
   Also whole-site snapshots per ref; heavy configuration; reST-centric ecosystem.
3. **Custom tool, pre-rendering every version statically** — exactly the required model; few dependencies (markdown-it-py, pyyaml, jinja2); build time grows with docs × commits, mitigated by incremental caching.
4. **Custom live server reading git per request** — no build step, but another running service and no static output.
5. **Custom tool, versions only at git tags** — fewer pages, but contradicts "every commit is a version".

## Decision

Option 3.
A small Python tool, **docspecsite**, using markdown-it-py for Markdown and the git CLI for history, producing a static site. Design: [docs-tooling.md](../docs-tooling.md).

## Consequences

- We own the code for navigation, indexes and search; no theme ecosystem.
- Full-text search is not provided initially (the agent-oriented `list` command and tag / component indexes cover navigation); a static search index can be added later.
- The tool is small enough to rewrite if requirements change, and the method's rules stay independent of it.
