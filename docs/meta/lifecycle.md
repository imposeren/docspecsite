---
title: Doc lifecycle and docs as a task list
summary: The status values a doc moves through, what each means, how ADR decisions fit in, and how statuses turn the docs into the project's task list.
layer: meta
status: implemented
components: [docs-system]
tags: [meta, status, lifecycle, project-management, rules]
related:
  - meta/front-matter.md
  - agents/working-from-specs.md
---

# Doc lifecycle and docs as a task list

## Specs, not tickets

Docs describe **the target state** of the system, written as if it were already true: "Checkout keeps the items in the order they were added to the cart", not "Make checkout keep item order" or "Bug: items are reordered".
There are no change requests or bug reports in `docs/`.

Work arises from the **gap between docs and code**.
To ask for a change, edit the spec to describe the desired state and set its `status` accordingly; the diff of that commit *is* the change request.
A bug is code that contradicts an `implemented` doc.

## Status values

| `status` | Meaning | Is it work? |
| -- | -- | -- |
| `draft` | Being written; not agreed. Do not build from it. | Spec work |
| `specified` | Agreed target state; not (fully) true in the code yet. | **Yes — to do** |
| `implemented` | The code (or practice) matches the doc. | No |
| `deprecated` | Still true, but scheduled to go away; says what replaces it. | Removal work |
| `redirect` | Renamed, moved, merged, split, replaced or removed; see `redirect_kind`, `redirect_to`, `reason`. | No |

Transitions: `draft → specified → implemented`; any → `deprecated` → `redirect`.
When an `implemented` doc is edited to describe new behavior, it goes back to `specified` until the code catches up.
For docs that describe practices rather than code (meta, agents), `implemented` means "in effect".

A parent doc's status summarizes its children: if any child is `specified`, the parent should not claim `implemented` for that part.

## ADRs

Architecture decision records ([ADRs](glossary.md#adr)) also carry `decision`:

| `decision` | Meaning |
| -- | -- |
| `proposed` | Suggested, not yet agreed. |
| `accepted` | Agreed. Its `status` then tracks whether it is built (`specified` / `implemented`). |
| `superseded` | Replaced; `superseded_by` points to the newer ADR. ADR text is not rewritten. |

The ADR index (`architecture/decisions/index.md`) lists each ADR as `- [<PREFIX>-NNNN](<PREFIX>-NNNN-<slug>.md) — <decision>, <status> — <title>`, so both are visible at a glance; it groups ADRs by prefix ([structure.md](structure.md#adr-ids)).

ADRs are the one place where history is part of the content: a superseded ADR keeps its original reasoning.
All other docs only ever describe the current target.

## Using status as a task list

- "What is left to do?" → all docs with `status: specified` (and `draft` for spec work).
- "What is left for part X?" → the same, filtered by `components: [X]`.
- "What is next?" → `specified` docs of the earliest unfinished milestone (the project's `roadmap.md`), `must` first, then `should`, then `could`.
- Tooling provides a status board and filtered listings ([docspecsite](https://github.com/imposeren/docspecsite/blob/main/docs/behavior/index.md)).
- `milestone` says *when* a target state is due, `priority` how important it is within that milestone ([front-matter.md](front-matter.md)); a milestone is reached when all its `must` docs are `implemented`.
- Granularity comes for free from depth: a depth-1 doc is an epic, its depth-2 children are stories.
