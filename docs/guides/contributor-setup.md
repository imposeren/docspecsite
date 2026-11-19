---
title: Set up your machine to contribute
summary: One-time setup for working on docspecsite itself — Docker, uv, prek and the commit hooks — and the docker compose commands used every day.
layer: guides
status: specified
milestone: first-release
priority: should
components: [quality-gate, dev-environment]
tags: [guide, setup]
related:
  - architecture/dev-environment.md
  - architecture/quality-gate.md
  - agents/claude-code-setup.md
---

# Set up your machine to contribute

After this guide, you can run docspecsite's tests and tools from its source and your commits run the project's hooks.
Why the setup looks like this: [architecture/dev-environment.md](../architecture/dev-environment.md) and [architecture/quality-gate.md](../architecture/quality-gate.md).

## Before you start

- Docker Engine with Compose v2, and git.
- [uv](https://docs.astral.sh/uv/): the `pyrefly` and `docs-check` commit hooks run through it, and it runs every other command natively too (`uv run pytest`, `uv run docspecsite check`, …).
- [Claude Code](https://claude.com/claude-code), for agent-assisted work ([agents/claude-code-setup.md](../agents/claude-code-setup.md)).

## Steps

1. Install [prek](https://github.com/j178/prek) (a single binary).
2. In the repo, run `printf 'UID=%s\nGID=%s\n' "$(id -u)" "$(id -g)" >> .env` once, so containers run as your user ([architecture/dev-environment.md](../architecture/dev-environment.md)); bash and zsh don't export `UID` and `GID` themselves.
3. Run `docker compose build dev`: builds the dev image with the pinned Python and the locked dependencies.
4. Run `uv sync`, then `prek install`: the hooks' environment, and the commit hooks from `.pre-commit-config.yaml`.

## Daily use

- `docker compose run --rm test` runs the tests; `lint`, `typecheck` and `docs-check` are the other checks, and `docker compose run --rm docs <command>` runs docspecsite itself from the source ([architecture/dev-environment.md](../architecture/dev-environment.md#services)).
- Commit as usual; the hooks run automatically.
- Before committing, run the tests and get the change reviewed against its docs ([architecture/quality-gate.md](../architecture/quality-gate.md#review-before-commit)).
- To read the docs as a site: `docker compose run --rm docs-build && docker compose up docs-serve`, then open http://127.0.0.1:8071. `docker compose run --rm docs build --include-worktree` shows uncommitted edits.
- After a change to `pyproject.toml` or `uv.lock`, run `docker compose build dev` again.
- After an interactive rebase, run `prek run --from-ref <base> --to-ref HEAD`: rebases don't run the commit hooks.

## Check that it worked

- `docker compose run --rm test` passes, and `prek run --all-files` runs every hook and passes on a clean checkout.

## If something goes wrong

- Hooks fail on files you didn't touch: run `prek run --all-files` on a clean `main` to see whether the problem is already there.
- A command fails with an import error after a dependency change: the dev image is out of date; run `docker compose build dev`.
