---
title: Set up your machine to contribute
summary: One-time setup for contributing to the project — host tools, commit hooks (prek), and daily use.
layer: guides
status: implemented
milestone: foundation
priority: should
components: [quality-gate, dev-environment, agents]
tags: [guide, setup]
related:
  - architecture/dev-environment.md
  - architecture/quality-gate.md
  - agents/claude-code-setup.md
---

# Set up your machine to contribute

After this guide, your commits run the project's hooks.
Why the setup looks like this: [architecture/dev-environment.md](../architecture/dev-environment.md) and [architecture/quality-gate.md](../architecture/quality-gate.md).

## Before you start

- Docker Engine with Compose v2, and git.
- [Claude Code](https://claude.com/claude-code), for agent-assisted work.

## Steps

1. Install [prek](https://github.com/j178/prek) (a single binary).
2. In the repo, run `printf 'UID=%s\nGID=%s\n' "$(id -u)" "$(id -g)" >> .env` once, so containers run as your user ([architecture/dev-environment.md](../architecture/dev-environment.md)); bash and zsh don't export `UID` and `GID` themselves.
3. Run `prek install`: installs the commit hooks from `.pre-commit-config.yaml`.
4. Run `docker compose run --rm docs-check`: builds the docs image on first use and checks the docs.

## Daily use

- Commit as usual; the hooks run automatically.
- Before committing, get the change reviewed against its docs ([architecture/quality-gate.md](../architecture/quality-gate.md#review-before-commit)).
- Push to `origin` as usual; CI runs the checks again.
- To read the docs as a site: `docker compose run --rm docs-build && docker compose up docs-serve`, then open http://127.0.0.1:8071. `docker compose run --rm docs build --include-worktree` shows uncommitted edits.
- After an interactive rebase, run `prek run --from-ref <base> --to-ref HEAD`: rebases don't run the commit hooks.

## Check that it worked

- `prek run --all-files` runs every hook and passes on a clean checkout.

## If something goes wrong

- Hooks fail on files you didn't touch: run `prek run --all-files` on a clean `main` to see whether the problem is already there.
- A commit made with `--no-verify` skips the hooks; CI still runs them after the push.
