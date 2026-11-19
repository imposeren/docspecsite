---
title: Development environment
summary: docker compose is the entry point for working on docspecsite — tests, lint, type check, its own docs check, build and preview run in the Dockerfile's dev target with the source mounted; uv on the host runs the commit hooks and is a shortcut for the rest.
layer: architecture
status: implemented
milestone: first-release
priority: must
components: [dev-environment]
tags: [local-dev, python, uv, docker, compose]
related:
  - architecture/decisions/BASE-0003-docker-compose-as-entry-point.md
  - architecture/decisions/DSS-0002-single-python-toolchain.md
  - architecture/docs-tooling.md
  - guides/contributor-setup.md
---

# Development environment

Everything runs through **docker compose**, defined in `compose.yaml` at the repo root, as in every repo started from the template ([BASE-0003](decisions/BASE-0003-docker-compose-as-entry-point.md), an [architecture decision record](../meta/glossary.md#adr)).
The services run the `dev` target of the `Dockerfile`: the same Python and locked dependencies as the image other repos build ([DSS-0002](decisions/DSS-0002-single-python-toolchain.md)), plus the development group (pytest, Ruff, Pyrefly), with docspecsite installed editable from `/repo`, where this checkout is mounted.
So every command runs the source being worked on.

## Host requirements

| Tool | Required | Why |
| -- | -- | -- |
| Docker Engine + Compose v2 (with BuildKit) | yes | Runs everything, and builds the image other repos use ([docs-tooling.md](docs-tooling.md#docker-image)). |
| git | yes | Source and doc versions. |
| prek | yes, for contributors | Commit hooks ([quality-gate.md](quality-gate.md)). |
| uv | yes, for contributors | The `pyrefly` and `docs-check` commit hooks run with `uv run` on the host ([quality-gate.md](quality-gate.md#prek-on-commit)); every other command can also run natively with `uv run`, for speed and IDE support. uv installs the same `.python-version` and `uv.lock` into `.venv/` ([DSS-0002](decisions/DSS-0002-single-python-toolchain.md)). |

## Services

| Service | Profile | Runs |
| -- | -- | -- |
| `dev` | `dev` (run-once) | Any command in the dev image (`docspecsite-dev:local`), e.g. `docker compose run --rm dev ruff format --check`. |
| `test` | `dev` (run-once) | `pytest`; pytest's arguments can follow, e.g. `docker compose run --rm test -k config`. |
| `lint` | `dev` (run-once) | `ruff check`; arguments can follow, as for every tool service. |
| `format` | `dev` (run-once) | `ruff format` (rewrites files); `docker compose run --rm format --check` only reports. |
| `typecheck` | `dev` (run-once) | `pyrefly check`, strict. |
| `docs` | `docs` (run-once) | Any `docspecsite` command from this source, e.g. `docker compose run --rm docs list --status specified`. |
| `docs-check` | `docs` (run-once) | `docspecsite check` on docspecsite's own docs. |
| `docs-build` | `docs` (run-once) | `docspecsite build` → `./site`. |
| `docs-serve` | `docs` | Pinned official Caddy image (`caddy:2.11.8`) serving `./site` with `docker/docs-serve/Caddyfile`, both from the repo mounted read-only (so Docker never creates a root-owned `./site`, and an edited Caddyfile is picked up after a restart), published on the host as **`127.0.0.1:8071`**; pages are sent with `Cache-Control: no-cache`, so a normal reload shows a rebuilt site. |

Conventions:

- The repo is bind-mounted at `/repo`; generated output goes to gitignored paths (`site/`, `.docspecsite-cache/`, `.pytest_cache/`, `.ruff_cache/`).
- Containers run as the host user's UID/GID (`user: "${UID:-1000}:${GID:-1000}"`), so generated files are not root-owned.
  bash and zsh do not export `UID`, and bash has no `GID`, so without them every container runs as 1000:1000.
  Set them once in `.env` (gitignored): `printf 'UID=%s\nGID=%s\n' "$(id -u)" "$(id -g)" >> .env`.
- Run-once tools use `docker compose run --rm <service>`; `docs-serve` uses `docker compose up`.
- The commit hooks are the exception: they run through uv on the host ([quality-gate.md](quality-gate.md#prek-on-commit)).
- After a change to `pyproject.toml` or `uv.lock`, rebuild the dev image: `docker compose build dev`.
- Machine-specific changes go in a `compose.override.yaml`, which compose loads automatically and git ignores.

## The runtime image

`docker build .` without a target builds the `runtime` target, the last stage of the `Dockerfile`: docspecsite as a regular package, without the development group.
That is what other repos get from the git URL ([docs-tooling.md](docs-tooling.md#docker-image)); try it on any docs tree with `docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/repo" <image> check`.

## See also

- [docs-tooling.md](docs-tooling.md) — what the code does and how the images and hook are built.
- [guides/contributor-setup.md](../guides/contributor-setup.md) — one-time setup and daily commands.
