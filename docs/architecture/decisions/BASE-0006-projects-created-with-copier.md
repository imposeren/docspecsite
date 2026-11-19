---
title: "BASE-0006: Projects are created from the template with Copier"
summary: A project is created from the template with Copier, which asks for the project's settings and options, records the template version it used, and can apply later template changes; projects are no longer git forks of the template.
layer: architecture
status: implemented
milestone: foundation
priority: must
decision: accepted
date: 2026-11-19
components: [docs-system]
tags: [adr, template, copier]
related:
  - meta/index.md
  - architecture/decisions/BASE-0001-docs-checked-and-rendered-by-docspecsite.md
---

# BASE-0006: Projects are created from the template with Copier

## Context

Projects started as git forks of the template: they shared its history and pulled template changes with `git merge`.
That works for one kind of project, but the method needs more:

- **Options per project.** Projects differ in what the template should give them, such as their languages and the language server agents use; a fork gets everything or nothing.
- **Applying the method to an existing repo**, which has its own history and cannot become a fork.
- **Several sources of docs in one project**, such as the template and, later, packs of docs for one kind of project.

Updates from the template are useful but optional: a project may take the template's changes by hand, or let an agent read what changed since the version the project records and carry over what fits.

## Options considered

1. **git fork of the template** (the previous way): updates are a `git merge`, but there are no options, no applying to an existing repo, and only one template per project.
2. **Copier**: a template is a git repository; `copier copy` asks the template's questions, renders the files marked as templates and copies the rest unchanged, and writes an answers file with the answers and the template version.
   It applies templates to existing repos and several independent templates to one project, and `copier update` applies a newer template version as a 3-way merge with conflict markers.
3. **Cookiecutter, with cruft for updates**: popular, but it creates new directories from one template only; cruft adds updates and has not had a release since December 2024.
4. **Yeoman**: needs Node and has no updates.

## Decision

- **Projects are created with Copier** (option 2), pinned to a release (`uvx copier==9.19.1`).
- The template's project files live in its `template/` directory; only files ending in `.jinja` are rendered, so the docs stay plain Markdown.
- The project's answers file (`.copier-answers.yml`) records the template version it was created or last updated from.
- **Updates are optional**: `copier update` when it helps, or an agent comparing template versions; either way the project reviews the result before committing it.
- Files a project owns after it is created (its CLAUDE.md, README, compose and prek config, layer index pages, components, glossaries, roadmap, decisions index, contributor guide, and the architecture docs it extends with its own tools: dev environment, quality gate, versioning) are written only when they don't exist yet, so an update never overwrites the project's content; they also don't receive template changes, which the project adds by hand.

## Consequences

- New projects run Copier instead of cloning; the template's README explains both creating and updating.
- Projects have no `template` remote and share no history with the template.
- The template checks itself by creating sample projects and running their checks, instead of being checked as a project.
- Template options can bring their own ADRs under their own prefixes, which projects accept as external ADRs ([BASE-0001](BASE-0001-docs-checked-and-rendered-by-docspecsite.md)).
