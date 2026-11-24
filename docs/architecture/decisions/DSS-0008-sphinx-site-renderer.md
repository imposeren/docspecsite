---
title: "DSS-0008: Sphinx as the site renderer, behind a renderer seam"
summary: The site is rendered by Sphinx with MyST-Parser, sphinx-autoapi and the furo theme, always installed, behind a small renderer seam whose temporary `internal` renderer keeps today's custom renderer selectable until a later release removes it; supersedes DSS-0001.
layer: architecture
status: specified
decision: proposed
date: 2026-11-24
components: [site, code-reference, distribution]
tags: [adr, rendering, tooling]
related:
  - architecture/site.md
  - architecture/docs-tooling.md
  - architecture/decisions/DSS-0001-custom-per-doc-history-renderer.md
  - architecture/decisions/DSS-0005-entry-points-for-backends.md
  - behavior/site.md
  - behavior/distribution.md
  - behavior/configuration.md
---

# DSS-0008: Sphinx as the site renderer, behind a renderer seam

## Context

[DSS-0001](DSS-0001-custom-per-doc-history-renderer.md) chose a custom renderer, built on markdown-it-py and Jinja, because the existing doc generators version whole sites, not single docs.
That renderer now owns about 2,900 lines that only `build` uses (pages, index pages, its build cache, templates and static files), plus the HTML side of the shared Markdown, link and code reference modules; it has no search, and its theme and role handling are docspecsite's own to keep up.

A spike (November 2026) built the whole site with Sphinx on top of docspecsite's own doc model and history: per-doc versions come from docspecsite's history as generated source files, not from whole-site snapshots, so DSS-0001's main objection to Sphinx does not hold.
On docspecsite and on a second project every page of today's site existed, with the same panels, markers, heading ids and `llms.txt`; the code reference had every object id, with Sphinx's Python roles in docstrings resolved natively.
The spike recommended going ahead; its open risks were three patches of other packages' internals and the packages the image gains.

The requirements that shape the choice: per-doc history and version-aware links ([DSR-5](../../behavior/versioning-backends.md#versions-of-a-doc), [DSR-11](../../behavior/site.md#rendering)), Sphinx-style roles in docstrings ([DSR-34](../../behavior/code-reference.md#requirements)), static output ([DSR-25](../../behavior/site.md#building)) and dependencies chosen for a reason ([DSR-23](../../behavior/distribution.md#requirements)).

## Options considered

How the switch is made, judged in this order: both renderers can render the same repo state side by side during the migration; nothing is built that has no use once the old renderer is gone; dependencies stay few and each has a reason.

1. **Sphinx as a Python optional dependency, renderers found through entry points** (the pattern of [DSS-0005](DSS-0005-entry-points-for-backends.md)).
   Keeps a minimal core install for `check`.
   Costs registration machinery for renderers that nobody outside docspecsite writes, and an optional dependency that loses its reason once the old renderer is gone.
2. **Sphinx always installed, a small internal seam chosen by a setting and an option.**
   The Sphinx packages are normal dependencies, and the image installs them.
   Little machinery, and the end state (Sphinx only) needs no packaging change.
   Costs: the image and the prek hook's environment install the Sphinx packages (about 25 with furo) although `check` never uses them; the old renderer, the setting and the option stay until a later release removes them.
3. **Switch in one go, no seam.**
   Least code: no seam, no setting, no second renderer to keep.
   But no side-by-side comparison during the migration, which the first criterion needs.

Which generator, once the custom renderer goes:

- **Sphinx with MyST-Parser and sphinx-autoapi** — renders CommonMark with front matter, resolves Sphinx's Python roles (`` :meth:`.attempt` ``) natively through its Python domain, generates the code reference without importing the code, and has full-text search and maintained themes.
- **MkDocs with mkdocstrings, or Zensical** — polished themes and search, but cross-references in docstrings use mkdocstrings' own syntax, not Sphinx's roles, so the roles that docspecsite's docstrings and [DSR-34](../../behavior/code-reference.md#requirements) use would again need docspecsite's own resolver; Zensical is young and its plugin support is still settling.
- **mystmd** (the MyST Markdown command-line tool) — native MyST, but a Node.js tool with no Python code reference of its own; it would add a second language runtime to the image.

## Decision

Proposed: option 2 with Sphinx.

- **Packages:** Sphinx, MyST-Parser (the docs), sphinx-autoapi with astroid (the code reference) and the furo theme are normal dependencies, always installed and pinned in the lock file.
- **Seam:** `docspecsite build` keeps one build front that loads the settings, the history, the docs, the code at the ref and the parts, and writes the output; a **site renderer** turns that prepared input into the site's files.
  There are two: `internal`, today's custom renderer moved behind the seam, and `sphinx`.
  The `[site] renderer` setting chooses one, `build --renderer` overrides it for one build, and the default is `sphinx`.
- **No entry points**, unlike [DSS-0005](DSS-0005-entry-points-for-backends.md): the two renderers are a fixed choice inside docspecsite, since nobody outside it plugs in a renderer.
- **The seam serves the migration**: both renderers build the same repo state into separate outputs, and a renderer comparison shows where they differ.
  It is kept clean enough to outlive the `internal` renderer: its interface carries nothing only the `internal` renderer uses.
  A later release removes the `internal` renderer, the setting and the option; the seam's interface and the build front stay as they are.
- **Theme:** furo, fixed; the page chrome is built on its template blocks.

The design: [site.md](../site.md).

## Consequences

- **Full builds.** Every `sphinx` build renders the whole site in an emptied Sphinx build directory: Sphinx's incremental build misses changes to docspecsite's extension and to the headings of linked docs.
  [DSR-24](../../behavior/site.md#building) is reworded from incremental builds to pages that are never stale; the `internal` renderer keeps its build cache while it exists.
- **Dependencies.** About 25 packages more in the image and in the prek hook's environment (Sphinx and its own dependencies, docutils, MyST-Parser, sphinx-autoapi, astroid, furo and its dependencies), each listed with its reason in [docs-tooling.md](../docs-tooling.md#dependencies).
  [DSR-23](../../behavior/distribution.md#requirements) and the guiding principle on dependencies ([architecture/index.md](../index.md#guiding-principles)) are reworded to the need: an established library before docspecsite's own code, each dependency with its reason, a new one by decision.
- **Two code readers** (known risk). `check --optional-checks code` keeps its own lookup over griffe, while the site's code reference is read by sphinx-autoapi through astroid and its roles are resolved by Sphinx's Python domain.
  [DSR-34](../../behavior/code-reference.md#requirements) is reworded to Sphinx's rules (including the fallback that finds `.name` as any object whose path ends in `.name`), and the griffe lookup follows them; a test compares the two on docspecsite's own code and fails on a role that resolves in one but not the other, or to different objects.
- **Public extension points instead of patches**, each with a test that fails when the upstream code it relies on changes; each has a fallback, used only where the extension point turns out not to work:
  - a `MystParser` subclass whose `parse` names docspecsite's renderer subclass, so a fence such as ```` ```{x} ```` stays a code block; fallback: the spike's patch of MyST's `render_fence`, pinned and tested;
  - an own docstring listener that calls napoleon's public `GoogleDocstring` and `Config`, without loading `sphinx.ext.napoleon` as an extension; fallback: napoleon loaded with its listener replaced, pinned and tested;
  - an HTML builder subclass that keeps version and diff pages out of the search index;
  - Sphinx run in-process with the whole configuration given in code; fallback: a generated `conf.py` in the Sphinx build directory;
  - furo's template blocks for the page chrome; fallback: Sphinx's built-in alabaster theme.
- **Drift from the custom renderer's site**, accepted where the site stays good for people: code pages at nested URLs (`reference/code/<pkg>/<module>/index.html` instead of `reference/code/<pkg>.<module>.html`), so outside bookmarks to code pages break; heading links in the body in docutils' section id form (`#don-t`) where it differs from the slug (`#dont`), with both ids on the page; furo's layout with a sidebar Contents instead of the generated in-body Contents list; autoapi's default code page without collapsible member sections or a per-page member index; added search, a general index and `_static/`, so more doc paths are reserved; an exception inside Sphinx fails the whole build.
- **Build time** grows; it was not a criterion.
- **Mermaid stays docspecsite's own**: the extension turns a `mermaid` fence into a diagram and loads the bundle that the image vendors, so the site works offline; sphinxcontrib-mermaid would be a new dependency that loads Mermaid its own way.
- **Diff pages use Sphinx's highlighter**: a diff page shows the unified diff as a `diff` code block highlighted by Pygments, instead of the `internal` renderer's own diff markup; the diff text itself is shared.
- **Maintenance moves**: the page model, history, links, markers and checks stay docspecsite's; Markdown parsing, the theme, search and role resolution become upstream's, pinned and updated like any dependency.
