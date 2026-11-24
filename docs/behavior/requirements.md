---
title: Docs system requirements — index
summary: The index of docspecsite's numbered requirements (DS-n) — every ID, the doc that holds it, and the rule for numbering new ones.
layer: behavior
status: implemented
milestone: first-release
priority: must
components: [docs-system]
tags: [requirements]
related:
  - scenarios/requirements.md
  - behavior/docs-format.md
  - behavior/site.md
  - behavior/code-reference.md
  - behavior/commands.md
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

Each requirement has an id (`DS-n`, see [DS-n](../meta/glossary.md#ds-n)) so that architecture docs and ADRs ([architecture decision records](../meta/glossary.md#adr)) can refer to it.
Ids are never renumbered or reused: a new requirement gets the next free number, even if it belongs in an earlier section, and is also listed here.
A new DS-n is listed under the section whose subject it matches, or under Other subjects when it matches none.

## Source

- **DS-1**, **DS-2**, **DS-3** Docs are Markdown files with front matter, readable without the tooling, converted by an established library: [docs-format.md](docs-format.md#requirements).

## Versioning

- **DS-4**, **DS-5**, **DS-6** Versions come from the version control, history is per doc, and files under `docs/` are never deleted or renamed: [versioning-backends.md](versioning-backends.md#versions-of-a-doc).

## Rendering

- **DS-7** to **DS-12**, **DS-35** Version pages, the version picker, the old-version warning, diffs, links in old versions, redirect pages, and building in parts: [site.md](site.md#rendering).
- **DS-13**, **DS-34** `code:` links, `Docs:` lines and Sphinx roles in docstrings: [code-reference.md](code-reference.md#requirements).

## Navigation and indexes

- **DS-14**, **DS-15**, **DS-16**, **DS-29** Page navigation, the index pages and the status board, the machine listing, and the site being for humans: [site.md](site.md#navigation-and-indexes).
- **DS-17**, **DS-28** The `list` and `backlinks` query commands: [commands.md](commands.md#queries).
- **DS-30** The web API schema lookup a project provides: [web-api-reference.md](web-api-reference.md#looking-up-the-schema).
- **DS-31** The code lookup a project provides: [code-reference.md](code-reference.md#requirements).

## Generated reference layer

- **DS-18**, **DS-19** The code reference, for the latest code only, with "described in" backlinks: [code-reference.md](code-reference.md#requirements).
- **DS-26**, **DS-27** The HTTP API reference and the check that its schema is up to date: [web-api-reference.md](web-api-reference.md#requirements).

## Checks

- **DS-20**, **DS-51**, **DS-36** What the check validates, hints under problems, and the code check: [commands.md](commands.md#checks).
- **DS-52**, **DS-33** A doc's title, and how ADR files are named: [docs-format.md](docs-format.md#requirements).
- **DS-53** Docs in a layer without a build status, today the scenario docs: their build status, milestone, priority and status notes ignored, a warning for `implemented`, and the docs they give cases for in `related`: [docs-format.md](docs-format.md#layers-without-a-build-status).
- **DS-21** The `docs-check` prek hook: [distribution.md](distribution.md#requirements).

## Settings

- **DS-32** Project settings in `docspecsite.toml`: [configuration.md](configuration.md#requirements).

## Running

- **DS-22**, **DS-23** The Docker image, what the host needs, and minimal dependencies: [distribution.md](distribution.md#requirements).
- **DS-24**, **DS-25** Incremental builds and static output: [site.md](site.md#building).

## Other subjects

- **DS-37** A docs project in a subdirectory of a git repo: [repo-subdirectory.md](repo-subdirectory.md).
- **DS-38**, **DS-40** to **DS-43** Where versions come from, versions from tags only, link patterns and backend checks: [versioning-backends.md](versioning-backends.md).
- **DS-39** Symlinks under `docs/`: [doc-symlinks.md](doc-symlinks.md#requirements).
- **DS-44** to **DS-50** Partly built docs: [status-notes.md](status-notes.md#requirements).
