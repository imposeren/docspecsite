---
title: Configuration — docspecsite.toml
summary: The optional `docspecsite.toml` file at the root of a checked repo — the repo's ADR prefix, its web URL, where its Python code is and which components it belongs to, and the Contents-list threshold.
layer: behavior
status: specified
milestone: first-release
priority: must
code: [docspecsite.config]
components: [cli]
tags: [configuration]
related:
  - behavior/requirements.md
  - meta/structure.md
  - guides/using-docspecsite.md
---

# Configuration — docspecsite.toml

A repo's settings for docspecsite live in `docspecsite.toml` at its root ([DS-32](requirements.md#settings)).
The file is optional, and every key in it is optional.
A missing key takes its default.
Without the file, every setting takes its default.
`check` reports an unknown key (such as a misspelled `adr_prefix`), a value of the wrong kind and a file that is not valid TOML as problems on `docspecsite.toml`: a setting with a wrong value takes its default, and a file that is not valid TOML makes `check` skip the ADR file-name rule, since the repo's prefix is unknown.
`list` and `build` stop with an error on a file that is not valid TOML or a value of the wrong kind; they warn about an unknown key and ignore it, so a setting from a newer docspecsite release doesn't stop an older one.
Every command reads the file from the working tree, as it is on disk: `build --ref` builds an older ref with today's settings, not the ones committed with it.

```toml
adr-prefix = "APP"
external-adr-prefixes = ["BASE"]
source-url = "https://github.com/example/project"
code-dirs = ["src"]
toc-min-headings = 5

[code-components]
example = ["core"]
"example.api" = ["backend"]
```

| Key | Default | Meaning |
| -- | -- | -- |
| `adr-prefix` | none | The repo's own ADR prefix: capital letters only (`A`–`Z`), such as `APP` ([DS-33](requirements.md#checks), [meta/structure.md](../meta/structure.md#adr-ids)). Without it, only external ADRs are valid. |
| `external-adr-prefixes` | none | Prefixes of external ADRs: ADRs the repo takes from elsewhere, such as the template it was created from (`BASE`) or another project, which keep their IDs. A list of capital-letter prefixes, other than `adr-prefix`, in the order listings show them. `check` reports an entry that is not capital letters, equals `adr-prefix` or repeats an earlier one, and leaves it out; `list` and `build` stop on it. |
| `source-url` | none | Web URL of the repo on its host, such as `https://github.com/example/project`. Code reference pages link each element to its source file at the built commit under `<source-url>/blob/<commit>/`. Body links to repo files outside the site go to `<source-url>/blob/<commit>/` or `<source-url>/tree/<commit>/`. Without it, code reference pages have no source links and body links to repo files are plain text. `build` then warns once about the missing setting: at the start when `code-dirs` is set, else at the first repo link it turns into plain text in the latest version of a doc, naming that version and link; links in older versions become plain text without a warning. |
| `code-dirs` | none | Directories, relative to the repo root, that hold the Python packages for the code reference; shell-style globs such as `services/*/src` are allowed, and `.` is the repo root. `check` reports an entry that is empty, absolute or contains `..` and leaves it out; `list` and `build` stop on it. A package is a directory with an `__init__.py` directly inside one of them, and its name must be unique across the directories: `check --code` reports a name found in more than one, and `build` warns that it cannot load the code. Without it, there is no code reference and `code:` links cannot resolve. |
| `code-components` | none | Table of component lists (lists of strings) by dotted module path. A code element gets the components of the longest key that matches its dotted path on whole segments, such as `example.api` for `example.api.routes`. Components must be in the repo's component list ([meta/vocabulary.md](../meta/vocabulary.md)). |
| `toc-min-headings` | `5` | A whole number of 0 or more. A doc with at least this many `##` sections gets a generated Contents list of its `##` and `###` headings, placed before the first `##` section ([meta/authoring.md](../meta/authoring.md#page-shape)). `0` turns the list off. |
