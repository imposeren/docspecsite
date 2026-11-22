---
title: Front matter
summary: The YAML header every doc starts with — required fields, optional fields, allowed values, and an example.
layer: meta
status: implemented
components: [docs-system]
tags: [meta, front-matter, rules]
related:
  - meta/lifecycle.md
  - meta/vocabulary.md
  - meta/linking.md
---

# Front matter

Every Markdown file under `docs/` (except generated reference pages, which get synthesized front matter) starts with a YAML block between `---` lines.

## Example

```yaml
---
title: Order checkout
summary: Turning a customer's cart into a paid order, including payment and confirmation.
layer: behavior
status: specified
components: [orders]
tags: [checkout]
related:
  - scenarios/orders/checkout.md
  - architecture/orders/checkout.md
code: [my_project.orders.checkout]
---
```

## Fields

| Field | Required | Meaning |
| -- | -- | -- |
| `title` | yes | Human title. Usually also the first `#` heading. |
| `summary` | yes | **One sentence.** Shown in indexes and listings; agents use it to decide whether to open the doc. Make it specific. |
| `layer` | yes | `root`, `meta`, `behavior`, `scenarios`, `architecture`, `ui`, `guides`, `agents`, `reference`. Must match the directory. |
| `status` | yes | Lifecycle state, see [lifecycle.md](lifecycle.md). |
| `components` | yes (may be `[]`) | Parts of the system this doc is about. Values from the project's component list (see [vocabulary.md](vocabulary.md)). |
| `tags` | yes (may be `[]`) | Free keywords for search and tag indexes. Lowercase, `-`-separated. |
| `related` | yes (may be `[]`) | Sideways / cross-layer links: paths **relative to `docs/`**. Parent and children are implied by directories and are not listed. See [linking.md](linking.md). |
| `milestone` | no | The roadmap milestone this doc's target state belongs to (*when*); one of the milestones listed in the project's `roadmap.md`. Mostly set on `specified` docs. |
| `priority` | no | How important the doc's target state is **within its milestone**: `must` (the milestone isn't reached without it), `should` (expected, can slip to a later milestone), `could` (nice to have). |
| `code` | no | Dotted code paths (modules, classes, functions) this doc describes. Creates links to code reference pages and "described in" backlinks on them. |
| `redirect_kind` | when `status: redirect` | What happened: `renamed`, `moved` (to another place or layer), `became-directory` (now `<name>/index.md`), `merged` (into another doc), `split` (into several docs), `replaced` (content gone; something different now does its job), `removed` (gone, nothing replaces it). |
| `redirect_to` | when `status: redirect`, except `removed` | Path (relative to `docs/`) of the doc with the content now (or, for `replaced`, of the doc describing the replacement); a list of paths for `split`. |
| `reason` | when `status: redirect` | One sentence on why, shown on the redirect page. |
| `decision` | ADRs ([architecture decision records](glossary.md#adr)) only | `proposed`, `accepted`, `superseded`. See [lifecycle.md](lifecycle.md#adrs). |
| `superseded_by` | ADRs with `decision: superseded` | Path of the superseding ADR. |
| `date` | ADRs only | `YYYY-MM-DD` of the decision. |

Unknown fields are allowed but should be added here before use, so the schema stays discoverable.
Depth and version information are **never** stored in front matter — they come from the path and from version control.
