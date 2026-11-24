---
title: Reading strategy for agents
summary: How an agent should find relevant docs and read only as deep as the task needs — summaries first, mirrored paths, related links, and the list command.
layer: agents
status: implemented
components: [agents]
tags: [agents, navigation, context]
related:
  - meta/structure.md
  - meta/linking.md
  - meta/authoring.md
---

# Reading strategy for agents

Context is limited; the docs are built so you can stop early.
Read **breadth-first, summaries first**, and go deeper only when the current doc does not answer your question.

## Steps

1. **Locate.**
   If you were given a doc, start there.
   Otherwise open the relevant layer's `index.md`, or use the docs tooling's `list` query (see [architecture/docs-tooling.md](../architecture/docs-tooling.md)).
   Without tooling, grep front matter: `grep -rl "components: \[.*<c>" docs/`.
2. **Read the summary.**
   Front-matter `summary` plus the document brief (the first paragraph). Often enough.
3. **Go across before going deep.**
   The same part lives at the same path in other layers ([mirrored paths](../meta/structure.md#mirrored-paths)): behavior says *what*, scenarios say *exactly what*, ui says *what it looks like*, architecture says *how*, guides say *how to operate it*. Follow `related:` links.
4. **Go deep only for specifics** — exact rules, formats, edge cases.
5. **Check decisions** in [architecture/decisions/](../architecture/decisions/index.md) before proposing technical approaches.

## History and diffs: use git, not the site

The rendered HTML site is for humans ([docspecsite](https://github.com/imposeren/docspecsite/blob/main/docs/behavior/index.md)); read raw Markdown and use git:

| Need | Command |
| -- | -- |
| A doc's versions | `git log --format='%h %as %s' -- docs/<path>` |
| What changed in each version | `git log -p -- docs/<path>` |
| A doc as of a commit | `git show <sha>:docs/<path>` |
| Changes between two versions | `git diff <old> <new> -- docs/<path>` |
| Which docs link here (before changing or redirecting a doc) | the docs tooling's `backlinks` query ([architecture/docs-tooling.md](../architecture/docs-tooling.md)); without tooling, grep for the file name |

## Typical reading sets

| Task | Read |
| -- | -- |
| Implement a feature | behavior doc → scenarios doc (acceptance criteria) → ui doc (if it has a UI) → architecture doc → its ADRs ([architecture decision records](../meta/glossary.md#adr)) |
| Fix a bug | the `implemented` behavior doc (or built section) it contradicts, or the scenario whose `Feature` links such a section ([meta/lifecycle.md](../meta/lifecycle.md#scenario-docs)) → architecture doc |
| Write a new spec | [meta/authoring.md](../meta/authoring.md) → template → parent `index.md` → siblings' summaries |
| Infra / tooling change | architecture doc for the area → its ADRs → the guides for that area |
| Integrate an external platform | its `reference/external/` doc → the architecture doc of the integration |

## Don't

- Don't load whole layers "for context".
- Don't treat an **old version** page or a `draft`/`deprecated`/`redirect` doc as current spec.
- Don't infer requirements from code alone; code may lag behind a `specified` or `changed` doc or section.
