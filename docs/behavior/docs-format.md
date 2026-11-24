---
title: Docs format
summary: What a doc is to docspecsite — a Markdown file with YAML front matter in docs/, readable without the tooling, whose title is its one level-1 heading right after the front matter, and how ADR files are named.
layer: behavior
status: implemented
milestone: first-release
priority: must
components: [checks, site]
tags: [requirements, checks]
related:
  - scenarios/docs-format.md
  - behavior/requirements.md
  - behavior/commands.md
  - architecture/docs-tooling.md
  - meta/front-matter.md
  - meta/authoring.md
---

# Docs format

A project's docs are plain Markdown files in `docs/`, each with a block of YAML front matter at the top, so they read well on GitHub, in an editor or to an agent without docspecsite.
This doc says what docspecsite takes as a doc: the files and how they are converted, where a doc's title is, and how the files of ADRs ([architecture decision records](../meta/glossary.md#adr)) are named.
The check reports what breaks these rules; its problem lines and hints are in [commands.md](commands.md#check).

## Requirements

These requirements are part of the [DS-n](../meta/glossary.md#ds-n) numbering listed in [requirements.md](requirements.md):

- **DS-1** Docs are Markdown files with YAML front matter ([meta/front-matter.md](../meta/front-matter.md)), in `docs/`.
- **DS-2** Raw Markdown stays fully readable and navigable without the tooling (GitHub, editors, agents).
- **DS-3** Markdown is converted by an established Markdown library, not a hand-written parser.
- **DS-52** A doc's **title** is its first level-1 heading: a line that starts with a single `#`, such as `# Import`, or a line underlined with `===`; either style may be used ([meta/authoring.md](../meta/authoring.md#page-shape)).
  A heading inside a block quote or a list is not a level-1 heading.
  The title comes right after the front matter: only blank lines may come between them, and any other text there, an HTML comment included, is a problem.
  A doc has exactly one level-1 heading, its title.
  The check reports text between the front matter and the title, a doc without a title, and each level-1 heading after the title; the problems and their hints are in [commands.md](commands.md#check).
  These rules are not checked in a doc whose front matter is missing or does not load: that is already a problem of its own.
  The site shows the title as the page's heading; for a doc without a title, it shows the front matter's `title` instead.
- **DS-33** Every doc under `docs/architecture/decisions/` other than an `index.md` is an ADR, and its file name is `<PREFIX>-NNNN-<slug>.md` ([meta/structure.md](../meta/structure.md#adr-ids)).
  `PREFIX` is the repo's own prefix (`adr-prefix`) or the prefix of an external ADR (`external-adr-prefixes`).
  An external ADR comes into the repo from somewhere else, such as the template the repo was created from or another project, and keeps the ID it has there.
  `NNNN` is four digits; the slug is lowercase words separated by `-`.
  Any other name is a problem, also when the doc's front matter does not load.
  When `docspecsite.toml` is not valid TOML, the prefixes are unknown and this rule is skipped.

## See also

- [Scenarios](../scenarios/docs-format.md) — exact cases of the rule on a doc's title.
- [commands.md](commands.md#checks) — everything else the check validates.
- [Architecture](../architecture/docs-tooling.md) — how it is built.
