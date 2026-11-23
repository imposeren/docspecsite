---
title: How docspecsite works
summary: docspecsite's design — a small Python package that checks docs, reads per-doc history through a versioning backend (git by default), renders every version to static HTML with version pickers, diffs and version-aware links, generates the code reference, and ships as a Docker image and a prek hook that other repos pin by tag.
layer: architecture
status: [changed, implemented]
code: [docspecsite.cli, docspecsite.config, docspecsite.check, docspecsite.schema, docspecsite.query, docspecsite.docset, docspecsite.build, docspecsite.history, docspecsite.coderef, docspecsite.pages, docspecsite.indexes, docspecsite.cache, docspecsite.links, docspecsite.urls, docspecsite.codeindex, docspecsite.errors, docspecsite.choices, docspecsite.docs, docspecsite.problems, docspecsite.markdown]
milestone: first-release
priority: must
components: [docs-system, cli, checks, queries, site, code-reference, distribution]
tags: [docs, tooling, rendering, versioning, git, docker]
related:
  - behavior/requirements.md
  - behavior/commands.md
  - behavior/configuration.md
  - architecture/decisions/DSS-0001-custom-per-doc-history-renderer.md
  - architecture/decisions/DSS-0002-single-python-toolchain.md
  - architecture/dev-environment.md
  - architecture/quality-gate.md
  - architecture/versioning-backends.md
  - behavior/status-notes.md
  - scenarios/commands.md
  - behavior/doc-symlinks.md
---

# How docspecsite works

**docspecsite** is a small Python package that implements the [docs system requirements](../behavior/requirements.md).
Those requirements are numbered `DS-1`, `DS-2`, … (DS = "docs system"), and this page cites them by number, e.g. "(DS-3)" means "this satisfies requirement DS-3 in that doc".
It reads a repo's `docs/` and their history, through a versioning backend ([versioning-backends.md](versioning-backends.md)), and writes a static site to `site/` (gitignored).
Its commands are `check`, `list`, `backlinks` and `build` ([behavior/commands.md](../behavior/commands.md)).
Why a custom tool rather than MkDocs/Sphinx: [DSS-0001](decisions/DSS-0001-custom-per-doc-history-renderer.md) (an [architecture decision record](../meta/glossary.md#adr)).

## Repository layout

> **Built.**

| Path | Holds |
| -- | -- |
| `src/docspecsite/` | The package: one module per concern (see [Modules](#modules)), Jinja templates in `templates/`, the site's CSS and JS in `static/`. |
| `tests/` | The pytest suite ([DSS-0004](decisions/DSS-0004-pytest-for-tests.md)); fixtures build throwaway docs trees and git repos. |
| `pyproject.toml`, `uv.lock`, `.python-version` | The one uv project and its Python pin ([DSS-0002](decisions/DSS-0002-single-python-toolchain.md)); also the Ruff, Pyrefly and pytest settings. |
| `Dockerfile` | The image other repos build for listing, building and serving, and the dev image ([Docker image](#docker-image)). |
| `compose.yaml`, `docker/docs-serve/` | Services for working on docspecsite itself ([dev-environment.md](dev-environment.md)). |
| `.pre-commit-hooks.yaml` | The `docs-check` hook other repos use ([prek hook](#prek-hook)). |
| `docspecsite.toml` | The settings for docspecsite's own docs ([behavior/configuration.md](../behavior/configuration.md)). |

## Dependencies

- Python: the version pinned in `.python-version`, installed by uv ([DSS-0002](decisions/DSS-0002-single-python-toolchain.md)).
- `markdown-it-py` + `mdit-py-plugins` (front matter, heading anchors, tables) — Markdown → HTML ([DS-3](../behavior/requirements.md#source)).
- `pyyaml` — front matter.
- `jinja2` — page templates (auto-escaping, loops and template inheritance without hand-written templating).
- **Mermaid** — renders `mermaid` code blocks as diagrams in the browser; its bundle is downloaded at a pinned version with a sha256 check when the image is built, kept in the image outside `/repo`, and copied by docspecsite into `site/assets/`, so the site works offline.
  The directory holding it is named by `DOCSPECSITE_VENDOR_DIR`; without it, diagrams are shown as source.
  A static asset, not a Python dependency.
- `griffe` (the library-only `griffelib` distribution) — docstrings → code reference pages ([DS-18](../behavior/requirements.md#generated-reference-layer)).
- stdlib `tomllib` for `docspecsite.toml`, `difflib` for diffs, `importlib.metadata` entry points for finding versioning backends, `subprocess` + the `git` CLI for the git backend ([DSS-0007](decisions/DSS-0007-git-command-line.md)).
  No other dependencies ([DS-23](../behavior/requirements.md#running)).
- Development only: pytest, Ruff and Pyrefly ([quality-gate.md](quality-gate.md)).

## Modules

The package has one module per concern: the config file, the checks, the query commands, the versioning backends (with git and `none`), the history core works on, the site build and the code reference.
State that several functions share lives on classes instead of being passed from function to function: the project's settings (`ProjectConfig`, read by a `ProjectConfigParser`), the loaded docs with their backlinks (`DocSet`), one check run (`Checker`), front-matter validation (`FrontMatterValidator`, with a `FrontMatterCheck` per doc), the project's code (`Codebase`) and its reference pages (`CodeReference`, with a `CodePage` per module), the index pages (`IndexRenderer`), the docs' version-aware links (`Resolver`, with the `PageLinks` of one page) and the site build (`SiteBuilder`, writing to the output directory through a `SiteWriter`).
Each function then takes only what it uses itself, and the state each part works on is in one place.
The generated [code reference](../reference/code/index.md) lists every module and class with its documentation.

## Configuration

Settings come only from `docspecsite.toml` at the root of the checked repo ([DS-32](../behavior/requirements.md#settings), keys in [behavior/configuration.md](../behavior/configuration.md)).
Every command reads the working-tree file from disk, never through the version control: reading the settings stays a light step that needs no history, the versioning backend is chosen from it before any history is read ([versioning-backends.md](versioning-backends.md#start-of-every-command)), and an old ref is built with today's settings.
The settings say where the repo's code is (`code-dirs`), so docspecsite does not depend on how a project lays out or builds its code.
One matcher (`docspecsite.config.ProjectConfig.is_code_dir`) decides which directories are code directories, both for the working tree and for the files of a ref, so `check` and `build` find the same packages; `.` (the repo root) makes `build` extract the whole tree.
Unknown settings and invalid values are reported, never silently ignored.

## ADR IDs

> **Built.**

An ADR's file name carries its ID: `architecture/decisions/<PREFIX>-NNNN-<slug>.md` ([meta/structure.md](../meta/structure.md#adr-ids)).
`check` accepts the repo's own `adr-prefix` and the prefixes in `external-adr-prefixes`, and reports any other name under `architecture/decisions/` ([DS-33](../behavior/requirements.md#checks)).
Each prefix's numbers are zero-padded, so sorting by path orders each prefix's ADRs by number; generated listings additionally put external ADRs first, in the order of `external-adr-prefixes`.
The hand-written `architecture/decisions/index.md` lists ADRs grouped by prefix, external prefixes first.

## History model

Core works on the version history the selected backend returns ([versioning-backends.md](versioning-backends.md#contract)); with the `none` backend each doc has one version from disk and no `/v/` pages.
The git backend, with `versions = "commits"` (the default), builds it as follows; `versions = "tags"` selects from the same lists ([versioning-backends.md](versioning-backends.md#git-backend)).

- Ordered version list: `git rev-list --first-parent <ref>` (linear, newest first).
- Versions of a doc: commits from that list that touch its path (`git log --first-parent --format=%H%x00%cI%x00%s <ref> -- <path>`) ([DS-4](../behavior/requirements.md#versioning), [DS-5](../behavior/requirements.md#versioning)).
- Content of a version: `git show <commit>:<path>`, decoded as UTF-8 with a leading byte order mark dropped, as `check` reads the working tree.
- git runs at the top level of the checked repo, and its `log` output is read with `--no-show-signature`, so a user's `log.showSignature` cannot put gpg output into it.
- Version-aware link resolution ([DS-11](../behavior/requirements.md#rendering)), in core and for every backend: in doc A's version X, a link to B resolves to B's newest version whose position in the backend's linear order is at or after X's position (i.e. not newer than X); with git commits mode the position is the commit's place in the first-parent list.
  If B has none, link to B's latest and add a "newer doc" marker.
  A body link to a target that is not found is text with the "not found" marker, whatever kind of file it names (one marker, since the build cannot tell a deleted doc from a typo or a missing image); `related` and `redirect_to` entries and `Docs:` lines in code do not use this marker.
  [behavior/commands.md](../behavior/commands.md#build) defines which targets are found.
  `SiteBuilder` puts the found repo file paths together and gives them to the `Resolver` (`docspecsite.urls`): the files of the built revision's tree (`Git.read_tree`) and, with `--include-worktree`, the non-Markdown files under `docs/` that git sees in the working tree (`Git.list_worktree_files`).
  The paths of the symlinks that lead to a doc and of the symlinks left out of the site are not among them; the files that a followed symlinked directory gives are, at their paths below the symlink ([Output layout](#output-layout)).
  The marker is shown in every version; the warning is given only for the latest version of the linking doc.
- Uncommitted working-tree changes are rendered as an extra "working copy (uncommitted)" version only when `--include-worktree` is given (useful while writing; never in CI).
  A working-tree file counts as changed when git hashes it, with its line-ending conversion and clean filters applied, to a blob other than the one in the ref's tree.
  The `build` command in `docspecsite.cli` decides which revision is built when `--ref` is not given: `HEAD`, the checked-out commit, with or without `--include-worktree` ([behavior/commands.md](../behavior/commands.md#build)); `History.load` and `SiteBuilder` always get a ref.
- A symlink is never a doc, whatever it leads to ([DS-39](../behavior/doc-symlinks.md#on-the-site)), and `History.load` never returns one.
  `Git` says of each path whether it is a symlink where it is read: in the built revision's tree (`Git.read_tree`, by the tree entry's mode, `120000`), in each change of the history (`Git.list_changes`) and in the working tree (`Git.list_worktree_files`).
  From that, `History.load` leaves out a version in which the path is a symlink; a path that is a symlink at the built revision is no doc of the site, with no pages in any version; a path that is a regular file at the built revision keeps the versions in which it was one.
  With `--include-worktree`, a path that is a symlink at the built revision but a regular doc in the working tree is a new uncommitted doc: it gets a working-copy version, its only version.
  A path that is a regular doc at the built revision but a symlink in the working tree has no working-copy version, and its committed versions keep their pages.
- One "is a doc" rule in `docspecsite.docs` says what a doc is: a `.md` path under `docs/`, outside the doc templates, that is a regular file with no symlinked directory between it and `docs/`.
  Every part that decides whether a path is a doc asks that one rule, and gives it what it knows about the path (the file on disk, or an entry of a tree):
  - `History.load`, for the docs of the built revision, of each change and of the working tree (through `History.is_doc`);
  - `DocSet.load`, for the docs that `check`, `list` and `backlinks` read;
  - the check's link check (`LinkCheck`), for whether a link's target is a doc, and its index check (`Checker.check_indexes`), for the children an index lists;
  - `SiteBuilder`'s copying of the docs files and the `Resolver`'s found files, where a file under `docs/` that is not a doc or a doc template is a file to copy;
  - `docspecsite.query.resolve_doc_path`, the path lookup of `backlinks`.
- `resolve_doc_path` takes the path as written, relative to `docs/`, and follows no link: `..` is worked out on the path's text, and a path that leaves `docs/` that way is no doc.
  A `docs/` directory that is itself a symlink is outside this design.
- One rule says what a symlink under `docs/` leads to, for `check` (whether the symlink is a problem, and its hint) and for the docs files `SiteBuilder` copies; [behavior/doc-symlinks.md](../behavior/doc-symlinks.md#how-a-symlink-is-followed) defines it and shows it as a diagram.
  The rule gives one of five kinds (out of the repo, nothing, a doc, a directory, another file) from the end of the symlink's chain alone, never from the symlink's own name.
  A chain of symlinks is followed while every step stays inside the repo: a target that is absolute or outside the repo gives "out of the repo", and one that does not exist, or a path already passed on the way from `docs/`, gives "nothing", so no loop of symlinks makes the check or the build run forever ([DS-39](../behavior/doc-symlinks.md#symlink-loops)).
  The symlinks inside a directory that a symlink leads to are followed by the same rule, with the paths already passed carried along; from them and the `.md` files there, the rule also says whether the directory has a doc inside.
  The target is looked up where the part reads its other files: on disk for `check`, and for `SiteBuilder` where it copies the docs files from ([Output layout](#output-layout)).
- `check` reports each symlink that leads out of the repo, to nothing, to a doc or to a directory with a doc inside once, with its target read from the link, and skips the symlinks inside `docs/meta/templates/`, as it skips templates in every check.
  It never reads outside the repo, and takes its kinds and the hint from the rule for following a symlink (the bullet above).
  A reported directory is one problem; inside a directory that is not reported, a symlink that leads out of the repo or to nothing is reported at its path below the directory's symlink.
  The index check takes no symlink as a directory that needs an `index.md` or as a child to list, and the link check gives a link to a symlink that leads to a doc, to a reported directory or to a `.md` file inside a symlinked directory its own message ([behavior/commands.md](../behavior/commands.md#check)).
  The staged check (`Checker.find_staged_deletes_renames`) passes over a path that is a symlink in the tree of `HEAD`.
- The rules on symlinks, found targets, the default revision and changed code files ([Code reference](#code-reference)) are stated here for the parts that hold them today.
  The backend contract keeps the same rules in its rows, for the git parts of `History.load` and `Git` as the git backend ([versioning-backends.md](versioning-backends.md#contract)).

## Statuses and status notes

> **Built.**

A doc's `status` is one value or, for a partly built doc, a list ([behavior/status-notes.md](../behavior/status-notes.md), DS-44 to DS-49).
The status is parsed once into one type that every reader uses; the section notes are read from the Markdown parser's block structure; and two checks compare them with the rules: the status note check, and the title check that keeps each doc's title in its place (DS-52).

```mermaid
flowchart TD
  H["A heading at the top level of the doc<br/>(not inside a block quote or list)"] --> T{"The doc's first level-1 heading<br/>(# or underlined with ===)?"}
  T -- yes --> Title["The title: no section.<br/>It and the brief under it carry no status note;<br/>the doc's whole status describes them"]
  T -- no --> N{"A status note right after it?"}
  N -- no --> First["A section with the first value of status"]
  N -- yes --> Own["A section with the status note's status"]
```

- **Vocabulary.** `docspecsite.schema` holds the statuses (`STATUSES`, also the status board's order), the values a list may hold (`LIST_STATUSES`) and the default status note texts by status (`STATUS_NOTES`); `schema.is_valid_status` is the one rule for a valid `status`.
  The project's `status-notes` setting, held by `ProjectConfig.status_notes`, replaces default texts.
- **Parsed status.** `docspecsite.docs.DocStatus` is the parsed field, built once per doc (`Doc.status`), and every reader of the status goes through it instead of reading the front matter: the `list` filter and output, `llms.txt`, index entries, the status board and the page badges (parse, don't validate).
  A single value and a one-value list give the same `DocStatus`; its values stay in the doc's order with duplicates kept, so the check can report them.
  It formats itself for listings, for JSON and for hints.
  A `status` of the wrong shape gives no values, so the doc is left off the status board like one with an unknown status.
- **Front-matter check.** `FrontMatterCheck.check_status` reports an invalid `status` (DS-44), and a single-only value in a list and a value listed twice, with hints (DS-46).
- **Title and sections.** `docspecsite.markdown.MarkdownText` is the one place that decides which heading is the doc's title: the first level-1 heading at the top level, in either style.
  The title check and the section notes both take the title from it, so they never disagree.
  Every other top-level heading opens a section, and sections form no tree: a section's status is its own status note's, else the first value, and nothing is compared between a heading and the headings above or below it.
- **Section notes.** `MarkdownText.get_section_notes` returns each note line with a bold label from the block quotes right after a heading, as a `SectionNote`: its label, its heading as written in the file (`#` marks included, so problems quote it as it is), whether that heading is the title, and its line.
  It reads the tokens of markdown-it, which docspecsite already uses for links and headings, so code blocks and notes after other content are left out without rules of their own (DS-45).
  It does not filter labels.
- **Note kinds.** `docspecsite.check` keeps a registry of note kinds, `StatusNoteCheck.note_kinds_by_label`, from label to kind; `StatusNote` (a label and its status) is the only kind, and a later kind (such as a warning) is a new entry.
  A label that is not in the registry stays ordinary text (DS-45), and nothing relies on the order of the notes in a block.
- **Status note check.** `StatusNoteCheck`, a `DocCheck`, compares a doc's `DocStatus` with its status notes (DS-46).
  One mistake gives one problem: it skips a doc whose `status` the front-matter check rejects, a status note under the title gives only the title problem, and a second status note in a section gives only its own problem while its status still counts as given.
  Its hints are built from the `DocStatus` with a value added or removed, and offer adding a value only when the result is a valid `status`.
- **Title check.** `TitleCheck`, a `DocCheck` in `docspecsite.check`, reports a doc whose text does not start with its title and each level-1 heading after the title (DS-52); it skips a doc whose front matter is missing or does not load.
  It compares lines, not blocks, since markdown-it leaves link reference definitions out of its blocks: any line that is not blank before the title's line is text before the title.
  Its hints quote the heading as written and, for a doc without a title, offer the front matter's `title`.
- **Rendering** does not touch status notes: they are ordinary block quotes in the body.
  A page shows one status badge per value, index entries one per value, and the status board places an entry under each of its values (DS-48, DS-49).

## Output layout

```
site/
  index.html                       rendered docs/index.md
  <path>.html                      latest version of docs/<path>.md
  <path>/v/<short-id>.html         each version (latest included, for permalinks); not for a versionless backend
  <path>/v/<short-id>.diff.html    diff vs previous version (DS-10)
  reference/code/<dotted.path>.html   code reference pages (latest code only, no /v/ versions)
  tags/<tag>.html  components/<c>.html  status.html     indexes (DS-15)
  llms.txt                         machine listing (DS-16)
  assets/                          one CSS file, minimal JS for the version picker, the Mermaid bundle
```

Some doc paths are **reserved**, because their page would take the URL of a generated page: `status.md`, every doc under `tags/` and `components/`, every doc under `reference/code/` other than `index.md`, and every doc under `<path>/v/` when `<path>.md` is a doc (where that doc's version and diff pages go).
`check` reports a doc at a reserved path ([DS-20](../behavior/requirements.md#checks)); the build keeps the generated page and reports the doc's page as an error.

`SiteBuilder` copies the non-Markdown files under `docs/` (images and the like; doc templates are left out) into the site at their own path: from the tree of the built revision, or with `--include-worktree` from the working tree, where only the files git sees count (`Git.list_worktree_files`).
A symlink there counts by what it leads to, whatever its name, which the builder finds by the rule for following a symlink ([History model](#history-model)).
One that leads to another file arrives as that file, never as its link text, and one that leads to a directory as the non-Markdown files inside it, at their paths below the symlink, with the symlinks inside followed by the same rule ([DS-39](../behavior/doc-symlinks.md#other-files-under-docs)).
A symlink that leads to a doc is left out without a word, since `check` reports it; one that leads out of the repo or to nothing is left out with a warning ([behavior/commands.md](../behavior/commands.md#build)).
The paths copied this way are the docs files the `Resolver` takes as found ([History model](#history-model)).

`site/.docspecsite-manifest` lists the files of the last build, so the next build removes only files it wrote itself.

### Parts

The site is built in parts ([DS-35](../behavior/requirements.md#rendering)): `docs` is everything above except `reference/code/`, and `code` is `reference/code/` (module pages and the entry page `reference/code/index.html`).
The build carries the set of parts it builds, and every link that crosses parts asks whether its target's part is in that set: the docs' resolver for `code:` links and the index entries of code modules (`llms.txt` lists docs only, [DS-16](../behavior/requirements.md#navigation-and-indexes)), the code pages for `Docs:` lines, "described in" lists, links to docs and the page chrome (breadcrumb, components, status badge).
A link into a part that is not built becomes text, or, from the code reference to a doc, a link to the doc's Markdown file through the backend's `file-link` pattern (with git by default `<source-url>/blob/<commit>/docs/…`).
A code-only build also writes the entry page as `index.html`, with its links relative to the root.
Since the entry page has no old versions, a link to it from an old version of a doc leads to its latest page with the "current code" marker, like an old version's `code:` link.
A build never reuses pages of an earlier build with other parts: a page's links depend on the parts, and the manifest leaves `--out` holding only what this build wrote.

## Page anatomy

> **Built.**

Every page: breadcrumb, title, status badges (one per status, [statuses](#statuses-and-status-notes)), components and tags (linked to indexes), version picker, body, related + backlinks panel; code pages also list their submodules (doc index pages list their children in their own `## Children` section) ([DS-8](../behavior/requirements.md#rendering), [DS-14](../behavior/requirements.md#navigation-and-indexes)).

**Contents:** a doc with at least `toc-min-headings` `##` sections gets a generated "Contents" list of its `##` headings, each with its `###` headings nested, inserted in the body right before the first `##` section, so after the summary paragraph when there is one ([meta/authoring.md](../meta/authoring.md#page-shape)).
It links to the same heading anchors that `docspecsite check` validates, and every version of the doc gets it.

**Old versions** ([DS-9](../behavior/requirements.md#rendering)): a full-width sticky red banner "⚠ OLD VERSION — <date>, <short-id> — this is NOT the current spec. → Latest version"; `<title>` prefixed with `[OLD]`; tinted page background.
**Redirect docs** ([DS-12](../behavior/requirements.md#rendering)): no automatic redirect. A normal page with a prominent notice box ("Renamed / Moved / Merged / Split / Became a directory / Replaced by … / Removed"), links to the replacement doc(s), the reason, the doc's own body, and its version picker. Links from other docs to a redirect doc are shown with a small "→ moved" marker.

## Code reference

Python code is loaded once, from the code directories the backend gives for the built revision, with griffe: every package directly inside a `code-dirs` directory.
Only the **latest** code gets pages ([DS-18](../behavior/requirements.md#generated-reference-layer)): no version picker, no `/v/` pages; older code is read with git or an IDE.
The hand-written entry page `docs/reference/code/index.md` follows the code: it is built from its latest version only, also in a full build ([DS-7](../behavior/requirements.md#rendering)).
Each module gets one page, built from the code's structure as well as its docstrings, in the spirit of Sphinx's autodoc:

- the module docstring, then its classes, functions, constants and type aliases;
- for each class: base classes (linked), the class docstring, then **members** — methods, properties, attributes and class variables — each with full **signature, type annotations and defaults**, decorators (e.g. `@property`, `@classmethod`), and its docstring; inherited members listed separately with a link to where they are defined;
- parameters, return values and raised exceptions from docstring sections (Google style), merged with the annotations;
- every type in a signature linked to its own reference entry when it is project code;
- every member with its own anchor and a link to its source at the built revision (through the backend's `file-link` pattern); with `--include-worktree`, the pages of a file that is new or changed in the working tree have no source links, since that revision does not hold the code they show: `SiteBuilder` finds those files as `History.load` finds changed docs (git's hash of the working-tree file against the blob in the built revision's tree) and passes them to `CodeReference`;
- member sections collapsible and a per-page member index, so large classes stay navigable.

Each page gets synthesized front matter (`layer: reference`, `components` from `code-components`) and goes through the same pipeline as other docs.
`code:<dotted.path>` links resolve to the module page plus an anchor.
Inside **old versions** of hand-written docs, `code:` links also lead to the latest code reference, marked "current code — may differ from this version"; a code element that no longer exists is shown as plain text with a "no longer exists" marker.
Sphinx-style roles in docstrings (`` :meth:`.attempt` ``) become links too ([DS-34](../behavior/requirements.md#rendering)).
As in Sphinx, where docutils recognizes a role while parsing and the reference is resolved later, a role is recognized by the Markdown parser, not found afterwards in its output: an inline rule of markdown-it, in the code reference's renderer only, placed before the code-span rule (as `mdit_py_plugins.myst_role` does for MyST's `` {role}`…` ``), turns `` :role:`content` `` and `` :py:role:`content` `` into a link around a code span.
The link's target keeps the role's target with its `~` and `Text <target>` form, and the code page resolves it with the docstring's object as context, passed with each render: a full dotted path is looked up in the codebase's index as is, a leading `.` first under the docstring's class and then among the definitions of its module, not its imports, and a target without a leading `.` that is not found as is is looked up the leading-`.` way too.
`<class>.__init__` falls back to the class when the class's `__init__` is not on the page.
The link text is set once the target is resolved: the found element's full dotted path, its last part with `~`, or the given text.
From there a role goes through the same link rewriting and markers as a `code:` link; code blocks are never touched, and a role name outside the Python ones is left as text.
`check --optional-checks code` ([DS-36](../behavior/requirements.md#checks)) loads the code from the working tree and looks up each docstring's `Docs:` lines, roles and `code:` links with the same lookup as the pages, without rendering anything; plain `check` does not look at docstrings.
`Docs:` docstring lines become links, and "described in" lists come from `code:` fields ([DS-13](../behavior/requirements.md#rendering), [DS-19](../behavior/requirements.md#generated-reference-layer)).
The HTTP API reference is not built yet ([behavior/web-api-reference.md](../behavior/web-api-reference.md)).

## Problems and hints

> **Built.**

`docspecsite.problems.Problem` holds a problem's location, its message and an optional hint ([DS-51](../behavior/requirements.md#checks)).
It prints as the problem line, then, when it has a hint, the hint line (`  hint: <hint>`); `check --no-hints` prints the problem line only.
The message keeps one form per kind of problem, so the problem line is stable for scripts; how to fix the case goes into the hint.

## Errors and warnings

> **Built.**

Errors in `docspecsite build` stay local to the page they occur in ([behavior/commands.md](../behavior/commands.md#build)).
An expected failure (a doc version that is not valid UTF-8, a doc at a reserved path) is an error line for that page.
Code that cannot be loaded is a warning instead, since it affects no single page: the code reference is built without modules, and `code:` links get the "no longer exists" marker.
Any other exception is a bug in docspecsite: it is reported as a Python warning of category `docspecsite.InternalErrorWarning`, raised while the exception is being handled, so the warning carries the original traceback.
docspecsite's own warnings (such as unresolvable links) are Python warnings of category `docspecsite.DocspecsiteWarning`.
Both go through Python's warning filters, so `PYTHONWARNINGS` can turn them into errors. Python reads it before docspecsite can be imported, so a filter names the built-in base category and the module that issues the warning: `PYTHONWARNINGS=error::RuntimeWarning:docspecsite.build` stops the build at the first internal error, with its traceback (useful while working on docspecsite).
With `--strict`, the build sets `error` filters for both warning categories.

## Incremental builds

A cache in `.docspecsite-cache/` (gitignored; inside the checked repo, so it persists between container runs) keys rendered HTML by (the version's content key from the backend — git's blob sha —, hash of the resolved link targets, docspecsite version).
Only changed versions and pages whose link targets moved are re-rendered ([DS-24](../behavior/requirements.md#running)).
A diff page's body is kept by the content keys of its two versions, so an unchanged pair is not diffed again.
The cache has one root per docspecsite version, set of built parts and versioning backend, so builds of different parts in turn do not throw away each other's entries: a build prunes the entries it did not use only in its own root, and removes other roots only when they belong to another docspecsite version.

## Docker image

The `Dockerfile` at the repo root has two targets.
The default, `runtime` (the last stage), is the image other repos use for `list`, `build` and any other command ([DS-22](../behavior/requirements.md#running)):

- base: the official uv image; uv installs Python from `.python-version` ([DSS-0002](decisions/DSS-0002-single-python-toolchain.md)), plus `git` from Debian;
- docspecsite is installed from the locked dependencies as a regular (non-editable) package into `/opt/venv`, without the development group;
- the vendored Mermaid bundle is in `/opt/docspecsite-vendor`, named by `DOCSPECSITE_VENDOR_DIR`;
- the entrypoint is `docspecsite`, the working directory `/repo`, and `git config --system --add safe.directory /repo` is set, so the image works for any user ID.

The image holds the built-in backends; a project that uses a third-party backend builds its own image `FROM` this one with the backend's package added ([versioning-backends.md](versioning-backends.md#operational-notes)).
A project builds it with docker compose straight from this repo's git URL at a release tag (`build: context: https://github.com/imposeren/docspecsite.git#vX.Y.Z`) and bind-mounts its own repo at `/repo`; no registry is involved.
Only `src/` and the files uv installs from are copied into the image (`.dockerignore`).

The `dev` target shares the base (Python, git, Mermaid) and installs every dependency group, with docspecsite editable from `/repo`; docspecsite's own `compose.yaml` runs its tests, lint, type check and docs from it ([dev-environment.md](dev-environment.md)).

## prek hook

`.pre-commit-hooks.yaml` defines one hook, `docs-check`: `docspecsite check --optional-checks git:staged` with `language: python`, so prek installs docspecsite from this repo at the pinned tag into an environment of its own.
A third-party backend is added to the hook's environment through `additional_dependencies`.
It runs on every commit (`always_run`, no file names passed), because a commit that only deletes or renames a doc stages no file that a filter could match ([DS-6](../behavior/requirements.md#versioning), [DS-21](../behavior/requirements.md#checks)).

## How other repos use docspecsite

A project pins one docspecsite release tag in two places, kept equal: the `rev` of the hook repo in `.pre-commit-config.yaml`, and the tag in the `docs` service's build context in `compose.yaml`.
Its settings are in its own `docspecsite.toml`.
Step by step: [guides/using-docspecsite.md](../guides/using-docspecsite.md).
How releases are named: [versioning.md](versioning.md).

docspecsite checks its own docs with its own source, not a release: its `.pre-commit-config.yaml` runs `uv run docspecsite check --optional-checks git:staged` ([quality-gate.md](quality-gate.md)).

## See also

> **Built.**

- [meta/versioning.md](../meta/versioning.md) — the rules this tool implements.
- [dev-environment.md](dev-environment.md) — working on docspecsite itself.
