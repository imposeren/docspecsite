---
title: Docs system requirements
summary: The numbered requirements (DS-n) docspecsite satisfies — source format, per-doc versioning, rendering, navigation and indexes, the generated code reference, checks, settings and how it runs.
layer: behavior
status: implemented
milestone: first-release
priority: must
components: [docs-system]
tags: [requirements, versioning, rendering, checks]
related:
  - meta/versioning.md
  - architecture/docs-tooling.md
  - behavior/commands.md
---

# Docs system requirements

This is the **contract** docspecsite fulfils for the docs of a repo that follows the docs-driven method.
It says *what* the tool does; how it does it is in [architecture/docs-tooling.md](../architecture/docs-tooling.md).

Each requirement has an id (`DS-n`, see [DS-n](../meta/glossary.md#ds-n)) so that architecture docs and ADRs ([architecture decision records](../meta/glossary.md#adr)) can refer to it.
Ids are never renumbered or reused: a new requirement gets the next free number, even if it belongs in an earlier section.

## Source

- **DS-1** Docs are Markdown files with YAML front matter ([meta/front-matter.md](../meta/front-matter.md)), in `docs/`.
- **DS-2** Raw Markdown stays fully readable and navigable without the tooling (GitHub, editors, agents).
- **DS-3** Markdown is converted by an established Markdown library, not a hand-written parser.

## Versioning

- **DS-4** Versions come from git: every commit on the main branch that touches a doc is a version of it ([meta/versioning.md](../meta/versioning.md)).
- **DS-5** History is **per doc**: each doc has its own list of versions.
- **DS-6** Files under `docs/` cannot be deleted or renamed; a check rejects such commits.
  Redirect docs replace them.

## Rendering

- **DS-7** Every version of every doc is viewable as a page.
- **DS-8** Each page shows a **version picker** listing all versions (date, short commit id, commit subject). A leading `spec:` or `docs:` prefix is removed from the subject, since it carries no information there.
- **DS-9** Each non-latest version shows a **loud, persistent "OLD VERSION — not the current spec" warning** with a link to the latest version, and a marker in the page title.
- **DS-10** Each version can show a **diff** against its previous version.
- **DS-11** Links inside an old version resolve to the version of the target current at that commit; if the target did not exist yet, to its latest version, marked as newer ([meta/versioning.md](../meta/versioning.md#links-in-old-versions)).
- **DS-12** Redirect docs **never redirect automatically**. They render as normal pages with a prominent notice: what happened (`redirect_kind`), a link to the replacement doc(s) (`redirect_to`, when there is one), and the `reason`. Their version history stays available like any other doc's.
- **DS-13** `code:` links and `Docs:` docstring lines resolve as described in [meta/linking.md](../meta/linking.md#code-links).
  `web-api:` links are part of the HTTP API reference ([web-api-reference.md](web-api-reference.md)).

## Navigation and indexes

- **DS-14** Each page shows: breadcrumb (up), children (down), `related` and computed **backlinks** (across), status, components and tags.
- **DS-15** Generated index pages: per tag, per component, and a **status board** grouping docs by `status`, then by `milestone` (in roadmap order) and `priority`.
- **DS-16** A plain-text machine listing of all docs (path, title, summary, status, components) for agents.
- **DS-17** A query command for agents: list docs filtered by tag / component / status / layer / milestone / priority, without rendering.
- **DS-28** A query command for agents: list the docs that link to a given doc (body links, `related`, `redirect_to`), without rendering.
- **DS-29** The rendered site is for humans. Agents use the raw Markdown and git for content, history and diffs, and lookup commands for code and the web API schema (DS-30, DS-31); the tooling provides no Markdown copies of rendered pages.
- **DS-30** A query command for agents: print one part of the committed web API schema (an operation, the operations of a tag, or a schema) as Markdown with references resolved, without rendering.
- **DS-31** A query command for agents: print the API of a code module or class (signatures with types, docstrings, base classes, inherited members) as Markdown, from the code, without rendering.

DS-30 and DS-31 are not docspecsite commands: a project provides them with its own lookup tools, chosen for its languages and its API schema.

Listings that include ADRs (index pages, the machine listing, `list`) sort docs by path, except that external ADRs come before the repo's own, by prefix in the order `external-adr-prefixes` lists them.

## Generated reference layer

- **DS-18** Code reference pages are generated from the **code itself and its docstrings** (structure, signatures, types, members, inheritance), rendered through the same pipeline, **for the latest version of the code only**. Older code is read with git or an IDE.
- **DS-19** Code reference pages show "described in" backlinks from docs' `code:` fields.

The HTTP API reference (DS-26, DS-27) is described in [web-api-reference.md](web-api-reference.md).

## Checks

- **DS-20** A check command validates: front-matter schema, `layer` matches directory, every directory has an `index.md` that lists each direct child doc and child directory with a description in its `## Children` section ([meta/structure.md](../meta/structure.md#every-directory-has-an-indexmd)), all links (body, `related`, `redirect_to`, `code:`, `web-api:`) resolve, components are in the project's component list or the shared ones ([meta/vocabulary.md](../meta/vocabulary.md)), no deletes/renames under `docs/`, no `#` or `%` in file or directory names under `docs/` ([meta/structure.md](../meta/structure.md#naming)).
  Doc templates are not docs and are not checked ([meta/structure.md](../meta/structure.md#outside-docs)).
- **DS-21** The check runs automatically before code leaves a developer's machine and again in CI: docspecsite provides it as a prek hook, `docs-check`, that a project pins to a release tag ([guides/using-docspecsite.md](../guides/using-docspecsite.md)).
- **DS-33** Every doc under `docs/architecture/decisions/` other than an `index.md` is an ADR, and its file name is `<PREFIX>-NNNN-<slug>.md` ([meta/structure.md](../meta/structure.md#adr-ids)).
  `PREFIX` is the repo's own prefix (`adr-prefix`) or the prefix of an external ADR (`external-adr-prefixes`).
  An external ADR comes into the repo from somewhere else, such as the template the repo was created from or another project, and keeps the ID it has there.
  `NNNN` is four digits; the slug is lowercase words separated by `-`.
  Any other name is a problem, also when the doc's front matter does not load.
  When `docspecsite.toml` is not valid TOML, the prefixes are unknown and this rule is skipped.

## Settings

- **DS-32** Project settings live in `docspecsite.toml` at the root of the checked repo ([configuration.md](configuration.md)): the repo's ADR prefix, its web URL, where its code is and which components the code belongs to, and the Contents-list threshold.
  The file is optional; a missing setting takes its default.
  The check reports an unknown setting or an invalid value as a problem, and the setting takes its default; `list` and `build` stop on an invalid value or a file that is not valid TOML, and warn about an unknown setting, which they ignore.
  Settings anywhere else, such as `pyproject.toml`, are not read.

## Running

- **DS-22** Building and serving docs run through Docker, in an image built from docspecsite's repo at a release tag; the check runs as a prek hook in an environment prek creates.
  Nothing beyond Docker, git and prek is required on the host.
- **DS-23** docspecsite keeps its dependencies minimal.
- **DS-24** Builds are incremental: unchanged versions are not re-rendered.
- **DS-25** Output is static files that can be opened locally or served by any web server.
