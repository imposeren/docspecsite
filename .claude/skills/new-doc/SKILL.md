---
name: new-doc
description: Use when creating a new documentation file under docs/ in this repo (any layer, an ADR, or an index.md) — scaffolds it from the right template at the mirrored path and wires up index and related links.
---

# new-doc

Create a doc that follows `docs/meta/` rules on the first try.

1. **Pick the layer** using `docs/meta/layers.md#choosing-a-layer`.
   One doc per layer; if the part needs several layers, create each (behavior → scenarios → ui → architecture).
2. **Pick the path.**
   Use the mirrored path: if counterparts exist in other layers, use the same relative path.
   Path segments come from components in `docs/architecture/components.md`; if a new component is needed, add it there in the same change.
   ADRs: `docs/architecture/decisions/<PREFIX>-NNNN-<slug>.md`, where `<PREFIX>` is `adr-prefix` from `docspecsite.toml` and `NNNN` the next free number of that prefix (`docs/meta/structure.md#adr-ids`).
3. **Copy the template** from `docs/meta/templates/` (`behavior-doc.md`, `scenarios-doc.md`, `architecture-doc.md`, `guide-doc.md`, `adr.md`, `index-doc.md`, `redirect-doc.md`) and replace every `<placeholder>`.
   New docs start as `status: draft` unless the user has agreed to the content (`specified`).
   New ADRs start as `decision: proposed`.
4. **Wire it in:**
   - list it under `## Children` in the parent `index.md` (`- [name.md](name.md) — …`) **with a one-line description** of what the reader finds there (`docs/meta/structure.md#every-directory-has-an-indexmd`): tooling can list files, but only a person can say what each one is for, and that line is what lets readers and agents choose without opening every doc.
     Create the parent `index.md` from `index-doc.md` if the directory is new;
   - if the parent was a single file `x.md` that now needs children, follow `docs/meta/structure.md#growing-a-doc-into-a-directory` (never rename; leave a redirect doc);
   - add `related:` entries both ways with counterparts in other layers;
   - ADRs: the line in `docs/architecture/decisions/index.md` is `- [<PREFIX>-NNNN](<PREFIX>-NNNN-<slug>.md) — <decision>, <status> — <title>` (`docs/meta/lifecycle.md#adrs`).
5. **Write** the summary sentence and first paragraph so a reader can stop there (`docs/meta/authoring.md`).
6. **Check** with the project's docs check (see `docs/architecture/docs-tooling.md`); if it doesn't exist yet, verify every link path exists.
7. Do not commit unless asked.
