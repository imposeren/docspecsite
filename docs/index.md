---
title: docspecsite documentation
summary: Entry point to all documentation layers of docspecsite, the docs checker and per-doc-history site generator — what each layer is for and where to start reading.
layer: root
status: implemented
components: []
tags: [overview, navigation]
related:
  - meta/index.md
  - agents/index.md
---

# docspecsite documentation

docspecsite checks a repo's docs against the docs-driven method and renders every version of every doc from git history as a static site; it is for projects started from the [docs-driven template](https://github.com/imposeren/docs-driven-template) and for the people and agents who write their docs.

These docs are the **finished specification** of the system — they describe what the system is and does, not a history of changes.
Where docs and code disagree, the docs say what the code should become (see [lifecycle](meta/lifecycle.md)).

## Children

Documentation is organized in parallel **layers**.
Each one describes the same system from a different angle, and each has its own overview (`index.md`) with deeper docs below it.

- [meta/](meta/index.md) — How documentation itself works: structure, front matter, linking, versioning.
- [behavior/](behavior/index.md) — What docspecsite does: its requirements, commands and settings.
- [scenarios/](scenarios/index.md) — Concrete scenarios in Given / When / Then form.
- [architecture/](architecture/index.md) — Technical design, the Docker image and prek hook, and recorded decisions ([ADRs](meta/glossary.md#adr) — architecture decision records).
- [ui/](ui/index.md) — The user interface: docspecsite has none beyond its command line and the rendered site.
- [guides/](guides/index.md) — Step-by-step procedures: contributing, and using docspecsite in a project.
- [agents/](agents/index.md) — How AI agents (Claude Code) should work here; setup for Claude users.
- [reference/](reference/index.md) — Precise lookup information: the generated code reference.
- [roadmap.md](roadmap.md) — docspecsite's milestones in order; docs' `milestone` and `priority` fields say what belongs to which.

## Where to start

- **New to docspecsite (any role):** read this page, then [behavior/index.md](behavior/index.md).
- **Using it in a project:** [guides/using-docspecsite.md](guides/using-docspecsite.md).
- **Developer:** [architecture/index.md](architecture/index.md), then [architecture/dev-environment.md](architecture/dev-environment.md).
- **Writing or changing docs:** [meta/index.md](meta/index.md).
- **Unfamiliar term?**
  See the glossaries: [docs](meta/glossary.md), [docspecsite](behavior/glossary.md), [technical](architecture/glossary.md).
- **AI agent:** [agents/index.md](agents/index.md) — and read only as deep as your task needs.
