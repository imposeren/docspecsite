---
title: Versioning and releases
summary: docspecsite releases are git tags vMAJOR.MINOR.PATCH on main, with MAJOR tied to incompatible changes in what other repos depend on; projects pin a tag for both the prek hook and the Docker image.
layer: architecture
status: implemented
milestone: first-release
priority: must
components: [distribution, deploy]
tags: [versioning, releases, semver]
related:
  - architecture/decisions/BASE-0005-semver-from-git-tags.md
  - architecture/docs-tooling.md
  - guides/using-docspecsite.md
---

# Versioning and releases

A **release** is a git tag `vMAJOR.MINOR.PATCH` on `main` ([SemVer](https://semver.org/), semantic versioning), as in [BASE-0005](decisions/BASE-0005-semver-from-git-tags.md) (an [architecture decision record](../meta/glossary.md#adr)).
The first release is `v0.1.0` ([roadmap.md](../roadmap.md)).
Nothing is published to a package index or a container registry: projects take docspecsite straight from this repo at a tag.

## Public interface

What other repos depend on, and so what a MAJOR bump is about:

- the commands, their options, output formats and exit codes ([behavior/commands/](../behavior/commands/index.md));
- the keys of `docspecsite.toml` ([behavior/configuration.md](../behavior/configuration.md));
- the rules `check` enforces, i.e. which docs pass ([behavior/commands/check.md](../behavior/commands/check.md#requirements));
- the hook id `docs-check` and the image's contract: entrypoint `docspecsite`, the repo mounted at `/repo`, Mermaid bundled.

| Bump | When |
| -- | -- |
| **MAJOR** | Something in the public interface changes incompatibly: a command, option or setting is removed or renamed, or a docs tree that passed `check` fails it (a stricter rule). |
| **MINOR** | New features, including new commands, options, settings and pages, and newly accepted docs. |
| **PATCH** | Fixes and internal changes with no new features. |

Before `v1.0.0`, incompatible changes bump MINOR.
A method change in the template that docspecsite enforces usually means a stricter rule, so its release is at least a MINOR bump before `v1.0.0`.

## Where the version lives

- The **git tag** names the release; projects pin it in `.pre-commit-config.yaml` (`rev`) and `compose.yaml` (the build context's `#vX.Y.Z`), the same in both.
- `version` in `pyproject.toml` is what `docspecsite --version` prints; the release commit sets it to the tag's version.
  The `internal` renderer's build cache is also keyed by a hash of the package's files, so a change between releases never reuses stale pages.
  The image is built from a git context without `.git`, so docspecsite cannot read its version from git at run time.

## Releasing

1. On `main`, `docker compose run --rm` with `test`, `lint`, `typecheck` and `docs-check` passes, `docker compose run --rm dev ruff format --check` finds nothing to change, and the runtime image builds and checks a docs tree ([dev-environment.md](dev-environment.md#services)).
2. Set `version` in `pyproject.toml` to the new version, run `uv lock`, and commit.
3. Tag that commit `vX.Y.Z` and push the tag.
