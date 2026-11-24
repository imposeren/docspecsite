---
title: Commands
summary: The docspecsite command line — `check`, `list`, `backlinks` and `build`, with their options, output and exit codes.
layer: behavior
status: [implemented, changed, specified]
milestone: first-release
priority: must
code: [docspecsite.cli]
components: [cli, checks, queries, site]
tags: [cli, checks, rendering]
related:
  - scenarios/docs-format.md
  - scenarios/commands.md
  - scenarios/doc-symlinks.md
  - behavior/doc-symlinks.md
  - behavior/requirements.md
  - behavior/docs-format.md
  - behavior/site.md
  - behavior/code-reference.md
  - behavior/distribution.md
  - architecture/docs-tooling.md
  - behavior/versioning-backends.md
  - behavior/status-notes.md
  - behavior/limits.md
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
| `check [--optional-checks C,…] [--no-hints] [--strict]` | Runs every check ([DS-20](#checks), [DS-33](docs-format.md#requirements)) on the working tree (the files as they are now on disk). `--no-hints` leaves out the hint lines under the problems ([DS-51](#checks)). `--strict` makes warnings count as problems ([check](#check)). `--optional-checks` adds the optional checks it names: `code`, the code check ([DS-36](#checks)), and the checks of the backend in use, such as `git:staged`, which reports docs marked in git as deleted or renamed in the next commit ("staged") ([DS-6](versioning-backends.md#versions-of-a-doc), [DS-43](versioning-backends.md#requirements)). |
| `list [--layer L] [--status S] [--component C] [--tag T] [--milestone M] [--priority P] [--format text\|json]` | Prints the docs whose front matter matches every given filter, from the working tree ([DS-17](#queries)). |
| `backlinks <path> [--format text\|json]` | Prints the docs that link to `<path>` through body links, `related`, `redirect_to` or `superseded_by`, from the working tree ([DS-28](#queries)). |
| `build [--ref REF] [--out site] [--parts P,…] [--include-worktree] [--strict]` | Renders the static site; with version control, from the history of a [ref](glossary.md), by default the commit that is checked out ([DS-7](site.md#rendering) … [DS-19](code-reference.md#requirements)). |

## Requirements

These requirements are part of the [DS-n](../meta/glossary.md#ds-n) numbering listed in [requirements.md](requirements.md).

### Queries

- **DS-17** A query command for agents: list docs filtered by tag / component / status / layer / milestone / priority, without rendering; a partly built doc matches each of its statuses ([DS-47](status-notes.md#requirements)).
- **DS-28** A query command for agents: list the docs that link to a given doc (body links, `related`, `redirect_to`), without rendering.

### Checks

> **Changed, not built yet.** The deletes-and-renames check is still `check --staged`. Every `web-api:` link is reported as a problem: there is no HTTP API reference for it to resolve to. A doc in a layer without a build status is checked like any other doc.

- **DS-20** A check command validates: front-matter schema, `layer` matches directory, every directory has an `index.md` that lists each direct child doc and child directory with a description in its `## Children` section ([meta/structure.md](../meta/structure.md#every-directory-has-an-indexmd)), where a symlink is neither a directory that needs an `index.md` nor a child that an index lists ([DS-39](doc-symlinks.md#requirements)), all links (body, `related`, `redirect_to`, `code:`, `web-api:`) resolve, where a body link to a directory is a link to its `index.md`, and an anchor in it names a heading there ([check](#check)), components are in the project's component list or the shared ones ([meta/vocabulary.md](../meta/vocabulary.md)), no `#`, `%` or `?` in file or directory names under `docs/` ([meta/structure.md](../meta/structure.md#naming)) and no file name under `docs/` that is not valid UTF-8 ([Input that cannot be used](#input-that-cannot-be-used)), no symlink under `docs/` that leads out of the repo, to nothing, to a doc or to a directory with a doc inside, whatever the symlink's own name ([DS-39](doc-symlinks.md#requirements)), every doc is readable UTF-8, every doc has its title in its place ([DS-52](docs-format.md#requirements)), and no doc's page takes the URL of a generated page ([architecture/docs-tooling.md](../architecture/docs-tooling.md#output-layout)).
  It also checks that a partly built doc's statuses and its status notes agree ([DS-44](status-notes.md#requirements) to [DS-46](status-notes.md#requirements)), and that a scenario doc names the docs it gives cases for ([DS-53](docs-format.md#layers-without-a-build-status)).
  Doc templates are not docs and are not checked ([meta/structure.md](../meta/structure.md#outside-docs)).
  The code is not checked: specs may change before it does ([meta/linking.md](../meta/linking.md#code-links)).
  Deletes and renames under `docs/` ([DS-6](versioning-backends.md#versions-of-a-doc)) are an optional check of the version control's backend ([DS-43](versioning-backends.md#requirements)).
- **DS-51** A problem may carry a **hint**: a line right under the problem that says how to fix it in this case, such as which value to add and the text of the field as it then reads ([check](#check)).
  The problem line always has the same form, so scripts can match it; the wording of the hint differs from case to case, and `check --no-hints` leaves hints out.
  In problems and hints, every piece of exact text (a value, a field name, a status note text, a heading, text to write, a path to create) is in double quotes; the path that says where the problem is stays unquoted.
- **DS-36** A **code check**, run on demand once an implementation is done, validates the code's references: `Docs:` docstring lines point at existing docs (and headings, with an anchor), and Sphinx roles ([DS-34](code-reference.md#requirements)) and `code:` links in docstrings point at code the code reference shows.
  An empty `code:` target in a docstring is a problem as in a doc's text ([Input that cannot be used](#input-that-cannot-be-used)).

How projects run the check before each commit and in CI is in [distribution.md](distribution.md) ([DS-21](distribution.md#requirements)).

## check

> **Changed, not built yet.** The `git:staged` check is still the `--staged` option, which the `docs-check` hook runs, and `--optional-checks` knows only `code`. `check` gives no warnings and has no `--strict` option.

Each problem is printed on its own line as `docs/<path>:<line>: <message>`, or as `<file>:<line>: <message>` for a problem outside `docs/` (such as a `Docs:` line in code found by the `code` check); the line number, with its colon, is left out only when the problem concerns the whole file, such as an invalid `docspecsite.toml` (`docspecsite.toml: <message>`).
A problem may carry a hint, which says how to fix this particular problem: it is printed on its own line right under the problem, indented by two spaces and starting with `hint: `.
The problem line always has the same form, so a script can match it, while the wording of the hint changes from case to case; `--no-hints` leaves the hint lines out, for scripts that read the output ([DS-51](#checks)).
In problems and hints, every piece of exact text is in double quotes: a value, a field name, a status note text, a heading (as written in the file: with its `#` marks, or, for a heading underlined with `===` or `---`, its first line), text to write, a path to create.
The path at the start of the line, which only says where the problem is, stays unquoted:

```
docs/import.md:12: status note "Not built yet." ("specified") in a doc with the single status "implemented"
  hint: add "specified" to "status" so it reads "status: [implemented, specified]", or remove the status note from the section "## Import"
```

A doc that cannot be read, or that is not valid UTF-8, is a problem on that doc, and the other docs are still checked.
Other input the check cannot use, such as a file name that is not valid UTF-8, is one problem each ([Input that cannot be used](#input-that-cannot-be-used)).
A doc whose page would take the URL of a generated page is a problem too ([architecture/docs-tooling.md](../architecture/docs-tooling.md#output-layout)).

A file or directory under `docs/` whose name contains `#`, `%` or `?` is a problem on that path ([meta/structure.md](../meta/structure.md#naming)):

```
docs/guides/faq?.md: name contains "#", "%" or "?", which break links to the rendered page
```

A [symlink](glossary.md) (a file that only points to another file or directory) under `docs/` is judged by what it leads to in the end, never by its own name ([DS-39](doc-symlinks.md#requirements), [doc-symlinks.md](doc-symlinks.md#how-a-symlink-is-followed)).
It is a problem when it leads out of the repo, to nothing, to a doc (a `.md` file) or to a directory with a doc inside.
The problem is reported on the symlink, names the target in the form the symlink stores it, and says where the symlink leads.
The hint depends on where that is ([doc-symlinks.md](doc-symlinks.md#what-the-check-reports)), and a hint names its paths from the repo root.
The example below shows five cases, in this order:

1. a symlink that leads to a doc inside `docs/`;
2. one that leads to a doc outside `docs/`;
3. one that leads to nothing (a target that does not exist, or a loop of symlinks);
4. one that leads out of the repo (here through an absolute path, one that starts at the root of the file system), which gets no hint;
5. one that leads to a directory outside `docs/` with a doc inside.

```
docs/guides/alias.md: symlink to "setup.md" leads to a doc
  hint: link to "docs/guides/setup.md" in the text instead, and remove the symlink
docs/reference/shared.md: symlink to "../../vendor/shared.md" leads to a doc
  hint: move "vendor/shared.md" to "docs/reference/shared.md", and put the symlink at "vendor/shared.md" instead
docs/guides/old.md: symlink to "gone.md" leads to nothing
  hint: remove the symlink; its target does not exist
docs/guides/notes.md: symlink to "/srv/notes/setup.md" leads out of the repo
docs/shared: symlink to "../vendor/shared" leads to a directory with docs
  hint: move "vendor/shared" to "docs/shared", and put the symlink at "vendor/shared" instead
```

A symlink that leads to a directory inside `docs/` with a doc inside gets the first hint, with that directory's path.
A symlink is not a doc, and nothing reached through one is.
Neither is checked any further as a doc (the check looks at what a symlink leads to only to decide the problem and its hint).
A symlinked directory with a doc inside is one problem: nothing inside it is reported.
A symlink that leads to another file, such as an image, or to a directory with no doc inside is not a problem; a symlink inside such a directory is reported at its path below it when it leads out of the repo or to nothing.
A symlink inside `docs/meta/templates/` is not reported, since doc templates are not checked.

A symlink is never a directory that needs an `index.md`, and never a child that an `index.md` lists, whatever it leads to.

A link to a symlink, from a doc's text or from its front matter, is a broken link in these three cases, each with its own message:

| The link's target | Problem |
| -- | -- |
| a symlink that leads to a doc | `broken link: <target> is a symlink, not a doc` |
| a symlink that leads to a directory with a doc inside | `broken link: <target> is a symlinked directory of docs` |
| a `.md` file inside a symlinked directory | `broken link: <target> is inside a symlinked directory, not a doc` |

`<target>` is the target's path from the repo root, such as `docs/guides/alias.md`.
Any other link to a symlink, or to a file reached through one, is checked like every other link, and resolves when what it leads to is there: a link to a symlink that leads to another file or to a directory with no doc inside, or to a file that is not a doc inside a symlinked directory, which the site copies even when the check reports the directory ([build](#build)).
A link to a symlink that leads out of the repo or to nothing is broken like a link to a file that does not exist.

A body link to a directory, written with or without a trailing `/` (`guides/` or `guides`), is a link to that directory's `index.md`, as on the site and in [backlinks](#backlinks).
An anchor in it, such as `guides/#setup`, must be a heading of that `index.md`, and the problem when it is not names the `index.md`:

```
docs/import.md:7: no heading "#setup" in docs/guides/index.md
```

A doc's title, its first level-1 heading (`# Import`, or `Import` underlined with `===`), must come right after the front matter, and a doc has no other level-1 heading ([DS-52](docs-format.md#requirements)).
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
A count of the problems follows on stderr, and a count of the warnings, `<n> warning(s)`, when there are any.

`--optional-checks` names the optional checks to run, separated by commas without spaces.
docspecsite's own optional checks have plain names (`code`); a backend's checks are named `<backend>:<check>` (`git:staged`).
Only docspecsite's own checks and those of the backend in use are available: any other name, such as `git:staged` with `backend = "none"`, or an empty list, is a command-line error whose message lists the available checks.
The `git:staged` check (`--optional-checks git:staged`) is a problem for each doc that git has staged as deleted or renamed ([DS-6](versioning-backends.md#versions-of-a-doc)); the `docs-check` commit hook runs it.
It passes over a path that was a symlink in the last commit: a symlink never was a doc, so it may be removed or renamed ([DS-39](doc-symlinks.md#requirements)).
The `code` check (`--optional-checks code`) checks the code in the settings' `code-dirs`, from the working tree: each `Docs:` line, Sphinx role and `code:` link in a docstring is a problem on its code file when its target is not found.
A package name found in more than one code directory is a problem naming the package and its directories, and the code is then not checked.
Without `code-dirs` the code check adds nothing.

The problems in `docspecsite.toml` are given with each setting in [configuration.md](configuration.md#settings); an unknown component in `[code-components]` is reported by every `check`, with or without the `code` check.

A warning is something the check found that does not break a rule but deserves a look, such as an ignored value that can mislead a reader ([DS-53](docs-format.md#layers-without-a-build-status)).
Each warning is printed on its own line, in the form of a problem line with `warning: ` before it (`warning: docs/<path>:<line>: <message>`), without a hint; the warnings come after all the problems.
`--strict` makes the check exit with 1 when there is any warning; the warnings and both counts are printed the same way.
It is meant for CI, as `build --strict` is.

The exit code is 0 when no problem is found, also when there are warnings, and 1 when there are problems or, with `--strict`, warnings.

### Docs without a build status

> **Not built yet.**

In a doc of a [layer without a build status](../meta/lifecycle.md#layers-without-a-build-status), today a scenario doc, the check ignores what [DS-53](docs-format.md#layers-without-a-build-status) says it ignores, and reports this warning and this problem, both on the doc's first line.
A `status` field that holds `implemented`, as a single value or in a list:

```
warning: docs/scenarios/import.md:1: "implemented" in "status" is ignored: the "scenarios" layer has no build status, and the value can mislead a reader once the doc that owns the rules changes and nobody updates it
```

A `related` front-matter field that names no behavior or ui doc that is neither `deprecated` nor `redirect`:

```
docs/scenarios/import.md:1: "related" names no behavior or ui doc that is neither deprecated nor redirect
  hint: add to "related" the behavior or ui docs whose rules this doc gives cases for
```

When the `related` field names a behavior or ui doc that is `deprecated`, the hint also offers deprecating the scenario doc: `hint: add to "related" the behavior or ui docs whose rules this doc gives cases for, or write "status: deprecated" if they are all deprecated`.

## list

`--status S` matches a doc that has `S` anywhere in its `status`, so a partly built doc is found under each of its statuses ([DS-47](status-notes.md#requirements)).
Text output has one line per doc: path, status, title and summary, separated by tabs; a list of statuses is shown comma-separated without spaces, in the doc's order (`implemented,specified`).
`--format json` prints a JSON list with the path and the fields `title`, `summary`, `layer`, `status`, `components`, `tags`, `milestone` and `priority`; `status` is a string for a single status and a list of strings for a list.
Docs are sorted as listings that include ADRs are ([site.md](site.md#navigation-and-indexes)).
Docs whose front matter does not load are left out.
A `docspecsite.toml` that is not valid TOML or has an invalid value stops `list` with an error and exit code 1; an unknown setting is a warning.
A doc that cannot be read, or that is not valid UTF-8, stops `list` with an error naming the doc and exit code 1.

For a doc whose name is not valid UTF-8, see [Input that cannot be used](#input-that-cannot-be-used).

When the program that reads the output stops reading early, as in `docspecsite list | head -1`, `list` stops writing, prints no error trace, and exits with the exit code it would have had anyway.

## backlinks

`<path>` is `docs/x.md` (from the repo root), `x.md` (relative to `docs/`) or an absolute path.
It is read as written, without following symlinks; a path that leaves `docs/` through `..` is not a doc.
Each linking doc is printed on one line: its path, the kinds of its links (`body`, `related`, `redirect_to`, `superseded_by`) and its title, separated by tabs; `--format json` prints the same as a JSON list.
A link to a directory counts as a link to its `index.md`.
A doc that cannot be read, or that is not valid UTF-8, stops `backlinks` with an error naming the doc and exit code 1.
Otherwise the exit code is 2 when `<path>` is not a doc, with `not a doc: <path>` on stderr, else 0.
A doc template, a symlink and a path inside a symlinked directory are not docs ([DS-39](doc-symlinks.md#requirements)).
When the program that reads the output stops reading early, `backlinks` stops writing, prints no error trace, and exits with the exit code it would have had anyway ([list](#list)).

## build

> **Changed, not built yet.** Git is the only version control: there is no `versioning:` line, no `none` backend and no link patterns, and a code-only build links docs under `<source-url>/blob/<commit>/`.

The site is written to `--out` (default `site/`, relative to the current directory).
Files of the previous build that are no longer produced are removed; nothing else in the directory is touched.
Rendered page bodies are kept in `.docspecsite-cache/` in the checked repo, so a rebuild renders only what changed ([DS-24](site.md#building)).

The first line on stderr names the backend in use, and `(auto)` when `auto` picked it: `versioning: git (auto)`, `versioning: none (auto)`, `versioning: git`.

- `--ref` names the [revision](glossary.md) whose history gives the versions; its code gives the code reference. With git it is a branch, tag or commit, and the history is its [main line of history](glossary.md). With git, the default is the commit that is checked out now (`HEAD` in git), on whichever branch, so that the site shows what you have checked out. With both `--include-worktree` and a `--ref`, the working copy is everything in which the working tree differs from that ref. With `none`, giving `--ref` is a command-line error. The settings always come from the working tree's `docspecsite.toml` ([configuration.md](configuration.md)).
- `--include-worktree` adds uncommitted doc changes on top of the built revision as a "working copy (uncommitted)" version, and reads the code and the files under `docs/` from the working tree. A code page whose file is new or changed in the working tree has no source links (the links from each code element to its source file on the repo's web host), since the built revision does not hold the code it shows; the pages of unchanged files keep theirs. It is meant for previews while writing, never for CI (continuous integration, the automatic checks and builds on a server). With `none` it is accepted and changes nothing: the docs, the code and the files under `docs/` are always read from disk.
- `--parts` names the parts to build, separated by commas without spaces: `docs`, `code` ([DS-35](site.md#rendering)).
  Without it, every part the repo has is built: `docs`, and `code` when `code-dirs` is set.
  An unknown part, or an empty list, is a command-line error; `code` without `code-dirs` stops the build before it starts.
- `--strict` stops at the first page error without writing anything, and turns every warning into an error. It is meant for CI.
  Warnings come only from the parts being built, so `--parts docs --strict` does not fail on docstrings.

A docs-only build (`--parts docs`):

- shows `code:` links, in every version of a doc, as their text in code style, with no link and no marker;
- lists no code modules on component pages, and leaves the code reference's entry page out of `llms.txt` (which lists docs only, in every build);
- leaves out the code reference's entry page; links to it are text;
- links a file of the code part (such as an image under `reference/code/`) on the repository host, as a repo file outside `docs/` is linked.

A code-only build (`--parts code`):

- writes the code reference and its entry page, which is also the site's root page;
- has no index pages and no `llms.txt`; the breadcrumb above the code reference, component labels and status badges are text;
- links `Docs:` lines, "described in" lists and the entry page's backlinks to the doc's Markdown file on the repo host at the built revision, through the backend's [link pattern](glossary.md) ([DS-42](versioning-backends.md#requirements)), or shows the doc's path as text when there is no link pattern to use (without `source-url`, or with `none` and no pattern set) or for a doc not in the built revision (with `--include-worktree`);
- links a file of the docs part (such as an image a doc uses) on the repository host, as a repo file outside `docs/` is linked.

Code reference pages link each element to its source file at the built revision (with git, the built commit), through the `source-url` setting ([configuration.md](configuration.md#settings)); for pages built with `--include-worktree`, see that option above.
For a path in `code-dirs` that is a symlink to a directory inside the repo, the links use the path of the directory it leads to, since that is where the file is in the repo.
Without `source-url`, a link pattern that uses `{source-url}` gives no link: code reference pages have no source links and body links to repo files are plain text, and `build` warns once about the missing setting.
When `code-dirs` is set, it warns at the start of the build, and only when the `code` part is built.
When `code-dirs` is not set, it warns at the first repo link it turns into plain text in the latest version of a doc, naming that version and link; links in older versions become plain text without a warning.

Without `--strict`, an error stays local to its page: a doc version, diff, code page or index page that cannot be built is left out, and the rest of the site is still built.
Each such error is printed on stderr as `error: <page>: <message>`; warnings (such as an unresolvable link) are printed as `warning: <message>`.
A doc whose page would take the URL of a generated page (which `check` reports) is such an error for the doc's page; the generated page is kept.
A symlink that leads to a doc gets no pages, and the build says nothing about it: it is neither an error nor a warning and is not counted, since `check` reports it ([DS-39](doc-symlinks.md#on-the-site)).
A path can be a symlink in some revisions and a doc, a file with its own text, in others:

- a version in which the path is a symlink is left out;
- a path that is a symlink at the built revision is not a doc of the site, and has no pages in any version;
- a path that is a doc at the built revision keeps the versions in which it was one.

With `--include-worktree`, the working tree counts too:

- a path that is a symlink at the built revision but a doc in the working tree is a new uncommitted doc: it gets a working-copy version, its only version;
- a path that is a doc at the built revision but a symlink in the working tree has no working-copy version, and its committed versions keep their pages.

A symlink under `docs/` that leads to a file that is not a doc, such as an image, reaches the site as that file, never as the text of its link (the path the symlink stores).
A symlink that leads to a directory is followed in the same way.
The files inside the directory that are not docs reach the site at their paths below the symlink, and the symlinks inside it are followed like any other.
A `.md` file inside it is not a doc and gets no page, and the build says nothing about it.

How the build follows a symlink, and where it looks the target up, is in [doc-symlinks.md](doc-symlinks.md#how-a-symlink-is-followed).
The build leaves out a symlink that leads out of the repo or to nothing (a target that does not exist where the build looks it up, or a loop of symlinks).
`check` reports each such symlink; when the build still meets one, it gives a warning that names it:

```
warning: docs/guides/flow.png: symlink to an absolute path, outside the repo or to a missing file; left out
```

A body link (a link in a doc's text) whose target is not found is shown as its text with the marker "not found".
The marker is for body links only: a `code:` link has markers of its own, and the marker is not used for the `related` and `redirect_to` entries of the front matter or for `Docs:` lines in code.
The marker is shown in every version; the warning (an unresolvable link) is given only for the latest version of the linking doc.
A target is **found** when it is a doc of the site, or a file that the [versioning backend](glossary.md) provides for the build.
Such a file is:

- a file in the built revision;
- with `--include-worktree`, also a file under `docs/` in the working tree that is not a Markdown file (so a doc template that is not committed yet is not found: it is not a doc, and the site does not copy it);
- with `none`, a file on disk.

A symlink that leads to a doc is not found, and neither is a symlink or other file that the build leaves out, so a link to one of them shows the marker.

Code that cannot be loaded (a package that is not valid Python or UTF-8, a package name found in more than one code directory) is a warning, `cannot load code: <message>`, and the code reference is then built without modules.
Other input the build cannot use, such as a package directory whose name Python cannot import, is one warning each, and the build leaves it out ([Input that cannot be used](#input-that-cannot-be-used)).

The code read from a ref is the files exactly as they are committed: git's export settings for archives (`export-ignore`, `export-subst` in `.gitattributes`) change nothing in it.
When the `code` part is built, an unknown component in `[code-components]` is a warning, and the code pages leave that component out:

```
warning: docspecsite.toml: "code-components" of "example.api" has an unknown component: "backned"; ignored
```

A symlink in a code directory that points to an absolute path or out of the code directories is left out of the code read from the ref, with a warning naming it.
A path in `code-dirs` that is a symlink is followed within the built revision: the files of the directory it leads to are read as that code directory; one that leads to an absolute path, out of the repo or to nothing is left out with a warning naming it, as a symlinked image under `docs/` is, and one that leads to a file is left out with a warning too ([Input that cannot be used](#input-that-cannot-be-used)).

The last line counts the pages built, rendered afresh, taken from the cache and failed.

The exit code is 0 when every page was built, 1 when a page failed or the build could not start (for example a `docspecsite.toml` that is not valid TOML or has an invalid value), and 2 for an unknown ref and the other command-line errors.

## Input that cannot be used

Input that docspecsite cannot use never ends a command with an error trace.
The cases below are the ones docspecsite handles; for text that is not UTF-8, anything else is outside what it supports ([limits.md](limits.md#text-that-is-not-utf-8)).
`check` gives one problem and `build` one warning, each naming the file (with the line, when there is one) and the reason; that thing is left out, and the rest goes on:

```
<path>: <reason>
warning: <path>: <reason>; left out
```

The known cases:

- A package directory directly inside a code directory whose name Python cannot import (letters, digits and underscores, not starting with a digit, not a reserved word such as `class`), such as `src/a.b`: `directory name "a.b" is not a valid Python package name`. Only these top-level names are checked; subpackages are loaded as the code reference's reader handles them. With no valid package left, the code reference has no modules.
- A path in `code-dirs` that is a symlink pointing to a file instead of a directory: `symlink to a file, not a directory`. That path is left out.
- A link with nothing after `code:`, such as `[see](code:)`, in a doc's text or in a docstring: `empty code: target`. It is shown as its text, with no link and no marker. In a doc's text, `build` warns about it only for the doc's latest version, as for an unresolvable link.
- A file under `docs/`, a doc or any other file, whose name is not valid UTF-8: `name is not valid UTF-8, which breaks links to the rendered page`. The build gives it no page and does not copy it; `list` still lists such a doc, and `backlinks` finds no links to it, since a link is text and cannot name it. Wherever such a name is printed, each byte that is not UTF-8 shows as `\x` and two hex digits, such as `docs/guides/caf\xe9.md`. Outside `docs/`, such as in the code, a file is read under its name as it is.
- A commit subject that is not valid UTF-8: shown with `�` in place of each invalid byte sequence, with no problem or warning.
