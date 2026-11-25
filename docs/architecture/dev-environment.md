---
title: Development environment
summary: docker compose is the entry point for working on docspecsite — tests, lint, type check, its own docs check, build and preview run in the Dockerfile's dev target with the source mounted; uv on the host runs the commit hooks and is a shortcut for the rest.
layer: architecture
status: implemented
milestone: hardening  # stand-in until docs can list several milestones (backlog: docs in several milestones); this doc's first form shipped in first-release
priority: should
components: [dev-environment]
tags: [local-dev, python, uv, docker, compose]
related:
  - architecture/decisions/BASE-0003-docker-compose-as-entry-point.md
  - architecture/decisions/DSS-0002-single-python-toolchain.md
  - architecture/decisions/DSS-0008-dependency-cooldown.md
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
| uv | yes, for contributors | The `pyrefly` and `docs-check` commit hooks run with `uv run` on the host ([quality-gate.md](quality-gate.md#prek-on-commit)); every other command can also run natively with `uv run`, for speed and IDE support. uv installs the same `.python-version` and `uv.lock` into `.venv/` ([DSS-0002](decisions/DSS-0002-single-python-toolchain.md)). Version 0.13.7 or later, the floor that goes with the [dependency cooldown](#dependency-cooldown). |

## Dependency cooldown

`pyproject.toml` sets two keys under `[tool.uv]` ([DSS-0008](decisions/DSS-0008-dependency-cooldown.md)):

```toml
[tool.uv]
required-version = ">=0.13.7"
exclude-newer = "14 days"
```

- `exclude-newer = "14 days"`: `uv lock` takes only package versions uploaded to the index at least 14 days before it resolves, for direct and transitive dependencies ([uv docs at tag 0.13.7, "Dependency cooldowns"](https://github.com/astral-sh/uv/blob/0.13.7/docs/concepts/resolution.md#dependency-cooldowns), checked 2026-11-26).
  `uv.lock` records the span (`exclude-newer-span = "P14D"` under `[options]`), not a date, so `uv lock --check` stays satisfied as time passes; uv resolves again only on `--upgrade`, `--refresh` or a changed requirement.
  The image and `uv sync` install what the lock holds.
- `required-version = ">=0.13.7"`: 0.13.7 is the version whose span support was checked.
  uv 0.9.17 up to 0.13.6 stops with uv's version error instead of locking.
  uv before 0.9.17 cannot read the span: it only warns that it cannot parse `pyproject.toml`'s settings, ignores the floor with them, and locks without the cooldown; a current uv's `uv lock --check`, which the `uv-lock-check` commit hook runs ([quality-gate.md](quality-gate.md#prek-on-commit)), then reports the lock as out of date (trial locks with uv 0.9.16, 0.9.17, 0.11.0, 0.12.0 and 0.13.7, 2026-11-26).

A release needed sooner (a security fix, or a requirement only a newer version meets) is let through for its package alone with an `exclude-newer-package` entry under `[tool.uv]` that gives a shorter duration, e.g. `exclude-newer-package = { setuptools = "2 days" }`, not `false`, which would lift the cooldown for that package for good.
The entry is removed in the first `uv lock --upgrade` after that release is older than 14 days.
Nothing removes it automatically; exemptions are rare enough to track by hand.

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
