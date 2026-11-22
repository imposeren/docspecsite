---
title: Versioning, redirects and history
summary: Revisions (commits) of the project's version control are doc versions; docs are never deleted or renamed but become redirect docs; old versions are always clearly marked and link to their contemporaries.
layer: meta
status: implemented
components: [docs-system]
tags: [meta, versioning, version-control, redirects, rules]
related:
  - meta/structure.md
  - architecture/docs-tooling.md
---

# Versioning, redirects and history

## A commit is a version

Docs are versioned with the project's **version control** — usually git.
The method expects git: these docs use git's commands and terms where they help, without spelling out other version control systems; a project that uses another one, or none, reads them in its own terms.
You may edit as many times as you like; a **version** of a doc is created only when a revision (a commit) that touches it lands on the main line of history (with git: the first-parent history of the main branch).
Every such commit is one version of that doc — there is no separate version number.

The docs tooling can also build docs without version control: then each doc has only its current version, with no version list, old versions or diffs.

Consequences:

- Commit docs **deliberately**, with a message that says what changed in the spec ("spec: checkout keeps the cart's item order"), because commit subjects appear in each doc's version list (where the version control has commit messages).
- Avoid noise commits on docs (fixing a typo is fine — it is a real version, just a small one).
- Prefer committing a doc together with its counterparts in other layers when they change together, so their versions line up.

## No delete, no rename

**Docs under `docs/` are never deleted or renamed in version control.**
Old versions of other docs link to them, and external links may too.
Instead, the doc becomes a **redirect doc**: a short page that says what happened, why, and where the content went.
It does **not** forward the reader automatically, so the explanation and the doc's own history stay visible.

```markdown
---
title: Order checkout (moved)
summary: Moved to architecture/billing/checkout.md.
layer: architecture
status: redirect
components: [orders]
tags: []
related: []
redirect_kind: moved
redirect_to: architecture/billing/checkout.md
reason: Checkout became part of the billing component.
---

# Order checkout (moved)

Moved to [billing/checkout.md](../billing/checkout.md): checkout became part of the billing component.
```

Kinds of redirect (`redirect_kind`, see [front-matter.md](front-matter.md)): `renamed`, `moved`, `became-directory`, `merged`, `split`, `replaced`, `removed`.

- `renamed`, `moved`, `became-directory`, `merged` and `split`: the **same content** lives on elsewhere.
- `replaced`: the content is **gone**, and something different now does its job (a new subsystem, a third-party service, a redesign); `redirect_to` points to the doc describing the replacement, and the `reason` says what replaced it and why.
- `removed`: the content is gone and **nothing** replaces it; there is no `redirect_to`, and the `reason` says why.
  The doc's full history stays reachable from its redirect page.

The docs tooling rejects commits that delete or rename files under `docs/` with an optional check for the version control in use (with git: staged deletes and renames), which the project runs before each commit (see [docspecsite's requirements](https://github.com/imposeren/docspecsite/blob/main/docs/behavior/index.md)).

Exception: a doc with no real content yet (a placeholder) may be renamed or deleted without a redirect doc, deliberately, by skipping the check for that one commit (`SKIP=docs-check git commit …`, see [architecture/quality-gate.md](../architecture/quality-gate.md)); the commit message says so.

## Viewing history

For each doc, readers can see the list of its versions (date, short revision id, commit subject without its `spec:`/`docs:` prefix), open any old version, and see what changed relative to the previous version.

## Old versions are loud

An old version must be impossible to mistake for the current spec: a prominent, persistent warning ("OLD VERSION from <date> — not the current spec") with a link to the latest version, visible even after scrolling, plus a marker in the page title.

## Links in old versions

Inside an old version of doc A (from revision X), a link to doc B leads to **the version of B that was current at X** — the latest version of B at or before X in the main line of history.
If B did not exist yet at X, the link leads to B's latest version, marked as "newer doc".
Links in the latest version of A lead to latest versions.

Those linked older versions are themselves old versions, so they carry the same loud warning.
