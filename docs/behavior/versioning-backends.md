---
title: Where versions come from
summary: A project chooses where docspecsite reads the versions of its docs from (git, no version control at all, or another version control added by a separate package), and git can give a version for every commit or only for tagged releases.
layer: behavior
status: [specified, changed]
milestone: later
priority: should
components: [versioning]
tags: [requirements, versioning, configuration]
related:
  - scenarios/versioning-backends.md
  - architecture/versioning-backends.md
  - behavior/requirements.md
  - behavior/configuration.md
  - behavior/commands.md
  - meta/versioning.md
---

# Where versions come from

docspecsite reads the versions of each doc from the project's **version control**, the system that records the project's history ([glossary](glossary.md)).
The part of docspecsite that reads one kind of version control is called a **versioning backend**: docspecsite comes with one for git and one for "no version control", and other version control systems, such as Mercurial, can be added by installing a separate package.
By default docspecsite picks the backend itself, so a git project builds as it always has, and a folder without version control still gets a site, only without old versions.
With git, a project can also choose to keep only the versions that were current at its tagged releases, so a long history gives far fewer pages.

## What a project can choose

The `backend` setting in the `[versioning]` section of `docspecsite.toml` says where versions come from ([configuration.md](configuration.md#versioning)):

| `backend` | What the project gets |
| -- | -- |
| `auto` (the default) | docspecsite asks each backend it knows whether it recognizes the project's folder, and uses the one that does. If none does, the site is built without versions, as with `none`; a folder inside a git repo that is not its top level is the exception: every command stops, as [commands.md](commands.md) says. If more than one does, every command stops and asks the project to set `backend`. |
| `git` | Versions from git, as described in [Versions of a doc](#versions-of-a-doc). |
| `none` | No version control: each doc has only its current version, even when the folder is a git repository. |
| a backend's own name, such as `hg` | A backend from a separately installed package, under the name that package gives it. |
| an import path, such as `example_vcs.backend:Backend` | A backend from an installed package that does not give it a name. The import path says where the backend is inside that package, written as `<module>:<name>`; the package's own documentation gives it. |

`build` says at its start which backend it uses, and whether it was picked by `auto`, for example `versioning: git (auto)`, so a site without versions is never a surprise.

A project that needs its history, such as one whose site is built automatically on a server, sets `backend` itself.
Then a copy of the project without its history (for example a download without the `.git` folder) stops the build with an error instead of quietly producing a site without versions.
Projects created from the [docs-driven template](https://github.com/imposeren/docs-driven-template) set `backend = "git"`.

Each backend has its own section of settings, `[versioning.<backend>]`, such as `[versioning.git]`; a section for a backend that is not in use is ignored, so a project can switch back and forth without deleting it.

## Requirements

These requirements are part of the [DS-n](../meta/glossary.md#ds-n) numbering listed in [requirements.md](requirements.md):

- **DS-40** Versions come from a backend for the project's version control, chosen with the `backend` setting.
  docspecsite comes with `git` and `none`; a backend from another package is chosen by the name that package gives it, or by its import path.
  With `auto`, the default, docspecsite uses the one backend that recognizes the [checked repo](glossary.md) (the project folder docspecsite works on), builds without versions when none does, and stops every command when more than one does.
  A backend chosen by name never falls back to another: when it cannot read the checked repo (such as `git` in a folder that is not a git repository), every command stops with an error.
- **DS-41** With `none`, each doc has one version: the file as it is on disk.
  The site then has no pages for older versions, no version picker, no diffs and no old-version warnings, and the [code reference](glossary.md) and the other files under `docs/` are read from disk.
  Asking `build` for an older state of the project (`--ref`) is an error, and the rule that docs are never deleted or renamed ([DS-6](#versions-of-a-doc)) is not checked.
- **DS-42** Links from the site to files on the project's web host (such as GitHub or GitLab) follow **link patterns**: the code reference's links to the source code, links in docs to repo files outside the site, and, in a site built with only the code reference (`build --parts code`), links to a doc's Markdown file.
  A link pattern is the address of a file or folder on the host, with placeholders that docspecsite fills in, such as the file's path.
  Each backend has default patterns, and a project changes them in the backend's settings, for example for a host whose addresses differ from GitHub's.
- **DS-43** A backend can offer optional checks of its own, which `check --optional-checks <backend>:<check>` runs ([commands.md](commands.md#check)).
  The git backend offers `git:staged`, which reports a problem for each doc that is marked in git as deleted or renamed in the next commit ("staged") ([DS-6](#versions-of-a-doc)); the `docs-check` hook that runs before each commit runs it.

### Versions of a doc

> **Changed, not built yet.** Git is the only version control, and deletes and renames are rejected by `check --staged`.

- **DS-4** Versions come from the project's [version control](glossary.md), git by default: every [revision](glossary.md) on the [main line of history](glossary.md) that touches a doc is a version of it ([meta/versioning.md](../meta/versioning.md)).
  Where versions come from, and the choice of building without version control, is in this doc ([DS-40](#requirements), [DS-41](#requirements)).
- **DS-5** History is **per doc**: each doc has its own list of versions.
- **DS-6** Files under `docs/` cannot be deleted or renamed; where the version control can tell, an optional check of its [versioning backend](glossary.md) rejects such commits (with git: `git:staged`, [DS-43](#requirements)).
  Redirect docs replace them.
  A [symlink](glossary.md) under `docs/` is no such file: whatever it leads to, it never was a doc, so it may be removed or renamed, and the check passes over a path that was a symlink in the last commit ([DS-39](doc-symlinks.md#requirements)).

## Versions from tags only

By default every commit that touches a doc is a version of it, so a doc with a long history has many versions, pages and diffs.
A project that releases with git tags can set `versions = "tags"` in `[versioning.git]` to keep only the versions that were current at a tag; `tag-pattern`, which it then requires, names the tags that count, such as `v*` for tags like `v1.2.0`.

- **DS-38** With `versions = "tags"`, a doc's versions are, for each tag matching `tag-pattern` on the [main line of history](glossary.md) of the built ref, the newest commit at or before the tag that touches the doc. A matching tag on a commit off the main line, such as one inside a merged branch, does not count.
  A tag whose commit does not touch the doc keeps the version the doc had then, and tags that keep the same version give it once, under the first of those tags.
  A link in such a version leads to the linked doc as it was at that tag ([DS-11](site.md#rendering)), so a reader of a release sees every doc as it was in that release.
  The version picker shows each version's date, short id and tag name with its commit message, and the version's page address keeps its commit's short id, so addresses stay the same when a project switches between all commits and tags.

## Rules and limits

- Choosing a backend adds no command options: a backend is set up only in `docspecsite.toml`, and its checks are switched on with `check --optional-checks`.
- Only the optional checks of docspecsite itself (such as `code`) and those of the backend in use can be named; any other name, such as `git:staged` with `none`, is a command-line error that lists the available checks.
- With `none`, `build --include-worktree` is accepted and changes nothing, since the docs are read from disk anyway.
- With `none`, files under `docs/` whose names start with `.` are not copied into the site.
- A backend that needs extra software comes as an optional add-on of docspecsite, installed as `docspecsite[<backend>]`, such as `docspecsite[hg]`; `auto` skips such a backend when its add-on is not installed.
  The git backend needs only the `git` program.
- A backend from another package is installed next to docspecsite: for the commit hook, by adding the package to the hook's settings; for the Docker image, in the project's own image built on top of docspecsite's ([guides/using-docspecsite.md](../guides/using-docspecsite.md)).

## What it does not do

- It does not read `docspecsite.toml` through the version control: the settings always come from the file on disk ([configuration.md](configuration.md)).
- It does not change where the docs live: they are always in `docs/` at the top of the checked repo.
  A docs project in a subdirectory of a repo is a separate plan ([repo-subdirectory.md](repo-subdirectory.md)).

## Not decided yet

- Whether commits after the newest tag show as versions too, with `versions = "tags"`.

## See also

- [Scenarios](../scenarios/versioning-backends.md) — exact cases.
- [Architecture](../architecture/versioning-backends.md) — how backends plug in.
- [meta/versioning.md](../meta/versioning.md) — the method's rules on versions, which every backend follows.
