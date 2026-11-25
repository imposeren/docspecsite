---
title: Quality gate
summary: How changes to docspecsite are checked — review against the spec before commit, prek hooks on commit (Ruff, strict Pyrefly, mdformat, and docspecsite checking its own docs from source), and the full test suite before a release.
layer: architecture
status: [implemented, changed]
milestone: first-release
priority: must
components: [quality-gate]
tags: [quality, git-hooks, review, python]
related:
  - architecture/decisions/BASE-0002-quality-gate-no-mistakes-and-prek.md
  - architecture/decisions/DSS-0003-ruff-and-strict-pyrefly.md
  - architecture/decisions/DSS-0004-pytest-for-tests.md
  - architecture/dev-environment.md
  - guides/contributor-setup.md
---

# Quality gate

docspecsite follows the template's quality gate: **review** before a change is committed, **prek** hooks when committing ([BASE-0002](decisions/BASE-0002-quality-gate-no-mistakes-and-prek.md), an [architecture decision record](../meta/glossary.md#adr)).
CI is not set up for docspecsite yet; until it is, the full checks below run before every release ([versioning.md](versioning.md#releasing)).

## prek (on commit)

> **Changed, not built yet.** The `docs-check` hook still runs `uv run docspecsite check --staged`.

[prek](https://github.com/j178/prek) reads the standard `.pre-commit-config.yaml`. Hooks:

| Hook | Runs | Purpose |
| -- | -- | -- |
| `docs-check` | `uv run docspecsite check --optional-checks git:staged`, from this repo's source, on every commit (a commit that only deletes a doc stages no file for a filter to match) | Checks docspecsite's own docs with the code being committed, and rejects staged `D`/`R` changes under `docs/` ([meta/versioning.md](../meta/versioning.md#no-delete-no-rename)). |
| `mdformat` | mdformat on Markdown, with compact tables and front matter passed through ([BASE-0004](decisions/BASE-0004-mdformat-for-markdown.md)); settings in `.mdformat.toml` | Consistent Markdown; never re-wraps lines. |
| `no-fixed-config-dir` | a pattern check over text files | The Claude Code config directory is written as `${CLAUDE_CONFIG_DIR:-~/.claude}`, never as a fixed path. |
| standard hygiene | prek's built-in hooks: trailing whitespace, EOF newline, YAML validity, large files |  |
| `ruff-check`, `ruff-format` | Ruff lint (with import sorting) and format ([DSS-0003](decisions/DSS-0003-ruff-and-strict-pyrefly.md)) | Python style and common bugs. |
| `pyrefly` | `uv run pyrefly check`, strict ([DSS-0003](decisions/DSS-0003-ruff-and-strict-pyrefly.md)) | Python types. |

Where hooks run:

- Ruff and mdformat run in environments that prek creates and pins itself; the Ruff hook's version is kept equal to the Ruff pin in `pyproject.toml`.
- `pyrefly` and `docs-check` need docspecsite's own dependencies, so they run through `uv run` on the host ([dev-environment.md](dev-environment.md)).
  Not in a container: there they would miss git's temporary index of `git commit -a` or `git commit <paths>`, and fail in git worktrees, whose `.git` file points at a host path outside the mount.

The tests are not a hook: `docker compose run --rm test` takes a while, so it runs before handing a change over for review and before every release.

Hooks run on what a commit stages.
`git rebase -i` (squash, fixup) does not run them; after a rebase, `prek run --from-ref <base> --to-ref HEAD` checks every file the branch changed.

### Ruff rule sets

> **Changed, not built yet.** The configuration does not select `D1`, `D205`, `D212`, `D417`, `PLC0415`, `ERA001` and `TD003` yet.

Ruff settings live in `pyproject.toml`: line length 120, and these rule sets:

| Rules | What they check |
| -- | -- |
| `E`, `W` | pycodestyle errors and warnings: indentation, whitespace, line length, statement layout. |
| `F` | Pyflakes: undefined and unused names, unused imports, invalid syntax-level constructs. |
| `I` | Import sorting into sections (see below). |
| `UP` | pyupgrade: newer syntax where the project's Python version allows it (e.g. `list[int]` instead of `List[int]`). |
| `B` | flake8-bugbear: likely bugs, such as mutable default arguments or calls in defaults. |
| `N` | pep8-naming: naming conventions, e.g. `CamelCase` classes and exception names ending in `Error`. |
| `ISC` | Implicit string concatenation: long strings are split as adjacent literals in parentheses, not joined with `+`. |
| `S101` | No `assert` outside tests (it disappears under `python -O`); tests are exempt. |
| `BLE001` | No catch-all `except Exception`; a deliberate one carries a `# noqa: BLE001` with its reason. |
| `PLW0603` | No `global` statements. |
| `TID252` | Relative imports only one level deep (`from .x`, never `from ..x`). |
| `D1` | Public modules, classes, functions and methods have a docstring; tests are exempt. |
| `D205`, `D212` | A docstring's summary is one line that starts on the line of the opening quotes, followed by a blank line. |
| `D417` | Every parameter is documented in the `Args:` section of a docstring (Google convention, set under `[tool.ruff.lint.pydocstyle]`). |
| `PLC0415` | Imports sit at the top of the module; a deliberate import inside a function is for an optional dependency and carries a `# noqa: PLC0415` with its reason. |
| `ERA001` | No commented-out code. |
| `TD003` | A `TODO` comment links to an issue. |

Imports come in four blank-line-separated sections: standard library, third-party, first-party (`docspecsite`, as the tests import it), and the package's own modules as single-dot relative imports (`from .x import …`; `from ..x` is not allowed).

## Review (before commit)

Every change is reviewed against the docs it implements before it is committed: does the code do what its `specified` docs say, are statuses honest (`specified` → `implemented`), and does nothing contradict an `implemented` doc ([agents/working-from-specs.md](../agents/working-from-specs.md)).
Agent work gets two reviews, each in a fresh context: a spec review against the docs it implements, and a code review of the code itself ([step 6 of implementing a doc](../agents/working-from-specs.md#implementing-a-specified-doc)).
A change to a rule that docspecsite enforces also needs the matching change in the template's `docs/meta/`, synced into this repo's copy.
A change that alters behavior is also checked live — the changed command is run on a real docs tree and its output inspected — not only through its tests.

## See also

- [docs-tooling.md](docs-tooling.md#prek-hook) — the `docs-check` hook other repos use.
