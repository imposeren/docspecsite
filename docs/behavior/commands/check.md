---
title: The check command
summary: The `check` command — what it validates (DSR-20), hints under problems (DSR-51), the code check (DSR-36) and the other optional checks, warnings, `--strict` and exit codes.
layer: behavior
status: [implemented, changed]
milestone: first-release
priority: must
code: [docspecsite.cli]
components: [checks, cli, code-reference, versioning]
tags: [cli, checks]
related:
  - scenarios/commands/check.md
  - behavior/commands/index.md
  - behavior/commands/build.md
  - behavior/docs-format.md
  - behavior/doc-symlinks.md
  - behavior/status-notes.md
  - behavior/code-reference.md
  - behavior/configuration.md
  - behavior/distribution.md
  - behavior/versioning-backends.md
  - behavior/requirements.md
  - architecture/docs-tooling.md
---

# The check command

`docspecsite check` validates the docs in the working tree (the files as they are now on disk) and prints each problem it finds on its own line, with a hint on how to fix it when there is one.
Optional checks add the references in the code and the checks of the version control's backend; warnings point at what deserves a look without breaking a rule.
The exit code says whether there were problems, or, with `--strict`, warnings too.

## Requirements

> **Changed, not built yet.** The deletes-and-renames check is still `check --staged`. Every `web-api:` link is reported as a problem: there is no HTTP API reference for it to resolve to.

These requirements are part of the [DSR-n](../../meta/glossary.md#dsr-n) numbering listed in [requirements.md](../requirements.md).

- **DSR-20** A check command validates: front-matter schema, `layer` matches directory, every directory has an `index.md` that lists each direct child doc and child directory with a description in its `## Children` section ([meta/structure.md](../../meta/structure.md#every-directory-has-an-indexmd)), where a symlink is neither a directory that needs an `index.md` nor a child that an index lists ([DSR-39](../doc-symlinks.md#requirements)), all links (body, `related`, `redirect_to`, `code:`, `web-api:`) resolve, where a body link to a directory is a link to its `index.md`, and an anchor in it names a heading there ([check](#what-the-check-reports)), components are in the project's component list or the shared ones ([meta/vocabulary.md](../../meta/vocabulary.md)), no `#`, `%` or `?` in file or directory names under `docs/` ([meta/structure.md](../../meta/structure.md#naming)) and no file name under `docs/` that is not valid UTF-8 ([Input that cannot be used](index.md#input-that-cannot-be-used)), no symlink under `docs/` that leads out of the repo, to nothing, to a doc or to a directory with a doc inside, whatever the symlink's own name ([DSR-39](../doc-symlinks.md#requirements)), every doc is readable UTF-8, every doc has its title in its place ([DSR-52](../docs-format.md#requirements)), and no doc's page takes the URL of a generated page ([architecture/docs-tooling.md](../../architecture/docs-tooling.md#output-layout)).
  It also checks that a partly built doc's statuses and its status notes agree ([DSR-44](../status-notes.md#requirements) to [DSR-46](../status-notes.md#requirements)), and that a scenario doc names the docs it gives cases for ([DSR-53](../docs-format.md#layers-without-a-build-status)).
  Doc templates are not docs and are not checked ([meta/structure.md](../../meta/structure.md#outside-docs)).
  The code is not checked: specs may change before it does ([meta/linking.md](../../meta/linking.md#code-links)).
  Deletes and renames under `docs/` ([DSR-6](../versioning-backends.md#versions-of-a-doc)) are an optional check of the version control's backend ([DSR-43](../versioning-backends.md#requirements)).
- **DSR-51** A problem may carry a **hint**: a line right under the problem that says how to fix it in this case, such as which value to add and the text of the field as it then reads ([check](#what-the-check-reports)).
  The problem line always has the same form, so scripts can match it; the wording of the hint differs from case to case, and `check --no-hints` leaves hints out.
  In problems and hints, every piece of exact text (a value, a field name, a status note text, a heading, text to write, a path to create) is in double quotes; the path that says where the problem is stays unquoted.
- **DSR-36** A **code check**, run on demand once an implementation is done, validates the code's references: `Docs:` docstring lines point at existing docs (and headings, with an anchor), and Sphinx roles ([DSR-34](../code-reference.md#requirements)) and `code:` links in docstrings point at code the code reference shows.
  An empty `code:` target in a docstring is a problem as in a doc's text ([Input that cannot be used](index.md#input-that-cannot-be-used)).

How projects run the check before each commit and in CI is in [distribution.md](../distribution.md) ([DSR-21](../distribution.md#requirements)).

## What the check reports

> **Changed, not built yet.** The `git:staged` check is still the `--staged` option, which the `docs-check` hook runs, and `--optional-checks` knows only `code`. A doc at an address that only the `sphinx` renderer uses, such as `search.md`, is not reported yet.

Each problem is printed on its own line as `docs/<path>:<line>: <message>`, or as `<file>:<line>: <message>` for a problem outside `docs/` (such as a `Docs:` line in code found by the `code` check); the line number, with its colon, is left out only when the problem concerns the whole file, such as an invalid `docspecsite.toml` (`docspecsite.toml: <message>`).
A problem may carry a hint, which says how to fix this particular problem: it is printed on its own line right under the problem, indented by two spaces and starting with `hint: `.
The problem line always has the same form, so a script can match it, while the wording of the hint changes from case to case; `--no-hints` leaves the hint lines out, for scripts that read the output ([DSR-51](#requirements)).
In problems and hints, every piece of exact text is in double quotes: a value, a field name, a status note text, a heading (as written in the file: with its `#` marks, or, for a heading underlined with `===` or `---`, its first line), text to write, a path to create.
The path at the start of the line, which only says where the problem is, stays unquoted:

```
docs/import.md:12: status note "Not built yet." ("specified") in a doc with the single status "implemented"
  hint: add "specified" to "status" so it reads "status: [implemented, specified]", or remove the status note from the section "## Import"
```

A doc that cannot be read, or that is not valid UTF-8, is a problem on that doc, and the other docs are still checked.
Other input the check cannot use, such as a file name that is not valid UTF-8, is one problem each ([Input that cannot be used](index.md#input-that-cannot-be-used)).
A doc whose page would take the URL of a generated page is a problem too ([architecture/docs-tooling.md](../../architecture/docs-tooling.md#output-layout)).
The generated pages of both [renderers](../site.md#renderers) count, whatever the `renderer` setting, so a change of renderer never makes a doc's page clash with a generated one: besides the index pages, the status board and the pages of the code reference and of old versions, these are the search page (`search.md`), the general index (`genindex.md`) and the files the site needs to look and work right (any doc under `_static/`).

A file or directory under `docs/` whose name contains `#`, `%` or `?` is a problem on that path ([meta/structure.md](../../meta/structure.md#naming)):

```
docs/guides/faq?.md: name contains "#", "%" or "?", which break links to the rendered page
```

A [symlink](../glossary.md) (a file that only points to another file or directory) under `docs/` is judged by what it leads to in the end, never by its own name ([DSR-39](../doc-symlinks.md#requirements), [doc-symlinks.md](../doc-symlinks.md#how-a-symlink-is-followed)).
It is a problem when it leads out of the repo, to nothing, to a doc (a `.md` file) or to a directory with a doc inside.
The problem is reported on the symlink, names the target in the form the symlink stores it, and says where the symlink leads.
The hint depends on where that is ([doc-symlinks.md](../doc-symlinks.md#what-the-check-reports)), and a hint names its paths from the repo root.
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
Any other link to a symlink, or to a file reached through one, is checked like every other link, and resolves when what it leads to is there: a link to a symlink that leads to another file or to a directory with no doc inside, or to a file that is not a doc inside a symlinked directory, which the site copies even when the check reports the directory ([build](build.md#what-the-build-does)).
A link to a symlink that leads out of the repo or to nothing is broken like a link to a file that does not exist.

A body link to a directory, written with or without a trailing `/` (`guides/` or `guides`), is a link to that directory's `index.md`, as on the site and in [backlinks](backlinks.md).
An anchor in it, such as `guides/#setup`, must be a heading of that `index.md`, and the problem when it is not names the `index.md`:

```
docs/import.md:7: no heading "#setup" in docs/guides/index.md
```

A doc's title, its first level-1 heading (`# Import`, or `Import` underlined with `===`), must come right after the front matter, and a doc has no other level-1 heading ([DSR-52](../docs-format.md#requirements)).
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

In a [partly built doc](../status-notes.md), whose `status` is a list of statuses, the check reports each case listed in [DSR-46](../status-notes.md#requirements): a problem with the `status` field (a status listed twice, `draft`, `deprecated` or `redirect` combined with other statuses, a listed status that no status note gives) on the doc's first line, and a problem with a status note (one whose status is not in `status`, one that gives the status its section already has, a second one in a section, one right under the doc's title, any in a doc with a single status) on the status note's line.
Each of these problems names the statuses involved and carries a hint ([DSR-46](../status-notes.md#requirements)).
Then stderr gets a count of the problems, `<n> problem(s)`, when there are problems, and a count of the warnings, `<n> warning(s)`, when there are warnings; with warnings only, just the warning count is printed.

`--optional-checks` names the optional checks to run, separated by commas without spaces.
docspecsite's own optional checks have plain names (`code`); a backend's checks are named `<backend>:<check>` (`git:staged`).
Only docspecsite's own checks and those of the backend in use are available: any other name, such as `git:staged` with `backend = "none"`, or an empty list, is a command-line error whose message lists the available checks.
The `git:staged` check (`--optional-checks git:staged`) is a problem for each doc that git has staged as deleted or renamed ([DSR-6](../versioning-backends.md#versions-of-a-doc)); the `docs-check` commit hook runs it.
It passes over a path that was a symlink in the last commit: a symlink never was a doc, so it may be removed or renamed ([DSR-39](../doc-symlinks.md#requirements)).
The `code` check (`--optional-checks code`) checks the code in the settings' `code-dirs`, from the working tree: each `Docs:` line, Sphinx role and `code:` link in a docstring is a problem on its code file when its target is not found.
A package name found in more than one code directory is a problem naming the package and its directories, and the code is then not checked.
Without `code-dirs` the code check adds nothing.

The problems in `docspecsite.toml` are given with each setting in [configuration.md](../configuration.md#settings); an unknown component in `[code-components]` is reported by every `check`, with or without the `code` check.

A warning is something the check found that does not break a rule but deserves a look, such as an ignored value that can mislead a reader ([DSR-53](../docs-format.md#layers-without-a-build-status)).
Each warning is printed on its own line, in the form of a problem line with `warning: ` before it (`warning: docs/<path>:<line>: <message>`), without a hint; the warnings come after all the problems.
`--strict` makes the check exit with 1 when there is any warning; the warnings and the counts are printed the same way as without it.
It is meant for CI, as `build --strict` is.

The exit code is 0 when no problem is found, also when there are warnings, and 1 when there are problems or, with `--strict`, warnings.

### Docs without a build status

In a doc of a [layer without a build status](../../meta/lifecycle.md#layers-without-a-build-status), today a scenario doc, the check ignores what [DSR-53](../docs-format.md#layers-without-a-build-status) says it ignores, and reports this warning and this problem, both on the doc's first line.
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

## See also

- [Scenarios](../../scenarios/commands/check.md) — exact cases for file names, links to a directory, warnings and unknown components in the check.
- [docs-format.md](../docs-format.md) — the rules on a doc's title and on docs without a build status that the check enforces.
- [doc-symlinks.md](../doc-symlinks.md) — how the check judges a symlink under `docs/`.
