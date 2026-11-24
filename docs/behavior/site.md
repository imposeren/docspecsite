---
title: The docs site
summary: The static site docspecsite builds for people — a page for every version of every doc with a version picker, old-version warnings and diffs, redirect pages, built in parts, with navigation, search, index pages, a status board and a plain-text listing of all docs; rebuilt in full into static files by one of two renderers.
layer: behavior
status: [implemented, changed, specified]
milestone: first-release
priority: must
components: [site]
tags: [requirements, rendering, versioning]
related:
  - behavior/requirements.md
  - behavior/commands/build.md
  - behavior/commands/list.md
  - behavior/code-reference.md
  - behavior/versioning-backends.md
  - behavior/status-notes.md
  - scenarios/status-notes.md
  - behavior/configuration.md
  - scenarios/commands/build.md
  - architecture/docs-tooling.md
  - architecture/site.md
  - architecture/decisions/DSS-0008-sphinx-site-renderer.md
  - meta/versioning.md
---

# The docs site

`docspecsite build` turns a project's docs into a static site for people to read: every version of every doc has its own page, old versions say loudly that they are old, and each page shows where the doc sits among the others.
Index pages group the docs by tag, component and status, a search box finds words in the current docs, and a plain-text listing of all docs is there for agents, which otherwise read the Markdown and the version control directly.
The site is drawn by one of two [renderers](#renderers); the standard one is used unless a project chooses the older one.
The code reference, a part of the same site, is in [code-reference.md](code-reference.md); the `build` command and its options are in [build.md](commands/build.md#what-the-build-does).

## Requirements

These requirements are part of the [DSR-n](../meta/glossary.md#dsr-n) numbering listed in [requirements.md](requirements.md).

### Rendering

- **DSR-7** Every version of every doc is viewable as a page.
  The code reference's entry page (`docs/reference/code/index.md`) is the exception: like the rest of the code reference ([DSR-18](code-reference.md#requirements)), only its latest version is shown.
- **DSR-8** Each page shows a **version picker** listing all versions (date, short revision id, message: with git, the commit subject). A leading `spec:` or `docs:` prefix is removed from the message, since it carries no information there.
- **DSR-9** Each non-latest version shows a **loud, persistent "OLD VERSION — not the current spec" warning** with a link to the latest version, and a marker in the page title.
- **DSR-10** Each version can show a **diff** against its previous version.
- **DSR-11** Links inside an old version resolve to the version of the target current at that revision; if the target did not exist yet, to its latest version, marked as newer ([meta/versioning.md](../meta/versioning.md#links-in-old-versions)).
- **DSR-12** Redirect docs **never redirect automatically**. They render as normal pages with a prominent notice: what happened (`redirect_kind`), a link to the replacement doc(s) (`redirect_to`, when there is one), and the `reason`. Their version history stays available like any other doc's.
- **DSR-35** The site is built in **parts**, and a build renders the parts it is asked for: `docs` (the hand-written docs, their versions and diffs, the index pages and `llms.txt`) and `code` (the code reference with its entry page); by default every part the repo has ([build.md](commands/build.md#what-the-build-does)).
  Links into a part that is not built never dangle: a `code:` link in a docs-only site is its text in code style, and a link from the code reference to a doc in a code-only site leads to the doc's Markdown file on the repo host (plain text without `source-url`), and a link to another file of the part not built, such as an image, leads to that file on the repo host the same way.
  When the parts are built together, they link to each other as one site.

### Navigation and indexes

- **DSR-14** Each page shows: breadcrumb (up), children (down), `related` and computed **backlinks** (across), status (every status of a partly built doc and none for a doc without a status: [DSR-49](status-notes.md#requirements)), components and tags.
- **DSR-15** Generated index pages: per tag, per component, and a **status board** grouping docs by `status`, then by `milestone` (in roadmap order) and `priority`; a partly built doc is listed under each of its statuses ([DSR-48](status-notes.md#requirements)).
  The milestone groups come in roadmap order, then each other milestone by the code points of its name, then the docs without a milestone. Within a milestone, the priority groups come in the order `must`, `should`, `could`, then each other value (one that `check` reports, [meta/front-matter.md](../meta/front-matter.md#fields), such as `Must` with a capital or `high`) in a group of its own named by that value, by code point (so `Must` before `high`), and last the docs without a priority. A doc with such a value is still listed, so that it never drops off the board while its front matter is being fixed.
- **DSR-16** A plain-text machine listing of all docs (path, title, summary, status, components) for agents.
  Each doc is one Markdown list line, `- [<title>](<url>): <summary> (status: <status>; components: <components>; source: docs/<path>)`, which stays one valid link whatever the doc's path and title hold: in the URL, every character other than ASCII letters (`A`–`Z`, `a`–`z`), digits and `-`, `.`, `_`, `~`, `/` is percent-encoded (a space as `%20`, `(` and `)` as `%28` and `%29`, a letter such as `é` as the percent codes of its UTF-8 bytes), and in the title each `\`, `[` and `]` is written with a backslash before it (`\\`, `\[`, `\]`).
  A doc without a status has no `status:` part: `- [<title>](<url>): <summary> (components: <components>; source: docs/<path>)` ([DSR-47](status-notes.md#requirements)).
- **DSR-29** The rendered site is for humans. Agents use the raw Markdown and git for content, history and diffs, and lookup commands for code and the web API schema ([DSR-30](web-api-reference.md#looking-up-the-schema), [DSR-31](code-reference.md#requirements)); the tooling provides no Markdown copies of rendered pages.

Listings that include ADRs (the index pages and the machine listing here, and `list`, [list.md](commands/list.md#options-and-output)) sort docs by path, except that external ADRs come before the repo's own, by prefix in the order `external-adr-prefixes` lists them.

### Search and page layout

> **Not built yet.**

- **DSR-54** The site has a search box that finds words in the latest version of every doc and in the code reference.
  Old versions, diffs and the generated index pages are left out of the search, so a search never leads to an outdated spec.
  Each page has a side bar with the tree of docs and the list of the page's own sections, and each heading has a link to itself.
  With the older renderer, the site has no search and no side bar ([Renderers](#renderers)).

### Building

> **Changed, not built yet.** Git is the only version control, and every build needs it. Unchanged versions are taken from the build cache.

- **DSR-24** Every build draws the whole site afresh, whichever backend gives the versions, so no page is left stale by a change to a doc it links to, to the settings or to docspecsite itself.
  The older renderer is the exception: it keeps the pages it has drawn and draws again only the versions that changed and the pages whose links changed ([Renderers](#renderers)).
- **DSR-25** Output is static files that can be opened locally or served by any web server.

## Renderers

> **Not built yet.**

A renderer is the part of docspecsite that draws the site's pages.
There are two, and a project chooses one with the `renderer` setting ([configuration.md](configuration.md#site)), or for one build with `build --renderer` ([build.md](commands/build.md#what-the-build-does)):

- `sphinx`, the standard renderer, named after the documentation tool it is built on; it is used when nothing else is chosen.
- `internal`, docspecsite's older renderer of its own.
  It stays only while projects move to the standard renderer, so that a project can keep it until the new site suits it, and so that both sites of the same docs can be built and compared side by side.
  A later release removes it, together with the setting and the option that choose it.

Both draw the same pages from the same docs: every version, diff, index page, the status board and the listing for agents, with the same status badges, components, tags, breadcrumb, panels, markers and warnings.
They differ in these points, each named with the renderer it applies to:

- **Search and side bar** — `sphinx` only ([DSR-54](#search-and-page-layout)).
- **Contents list in the text** — `internal` only: a doc with many sections gets a list of them after its first paragraph, as the `toc-min-headings` setting says ([configuration.md](configuration.md#settings)); with `sphinx`, the side bar lists the page's sections instead.
- **Addresses of code reference pages** — `sphinx` gives each module a folder of its own, such as `reference/code/example/api/index.html`; `internal` gives it one file, such as `reference/code/example.api.html`.
  Links within the site always lead to the right page; only bookmarks kept from one renderer's site do not work on the other's.
- **Links to a heading** — a heading whose text holds punctuation, such as "Don't", can be reached as `#dont` with both renderers; in the links it draws, `sphinx` may use another form of the same address, `#don-t`, which works as well.
  A heading made only of punctuation has no link of its own with `sphinx`.
- **Code reference pages** — `internal` lets a reader fold each member's section and lists a page's members at its top; `sphinx` shows every member in full, with no such list.
- **Rebuilds** — `sphinx` draws the whole site on every build; `internal` keeps the pages it has drawn in `.docspecsite-cache/` in the checked repo and draws again only what changed ([DSR-24](#building)).
- **A failure of the drawing itself** — with `sphinx`, a failure inside the documentation tool, one that concerns no single page, stops the whole build ([build.md](commands/build.md#what-the-build-does)); with `internal`, every error stays with its page.

## See also

- [code-reference.md](code-reference.md) — the code reference part of the site.
- [versioning-backends.md](versioning-backends.md) — where the versions come from.
- [Architecture](../architecture/docs-tooling.md) — how it is built.
