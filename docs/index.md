---
title: "docspecsite documentation"
summary: Entry point to all documentation layers — what each layer is for and where to start reading.
layer: root
status: implemented
components: []
tags: [overview, navigation]
related:
  - meta/index.md
  - agents/index.md
---

# docspecsite documentation

docspecsite checks a repo's docs and renders every version of every doc from git history to a static site.

These docs are the **finished specification** of the system — they describe what the system is and does, not a history of changes.
Where docs and code disagree, the docs say what the code should become (see [lifecycle](meta/lifecycle.md)).

## Children

Documentation is organized in parallel **layers**.
Each one describes the same system from a different angle, and each has its own overview (`index.md`) with deeper docs below it.

- [meta/](meta/index.md) — How documentation itself works: structure, front matter, linking, versioning.
- [behavior/](behavior/index.md) — What the system does and why, in plain non-technical language.
- [scenarios/](scenarios/index.md) — Concrete user scenarios in Given / When / Then form.
- [architecture/](architecture/index.md) — Technical design, infrastructure, and recorded decisions ([ADRs](meta/glossary.md#adr) — architecture decision records).
- [ui/](ui/index.md) — Screens, user flows and design-system rules.
- [guides/](guides/index.md) — Step-by-step procedures: how to do common development and operations tasks.
- [agents/](agents/index.md) — How AI agents (Claude Code) should work here; setup for Claude users.
- [reference/](reference/index.md) — Precise lookup information: generated code and HTTP API reference, and hand-written facts about external platforms.
- [roadmap.md](roadmap.md) — the project's milestones in order; docs' `milestone` and `priority` fields say what belongs to which.

## Where to start

- **New to the project (any role):** read this page, then [behavior/index.md](behavior/index.md).
- **Developer:** [architecture/index.md](architecture/index.md), then [architecture/dev-environment.md](architecture/dev-environment.md).
- **Doing a specific task (setup, migration, release…):** [guides/index.md](guides/index.md).
- **Writing or changing docs:** [meta/index.md](meta/index.md).
- **Unfamiliar term?**
  See the glossaries: [docs](meta/glossary.md), [product](behavior/glossary.md), [technical](architecture/glossary.md).
- **AI agent:** [agents/index.md](agents/index.md) — and read only as deep as your task needs.
