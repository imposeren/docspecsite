---
title: Quality gate
summary: Three checkpoints for every change — review against its spec before it is committed, fast deterministic prek hooks on commit, and CI after the push.
layer: architecture
status: specified
milestone: foundation
priority: must
components: [quality-gate]
tags: [quality, git-hooks, review, agents]
related:
  - architecture/decisions/BASE-0002-quality-gate-no-mistakes-and-prek.md
  - architecture/decisions/BASE-0004-mdformat-for-markdown.md
  - architecture/docs-tooling.md
  - guides/contributor-setup.md
---

# Quality gate

Changes pass three checkpoints: **review** before they are committed, **prek** hooks when committing (seconds, deterministic), and **CI** after the push.
Rationale: [BASE-0002](decisions/BASE-0002-quality-gate-no-mistakes-and-prek.md) (an [architecture decision record](../meta/glossary.md#adr)).

## prek (on commit)

[prek](https://github.com/j178/prek) is a fast, drop-in reimplementation of `pre-commit` and reads the standard `.pre-commit-config.yaml`. Hooks:

| Hook | Runs | Purpose |
| -- | -- | -- |
| `docs-check` | `docspecsite check --staged`, from docspecsite's repo at the pinned version ([docs-tooling.md](docs-tooling.md)), on every commit (a commit that only deletes a doc stages no file for a filter to match) | Front matter, links, indexes, vocabulary, and rejects staged `D`/`R` changes under `docs/` ([meta/versioning.md](../meta/versioning.md#no-delete-no-rename)). |
| `mdformat` | mdformat on Markdown, with compact tables and front matter passed through ([BASE-0004](decisions/BASE-0004-mdformat-for-markdown.md)); settings in `.mdformat.toml` | Consistent Markdown; never re-wraps lines. |
| `no-fixed-config-dir` | a pattern check over text files | The Claude Code config directory is written as `${CLAUDE_CONFIG_DIR:-~/.claude}`, never as a fixed path. |
| standard hygiene | prek's built-in hooks: trailing whitespace, EOF newline, YAML validity, large files |  |

A project adds the hooks for its own languages (linters, formatters, type checkers) next to these, with an ADR for each tool choice.

Where hooks run:

- mdformat runs in an environment that prek creates and pins itself; `docs-check` is defined in docspecsite's repo, and prek installs it at the pinned version. Neither needs anything on the host.
- `prek` itself is a single static binary on the host.

Hooks run on what a commit stages.
`git rebase -i` (squash, fixup) does not run them; after a rebase, `prek run --from-ref <base> --to-ref HEAD` checks every file the branch changed.

## Review (before commit)

Every change is reviewed against the docs it implements before it is committed: does the code do what its `specified` docs say, are statuses honest (`specified` → `implemented`), and does nothing contradict an `implemented` doc ([agents/working-from-specs.md](../agents/working-from-specs.md)).
Agent work gets an agent review in a fresh context (in Claude Code, `/code-review` or an equivalent review skill), then the maintainer's review; nothing is committed before both.
A change that alters behavior is also checked live — the changed command or endpoint is run and its output inspected — not only through its tests.

Pushing goes straight to `origin`; there is no separate push gate.

## CI (after push)

CI re-runs the prek hooks and the tests on every push, as the backstop for anything committed without them.
The CI system is the project's own choice, recorded in an ADR.

## See also

- [docs-tooling.md](docs-tooling.md) — the `docspecsite check` command.
