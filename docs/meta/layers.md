---
title: Documentation layers
summary: The parallel layers of documentation, who each is for, what belongs in each, and what does not.
layer: meta
status: implemented
components: [docs-system]
tags: [meta, layers, rules]
related:
  - meta/structure.md
  - meta/authoring.md
---

# Documentation layers

A **layer** is one parallel view of the whole system, written for a particular reader and purpose.
Layers are not sequential steps: the same feature typically appears in several layers at once, at mirrored paths (see [structure.md](structure.md#mirrored-paths)).

## Overview

| Layer | Directory | Reader | Answers |
| -- | -- | -- | -- |
| root | `docs/index.md` | everyone | Where do I start? |
| meta | `docs/meta/` | doc authors, agents | How do docs work here? |
| behavior | `docs/behavior/` | anyone, incl. non-developers | What does the system do, and why? |
| scenarios | `docs/scenarios/` | product, QA, developers | Exactly what happens in situation X? |
| architecture | `docs/architecture/` | developers, operators | How is it built, and why this way? |
| ui | `docs/ui/` | designers, frontend developers, product | What does the user see, and how do they move between screens? |
| guides | `docs/guides/` | developers, operators, agents | How do I do task X, step by step? |
| agents | `docs/agents/` | AI agents and their users | How should an agent work here? |
| reference | `docs/reference/` (partly generated) | developers, agents | What exactly does this module, endpoint or external platform offer? |

## meta

Rules of the documentation system itself. Tool-agnostic.
Changes here change how every other doc is written, so they should be rare and deliberate.

## behavior

Plain-language requirements: concepts, capabilities, rules and constraints the way a non-developer would explain them.
**Not here:** class names, endpoints, database tables, library names.
If a sentence would only make sense to a developer, it belongs in architecture.

## scenarios

Concrete, checkable situations in **Gherkin** (Feature / Scenario / Given / When / Then), embedded in Markdown so docs keep front matter and prose.
Each scenario names its actor ("As an anonymous visitor", "As a signed-in customer with a saved payment method").
Scenarios are precise enough to become automated acceptance tests later.
A scenario doc has no build status; each `Feature` links the section of the behavior or ui doc that owns its rule ([lifecycle.md](lifecycle.md#scenario-docs)).
**Not here:** implementation details; UI pixel specifics unless they *are* the behavior.

## architecture

Technical design: services, data model, integrations, infrastructure, tooling, and **decisions** recorded as ADRs ([architecture decision records](glossary.md#adr)) in `architecture/decisions/`.
Explains *why*, including options rejected.
It describes components, data, flows, invariants and decisions with their reasons, by their exact names.
**Not here:** per-function or per-endpoint reference (that is the reference layer), and a library's internals or line-level mechanics: those belong in the code's docstrings and, for an algorithm that is not obvious, in a comment where it is implemented.

## ui

The user interface: screens, user flows between them, layout and wireframes, and design-system rules (components, colors, typography).
Describes what users *see*; the behavior layer says what the system *does*, scenarios say exactly what happens.
**Not here:** frontend implementation (that is architecture).
Wireframes and flows are kept as text-based diagrams (Mermaid) or images committed next to the doc.

## guides

Step-by-step procedures for tasks people and agents perform on the project: "add an API endpoint", "add a database migration", "release and roll back", "rotate a secret".
A guide describes the **current** way to do something (target state, like every doc), not a one-off change.
Guides link to the architecture docs that explain *why*; architecture docs link to the guides that say *how to*.
**Not here:** explanations of design (architecture) or one-time instructions.

## agents

Guidance for AI agents: reading strategy, how to turn specs into work, conventions an agent must not break, and setup for people using Claude Code.
Complements the short root `CLAUDE.md`, which points here.

## reference

Precise lookup information. Three parts:

- `reference/code/` — **generated** from the code and its docstrings (the programming interface of the code); never edited by hand;
- `reference/web-api/` — **generated** from the committed, machine-readable schema of the web (HTTP) API; never edited by hand;
- `reference/external/` — **hand-written** facts about third-party platforms the project depends on: what their APIs offer, limits and quotas, terms of use, quirks; one doc (or directory) per platform, with links to the platform's own documentation and the date facts were checked.
  Hand-written docs link *into* it with `code:` and `web-api:` links, and code docstrings link *back* to hand-written docs (see [linking.md](linking.md#code-links)).

## Choosing a layer

Ask who needs the sentence you are writing:

- a non-developer needs it → **behavior**
- a tester needs to verify it → **scenarios**
- a developer needs to build or operate it → **architecture**
- it explains one function's contract → **docstring** (appears in **reference**)
- it defines a web API endpoint → the endpoint's code and schema (appears in **reference**)
- it says how to perform a task, step by step → **guides**
- it describes what a screen looks like or how users move between screens → **ui**
- it is a fact about a third-party platform (API capabilities, limits, terms) → **reference** (`reference/external/`)
- it tells an agent how to behave → **agents**

The same fact may legitimately appear in several layers at different levels of technicality; each layer then links to the others ([linking.md](linking.md)).
