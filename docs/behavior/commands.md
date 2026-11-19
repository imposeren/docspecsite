---
title: Commands
summary: The docspecsite command line — `check`, `list`, `backlinks` and `build`, with their options, output and exit codes.
layer: behavior
status: specified
milestone: first-release
priority: must
components: [cli, checks, queries, site]
tags: [cli, checks, rendering]
related:
  - behavior/requirements.md
  - architecture/docs-tooling.md
---

# Commands

`docspecsite [--repo DIR] <command> [options]` works on the docs of one git repo: the current directory, or `DIR` given with `--repo` (the checked repo).
`docspecsite --version` prints the installed version.

| Command | Does |
| -- | -- |
| `check [--staged]` | Runs every check ([DS-20](requirements.md#checks), [DS-33](requirements.md#checks)) on the working tree. `--staged` also rejects docs staged as deleted or renamed in git ([DS-6](requirements.md#versioning)). |
| `list [--layer L] [--status S] [--component C] [--tag T] [--milestone M] [--priority P] [--format text\|json]` | Prints the docs whose front matter matches every given filter, from the working tree ([DS-17](requirements.md#navigation-and-indexes)). |
| `backlinks <path> [--format text\|json]` | Prints the docs that link to `<path>` through body links, `related`, `redirect_to` or `superseded_by`, from the working tree ([DS-28](requirements.md#navigation-and-indexes)). |
| `build [--ref main] [--out site] [--include-worktree] [--strict]` | Renders the static site for a git ref ([DS-7](requirements.md#rendering) … [DS-19](requirements.md#generated-reference-layer)). |

## check

Each problem is printed on its own line as `docs/<path>:<line>: <message>`, or as `<file>: <message>` for a problem outside `docs/` (such as an invalid `docspecsite.toml` or a `Docs:` line in code); the line number is left out when the problem concerns the whole file.
A count of the problems follows on stderr.

The exit code is 0 when no problem is found, and 1 when there are problems or when `--staged` is used outside a git repo.

## list

Text output has one line per doc: path, status, title and summary, separated by tabs.
`--format json` prints a JSON list with the path and the fields `title`, `summary`, `layer`, `status`, `components`, `tags`, `milestone` and `priority`.
Docs are sorted by path, with external ADRs before the repo's own ADRs, by prefix in the order `external-adr-prefixes` lists them.
Docs whose front matter does not load are left out.
A `docspecsite.toml` that is not valid TOML or has an invalid value stops `list` with an error and exit code 1; an unknown setting is a warning.

## backlinks

`<path>` is `docs/x.md` (from the repo root), `x.md` (relative to `docs/`) or an absolute path.
Each linking doc is printed on one line: its path, the kinds of its links (`body`, `related`, `redirect_to`, `superseded_by`) and its title, separated by tabs; `--format json` prints the same as a JSON list.
A link to a directory counts as a link to its `index.md`.
The exit code is 2 when `<path>` is not a doc, else 0.

## build

The site is written to `--out` (default `site/`, relative to the current directory).
Files of the previous build that are no longer produced are removed; nothing else in the directory is touched.
Rendered page bodies are kept in `.docspecsite-cache/` in the checked repo, so a rebuild renders only what changed ([DS-24](requirements.md#running)).

- `--ref` names the branch, tag or commit whose first-parent history gives the versions; its `docspecsite.toml` gives the settings and its code the code reference.
- `--include-worktree` adds uncommitted doc changes as a "working copy (uncommitted)" version, and reads the settings, the code and the files under `docs/` from the working tree. It is meant for previews while writing, never for CI.
- `--strict` stops at the first page error without writing anything, and turns every warning into an error. It is meant for CI.

Without `--strict`, an error stays local to its page: a doc version, diff, code page or index page that cannot be built is left out, and the rest of the site is still built.
Each such error is printed on stderr as `error: <page>: <message>`; warnings (such as an unresolvable link) are printed as `warning: <message>`.
The last line counts the pages built, rendered afresh, taken from the cache and failed.

The exit code is 0 when every page was built, 1 when a page failed or the build could not start (for example a `docspecsite.toml` that is not valid TOML or has an invalid value), and 2 for an unknown ref.
