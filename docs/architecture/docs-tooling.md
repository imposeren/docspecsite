---
title: How docspecsite works
summary: docspecsite's design — a small Python package that checks docs, reads per-doc history from git, renders every version to static HTML with version pickers, diffs and version-aware links, generates the code reference, and ships as a Docker image and a prek hook that other repos pin by tag.
layer: architecture
status: implemented
code: [docspecsite.cli, docspecsite.config, docspecsite.check, docspecsite.schema, docspecsite.query, docspecsite.docset, docspecsite.build, docspecsite.history, docspecsite.coderef, docspecsite.pages, docspecsite.indexes, docspecsite.cache, docspecsite.links, docspecsite.urls, docspecsite.codeindex, docspecsite.errors]
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
---

# How docspecsite works

**docspecsite** is a small Python package that implements the [docs system requirements](../behavior/requirements.md).
Those requirements are numbered `DS-1`, `DS-2`, … (DS = "docs system"), and this page cites them by number, e.g. "(DS-3)" means "this satisfies requirement DS-3 in that doc".
It reads a repo's `docs/` and git history and writes a static site to `site/` (gitignored).
Its commands are `check`, `list`, `backlinks` and `build` ([behavior/commands.md](../behavior/commands.md)).
Why a custom tool rather than MkDocs/Sphinx: [DSS-0001](decisions/DSS-0001-custom-per-doc-history-renderer.md) (an [architecture decision record](../meta/glossary.md#adr)).

## Repository layout

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
- `markdown-it-py` + `mdit-py-plugins` (front matter, heading anchors, tables, task lists) — Markdown → HTML ([DS-3](../behavior/requirements.md#source)).
- `pyyaml` — front matter.
- `jinja2` — page templates (auto-escaping, loops and template inheritance without hand-written templating).
- **Mermaid** — renders `mermaid` code blocks as diagrams in the browser; its bundle is downloaded at a pinned version with a sha256 check when the image is built, kept in the image outside `/repo`, and copied by docspecsite into `site/assets/`, so the site works offline.
  The directory holding it is named by `DOCSPECSITE_VENDOR_DIR`; without it, diagrams are shown as source.
  A static asset, not a Python dependency.
- `griffe` (the library-only `griffelib` distribution) — docstrings → code reference pages ([DS-18](../behavior/requirements.md#generated-reference-layer)).
- stdlib `tomllib` for `docspecsite.toml`, `difflib` for diffs, `subprocess` + the `git` CLI for history.
  No other dependencies ([DS-23](../behavior/requirements.md#running)).
- Development only: pytest, Ruff and Pyrefly ([quality-gate.md](quality-gate.md)).

## Modules

The package has one module per concern: the config file, the checks, the query commands, git history, the site build and the code reference.
State that several functions share lives on classes instead of being passed from function to function: the project's settings (`ProjectConfig`, read by a `ProjectConfigParser`), the loaded docs with their backlinks (`DocSet`), one check run (`Checker`), front-matter validation (`FrontMatterValidator`, with a `FrontMatterCheck` per doc), the project's code (`Codebase`) and its reference pages (`CodeReference`, with a `CodePage` per module), the index pages (`IndexRenderer`), the docs' version-aware links (`Resolver`, with the `PageLinks` of one page) and the site build (`SiteBuilder`, writing to the output directory through a `SiteWriter`).
Each function then takes only what it uses itself, and the state each part works on is in one place.
The generated [code reference](../reference/code/index.md) lists every module and class with its documentation.

## Configuration

Settings come only from `docspecsite.toml` at the root of the checked repo ([DS-32](../behavior/requirements.md#settings), keys in [behavior/configuration.md](../behavior/configuration.md)).
Every command reads the working-tree file from disk, never through git: reading the settings stays a light step that needs no history, and an old ref is built with today's settings.
The settings say where the repo's code is (`code-dirs`), so docspecsite does not depend on how a project lays out or builds its code.
One matcher (`docspecsite.config.ProjectConfig.is_code_dir`) decides which directories are code directories, both for the working tree and for the files of a ref, so `check` and `build` find the same packages; `.` (the repo root) makes `build` extract the whole tree.
Unknown settings and invalid values are reported, never silently ignored.

## ADR IDs

An ADR's file name carries its ID: `architecture/decisions/<PREFIX>-NNNN-<slug>.md` ([meta/structure.md](../meta/structure.md#adr-ids)).
`check` accepts the repo's own `adr-prefix` and the prefixes in `external-adr-prefixes`, and reports any other name under `architecture/decisions/` ([DS-33](../behavior/requirements.md#checks)).
Each prefix's numbers are zero-padded, so sorting by path orders each prefix's ADRs by number; generated listings additionally put external ADRs first, in the order of `external-adr-prefixes`.
The hand-written `architecture/decisions/index.md` lists ADRs grouped by prefix, external prefixes first.

## History model

- Ordered version list: `git rev-list --first-parent <ref>` (linear, newest first).
- Versions of a doc: commits from that list that touch its path (`git log --first-parent --format=%H%x00%cI%x00%s <ref> -- <path>`) ([DS-4](../behavior/requirements.md#versioning), [DS-5](../behavior/requirements.md#versioning)).
- Content of a version: `git show <commit>:<path>`, decoded as UTF-8 with a leading byte order mark dropped, as `check` reads the working tree.
- git runs at the top level of the checked repo, and its `log` output is read with `--no-show-signature`, so a user's `log.showSignature` cannot put gpg output into it.
- Version-aware link resolution ([DS-11](../behavior/requirements.md#rendering)): in doc A at commit X, a link to B resolves to B's newest version whose position in the first-parent list is at or after X's position (i.e. not newer than X).
  If B has none, link to B's latest and add a "newer doc" marker.
- Uncommitted working-tree changes are rendered as an extra "working copy (uncommitted)" version only when `--include-worktree` is given (useful while writing; never in CI).
  A working-tree file counts as changed when git hashes it, with its line-ending conversion and clean filters applied, to a blob other than the one in the ref's tree.

## Output layout

```
site/
  index.html                       rendered docs/index.md
  <path>.html                      latest version of docs/<path>.md
  <path>/v/<short-sha>.html        each version (latest included, for permalinks)
  <path>/v/<short-sha>.diff.html   diff vs previous version (DS-10)
  reference/code/<dotted.path>.html   code reference pages (latest code only, no /v/ versions)
  tags/<tag>.html  components/<c>.html  status.html     indexes (DS-15)
  llms.txt                         machine listing (DS-16)
  assets/                          one CSS file, minimal JS for the version picker, the Mermaid bundle
```

Some doc paths are **reserved**, because their page would take the URL of a generated page: `status.md`, every doc under `tags/` and `components/`, every doc under `reference/code/` other than `index.md`, and every doc under `<path>/v/` when `<path>.md` is a doc (where that doc's version and diff pages go).
`check` reports a doc at a reserved path ([DS-20](../behavior/requirements.md#checks)); the build keeps the generated page and reports the doc's page as an error.

`site/.docspecsite-manifest` lists the files of the last build, so the next build removes only files it wrote itself.

### Parts

The site is built in parts ([DS-35](../behavior/requirements.md#rendering)): `docs` is everything above except `reference/code/`, and `code` is `reference/code/` (module pages and the entry page `reference/code/index.html`).
The build carries the set of parts it builds, and every link that crosses parts asks whether its target's part is in that set: the docs' resolver for `code:` links and the index and `llms.txt` entries of code modules, the code pages for `Docs:` lines, "described in" lists, links to docs and the page chrome (breadcrumb, components, status badge).
A link into a part that is not built becomes text, or, from the code reference to a doc, a link to the doc's Markdown file under `<source-url>/blob/<commit>/docs/`.
A code-only build also writes the entry page as `index.html`, with its links relative to the root.
Since the entry page has no old versions, a link to it from an old version of a doc leads to its latest page with the "current code" marker, like an old version's `code:` link.
A build never reuses pages of an earlier build with other parts: a page's links depend on the parts, and the manifest leaves `--out` holding only what this build wrote.

## Page anatomy

Every page: breadcrumb, title, status badge, components and tags (linked to indexes), version picker, body, related + backlinks panel; code pages also list their submodules (doc index pages list their children in their own `## Children` section) ([DS-8](../behavior/requirements.md#rendering), [DS-14](../behavior/requirements.md#navigation-and-indexes)).

**Contents:** a doc with at least `toc-min-headings` `##` sections gets a generated "Contents" list of its `##` headings, each with its `###` headings nested, inserted in the body right before the first `##` section, so after the summary paragraph when there is one ([meta/authoring.md](../meta/authoring.md#page-shape)).
It links to the same heading anchors that `docspecsite check` validates, and every version of the doc gets it.

**Old versions** ([DS-9](../behavior/requirements.md#rendering)): a full-width sticky red banner "⚠ OLD VERSION — <date>, <short-sha> — this is NOT the current spec. → Latest version"; `<title>` prefixed with `[OLD]`; tinted page background.
**Redirect docs** ([DS-12](../behavior/requirements.md#rendering)): no automatic redirect. A normal page with a prominent notice box ("Renamed / Moved / Merged / Split / Became a directory / Replaced by … / Removed"), links to the replacement doc(s), the reason, the doc's own body, and its version picker. Links from other docs to a redirect doc are shown with a small "→ moved" marker.

## Code reference

Python code is loaded once, from the built ref, with griffe: every package directly inside a `code-dirs` directory.
Only the **latest** code gets pages ([DS-18](../behavior/requirements.md#generated-reference-layer)): no version picker, no `/v/` pages; older code is read with git or an IDE.
The hand-written entry page `docs/reference/code/index.md` follows the code: it is built from its latest version only, also in a full build ([DS-7](../behavior/requirements.md#rendering)).
Each module gets one page, built from the code's structure as well as its docstrings, in the spirit of Sphinx's autodoc:

- the module docstring, then its classes, functions, constants and type aliases;
- for each class: base classes (linked), the class docstring, then **members** — methods, properties, attributes and class variables — each with full **signature, type annotations and defaults**, decorators (e.g. `@property`, `@classmethod`), and its docstring; inherited members listed separately with a link to where they are defined;
- parameters, return values and raised exceptions from docstring sections (Google style), merged with the annotations;
- every type in a signature linked to its own reference entry when it is project code;
- every member with its own anchor and a link to its source at the built commit (under `source-url`);
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
`check --code` ([DS-36](../behavior/requirements.md#checks)) loads the code from the working tree and looks up each docstring's `Docs:` lines, roles and `code:` links with the same lookup as the pages, without rendering anything; plain `check` does not look at docstrings.
`Docs:` docstring lines become links, and "described in" lists come from `code:` fields ([DS-13](../behavior/requirements.md#rendering), [DS-19](../behavior/requirements.md#generated-reference-layer)).
The HTTP API reference is not built yet ([behavior/web-api-reference.md](../behavior/web-api-reference.md)).

## Errors and warnings

Errors in `docspecsite build` stay local to the page they occur in ([behavior/commands.md](../behavior/commands.md#build)).
An expected failure (a doc version that is not valid UTF-8, a doc at a reserved path) is an error line for that page.
Code that cannot be loaded is a warning instead, since it affects no single page: the code reference is built without modules, and `code:` links get the "no longer exists" marker.
Any other exception is a bug in docspecsite: it is reported as a Python warning of category `docspecsite.InternalErrorWarning`, raised while the exception is being handled, so the warning carries the original traceback.
docspecsite's own warnings (such as unresolvable links) are Python warnings of category `docspecsite.DocspecsiteWarning`.
Both go through Python's warning filters, so `PYTHONWARNINGS` can turn them into errors. Python reads it before docspecsite can be imported, so a filter names the built-in base category and the module that issues the warning: `PYTHONWARNINGS=error::RuntimeWarning:docspecsite.build` stops the build at the first internal error, with its traceback (useful while working on docspecsite).
With `--strict`, the build sets `error` filters for both warning categories.

## Incremental builds

A cache in `.docspecsite-cache/` (gitignored; inside the checked repo, so it persists between container runs) keys rendered HTML by (blob sha, hash of the resolved link targets, docspecsite version).
Only changed versions and pages whose link targets moved are re-rendered ([DS-24](../behavior/requirements.md#running)).
A diff page's body is kept by the blob shas of its two versions, so an unchanged pair is not diffed again.
The cache has one root per docspecsite version and set of built parts, so builds of different parts in turn do not throw away each other's entries: a build prunes the entries it did not use only in its own root, and removes other roots only when they belong to another docspecsite version.

## Docker image

The `Dockerfile` at the repo root has two targets.
The default, `runtime` (the last stage), is the image other repos use for `list`, `build` and any other command ([DS-22](../behavior/requirements.md#running)):

- base: the official uv image; uv installs Python from `.python-version` ([DSS-0002](decisions/DSS-0002-single-python-toolchain.md)), plus `git` from Debian;
- docspecsite is installed from the locked dependencies as a regular (non-editable) package into `/opt/venv`, without the development group;
- the vendored Mermaid bundle is in `/opt/docspecsite-vendor`, named by `DOCSPECSITE_VENDOR_DIR`;
- the entrypoint is `docspecsite`, the working directory `/repo`, and `git config --system --add safe.directory /repo` is set, so the image works for any user ID.

A project builds it with docker compose straight from this repo's git URL at a release tag (`build: context: https://github.com/imposeren/docspecsite.git#vX.Y.Z`) and bind-mounts its own repo at `/repo`; no registry is involved.
Only `src/` and the files uv installs from are copied into the image (`.dockerignore`).

The `dev` target shares the base (Python, git, Mermaid) and installs every dependency group, with docspecsite editable from `/repo`; docspecsite's own `compose.yaml` runs its tests, lint, type check and docs from it ([dev-environment.md](dev-environment.md)).

## prek hook

`.pre-commit-hooks.yaml` defines one hook, `docs-check`: `docspecsite check --staged` with `language: python`, so prek installs docspecsite from this repo at the pinned tag into an environment of its own.
It runs on every commit (`always_run`, no file names passed), because a commit that only deletes or renames a doc stages no file that a filter could match ([DS-6](../behavior/requirements.md#versioning), [DS-21](../behavior/requirements.md#checks)).

## How other repos use docspecsite

A project pins one docspecsite release tag in two places, kept equal: the `rev` of the hook repo in `.pre-commit-config.yaml`, and the tag in the `docs` service's build context in `compose.yaml`.
Its settings are in its own `docspecsite.toml`.
Step by step: [guides/using-docspecsite.md](../guides/using-docspecsite.md).
How releases are named: [versioning.md](versioning.md).

docspecsite checks its own docs with its own source, not a release: its `.pre-commit-config.yaml` runs `uv run docspecsite check --staged` ([quality-gate.md](quality-gate.md)).

## See also

- [meta/versioning.md](../meta/versioning.md) — the rules this tool implements.
- [dev-environment.md](dev-environment.md) — working on docspecsite itself.
