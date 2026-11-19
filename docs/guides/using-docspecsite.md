---
title: Use docspecsite in a project
summary: How a project adds docspecsite — the docs-check prek hook and the docs compose services, both pinned to one release tag, and docspecsite.toml — and how it upgrades to a new release.
layer: guides
status: implemented
milestone: first-release
priority: must
components: [distribution]
tags: [guide, setup]
related:
  - architecture/docs-tooling.md
  - architecture/versioning.md
  - behavior/configuration.md
  - behavior/commands.md
---

# Use docspecsite in a project

After this guide, the project's commits run `docspecsite check`, and docker compose lists, builds and serves its docs.
A project started from the [docs-driven template](https://github.com/imposeren/docs-driven-template) has all of this already; it only fills in `docspecsite.toml` and bumps the version when it upgrades.
How it works: [architecture/docs-tooling.md](../architecture/docs-tooling.md#how-other-repos-use-docspecsite).

## Before you start

- The project's docs follow the method's layout ([meta/structure.md](../meta/structure.md)): a `docs/` directory with an `index.md` in every directory.
- Docker Engine with Compose v2, git and [prek](https://github.com/j178/prek) on the machine.
- The docspecsite release to use: the latest [release tag](https://github.com/imposeren/docspecsite/tags) ([architecture/versioning.md](../architecture/versioning.md)); the examples below write it as `vX.Y.Z`.

## Steps

1. Add the hook to `.pre-commit-config.yaml`, with the release tag as `rev`:

   ```yaml
   repos:
     - repo: https://github.com/imposeren/docspecsite
       rev: vX.Y.Z # keep equal to the tag in compose.yaml
       hooks:
         - id: docs-check
   ```

2. Add the services to `compose.yaml`, with the same tag in the build context:

   ```yaml
   services:
     docs:
       build:
         # Keep the tag equal to the docspecsite rev in .pre-commit-config.yaml.
         context: https://github.com/imposeren/docspecsite.git#vX.Y.Z
       image: docspecsite:vX.Y.Z
       profiles: [docs]
       user: "${UID:-1000}:${GID:-1000}"
       volumes:
         - .:/repo
       working_dir: /repo

     docs-check:
       extends: docs
       command: ["check"]

     docs-build:
       extends: docs
       command: ["build"]
   ```

   Any static file server can serve `./site`; the template's `docs-serve` service uses Caddy.

3. Add `docspecsite.toml` at the repo root, with at least the project's ADR prefix and its web URL ([behavior/configuration.md](../behavior/configuration.md)):

   ```toml
   adr-prefix = "APP"
   source-url = "https://github.com/example/project"
   ```

   With Python code, also `code-dirs` (e.g. `["src"]`) and `[code-components]`.

4. Add `/site/` and `/.docspecsite-cache/` to `.gitignore`.

5. Run `prek install`.

## Daily use

- Commit as usual; `docs-check` runs on every commit.
- `docker compose run --rm docs list --status specified` — any docspecsite command ([behavior/commands.md](../behavior/commands.md)).
- `docker compose run --rm docs-build` builds `./site`, which `docs-serve` serves from the repo mounted read-only.
- `docker compose run --rm docs build --include-worktree` shows uncommitted edits.

## Upgrading

1. Read the changes since the pinned tag; a MAJOR bump (MINOR before `v1.0.0`) can make docs that passed fail ([architecture/versioning.md](../architecture/versioning.md#public-interface)).
2. Change the tag in both places: `rev` in `.pre-commit-config.yaml`, and the build context and image name in `compose.yaml`.
3. Run `docker compose build docs` and `prek run --all-files`, and fix what the new release reports.

## Check that it worked

- `prek run docs-check --all-files` passes.
- `docker compose run --rm docs-build` prints `built N pages` and writes `./site`.

## If something goes wrong

- `docs-check` and the compose services disagree: the two tags differ; set both to the same release.
- Every ADR is reported with "ADR file name must be …": `adr-prefix` is missing or not capital letters only.
- Code reference pages are missing and `code:` links do not resolve: `code-dirs` is missing or does not name the directories that hold the packages.
