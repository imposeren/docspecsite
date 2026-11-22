---
title: Commands
summary: The docspecsite command line — `check`, `list`, `backlinks` and `build`, with their options, output and exit codes.
layer: behavior
status: specified
milestone: first-release
priority: must
code: [docspecsite.cli]
components: [cli, checks, queries, site]
tags: [cli, checks, rendering]
related:
  - behavior/requirements.md
  - architecture/docs-tooling.md
---

# Commands

`docspecsite [--repo DIR] <command> [options]` works on the docs of one git repo: the current directory, or `DIR` given with `--repo` (the checked repo).
It must be the top level of the git repo: a subdirectory of one stops every command with an error and exit code 1 (support for a docs project in a subdirectory is planned: [repo-subdirectory.md](repo-subdirectory.md)).
`docspecsite --version` prints the installed version.

| Command | Does |
| -- | -- |
| `check [--staged] [--code]` | Runs every check ([DS-20](requirements.md#checks), [DS-33](requirements.md#checks)) on the working tree. `--staged` also rejects docs staged as deleted or renamed in git ([DS-6](requirements.md#versioning)); `--code` adds the code check ([DS-36](requirements.md#checks)). |
| `list [--layer L] [--status S] [--component C] [--tag T] [--milestone M] [--priority P] [--format text\|json]` | Prints the docs whose front matter matches every given filter, from the working tree ([DS-17](requirements.md#navigation-and-indexes)). |
| `backlinks <path> [--format text\|json]` | Prints the docs that link to `<path>` through body links, `related`, `redirect_to` or `superseded_by`, from the working tree ([DS-28](requirements.md#navigation-and-indexes)). |
| `build [--ref main] [--out site] [--parts P,…] [--include-worktree] [--strict]` | Renders the static site for a git ref ([DS-7](requirements.md#rendering) … [DS-19](requirements.md#generated-reference-layer)). |

## check

Each problem is printed on its own line as `docs/<path>:<line>: <message>`, or as `<file>: <message>` for a problem outside `docs/` (such as an invalid `docspecsite.toml`, or a `Docs:` line in code found by `--code`); the line number is left out when the problem concerns the whole file.
A doc that cannot be read, or that is not valid UTF-8, is a problem on that doc, and the other docs are still checked.
A doc whose page would take the URL of a generated page is a problem too ([architecture/docs-tooling.md](../architecture/docs-tooling.md#output-layout)).
A count of the problems follows on stderr.

`--code` also checks the code in the settings' `code-dirs`, from the working tree: each `Docs:` line, Sphinx role and `code:` link in a docstring is a problem on its code file when its target is not found.
A package name found in more than one code directory is a problem naming the package and its directories, and the code is then not checked.
Without `code-dirs` it adds nothing.

The exit code is 0 when no problem is found, and 1 when there are problems or when `--staged` is used outside a git repo.

## list

Text output has one line per doc: path, status, title and summary, separated by tabs.
`--format json` prints a JSON list with the path and the fields `title`, `summary`, `layer`, `status`, `components`, `tags`, `milestone` and `priority`.
Docs are sorted by path, with external ADRs before the repo's own ADRs, by prefix in the order `external-adr-prefixes` lists them.
Docs whose front matter does not load are left out.
A `docspecsite.toml` that is not valid TOML or has an invalid value stops `list` with an error and exit code 1; an unknown setting is a warning.
A doc that cannot be read, or that is not valid UTF-8, stops `list` with an error naming the doc and exit code 1.

## backlinks

`<path>` is `docs/x.md` (from the repo root), `x.md` (relative to `docs/`) or an absolute path.
Each linking doc is printed on one line: its path, the kinds of its links (`body`, `related`, `redirect_to`, `superseded_by`) and its title, separated by tabs; `--format json` prints the same as a JSON list.
A link to a directory counts as a link to its `index.md`.
A doc that cannot be read, or that is not valid UTF-8, stops `backlinks` with an error naming the doc and exit code 1.
Otherwise the exit code is 2 when `<path>` is not a doc, else 0.

## build

The site is written to `--out` (default `site/`, relative to the current directory).
Files of the previous build that are no longer produced are removed; nothing else in the directory is touched.
Rendered page bodies are kept in `.docspecsite-cache/` in the checked repo, so a rebuild renders only what changed ([DS-24](requirements.md#running)).

- `--ref` names the branch, tag or commit whose first-parent history gives the versions; its code gives the code reference. The settings always come from the working tree's `docspecsite.toml` ([configuration.md](configuration.md)).
- `--include-worktree` adds uncommitted doc changes as a "working copy (uncommitted)" version, and reads the code and the files under `docs/` from the working tree. It is meant for previews while writing, never for CI.
- `--parts` names the parts to build, separated by commas without spaces: `docs`, `code` ([DS-35](requirements.md#rendering)).
  Without it, every part the repo has is built: `docs`, and `code` when `code-dirs` is set.
  An unknown part, an empty list, or `code` without `code-dirs` stops the build before it starts.
- `--strict` stops at the first page error without writing anything, and turns every warning into an error. It is meant for CI.
  Warnings come only from the parts being built, so `--parts docs --strict` does not fail on docstrings.

A docs-only build (`--parts docs`):

- shows `code:` links, in every version of a doc, as their text in code style, with no link and no marker;
- lists no code modules on component pages or in `llms.txt`;
- leaves out the code reference's entry page; links to it are text.

A code-only build (`--parts code`):

- writes the code reference and its entry page, which is also the site's root page;
- has no index pages and no `llms.txt`; the breadcrumb above the code reference, component labels and status badges are text;
- links `Docs:` lines, "described in" lists and the entry page's backlinks to the doc's Markdown file on the repo host at the built commit, or shows the doc's path as text without `source-url` or for a doc not in the built commit (with `--include-worktree`).

The warning about `code-dirs` without `source-url` at the start of a build is given only when the `code` part is built.

Without `--strict`, an error stays local to its page: a doc version, diff, code page or index page that cannot be built is left out, and the rest of the site is still built.
Each such error is printed on stderr as `error: <page>: <message>`; warnings (such as an unresolvable link) are printed as `warning: <message>`.
A doc whose page would take the URL of a generated page (which `check` reports) is such an error for the doc's page; the generated page is kept.
Code that cannot be loaded (a package that is not valid Python or UTF-8, a package name found in more than one code directory) is a warning, `cannot load code: <message>`, and the code reference is then built without modules.
A symlink in a code directory that points to an absolute path or out of the code directories is left out of the code read from the ref, with a warning naming it.
The last line counts the pages built, rendered afresh, taken from the cache and failed.

The exit code is 0 when every page was built, 1 when a page failed or the build could not start (for example a `docspecsite.toml` that is not valid TOML or has an invalid value), and 2 for an unknown ref.
