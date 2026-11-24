---
title: The docs site
summary: The static site docspecsite builds for people — a page for every version of every doc with a version picker, old-version warnings and diffs, redirect pages, built in parts, with navigation, index pages, a status board and a plain-text listing of all docs; built incrementally into static files.
layer: behavior
status: [implemented, changed]
milestone: first-release
priority: must
components: [site]
tags: [requirements, rendering, versioning]
related:
  - behavior/requirements.md
  - behavior/commands.md
  - behavior/code-reference.md
  - behavior/versioning-backends.md
  - behavior/status-notes.md
  - scenarios/status-notes.md
  - architecture/docs-tooling.md
  - meta/versioning.md
---

# The docs site

`docspecsite build` turns a project's docs into a static site for people to read: every version of every doc has its own page, old versions say loudly that they are old, and each page shows where the doc sits among the others.
Index pages group the docs by tag, component and status, and a plain-text listing of all docs is there for agents, which otherwise read the Markdown and the version control directly.
The code reference, a part of the same site, is in [code-reference.md](code-reference.md); the `build` command and its options are in [commands.md](commands.md#build).

## Requirements

These requirements are part of the [DS-n](../meta/glossary.md#ds-n) numbering listed in [requirements.md](requirements.md).

### Rendering

- **DS-7** Every version of every doc is viewable as a page.
  The code reference's entry page (`docs/reference/code/index.md`) is the exception: like the rest of the code reference ([DS-18](code-reference.md#requirements)), only its latest version is shown.
- **DS-8** Each page shows a **version picker** listing all versions (date, short revision id, message: with git, the commit subject). A leading `spec:` or `docs:` prefix is removed from the message, since it carries no information there.
- **DS-9** Each non-latest version shows a **loud, persistent "OLD VERSION — not the current spec" warning** with a link to the latest version, and a marker in the page title.
- **DS-10** Each version can show a **diff** against its previous version.
- **DS-11** Links inside an old version resolve to the version of the target current at that revision; if the target did not exist yet, to its latest version, marked as newer ([meta/versioning.md](../meta/versioning.md#links-in-old-versions)).
- **DS-12** Redirect docs **never redirect automatically**. They render as normal pages with a prominent notice: what happened (`redirect_kind`), a link to the replacement doc(s) (`redirect_to`, when there is one), and the `reason`. Their version history stays available like any other doc's.
- **DS-35** The site is built in **parts**, and a build renders the parts it is asked for: `docs` (the hand-written docs, their versions and diffs, the index pages and `llms.txt`) and `code` (the code reference with its entry page); by default every part the repo has ([commands.md](commands.md#build)).
  Links into a part that is not built never dangle: a `code:` link in a docs-only site is its text in code style, and a link from the code reference to a doc in a code-only site leads to the doc's Markdown file on the repo host (plain text without `source-url`), and a link to another file of the part not built, such as an image, leads to that file on the repo host the same way.
  When the parts are built together, they link to each other as one site.

### Navigation and indexes

- **DS-14** Each page shows: breadcrumb (up), children (down), `related` and computed **backlinks** (across), status (every status of a partly built doc and none for a doc without a status: [DS-49](status-notes.md#requirements)), components and tags.
- **DS-15** Generated index pages: per tag, per component, and a **status board** grouping docs by `status`, then by `milestone` (in roadmap order) and `priority`; a partly built doc is listed under each of its statuses ([DS-48](status-notes.md#requirements)).
  The milestone groups come in roadmap order, then each other milestone by the code points of its name, then the docs without a milestone. Within a milestone, the priority groups come in the order `must`, `should`, `could`, then each other value (one that `check` reports, [meta/front-matter.md](../meta/front-matter.md#fields), such as `Must` with a capital or `high`) in a group of its own named by that value, by code point (so `Must` before `high`), and last the docs without a priority. A doc with such a value is still listed, so that it never drops off the board while its front matter is being fixed.
- **DS-16** A plain-text machine listing of all docs (path, title, summary, status, components) for agents.
  Each doc is one Markdown list line, `- [<title>](<url>): <summary> (status: <status>; components: <components>; source: docs/<path>)`, which stays one valid link whatever the doc's path and title hold: in the URL, every character other than ASCII letters (`A`–`Z`, `a`–`z`), digits and `-`, `.`, `_`, `~`, `/` is percent-encoded (a space as `%20`, `(` and `)` as `%28` and `%29`, a letter such as `é` as the percent codes of its UTF-8 bytes), and in the title each `\`, `[` and `]` is written with a backslash before it (`\\`, `\[`, `\]`).
  A doc without a status has no `status:` part: `- [<title>](<url>): <summary> (components: <components>; source: docs/<path>)` ([DS-47](status-notes.md#requirements)).
- **DS-29** The rendered site is for humans. Agents use the raw Markdown and git for content, history and diffs, and lookup commands for code and the web API schema ([DS-30](web-api-reference.md#looking-up-the-schema), [DS-31](code-reference.md#requirements)); the tooling provides no Markdown copies of rendered pages.

Listings that include ADRs (the index pages and the machine listing here, and `list`, [commands.md](commands.md#list)) sort docs by path, except that external ADRs come before the repo's own, by prefix in the order `external-adr-prefixes` lists them.

### Building

> **Changed, not built yet.** Git is the only version control, and every build needs it.

- **DS-24** Builds are incremental: unchanged versions are not re-rendered, whichever backend gives them.
- **DS-25** Output is static files that can be opened locally or served by any web server.

## See also

- [code-reference.md](code-reference.md) — the code reference part of the site.
- [versioning-backends.md](versioning-backends.md) — where the versions come from.
- [Architecture](../architecture/docs-tooling.md) — how it is built.
