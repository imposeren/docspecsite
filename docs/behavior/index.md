---
title: What docspecsite does
summary: Plain-language overview of docspecsite — a tool that checks a repo's docs against the docs-driven method and renders every version of every doc as a static site — and where its requirements, commands and settings are described.
layer: behavior
status: [changed, implemented]
components: [docs-system]
tags: [overview]
related:
  - architecture/index.md
  - guides/using-docspecsite.md
---

# What docspecsite does

docspecsite is the tool behind the [docs-driven template](https://github.com/imposeren/docs-driven-template): projects keep their spec as Markdown docs with front matter in `docs/`, and docspecsite keeps those docs consistent and readable.

- It **checks** the docs on every commit: front matter, links, indexes, file names, and that no doc is deleted or renamed.
- It **renders** a static site in which every doc has its own history: every commit that changed a doc is a version with its own page, a diff and a loud warning when it is not the latest.
  The history comes from the project's version control, git by default; a project without one gets a site with only the current version of each doc.
- It **answers questions** about the docs without rendering: which docs match some front-matter values, and which docs link to a given doc.
- It **generates a code reference** from a project's Python code and links docs and code both ways.

It implements the rules of the method's `docs/meta/` layer ([meta/](../meta/index.md)); it does not make those rules configurable.
Only project settings, such as the repo's ADR prefix, are configuration.

## Children

> **Built.**

- [requirements.md](requirements.md) — The index of the numbered docs system requirements (`DSR-n`): every ID and the doc that holds it.
- [docs-format.md](docs-format.md) — What a doc is: Markdown with front matter in `docs/`, its title, how ADR files are named, and scenario docs without a build status.
- [site.md](site.md) — The rendered site: version pages, pickers, old-version warnings, diffs, redirect pages, build parts, navigation, index pages and the machine listing.
- [code-reference.md](code-reference.md) — The code reference generated from the code and its docstrings, and the links between docs and code.
- [distribution.md](distribution.md) — How projects run docspecsite: the `docs-check` prek hook and the Docker image, pinned to a release tag.
- [commands/](commands/index.md) — The `check`, `list`, `backlinks` and `build` commands: options, output and exit codes.
- [configuration.md](configuration.md) — The `docspecsite.toml` settings file at the root of a checked repo.
- [web-api-reference.md](web-api-reference.md) — The HTTP API reference rendered from a committed web API schema.
- [repo-subdirectory.md](repo-subdirectory.md) — Support for a docs project in a subdirectory of a git repo.
- [versioning-backends.md](versioning-backends.md) — The choice of where versions come from: git, no version control, or another version control from a separate package; versions from tags only.
- [tag-versions.md](tag-versions.md) — Merged into versioning-backends.md.
- [doc-symlinks.md](doc-symlinks.md) — A symlink (a file that only points to another file or directory) under `docs/` is judged by what it leads to, never by its name: one that leads to a doc, to a directory with a doc inside, out of the repo or to nothing is a check problem, with a hint that depends on where it leads. Listings and the site leave such docs out; symlinked images reach the site as the file they point to.
- [status-notes.md](status-notes.md) — Partly built docs: a list of statuses with status notes, checked, listed and shown on the site; and how a doc without a status is listed and shown.
- [limits.md](limits.md) — What docspecsite deliberately does not handle: text that is not UTF-8 beyond the listed cases, and a few other limits.
- [glossary.md](glossary.md) — docspecsite's terms in plain language.
