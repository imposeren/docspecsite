---
title: Docs system requirements — index
summary: The index of docspecsite's numbered requirements (DSR-n) — every ID, the doc that holds it, and the rule for numbering new ones.
layer: behavior
status: [implemented, specified, changed]
milestone: first-release
priority: must
components: [docs-system]
tags: [requirements]
related:
  - scenarios/requirements.md
  - behavior/docs-format.md
  - behavior/site.md
  - behavior/code-reference.md
  - behavior/commands/check.md
  - behavior/commands/list.md
  - behavior/commands/backlinks.md
  - behavior/distribution.md
  - behavior/configuration.md
  - behavior/versioning-backends.md
  - behavior/web-api-reference.md
  - behavior/repo-subdirectory.md
  - behavior/doc-symlinks.md
  - behavior/status-notes.md
  - architecture/docs-tooling.md
---

# Docs system requirements — index

docspecsite's requirements are the **contract** it fulfils for the docs of a repo that follows the docs-driven method: *what* the tool does; how it does it is in [architecture/docs-tooling.md](../architecture/docs-tooling.md).
Each requirement lives in the behavior doc whose subject it is, in that doc's `## Requirements` section; this page lists every one of them and where it is.

Each requirement has an id (`DSR-n`, see [DSR-n](../meta/glossary.md#dsr-n)) so that architecture docs and ADRs ([architecture decision records](../meta/glossary.md#adr)) can refer to it.
Ids are never renumbered or reused: a new requirement gets the next free number, even if it belongs in an earlier section, and is also listed here.
A new DSR-n is listed under the section whose subject it matches, or under Other subjects when it matches none.

## Source

- **DSR-1**, **DSR-2**, **DSR-3** Docs are Markdown files with front matter, readable without the tooling, converted by an established library: [docs-format.md](docs-format.md#requirements).

## Versioning

- **DSR-4**, **DSR-5**, **DSR-6** Versions come from the version control, history is per doc, and files under `docs/` are never deleted or renamed: [versioning-backends.md](versioning-backends.md#versions-of-a-doc).

## Rendering

- **DSR-7** to **DSR-12**, **DSR-35** Version pages, the version picker, the old-version warning, diffs, links in old versions, redirect pages, and building in parts: [site.md](site.md#rendering).
- **DSR-13**, **DSR-34** `code:` links, `Docs:` lines and Sphinx roles in docstrings: [code-reference.md](code-reference.md#requirements).

## Navigation and indexes

> **Not built yet.** There is no search: DSR-54 is new.

- **DSR-14**, **DSR-15**, **DSR-16**, **DSR-29** Page navigation, the index pages and the status board, the machine listing, and the site being for humans: [site.md](site.md#navigation-and-indexes).
- **DSR-17**, **DSR-28** The `list` and `backlinks` query commands: [list.md](commands/list.md#requirements), [backlinks.md](commands/backlinks.md#requirements).
- **DSR-30** The web API schema lookup a project provides: [web-api-reference.md](web-api-reference.md#looking-up-the-schema).
- **DSR-31** The code lookup a project provides: [code-reference.md](code-reference.md#requirements).
- **DSR-54** Search and the page's side bar: [site.md](site.md#search-and-page-layout).

## Generated reference layer

- **DSR-18**, **DSR-19** The code reference, for the latest code only, with "described in" backlinks: [code-reference.md](code-reference.md#requirements).
- **DSR-26**, **DSR-27** The HTTP API reference and the check that its schema is up to date: [web-api-reference.md](web-api-reference.md#requirements).

## Checks

- **DSR-20**, **DSR-51**, **DSR-36** What the check validates, hints under problems, and the code check: [check.md](commands/check.md#requirements).
- **DSR-52**, **DSR-33** A doc's title, and how ADR files are named: [docs-format.md](docs-format.md#requirements).
- **DSR-53** Docs in a layer without a build status, today the scenario docs: their build status, milestone, priority and status notes ignored, a warning for `implemented`, and the docs they give cases for in `related`: [docs-format.md](docs-format.md#layers-without-a-build-status).
- **DSR-21** The `docs-check` prek hook: [distribution.md](distribution.md#requirements).

## Settings

- **DSR-32** Project settings in `docspecsite.toml`: [configuration.md](configuration.md#requirements).

## Running

> **Changed, not built yet.** A build still draws again only what changed, not the whole site.

- **DSR-22**, **DSR-23** The Docker image, what the host needs, and dependencies chosen for a reason: [distribution.md](distribution.md#requirements).
- **DSR-24**, **DSR-25** Full rebuilds and static output: [site.md](site.md#building).

## Other subjects

- **DSR-37** A docs project in a subdirectory of a git repo: [repo-subdirectory.md](repo-subdirectory.md).
- **DSR-38**, **DSR-40** to **DSR-43** Where versions come from, versions from tags only, link patterns and backend checks: [versioning-backends.md](versioning-backends.md).
- **DSR-39** Symlinks under `docs/`: [doc-symlinks.md](doc-symlinks.md#requirements).
- **DSR-44** to **DSR-50** Partly built docs: [status-notes.md](status-notes.md#requirements).
