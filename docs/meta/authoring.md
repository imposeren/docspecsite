---
title: Writing docs
summary: How to write a doc that works for both humans and AI agents — page shape, style per layer, size limits, and the templates to start from.
layer: meta
status: implemented
components: [docs-system]
tags: [meta, writing, style, templates]
related:
  - meta/layers.md
  - meta/templates/index.md
  - agents/reading-strategy.md
---

# Writing docs

## Page shape

Docs follow this shape where it fits, so readers (and agents) know where to stop.
The front matter and the title are required, and `docspecsite check` enforces them; the rest is guidance:

1. **Front matter** ([front-matter.md](front-matter.md)).
2. **Title**: the doc's first level-1 heading, right after the front matter; only blank lines may come between them.
   Either Markdown style works (`# Import`, or a line underlined with `===`); none is enforced.
   It is the doc's only level-1 heading; every other heading is level 2 or deeper.
   The check reports text before the title, a doc without one, and a second level-1 heading.
   No "Up" link: the parent is implied by the path and rendered as a breadcrumb.
3. **Document brief** — the paragraph right after the title: the whole doc in 2–5 sentences.
   It is not the front-matter `summary`, which is one sentence for listings and indexes.
   Someone who reads only this should come away with a correct picture.
   Tables, lists and code read better in the body's sections than here: a rendered page may insert a generated contents list right after this paragraph, before the first section.
   The title and the brief carry no [status note](lifecycle.md#status-notes): the doc's whole `status` describes them, so in a partly built doc the brief may mention built and unbuilt parts alike.
4. **Body** — the details, in sections.
5. **See also** — links across layers and to deeper docs, each with a few words on what the reader will find there.

## Writing for agents as well as humans

- **Self-contained at its depth.**
  Define terms or link to where they are defined; do not rely on the reader having read sibling docs.
- **Point, don't paste.**
  Summarize what a deeper doc says in one line and link it, instead of copying its content.
  Duplicated details drift apart.
- **Say what is *not* covered** and where it lives, when a reader is likely to look here for it.
- **Be concrete.**
  Exact names, values, limits and examples beat adjectives.
- **Keep it small.**
  Aim for ≤ ~300 lines per doc.
  If it grows past that, split it into a directory ([structure.md](structure.md#growing-a-doc-into-a-directory)).
- **Present tense, target state.**
  "The system does X", never "we will add X" or "X was changed".

## Terms and abbreviations

The **first use** of an abbreviation or project-specific term in each doc is either spelled out — "ADR (architecture decision record)" — or linked to its glossary entry.
A doc may be the first one someone (or an agent) reads, so never assume terms were introduced elsewhere.
IDs defined in another doc (e.g. requirement numbers like DS-3, or ADR IDs like BASE-0004) are always **links** to where they are defined, at every mention, not only the first.
New terms are added to the right glossary in the same change: [meta/glossary.md](glossary.md) (documentation terms), [behavior/glossary.md](../behavior/glossary.md) (product terms), [architecture/glossary.md](../architecture/glossary.md) (technical terms and tools).

## Line breaks

There is **no line-length limit**; readers use soft wrap.
Don't hard-wrap paragraphs at a fixed width, because re-wrapping turns a one-word edit into a multi-line diff.
Instead, you **may** put a line break after each sentence (or after a long clause), so diffs and `git blame` work per sentence.
Very short sentences can share a line.
Formatters must preserve line breaks as written.

## Style per layer

- **behavior** — plain language, no jargon.
  Concepts, capabilities, rules, limits.
  Test: could a non-developer user review it?
- **scenarios** — Gherkin in ```` ```gherkin ```` blocks. One `Feature` per doc (or per section), one behavior per `Scenario`, actor stated in each. Each `Feature`'s intro, the text before its block, links the section of the behavior or ui doc whose rule it gives cases for ([lifecycle.md](lifecycle.md#scenario-docs)). Use `Background` for shared setup and `Scenario Outline` + `Examples` for variations. Steps describe *what*, not *how* ("When I place the order", not "When I click the blue button").
- **architecture** — technical, with reasoning.
  Diagrams as Mermaid code blocks.
  Decisions as ADRs ([architecture decision records](glossary.md#adr)); design docs link to the ADRs that justify them.
- **ui** — what the user sees: screens, flows, layout; diagrams as Mermaid or committed images. No implementation details.
- **guides** — imperative, numbered steps with exact commands, what success looks like, and how to undo. Link to architecture for the *why*.
- **agents** — imperative and short.
  Rules first, explanations after.
- **docstrings** (shown in the reference layer) — the contract of the code element: what, inputs, outputs, errors, and `Docs:` links to the spec it implements.

## Templates

Start every new doc from a template in [templates/](templates/index.md).
