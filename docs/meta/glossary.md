---
title: Glossary — documentation terms
summary: Definitions of the terms and abbreviations used by the documentation system itself (layer, depth, ADR, status, redirect doc…), and where the other glossaries live.
layer: meta
status: implemented
components: [docs-system]
tags: [meta, glossary]
related:
  - architecture/glossary.md
  - behavior/glossary.md
---

# Glossary — documentation terms

Each glossary covers its own kind of term:

- **documentation terms** — this page;
- **product terms** (what users see and talk about) — [behavior/glossary.md](../behavior/glossary.md);
- **technical terms and tools** — [architecture/glossary.md](../architecture/glossary.md).

Rule: the **first use** of an abbreviation or project-specific term in a doc is either spelled out or linked to its glossary entry ([authoring.md](authoring.md#terms-and-abbreviations)).

## Terms

### ADR

**Architecture Decision Record.**
A short doc recording *one* technical decision: context, options considered, the decision, consequences.
Unlike other docs it is never rewritten; a changed decision gets a new ADR that *supersedes* the old one.
Has a `decision` state: `proposed` → `accepted` → (`superseded`). Lives in `architecture/decisions/`. See [lifecycle.md](lifecycle.md#adrs).
Its ID is `<PREFIX>-NNNN`: the repo's prefix and a number from that prefix's own sequence, e.g. `BASE-0002` for an ADR that comes from the template. IDs are unique across repos, so other repos cite an ADR by its ID. See [structure.md](structure.md#adr-ids).

### Backlink

A link computed by tooling: "these docs link to this one".
Never written by hand.

### Component

A named part of the system (e.g. `orders`, `payments/card`), used in front matter and as path segments.
The project's list is in `architecture/components.md`; how components work: [vocabulary.md](vocabulary.md).

### DSR-n

A numbered requirement for the docs tooling (DSR = "docs system requirement"), specified in [docspecsite's docs](https://github.com/imposeren/docspecsite/blob/main/docs/behavior/index.md).
Architecture docs cite these numbers to say which requirement a design element satisfies.

### Depth

How detailed a doc is, given by its position in its layer's directory tree; `index.md` at a layer's root is depth 0. See [structure.md](structure.md#depth).

### Document brief

The paragraph right after a doc's title, its level-1 heading: the whole doc in 2–5 sentences, so a reader who stops there has a correct picture. Not the front-matter `summary`, which is one sentence for listings. See [authoring.md](authoring.md#page-shape).

### Front matter

The YAML block at the top of each doc holding its metadata. See [front-matter.md](front-matter.md).

### Gherkin

A structured plain-language format for scenarios: `Feature`, `Scenario`, `Given` (context), `When` (action), `Then` (outcome).
Used in the scenarios layer.

### Layer

One parallel view of the whole system for a particular reader: meta, behavior, scenarios, architecture, ui, guides, agents, reference. See [layers.md](layers.md).

### Reference layer

Precise lookup information: code reference and HTTP API reference (both generated), and hand-written facts about external platforms (`reference/external/`).

### Milestone

A named step of the project's roadmap (listed in `roadmap.md` at the docs root). Docs' `milestone` field says which step their target state belongs to.

### Mirrored path

The rule that the same part of the system has the same relative path in every layer covering it. See [structure.md](structure.md#mirrored-paths).

### Old version

Any version of a doc other than the latest.
Always shown with a loud warning. See [versioning.md](versioning.md#old-versions-are-loud).

### Priority

How important a doc's target state is within its milestone: `must`, `should` or `could`.

### Redirect doc

What a doc becomes instead of being deleted or renamed: `status: redirect` plus `redirect_kind` (what happened), `redirect_to` (where the content went) and `reason` (why). It is a normal page with a notice and a link, never an automatic redirect. See [versioning.md](versioning.md#no-delete-no-rename).

### Section note

A note line in the block right after a heading, before any other content, recognized by the bold label at its start, such as a [status note](#status-note). A note line with an unknown label is ordinary text. See [lifecycle.md](lifecycle.md#section-notes).

### Spec

Short for specification.
Here: any doc in `docs/` — a description of the system's target state.

### Status

Where a doc is in its lifecycle: `draft`, `specified` (agreed, not built — i.e. work to do), `changed` (agreed, built in an older form — also work to do), `implemented`, `deprecated`, `redirect`. A partly built doc lists several of `implemented`, `specified` and `changed`, and marks its sections with [status notes](#status-note). Some layers have no [build status](#build-status). See [lifecycle.md](lifecycle.md).

### Build status

The `status` values that say how far the code has caught up with a doc: `specified`, `changed` and `implemented`. Docs in the layers listed in lifecycle.md, today scenario docs, carry none ([lifecycle.md](lifecycle.md#layers-without-a-build-status)).

### Status note

The kind of [section note](#section-note), such as `> **Not built yet.**`, that gives its section, a heading and its text up to the next heading of any level, a status other than the doc's first `status` value, in a partly built doc. It does not cover the sections under deeper headings below it. A section has at most one; the doc's title and its [document brief](#document-brief) carry none, as the doc's whole `status` describes them. See [lifecycle.md](lifecycle.md#status-notes).

### Version (of a doc)

A revision (commit) on the main line of the project's version control — usually git — that changed the doc. See [versioning.md](versioning.md).
Without version control, a doc has only its current version.
