---
title: Docs tooling
summary: Docs are checked and rendered by docspecsite at a pinned version — a prek hook on commit, docker compose services for listing, building and serving the site, and settings in docspecsite.toml.
layer: architecture
status: implemented
components: [docs-system]
tags: [docs, tooling, rendering]
related:
  - architecture/decisions/BASE-0001-docs-checked-and-rendered-by-docspecsite.md
  - architecture/quality-gate.md
  - architecture/dev-environment.md
---

# Docs tooling

The docs are checked and rendered by [docspecsite](https://github.com/imposeren/docspecsite), a separate tool that implements the rules in [meta/](../meta/index.md).
It reads `docs/` and git history, checks every doc, and writes a static site with every version of every doc to `site/` (gitignored).
What it provides and how it works is in [docspecsite's docs](https://github.com/imposeren/docspecsite/blob/main/docs/behavior/index.md).
Why this tool: [BASE-0001](decisions/BASE-0001-docs-checked-and-rendered-by-docspecsite.md) (an [architecture decision record](../meta/glossary.md#adr)).

## Version

The project pins one docspecsite version, a git tag of its repo, in two places that are kept equal:

- `.pre-commit-config.yaml`: the `rev` of the docspecsite hook repo;
- `compose.yaml`: the tag in the build context of the `docs` service.

A mismatch between the two is a review finding.

## Where it runs

- **On commit:** the `docs-check` hook from docspecsite's repo runs `docspecsite check --staged` on every commit; it also rejects staged deletes and renames under `docs/` ([meta/versioning.md](../meta/versioning.md#no-delete-no-rename), [quality-gate.md](quality-gate.md)).
- **Through docker compose** ([dev-environment.md](dev-environment.md)):

```
docker compose run --rm docs <args>     # any docspecsite command, e.g. list --status specified
docker compose run --rm docs-check      # docspecsite check
docker compose run --rm docs-build      # docspecsite build → ./site
docker compose up docs-serve            # serves ./site on http://127.0.0.1:8071
```

The `docs` image is built from docspecsite's repo at the pinned tag; the repo is bind-mounted at `/repo`.

## Settings

`docspecsite.toml` at the repo root holds the project's settings:

| Key | Meaning |
| -- | -- |
| `adr-prefix` | This repo's ADR prefix ([meta/structure.md](../meta/structure.md#adr-ids)). |
| `source-url` | The repo's web URL, for links to source files from the rendered site. |
| `code-dirs` | The directories that hold the project's Python packages (globs allowed, e.g. `["src"]`), for the generated code reference; only once the project has code. |
| `code-components` | Which components each code package belongs to, for the generated code reference; only once the project has code. |

## See also

- [quality-gate.md](quality-gate.md) — where `docspecsite check` runs automatically.
- [meta/versioning.md](../meta/versioning.md) — the rules the tool implements.
