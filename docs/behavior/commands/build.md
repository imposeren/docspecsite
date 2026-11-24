---
title: The build command
summary: The `build` command — its options, the renderer it draws the site with, docs-only and code-only builds, source links, symlinks, links whose target is not found, code that cannot be loaded, its warnings, errors and exit codes.
layer: behavior
status: changed
milestone: first-release
priority: must
code: [docspecsite.cli]
components: [site, cli, code-reference, versioning]
tags: [cli, rendering]
related:
  - scenarios/commands/build.md
  - behavior/commands/index.md
  - behavior/commands/check.md
  - behavior/site.md
  - behavior/code-reference.md
  - behavior/doc-symlinks.md
  - behavior/configuration.md
  - behavior/versioning-backends.md
  - behavior/requirements.md
  - architecture/docs-tooling.md
  - architecture/site.md
---

# The build command

`docspecsite build` renders the static site; with version control, from the history of a [ref](../glossary.md), by default the commit that is checked out.
Its options choose the revision, the output directory, the parts of the site, the [renderer](../site.md#renderers) that draws it and a preview of the working tree, and `--strict` makes it fail on any error or warning, for CI.
Without `--strict`, an error that concerns one page leaves that page out and the rest of the site is still built; with it, the build stops at the first page error and writes nothing.

## What the build does

The site is written to `--out` (default `site/`, relative to the current directory).
Files of the previous build that are no longer produced are removed; nothing else in the directory is touched.
Every build draws the whole site afresh ([DSR-24](../site.md#building)); the files it needs while drawing are kept in `.docspecsite-cache/` in the checked repo, and emptied at the start of the next build.
With the `internal` renderer, the drawn pages are kept there too, so a rebuild draws only what changed.
Two builds of the same repo must not run at the same time.

The first line on stderr names the backend in use, and `(auto)` when `auto` picked it: `versioning: git (auto)`, `versioning: none (auto)`, `versioning: git`.

- `--ref` names the [revision](../glossary.md) whose history gives the versions; its code gives the code reference. With git it is a branch, tag or commit, and the history is its [main line of history](../glossary.md). With git, the default is the commit that is checked out now (`HEAD` in git), on whichever branch, so that the site shows what you have checked out. With both `--include-worktree` and a `--ref`, the working copy is everything in which the working tree differs from that ref. With `none`, giving `--ref` is a command-line error. The settings always come from the working tree's `docspecsite.toml` ([configuration.md](../configuration.md)).
- `--include-worktree` adds uncommitted doc changes on top of the built revision as a "working copy (uncommitted)" version, and reads the code and the files under `docs/` from the working tree. A code page whose file is new or changed in the working tree has no source links (the links from each code element to its source file on the repo's web host), since the built revision does not hold the code it shows; the pages of unchanged files keep theirs. It is meant for previews while writing, never for CI (continuous integration, the automatic checks and builds on a server). With `none` it is accepted and changes nothing: the docs, the code and the files under `docs/` are always read from disk.
- `--parts` names the parts to build, separated by commas without spaces: `docs`, `code` ([DSR-35](../site.md#rendering)).
  Without it, every part the repo has is built: `docs`, and `code` when `code-dirs` is set.
  An unknown part, or an empty list, is a command-line error; `code` without `code-dirs` stops the build before it starts.
- `--renderer` names the [renderer](../site.md#renderers) that draws the site: `sphinx` or `internal`.
  It wins over the `renderer` setting ([configuration.md](../configuration.md#site)), which applies when the option is not given; without either, the renderer is `sphinx`.
  An unknown name is a command-line error.
  Building the same revision once with each renderer, into two output directories, gives both sites of the same docs side by side.
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
- links `Docs:` lines, "described in" lists and the entry page's backlinks to the doc's Markdown file on the repo host at the built revision, through the backend's [link pattern](../glossary.md) ([DSR-42](../versioning-backends.md#requirements)), or shows the doc's path as text when there is no link pattern to use (without `source-url`, or with `none` and no pattern set) or for a doc not in the built revision (with `--include-worktree`);
- links a file of the docs part (such as an image a doc uses) on the repository host, as a repo file outside `docs/` is linked.

Code reference pages link each element to its source file at the built revision (with git, the built commit), through the `source-url` setting ([configuration.md](../configuration.md#settings)); for pages built with `--include-worktree`, see that option above.
For a path in `code-dirs` that is a symlink to a directory inside the repo, the links use the path of the directory it leads to, since that is where the file is in the repo.
Without `source-url`, a link pattern that uses `{source-url}` gives no link: code reference pages have no source links and body links to repo files are plain text, and `build` warns once about the missing setting.
When `code-dirs` is set, it warns at the start of the build, and only when the `code` part is built.
When `code-dirs` is not set, it warns at the first repo link it turns into plain text in the latest version of a doc, naming that version and link; links in older versions become plain text without a warning.

Without `--strict`, an error stays local to its page: a doc version, diff, code page or index page that cannot be built is left out, and the rest of the site is still built.
Each such error is printed on stderr as `error: <page>: <message>`; warnings (such as an unresolvable link) are printed as `warning: <message>`.
With the `sphinx` renderer, the warnings of the documentation tool it is built on, such as a link to a heading that does not exist, are build warnings in the same form, so `--strict` turns them into errors too.
A failure inside that tool that concerns no single page stops the whole build: one error line, exit code 1, and the output directory is left as it was.
A doc whose page would take the URL of a generated page (which `check` reports) is such an error for the doc's page; the generated page is kept.
A symlink that leads to a doc gets no pages, and the build says nothing about it: it is neither an error nor a warning and is not counted, since `check` reports it ([DSR-39](../doc-symlinks.md#on-the-site)).
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

How the build follows a symlink, and where it looks the target up, is in [doc-symlinks.md](../doc-symlinks.md#how-a-symlink-is-followed).
The build leaves out a symlink that leads out of the repo or to nothing (a target that does not exist where the build looks it up, or a loop of symlinks).
`check` reports each such symlink; when the build still meets one, it gives a warning that names it:

```
warning: docs/guides/flow.png: symlink to an absolute path, outside the repo or to a missing file; left out
```

A body link (a link in a doc's text) whose target is not found is shown as its text with the marker "not found".
The marker is for body links only: a `code:` link has markers of its own, and the marker is not used for the `related` and `redirect_to` entries of the front matter or for `Docs:` lines in code.
The marker is shown in every version; the warning (an unresolvable link) is given only for the latest version of the linking doc.
A target is **found** when it is a doc of the site, or a file that the [versioning backend](../glossary.md) provides for the build.
Such a file is:

- a file in the built revision;
- with `--include-worktree`, also a file under `docs/` in the working tree that is not a Markdown file (so a doc template that is not committed yet is not found: it is not a doc, and the site does not copy it);
- with `none`, a file on disk.

A symlink that leads to a doc is not found, and neither is a symlink or other file that the build leaves out, so a link to one of them shows the marker.

Code that cannot be loaded (a package that is not valid Python or UTF-8, a package name found in more than one code directory) is a warning, `cannot load code: <message>`, and the code reference is then built without modules.
Other input the build cannot use, such as a package directory whose name Python cannot import, is one warning each, and the build leaves it out ([Input that cannot be used](index.md#input-that-cannot-be-used)).

The code read from a ref is the files exactly as they are committed: git's export settings for archives (`export-ignore`, `export-subst` in `.gitattributes`) change nothing in it.
When the `code` part is built, an unknown component in `[code-components]` is a warning, and the code pages leave that component out:

```
warning: docspecsite.toml: "code-components" of "example.api" has an unknown component: "backned"; ignored
```

A symlink in a code directory that points to an absolute path or out of the code directories is left out of the code read from the ref, with a warning naming it.
A path in `code-dirs` that is a symlink is followed within the built revision: the files of the directory it leads to are read as that code directory; one that leads to an absolute path, out of the repo or to nothing is left out with a warning naming it, as a symlinked image under `docs/` is, and one that leads to a file is left out with a warning too ([Input that cannot be used](index.md#input-that-cannot-be-used)).

The last line counts the pages built, rendered afresh, taken from the cache and failed; with the `sphinx` renderer every page is rendered afresh, and the count taken from the cache is always 0.

The exit code is 0 when every page was built, 1 when a page failed or the build could not start (for example a `docspecsite.toml` that is not valid TOML or has an invalid value), and 2 for an unknown ref and the other command-line errors.

## See also

- [Scenarios](../../scenarios/commands/build.md) — exact cases for the revision a build shows, source links, links whose target is not found and unknown components.
- [site.md](../site.md) — what the site shows, and [code-reference.md](../code-reference.md) — the code reference it renders.
- [architecture/docs-tooling.md](../../architecture/docs-tooling.md#history-model) — how the history, the working copy and link markers are built.
