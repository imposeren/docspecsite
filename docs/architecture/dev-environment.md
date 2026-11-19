---
title: Development environment
summary: docker compose is the single entry point for running anything in the project; the host needs only Docker, git and prek.
layer: architecture
status: implemented
milestone: foundation
priority: must
components: [dev-environment]
tags: [docker, compose, local-dev]
related:
  - architecture/decisions/BASE-0003-docker-compose-as-entry-point.md
  - architecture/docs-tooling.md
  - guides/contributor-setup.md
---

# Development environment

Everything runs through **docker compose**, defined in `compose.yaml` at the repo root: documentation now, and the project's own services and tools as they are added.
CI uses the same images.
Rationale: [BASE-0003](decisions/BASE-0003-docker-compose-as-entry-point.md) (an [architecture decision record](../meta/glossary.md#adr)).

## Host requirements

| Tool | Required | Why |
| -- | -- | -- |
| Docker Engine + Compose v2 | yes | Runs everything. |
| git | yes | Source and doc versions. |
| prek | yes, for contributors | Commit hooks ([quality-gate.md](quality-gate.md)). |

## Services

| Service | Profile | Purpose |
| -- | -- | -- |
| `docs` | `docs` (run-once) | Any `docspecsite` command, e.g. `docker compose run --rm docs list --status specified`; built from docspecsite's repo at the pinned tag ([docs-tooling.md](docs-tooling.md#version)). |
| `docs-check` | `docs` (run-once) | `docspecsite check` |
| `docs-build` | `docs` (run-once) | `docspecsite build` → `./site` |
| `docs-serve` | `docs` | Pinned official Caddy image (`caddy:2.11.8`) serving `./site` with `docker/docs-serve/Caddyfile`, both from the repo mounted read-only (so Docker never creates a root-owned `./site`, and an edited Caddyfile is picked up after a restart), published on the host as **`127.0.0.1:8071`**; pages are sent with `Cache-Control: no-cache`, so a normal reload shows a rebuilt site. |

A project adds its own services (application, database, tools) to the same file.

Conventions:

- The repo is bind-mounted at `/repo` in tool containers; generated output is written to gitignored directories (`site/`, `.docspecsite-cache/`).
- Containers run as the host user's UID/GID (`user: "${UID:-1000}:${GID:-1000}"`) so generated files are not root-owned.
  bash and zsh do not export `UID`, and bash has no `GID`, so without them every container runs as 1000:1000.
  Set them once in `.env` (gitignored): `printf 'UID=%s\nGID=%s\n' "$(id -u)" "$(id -g)" >> .env`.
- Configuration via `.env` (gitignored) with a committed `.env.example`, once there is configuration.
- Run-once tools use `docker compose run --rm <service>`; long-running ones `docker compose up`.
- Machine-specific changes go in a `compose.override.yaml`, which compose loads automatically and git ignores; for example, to build docspecsite from a local checkout instead of its git tag, override `services.docs.build.context`.

## See also

- [docs-tooling.md](docs-tooling.md) — docs commands.
