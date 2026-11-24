---
title: Linking and cross-references
summary: How docs link up, down, across layers and to code — syntax that works in raw Markdown, and what tooling derives (backlinks, version-aware links).
layer: meta
status: implemented
components: [docs-system]
tags: [meta, links, cross-reference, rules]
related:
  - meta/structure.md
  - meta/front-matter.md
  - meta/versioning.md
---

# Linking and cross-references

Docs form a graph.
Every doc should let a reader move **up** (more general), **down** (more detailed), **across** (same part of the system, other layer) and **to code**.

## Link kinds

| Kind | Where it is declared | Example |
| -- | -- | -- |
| up | **Not written in docs.** Derived from the path: the parent of `x/y.md` is `x/index.md`, the parent of `x/index.md` is `../index.md`. Tooling renders it as a breadcrumb. | — |
| down | The parent `index.md` lists its children. | `- [checkout.md](checkout.md) — ...` |
| across | `related:` in front matter **and** a "See also" section in the body. | `scenarios/orders/checkout.md` |
| inline | Ordinary links in prose, wherever a term is defined elsewhere. | `[linked account](../accounts/index.md)` |
| to code | `code:` in front matter, or `code:` links in prose. | `[place_order](code:my_project.orders.checkout.place_order)` |
| to an HTTP endpoint | `web-api:` links in prose. | `[create order](web-api:create_order)` |
| from code | `Docs:` lines in docstrings. | `Docs: architecture/orders/checkout.md` |

## Syntax rules

- **Body links are relative to the current file** (standard Markdown), so they work on GitHub, in editors and for agents reading raw files.
- **Front-matter paths are relative to `docs/`** (stable regardless of where the doc sits).
- Link to a section with `#anchor` (GitHub-style heading slugs).
- A link whose text is a path shows the target's path from `docs/` (`[meta/lifecycle.md](../meta/lifecycle.md)`), or from the current directory when the target is in it or below it (`[orders/checkout.md](orders/checkout.md)`).
  A directory's `index.md` is named by the directory, ending in `/`: `[decisions/](decisions/index.md)`, also with an anchor (`[decisions/](decisions/index.md#numbering)`).
  An inline link from a doc directly in that directory to its `index.md` (or an anchor in it) reads `[index.md](index.md)`; the up link itself is still never written.
- Every link must resolve.
  Broken links are errors, not warnings.
- Prefer linking to the **shallowest doc that answers the question**; let the reader go deeper themselves.

## Code links

- **`code:<dotted.path>`** in a Markdown link target refers to the code reference page of a module, class or function.
  In raw form the dotted path tells a reader exactly where the code lives.
- **`code:`** in front matter lists what the doc describes as a whole.
- A reference from a doc to code that does not exist is an error (the code may be *specified* but not yet written — in that case keep the reference in prose without the `code:` scheme until the code exists).
- **In docstrings**, a line `Docs: <path relative to docs/>` (one or more) links the code back to hand-written docs.
- `Docs:` lines belong to the code, not to the docs: one may be stale for any reason, and that is not an error of the docs.
  Whoever works on the code can find stale ones with the code check (`docspecsite check --optional-checks code`, [agents/working-from-specs.md](../agents/working-from-specs.md#implementing-a-specified-doc)).
- **`web-api:<operationId>`** in a Markdown link target refers to one endpoint of the web API, by its operation id in the committed HTTP API schema.
  An unknown operation id is an error, with the same "specified but not written yet" exception as `code:` links.

## Derived links (provided by tooling)

These are not written by hand; the docs system ([docspecsite](https://github.com/imposeren/docspecsite/blob/main/docs/behavior/index.md)) computes them:

- **backlinks** — "linked from" lists on every page;
- **"described in"** lists on code reference pages, from `code:` fields;
- **version-aware links** — inside an old version of a doc, links lead to the version of the target that was current at that time (see [versioning.md](versioning.md#links-in-old-versions)).

## See also

- [structure.md](structure.md) — why mirrored paths make "across" links predictable.
