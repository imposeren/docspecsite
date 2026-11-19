---
title: Directory structure and depth
summary: How docs are laid out on disk — one directory per layer, an index.md in every directory, depth derived from the path, and mirrored paths across layers.
layer: meta
status: implemented
components: [docs-system]
tags: [meta, structure, depth, rules]
related:
  - meta/layers.md
  - meta/linking.md
  - meta/versioning.md
---

# Directory structure and depth

## Layout

```
docs/
  index.md               depth 0 of everything
  roadmap.md             the project's milestones, in order (root level)
  <layer>/
    index.md             depth 0 of the layer: overview of the layer
    <part>.md            depth 1: one part of the system
    <part>/
      index.md           depth 1: overview of a part that has sub-parts
      <sub-part>.md      depth 2
      ...
```

Docs are "fractal": every level has the same shape — an overview that summarizes and links to more detailed docs below it.

## Depth

**Depth** is how many directories below the layer root a doc's *topic* sits.
`<layer>/index.md` is depth 0; `<layer>/x.md` and `<layer>/x/index.md` are both depth 1; `<layer>/x/y.md` is depth 2.
Depth is never written in front matter — it follows from the path.

What each depth should contain:

- **depth 0** — what this layer covers overall, a map of its parts, cross-cutting rules.
  Readable in a couple of minutes.
- **depth 1** — one part of the system: purpose, main concepts, boundaries, links to its sub-parts.
- **depth 2+** — specifics: rules, edge cases, exact formats, detailed flows.

A reader should get a correct (if coarse) picture from any depth without reading deeper.
Deeper docs refine; they never contradict their parent.
If they would, fix the parent.

## Every directory has an `index.md`

An `index.md` must:

1. summarize the area in its first paragraph;
2. list every direct child doc and child directory in a `## Children` section, one list item each with a one-line description: `- [name.md](name.md) — …`, or `- [name/](name/index.md) — …` for a directory (redirect docs may be left out).
   The index may have other sections before or after it; links to children elsewhere do not count as listing them.

No doc links up to its parent by hand: the parent is always derivable from the path (the `index.md` of the same directory, or of the directory above for an `index.md`), editors and GitHub show the directory tree, and rendered pages show a generated breadcrumb.

## Mirrored paths

The same part of the system uses **the same relative path** in every layer that covers it:

```
behavior/orders/checkout.md       what checkout means for a customer
scenarios/orders/checkout.md      Given/When/Then cases for it
architecture/orders/checkout.md   how it is implemented
```

This lets humans and agents guess where the counterpart lives, and lets tooling flag missing counterparts.
Not every part needs a doc in every layer — e.g. most infrastructure topics exist only in architecture.
A part's path segments should come from the project's components (see [vocabulary.md](vocabulary.md)) where possible.

## Growing a doc into a directory

A part starts as a single file `x.md`.
When it needs sub-docs:

1. create `x/index.md` with the content of `x.md` (adjusted to be an overview);
2. add the sub-docs under `x/`;
3. turn `x.md` into a **redirect doc** (`redirect_kind: became-directory`) pointing to `x/index.md`.

Step 3 follows from the no-delete/no-rename rule ([versioning.md](versioning.md#no-delete-no-rename)).

## Naming

- lowercase, words separated by `-`: `order-sync.md`;
- no `#` or `%` in file or directory names: they have a meaning in URLs and break links to the rendered page;
- name the *thing*, not an action: `checkout.md`, not `add-checkout.md`;
- ADRs ([architecture decision records](glossary.md#adr)): `architecture/decisions/<PREFIX>-NNNN-<slug>.md`, see [ADR IDs](#adr-ids).

## ADR IDs

Every ADR has an ID `<PREFIX>-NNNN`, e.g. `BASE-0002`, used in its file name (`architecture/decisions/BASE-0002-<slug>.md`), its title and every citation.

- **Prefix:** each repo has its own, set by `adr-prefix` in `docspecsite.toml` at the repo root.
  A repo can also hold **external ADRs**: ADRs that come from elsewhere and keep the ID they have there; `external-adr-prefixes` in `docspecsite.toml` lists their prefixes.
  `BASE` is the prefix of the template's own ADRs, which every project created from the template holds.
  A template option can bring ADRs under a prefix of its own, such as `PYRF` for the Pyrefly language server; only projects that chose the option hold them.
- **Number:** each prefix has its own gap-free sequence, starting at `0001`.
  A number is never reused, not even after its ADR is superseded.
  A repo has one sequence for all its ADRs, whatever layer or part of the system they are about.
- **Across repos:** IDs are unique across all repos that share the template, so a doc cites an ADR of another repo by its ID, linked to that ADR in its repo.
- **In text:** cite an ADR by its ID ("BASE-0002"), not by "ADR 0002".

## Outside `docs/`

`README.md` (humans) and `CLAUDE.md` (Claude Code) at the repo root are short entry points that link into `docs/`.
Temporary planning notes may live in `notes/`; they are not part of the spec and do not follow these rules.

Doc templates live inside `docs/`, in `meta/templates/`, but they are not docs either: their placeholders are not valid front matter or links, so checks, listings and backlinks skip them.
Only `meta/templates/index.md` is a doc, and it lists every template.
