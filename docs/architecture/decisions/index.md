---
title: Architecture decision records
summary: Index of all ADRs in this repo, grouped by ID prefix — the template's BASE decisions and its Pyrefly option's PYRF decisions, then docspecsite's own DSS decisions — each recording one decision with context, options and consequences, and never renumbered.
layer: architecture
status: implemented
components: []
tags: [adr, overview]
related:
  - meta/lifecycle.md
  - meta/templates/adr.md
---

# Architecture decision records

An **ADR** ([architecture decision record](../../meta/glossary.md#adr)) records one decision: context, options considered, decision, consequences.
Each ADR has an ID `<PREFIX>-NNNN` that is never reused ([meta/structure.md](../../meta/structure.md#adr-ids)); a changed decision gets a **new** ADR and the old one becomes `decision: superseded` ([meta/lifecycle.md](../../meta/lifecycle.md#adrs)).
New ADRs start from [the template](../../meta/templates/adr.md) and use this repo's prefix, `DSS` (`adr-prefix` in `docspecsite.toml`).

## Children

Each line gives the ADR's `decision` and `status`, then its title ([meta/lifecycle.md](../../meta/lifecycle.md#adrs)).

### BASE — from the template

- [BASE-0001](BASE-0001-docs-checked-and-rendered-by-docspecsite.md) — accepted, implemented — Docs are checked and rendered by docspecsite
- [BASE-0002](BASE-0002-quality-gate-no-mistakes-and-prek.md) — accepted, specified — Quality gate: review before commit, prek on commit, CI after push
- [BASE-0003](BASE-0003-docker-compose-as-entry-point.md) — accepted, implemented — docker compose as the single entry point
- [BASE-0004](BASE-0004-mdformat-for-markdown.md) — accepted, implemented — mdformat for Markdown
- [BASE-0005](BASE-0005-semver-from-git-tags.md) — accepted, specified — Semantic versions tied to public-interface compatibility, defined only by git tags
- [BASE-0006](BASE-0006-projects-created-with-copier.md) — accepted, implemented — Projects are created from the template with Copier

### PYRF — Pyrefly option

- [PYRF-0001](PYRF-0001-pyrefly-language-server.md) — accepted, implemented — Pyrefly language server for agents

### DSS — docspecsite

- [DSS-0001](DSS-0001-custom-per-doc-history-renderer.md) — superseded, implemented — Custom static renderer with per-doc git history
- [DSS-0002](DSS-0002-single-python-toolchain.md) — accepted, implemented — One Python version and one uv project
- [DSS-0003](DSS-0003-ruff-and-strict-pyrefly.md) — accepted, implemented — Ruff for linting and formatting, strict Pyrefly for types
- [DSS-0004](DSS-0004-pytest-for-tests.md) — accepted, implemented — pytest for tests
- [DSS-0005](DSS-0005-entry-points-for-backends.md) — proposed, specified — Entry points for versioning backends
- [DSS-0006](DSS-0006-history-level-backend-contract.md) — proposed, specified — History-level backend contract with a layered git backend
- [DSS-0007](DSS-0007-git-command-line.md) — proposed, specified — git through its command line, not a git library
- [DSS-0008](DSS-0008-sphinx-site-renderer.md) — proposed, specified — Sphinx as the site renderer, behind a renderer seam
