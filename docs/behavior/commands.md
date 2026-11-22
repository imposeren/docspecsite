---
title: Commands
summary: The docspecsite command line — `check`, `list`, `backlinks` and `build`, with their options, output and exit codes.
layer: behavior
status: [implemented, changed]
milestone: first-release
priority: must
code: [docspecsite.cli]
components: [cli, checks, queries, site]
tags: [cli, checks, rendering]
related:
  - scenarios/requirements.md
  - behavior/requirements.md
  - architecture/docs-tooling.md
  - behavior/versioning-backends.md
  - behavior/status-notes.md
---

# Commands

`docspecsite [--repo DIR] <command> [options]` works on the docs of one repo: the current directory, or `DIR` given with `--repo` (the [checked repo](glossary.md)).
Every command reads `docspecsite.toml` from disk first ([configuration.md](configuration.md)), then picks the [versioning backend](glossary.md), the part of docspecsite that reads the project's version control ([versioning-backends.md](versioning-backends.md)).
These stop every command with an error and exit code 1: a backend chosen by name that cannot read the checked repo (such as `git` outside a git repository), and `auto` finding more than one backend that recognizes it.
`list`, `build` and `backlinks` also stop when `backend` names no installed backend; `check` reports that as a problem ([configuration.md](configuration.md#versioning)).
A subdirectory of a git repository stops every command with an error and exit code 1, also with `auto`, unless `backend = "none"` (for a docs project in a subdirectory, see [repo-subdirectory.md](repo-subdirectory.md)).
`docspecsite --version` prints the installed version.
A command-line error (an unknown option, or an option value that is not valid, such as an unknown name in `--parts` or `--optional-checks`) stops the command before it starts, with a usage message on stderr (the command's error output) and exit code 2.

| Command | Does |
| -- | -- |
| `check [--optional-checks C,…] [--no-hints]` | Runs every check ([DS-20](requirements.md#checks), [DS-33](requirements.md#checks)) on the working tree (the files as they are now on disk). `--no-hints` leaves out the hint lines under the problems ([DS-51](requirements.md#checks)). `--optional-checks` adds the optional checks it names: `code`, the code check ([DS-36](requirements.md#checks)), and the checks of the backend in use, such as `git:staged`, which reports docs marked in git as deleted or renamed in the next commit ("staged") ([DS-6](requirements.md#versioning), [DS-43](versioning-backends.md#requirements)). |
| `list [--layer L] [--status S] [--component C] [--tag T] [--milestone M] [--priority P] [--format text\|json]` | Prints the docs whose front matter matches every given filter, from the working tree ([DS-17](requirements.md#navigation-and-indexes)). |
| `backlinks <path> [--format text\|json]` | Prints the docs that link to `<path>` through body links, `related`, `redirect_to` or `superseded_by`, from the working tree ([DS-28](requirements.md#navigation-and-indexes)). |
| `build [--ref main] [--out site] [--parts P,…] [--include-worktree] [--strict]` | Renders the static site; with version control, from the history of a [ref](glossary.md) ([DS-7](requirements.md#rendering) … [DS-19](requirements.md#generated-reference-layer)). |

## check

> **Changed, not built yet.** The `git:staged` check is still the `--staged` option, which the `docs-check` hook runs, and `--optional-checks` knows only `code`.

Each problem is printed on its own line as `docs/<path>:<line>: <message>`, or as `<file>: <message>` for a problem outside `docs/` (such as an invalid `docspecsite.toml`, or a `Docs:` line in code found by the `code` check); the line number is left out when the problem concerns the whole file.
A problem may carry a hint, which says how to fix this particular problem: it is printed on its own line right under the problem, indented by two spaces and starting with `hint: `.
The problem line always has the same form, so a script can match it, while the wording of the hint changes from case to case; `--no-hints` leaves the hint lines out, for scripts that read the output ([DS-51](requirements.md#checks)).
In problems and hints, every piece of exact text is in double quotes: a value, a field name, a status note text, a heading (as written in the file: with its `#` marks, or, for a heading underlined with `===` or `---`, its first line), text to write, a path to create.
The path at the start of the line, which only says where the problem is, stays unquoted:

```
docs/import.md:12: status note "Not built yet." ("specified") in a doc with the single status "implemented"
  hint: add "specified" to "status" so it reads "status: [implemented, specified]", or remove the status note from the section "## Import"
```

A doc that cannot be read, or that is not valid UTF-8, is a problem on that doc, and the other docs are still checked.
A doc whose page would take the URL of a generated page is a problem too ([architecture/docs-tooling.md](../architecture/docs-tooling.md#output-layout)).

A doc's title, its first level-1 heading (`# Import`, or `Import` underlined with `===`), must come right after the front matter, and a doc has no other level-1 heading ([DS-52](requirements.md#checks)).
These rules give two problems; they are not checked in a doc whose front matter is missing or does not load.
Text between the front matter and the title, an HTML comment included, is a problem on the line where that text starts.
A doc without a title is a problem on the line where the text after the front matter starts, or on the doc's first line when there is no such text.
Both give the same problem; with text before the title it reads:

```
the doc does not start with its title heading
  hint: move this text below "# Import", or remove it
```

When the doc has no title, the hint offers the front matter's `title` as the heading: `hint: add the title "# Import" right after the front matter`, or `hint: add a "#" title heading right after the front matter` when the front matter has no `title`.
Each level-1 heading after the title, in either style, is a problem on its line:

```
"# Export" is a second level-1 heading; a doc has one, its title
  hint: write it as "## Export"
```

In a [partly built doc](status-notes.md), whose `status` is a list of statuses, the check reports each case listed in [DS-46](status-notes.md#requirements): a problem with the `status` field (a status listed twice, `draft`, `deprecated` or `redirect` combined with other statuses, a listed status that no status note gives) on the doc's first line, and a problem with a status note (one whose status is not in `status`, one that gives the status its section already has, a second one in a section, one right under the doc's title, any in a doc with a single status) on the status note's line.
Each of these problems names the statuses involved and carries a hint ([DS-46](status-notes.md#requirements)).
A count of the problems follows on stderr.

`--optional-checks` names the optional checks to run, separated by commas without spaces.
docspecsite's own optional checks have plain names (`code`); a backend's checks are named `<backend>:<check>` (`git:staged`).
Only docspecsite's own checks and those of the backend in use are available: any other name, such as `git:staged` with `backend = "none"`, or an empty list, is a command-line error whose message lists the available checks.
The `git:staged` check (`--optional-checks git:staged`) is a problem for each doc that git has staged as deleted or renamed ([DS-6](requirements.md#versioning)); the `docs-check` commit hook runs it.
The `code` check (`--optional-checks code`) checks the code in the settings' `code-dirs`, from the working tree: each `Docs:` line, Sphinx role and `code:` link in a docstring is a problem on its code file when its target is not found.
A package name found in more than one code directory is a problem naming the package and its directories, and the code is then not checked.
Without `code-dirs` it adds nothing.

The exit code is 0 when no problem is found, and 1 when there are problems.

## list

`--status S` matches a doc that has `S` anywhere in its `status`, so a partly built doc is found under each of its statuses ([DS-47](status-notes.md#requirements)).
Text output has one line per doc: path, status, title and summary, separated by tabs; a list of statuses is shown comma-separated without spaces, in the doc's order (`implemented,specified`).
`--format json` prints a JSON list with the path and the fields `title`, `summary`, `layer`, `status`, `components`, `tags`, `milestone` and `priority`; `status` is a string for a single status and a list of strings for a list.
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

> **Changed, not built yet.** Git is the only version control: there is no `versioning:` line, no `none` backend and no link patterns, and a code-only build links docs under `<source-url>/blob/<commit>/`.

The site is written to `--out` (default `site/`, relative to the current directory).
Files of the previous build that are no longer produced are removed; nothing else in the directory is touched.
Rendered page bodies are kept in `.docspecsite-cache/` in the checked repo, so a rebuild renders only what changed ([DS-24](requirements.md#running)).

The first line on stderr names the backend in use, and `(auto)` when `auto` picked it: `versioning: git (auto)`, `versioning: none (auto)`, `versioning: git`.

- `--ref` names the [revision](glossary.md) whose history gives the versions; its code gives the code reference. With git it is a branch, tag or commit, and the history is its [main line of history](glossary.md); the default is `main`. With `none`, giving `--ref` is a command-line error. The settings always come from the working tree's `docspecsite.toml` ([configuration.md](configuration.md)).
- `--include-worktree` adds uncommitted doc changes as a "working copy (uncommitted)" version, and reads the code and the files under `docs/` from the working tree. It is meant for previews while writing, never for CI (continuous integration, the automatic checks and builds on a server). With `none` it is accepted and changes nothing: the docs, the code and the files under `docs/` are always read from disk.
- `--parts` names the parts to build, separated by commas without spaces: `docs`, `code` ([DS-35](requirements.md#rendering)).
  Without it, every part the repo has is built: `docs`, and `code` when `code-dirs` is set.
  An unknown part, or an empty list, is a command-line error; `code` without `code-dirs` stops the build before it starts.
- `--strict` stops at the first page error without writing anything, and turns every warning into an error. It is meant for CI.
  Warnings come only from the parts being built, so `--parts docs --strict` does not fail on docstrings.

A docs-only build (`--parts docs`):

- shows `code:` links, in every version of a doc, as their text in code style, with no link and no marker;
- lists no code modules on component pages or in `llms.txt`;
- leaves out the code reference's entry page; links to it are text.

A code-only build (`--parts code`):

- writes the code reference and its entry page, which is also the site's root page;
- has no index pages and no `llms.txt`; the breadcrumb above the code reference, component labels and status badges are text;
- links `Docs:` lines, "described in" lists and the entry page's backlinks to the doc's Markdown file on the repo host at the built revision, through the backend's [link pattern](glossary.md) ([DS-42](versioning-backends.md#requirements)), or shows the doc's path as text when there is no link pattern to use (without `source-url`, or with `none` and no pattern set) or for a doc not in the built revision (with `--include-worktree`).

The warning about `code-dirs` without `source-url` at the start of a build is given only when the `code` part is built.

Without `--strict`, an error stays local to its page: a doc version, diff, code page or index page that cannot be built is left out, and the rest of the site is still built.
Each such error is printed on stderr as `error: <page>: <message>`; warnings (such as an unresolvable link) are printed as `warning: <message>`.
A doc whose page would take the URL of a generated page (which `check` reports) is such an error for the doc's page; the generated page is kept.
Code that cannot be loaded (a package that is not valid Python or UTF-8, a package name found in more than one code directory) is a warning, `cannot load code: <message>`, and the code reference is then built without modules.
A symlink in a code directory that points to an absolute path or out of the code directories is left out of the code read from the ref, with a warning naming it.
The last line counts the pages built, rendered afresh, taken from the cache and failed.

The exit code is 0 when every page was built, 1 when a page failed or the build could not start (for example a `docspecsite.toml` that is not valid TOML or has an invalid value), and 2 for an unknown ref and the other command-line errors.
