---
title: Glossary — docspecsite terms
summary: Plain-language definitions of the terms docspecsite's docs and output use — checked repo, link pattern, main line of history, problem, ref, revision, site, symlink, version control, versioning backend, versionless site, code reference, ADR prefix.
layer: behavior
status: changed
components: []
tags: [glossary]
related:
  - meta/glossary.md
  - architecture/glossary.md
---

# Glossary — docspecsite terms

Documentation terms (layer, status, redirect doc, version of a doc…) are in [meta/glossary.md](../meta/glossary.md); technical terms and tools in [architecture/glossary.md](../architecture/glossary.md).

| Term | Meaning |
| -- | -- |
| **ADR prefix** | The letters before the number in an ADR ID, such as `BASE` in `BASE-0002`. A repo has its own prefix (`adr-prefix` in `docspecsite.toml`) and may hold external ADRs, taken from elsewhere with their IDs, whose prefixes `external-adr-prefixes` lists, such as the template's `BASE` ([configuration.md](configuration.md)). |
| **checked repo** | The folder whose `docs/` docspecsite works on: the current directory, or the one given with `--repo`. With git, it is the top level of a git repository. |
| **code reference** | Pages generated from a project's Python code and its docstrings, one per module, for the latest code only. |
| **link pattern** | The address of a file or folder on the repo's web host, with placeholders such as `{path}` that docspecsite fills in for each link; set per backend ([configuration.md](configuration.md#versioning)). |
| **main line of history** | The history that gives the versions, with git: the commits of the built ref's own branch, where a merged branch counts as its one merge commit, so the commits made on a merged branch before the merge are not versions of their own. |
| **problem** | One thing `docspecsite check` found wrong, printed as `path:line: message`. |
| **ref** | The name of a revision: with git, a branch, tag or commit. `docspecsite build` renders the history of one ref; without version control there is none. |
| **revision** | One saved state of the project in its version control: a commit, with git. |
| **site** | The static HTML files `docspecsite build` writes: one page per doc version, diffs, index pages and a machine listing. |
| **symlink** | A file that only points to another file or directory. Under `docs/`, a symlink is judged by what it leads to: no doc is reached through one, while other files, such as images, may be ([doc-symlinks.md](doc-symlinks.md)). |
| **version control** | The system that records a project's history, such as git or Mercurial. Without one, docspecsite builds a versionless site. |
| **versioning backend** | The part of docspecsite that reads the history of one kind of version control (`git`), or that works without one (`none`); chosen with the `backend` setting ([versioning-backends.md](versioning-backends.md)). |
| **versionless site** | A site built without version control: each doc has only its current version, with no older versions, version picker or diffs. |
| **working copy version** | Changes to a doc not yet saved as a revision (uncommitted, with git), shown as an extra newest version when the site is built with `--include-worktree`. |
