---
title: Docs system requirements
summary: The numbered requirements (DS-n) docspecsite satisfies — source format, per-doc versioning, rendering, navigation and indexes, the generated code reference, checks, settings and how it runs.
layer: behavior
status: specified
milestone: first-release
priority: must
components: [docs-system]
tags: [requirements, versioning, rendering, checks]
related:
  - scenarios/requirements.md
  - meta/versioning.md
  - architecture/docs-tooling.md
  - behavior/commands.md
  - behavior/status-notes.md
---

# Docs system requirements

This is the **contract** docspecsite fulfils for the docs of a repo that follows the docs-driven method.
It says *what* the tool does; how it does it is in [architecture/docs-tooling.md](../architecture/docs-tooling.md).

Each requirement has an id (`DS-n`, see [DS-n](../meta/glossary.md#ds-n)) so that architecture docs and ADRs ([architecture decision records](../meta/glossary.md#adr)) can refer to it.
Ids are never renumbered or reused: a new requirement gets the next free number, even if it belongs in an earlier section.

## Source

- **DS-1** Docs are Markdown files with YAML front matter ([meta/front-matter.md](../meta/front-matter.md)), in `docs/`.
- **DS-2** Raw Markdown stays fully readable and navigable without the tooling (GitHub, editors, agents).
- **DS-3** Markdown is converted by an established Markdown library, not a hand-written parser.

## Versioning

- **DS-4** Versions come from the project's [version control](glossary.md), git by default: every [revision](glossary.md) on the [main line of history](glossary.md) that touches a doc is a version of it ([meta/versioning.md](../meta/versioning.md)).
  Where versions come from, and the choice of building without version control, is in [versioning-backends.md](versioning-backends.md) ([DS-40](versioning-backends.md#requirements), [DS-41](versioning-backends.md#requirements)).
- **DS-5** History is **per doc**: each doc has its own list of versions.
- **DS-6** Files under `docs/` cannot be deleted or renamed; where the version control can tell, an optional check of its [versioning backend](glossary.md) rejects such commits (with git: `git:staged`, [DS-43](versioning-backends.md#requirements)).
  Redirect docs replace them.

## Rendering

- **DS-7** Every version of every doc is viewable as a page.
  The code reference's entry page (`docs/reference/code/index.md`) is the exception: like the rest of the code reference ([DS-18](#generated-reference-layer)), only its latest version is shown.
- **DS-8** Each page shows a **version picker** listing all versions (date, short revision id, message: with git, the commit subject). A leading `spec:` or `docs:` prefix is removed from the message, since it carries no information there.
- **DS-9** Each non-latest version shows a **loud, persistent "OLD VERSION — not the current spec" warning** with a link to the latest version, and a marker in the page title.
- **DS-10** Each version can show a **diff** against its previous version.
- **DS-11** Links inside an old version resolve to the version of the target current at that revision; if the target did not exist yet, to its latest version, marked as newer ([meta/versioning.md](../meta/versioning.md#links-in-old-versions)).
- **DS-12** Redirect docs **never redirect automatically**. They render as normal pages with a prominent notice: what happened (`redirect_kind`), a link to the replacement doc(s) (`redirect_to`, when there is one), and the `reason`. Their version history stays available like any other doc's.
- **DS-13** `code:` links and `Docs:` docstring lines resolve as described in [meta/linking.md](../meta/linking.md#code-links).
  `web-api:` links are part of the HTTP API reference ([web-api-reference.md](web-api-reference.md)).
- **DS-34** Docstrings refer to code with Sphinx's Python roles: `` :mod:`…` ``, `` :class:`…` ``, `` :func:`…` ``, `` :meth:`…` ``, `` :attr:`…` ``, `` :data:`…` ``, `` :exc:`…` `` and `` :obj:`…` ``, also with the `py:` domain (`` :py:meth:`…` ``).
  A target is a full dotted path (`` :class:`docspecsite.build.SiteBuilder` ``), or starts with `.` and is looked up from the docstring's place: first among the members of its class (the class itself for the class docstring, the enclosing class for a member's docstring), then among the definitions of its module (`` :meth:`.attempt` `` in any docstring of `SiteBuilder`).
  A target without a leading `.` that is no full dotted path of an element is looked up the same way, as Sphinx does: `` :meth:`attempt` `` works like `` :meth:`.attempt` ``.
  A name the module only imports is not found that way: a reference to code defined elsewhere uses that code's own dotted path.
  A target is found only when the code reference shows it, as for `code:` links: a private member is not.
  A target `<class>.__init__` stands for how the class is constructed: it leads to the `__init__` entry when the code reference shows one, else to the class.
  A role reads as the full dotted path of the element it leads to (`` :meth:`.attempt` `` in `SiteBuilder` reads `docspecsite.build.SiteBuilder.attempt`).
  `~` before the target shows only the last part of that path (`` :class:`~docspecsite.build.SiteBuilder` `` and `` :meth:`~.attempt` `` read `SiteBuilder` and `attempt`), and `Text <target>` sets the text.
  Each role renders as a link to the element on the code reference; the role names the kind of element for readers, and docspecsite does not check that it matches.
  Other roles are shown as written.
  A target that is not found is shown as written (without `~`) with the "no longer exists" marker and is a build warning; plain `check` does not look at it, the code check does ([DS-36](#checks)).
- **DS-35** The site is built in **parts**, and a build renders the parts it is asked for: `docs` (the hand-written docs, their versions and diffs, the index pages and `llms.txt`) and `code` (the code reference with its entry page); by default every part the repo has ([commands.md](commands.md#build)).
  Links into a part that is not built never dangle: a `code:` link in a docs-only site is its text in code style, and a link from the code reference to a doc in a code-only site leads to the doc's Markdown file on the repo host (plain text without `source-url`).
  When the parts are built together, they link to each other as one site.

## Navigation and indexes

- **DS-14** Each page shows: breadcrumb (up), children (down), `related` and computed **backlinks** (across), status (every status of a partly built doc, [DS-49](status-notes.md#requirements)), components and tags.
- **DS-15** Generated index pages: per tag, per component, and a **status board** grouping docs by `status`, then by `milestone` (in roadmap order) and `priority`; a partly built doc is listed under each of its statuses ([DS-48](status-notes.md#requirements)).
- **DS-16** A plain-text machine listing of all docs (path, title, summary, status, components) for agents.
- **DS-17** A query command for agents: list docs filtered by tag / component / status / layer / milestone / priority, without rendering; a partly built doc matches each of its statuses ([DS-47](status-notes.md#requirements)).
- **DS-28** A query command for agents: list the docs that link to a given doc (body links, `related`, `redirect_to`), without rendering.
- **DS-29** The rendered site is for humans. Agents use the raw Markdown and git for content, history and diffs, and lookup commands for code and the web API schema (DS-30, DS-31); the tooling provides no Markdown copies of rendered pages.
- **DS-30** A query command for agents: print one part of the committed web API schema (an operation, the operations of a tag, or a schema) as Markdown with references resolved, without rendering.
- **DS-31** A query command for agents: print the API of a code module or class (signatures with types, docstrings, base classes, inherited members) as Markdown, from the code, without rendering.

DS-30 and DS-31 are not docspecsite commands: a project provides them with its own lookup tools, chosen for its languages and its API schema.

Listings that include ADRs (index pages, the machine listing, `list`) sort docs by path, except that external ADRs come before the repo's own, by prefix in the order `external-adr-prefixes` lists them.

## Generated reference layer

- **DS-18** Code reference pages are generated from the **code itself and its docstrings** (structure, signatures, types, members, inheritance), rendered through the same pipeline, **for the latest version of the code only**, and so is their hand-written entry page. Older code is read with the version control or an IDE.
- **DS-19** Code reference pages show "described in" backlinks from docs' `code:` fields.

The HTTP API reference (DS-26, DS-27) is described in [web-api-reference.md](web-api-reference.md).

## Checks

- **DS-20** A check command validates: front-matter schema, `layer` matches directory, every directory has an `index.md` that lists each direct child doc and child directory with a description in its `## Children` section ([meta/structure.md](../meta/structure.md#every-directory-has-an-indexmd)), all links (body, `related`, `redirect_to`, `code:`, `web-api:`) resolve, components are in the project's component list or the shared ones ([meta/vocabulary.md](../meta/vocabulary.md)), no `#` or `%` in file or directory names under `docs/` ([meta/structure.md](../meta/structure.md#naming)), every doc is readable UTF-8, every doc has its title in its place ([DS-52](#checks)), and no doc's page takes the URL of a generated page ([architecture/docs-tooling.md](../architecture/docs-tooling.md#output-layout)).
  It also checks that a partly built doc's statuses and its status notes agree ([DS-44](status-notes.md#requirements) to [DS-46](status-notes.md#requirements)).
  Doc templates are not docs and are not checked ([meta/structure.md](../meta/structure.md#outside-docs)).
  The code is not checked: specs may change before it does ([meta/linking.md](../meta/linking.md#code-links)).
  Deletes and renames under `docs/` ([DS-6](#versioning)) are an optional check of the version control's backend ([DS-43](versioning-backends.md#requirements)).
- **DS-51** A problem may carry a **hint**: a line right under the problem that says how to fix it in this case, such as which value to add and the text of the field as it then reads ([commands.md](commands.md#check)).
  The problem line always has the same form, so scripts can match it; the wording of the hint differs from case to case, and `check --no-hints` leaves hints out.
  In problems and hints, every piece of exact text (a value, a field name, a status note text, a heading, text to write, a path to create) is in double quotes; the path that says where the problem is stays unquoted.
- **DS-52** A doc's **title** is its first level-1 heading: a line that starts with a single `#`, such as `# Import`, or a line underlined with `===`; either style may be used ([meta/authoring.md](../meta/authoring.md#page-shape)).
  A heading inside a block quote or a list is not a level-1 heading.
  The title comes right after the front matter: only blank lines may come between them, and any other text there, an HTML comment included, is a problem.
  A doc has exactly one level-1 heading, its title.
  The check reports text between the front matter and the title, a doc without a title, and each level-1 heading after the title; the problems and their hints are in [commands.md](commands.md#check).
  These rules are not checked in a doc whose front matter is missing or does not load: that is already a problem of its own.
  The site shows the title as the page's heading; for a doc without a title, it shows the front matter's `title` instead.
- **DS-36** A **code check**, run on demand once an implementation is done, validates the code's references: `Docs:` docstring lines point at existing docs (and headings, with an anchor), and Sphinx roles ([DS-34](#rendering)) and `code:` links in docstrings point at code the code reference shows.
- **DS-21** The check runs automatically before code leaves a developer's machine and again in CI: docspecsite provides it, with the git backend's `git:staged` check, as a prek hook, `docs-check`, that a project pins to a release tag ([guides/using-docspecsite.md](../guides/using-docspecsite.md)).
- **DS-33** Every doc under `docs/architecture/decisions/` other than an `index.md` is an ADR, and its file name is `<PREFIX>-NNNN-<slug>.md` ([meta/structure.md](../meta/structure.md#adr-ids)).
  `PREFIX` is the repo's own prefix (`adr-prefix`) or the prefix of an external ADR (`external-adr-prefixes`).
  An external ADR comes into the repo from somewhere else, such as the template the repo was created from or another project, and keeps the ID it has there.
  `NNNN` is four digits; the slug is lowercase words separated by `-`.
  Any other name is a problem, also when the doc's front matter does not load.
  When `docspecsite.toml` is not valid TOML, the prefixes are unknown and this rule is skipped.

## Settings

- **DS-32** Project settings live in `docspecsite.toml` at the root of the checked repo ([configuration.md](configuration.md)): the repo's ADR prefix, its web URL, where its code is and which components the code belongs to, the Contents-list threshold, and where versions come from ([versioning-backends.md](versioning-backends.md)).
  The file is always read from disk, never through the version control.
  The file is optional; a missing setting takes its default.
  The check reports an unknown setting or an invalid value as a problem, and the setting takes its default; `list` and `build` stop on an invalid value or a file that is not valid TOML, and warn about an unknown setting, which they ignore.
  Settings anywhere else, such as `pyproject.toml`, are not read.

## Running

- **DS-22** Building and serving docs run through Docker, in an image built from docspecsite's repo at a release tag; the check runs as a prek hook in an environment prek creates.
  Nothing beyond Docker, prek and the project's version control (git by default) is required on the host.
- **DS-23** docspecsite keeps its dependencies minimal.
- **DS-24** Builds are incremental: unchanged versions are not re-rendered, whichever backend gives them.
- **DS-25** Output is static files that can be opened locally or served by any web server.
