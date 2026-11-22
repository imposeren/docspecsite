---
title: Configuration — docspecsite.toml
summary: The optional `docspecsite.toml` file at the root of a checked repo — the repo's ADR prefix, its web URL, where its Python code is and which components it belongs to, the Contents-list threshold, and where versions come from.
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
  - behavior/versioning-backends.md
---

# Configuration — docspecsite.toml

A repo's settings for docspecsite live in `docspecsite.toml` at its root ([DS-32](requirements.md#settings)).
The file is optional, and every key in it is optional: a missing key takes its default, and without the file every setting takes its default.
Every command reads the file as it is on disk in the checked-out files, never a copy kept by the version control, committed or staged: `build --ref` builds an older ref with today's settings, not the ones committed with it.

## Settings

`check` reports an unknown key (such as a misspelled `adr_prefix`), a value of the wrong kind and a file that is not valid TOML as problems on `docspecsite.toml`: a setting with a wrong value takes its default, and a file that is not valid TOML makes `check` skip the ADR file-name rule, since the repo's prefix is unknown.
`list` and `build` stop with an error on a file that is not valid TOML or a value of the wrong kind; they warn about an unknown key and ignore it, so a setting from a newer docspecsite release doesn't stop an older one.

```toml
adr-prefix = "APP"
external-adr-prefixes = ["BASE"]
source-url = "https://github.com/example/project"
code-dirs = ["src"]
toc-min-headings = 5

[code-components]
example = ["core"]
"example.api" = ["backend"]

[versioning]
backend = "git"

[versioning.git]
versions = "tags"
tag-pattern = "v*"
```

| Key | Default | Meaning |
| -- | -- | -- |
| `adr-prefix` | none | The repo's own ADR prefix: capital letters only (`A`–`Z`), such as `APP` ([DS-33](requirements.md#checks), [meta/structure.md](../meta/structure.md#adr-ids)). Without it, only external ADRs are valid. |
| `external-adr-prefixes` | none | Prefixes of external ADRs: ADRs the repo takes from elsewhere, such as the template it was created from (`BASE`) or another project, which keep their IDs. A list of capital-letter prefixes, other than `adr-prefix`, in the order listings show them. `check` reports an entry that is not capital letters, equals `adr-prefix` or repeats an earlier one, and leaves it out; `list` and `build` stop on it. |
| `source-url` | none | Web URL of the repo on its host, such as `https://github.com/example/project`. Code reference pages link each element to its source file at the built [revision](glossary.md) (with git, the built commit), and body links to repo files outside the site go to the file or directory there, through the versioning backend's link patterns ([Versioning](#versioning)); with git, under `<source-url>/blob/<commit>/` or `<source-url>/tree/<commit>/`. Without it, a link pattern that uses `{source-url}` gives no link: code reference pages have no source links and body links to repo files are plain text. `build` then warns once about the missing setting: at the start when `code-dirs` is set, else at the first repo link it turns into plain text in the latest version of a doc, naming that version and link; links in older versions become plain text without a warning. |
| `code-dirs` | none | Directories, relative to the repo root, that hold the Python packages for the code reference; shell-style globs such as `services/*/src` are allowed, and `.` is the repo root. `check` reports an entry that is empty, absolute or contains `..` and leaves it out; `list` and `build` stop on it. A package is a directory with an `__init__.py` directly inside one of them, and its name must be unique across the directories: `check --optional-checks code` reports a name found in more than one, and `build` warns that it cannot load the code. Without it, there is no code reference and `code:` links cannot resolve. |
| `code-components` | none | Table of component lists (lists of strings) by dotted module path. A code element gets the components of the longest key that matches its dotted path on whole segments, such as `example.api` for `example.api.routes`. Components must be in the repo's component list ([meta/vocabulary.md](../meta/vocabulary.md)). |
| `toc-min-headings` | `5` | A whole number of 0 or more. A doc with at least this many `##` sections gets a generated Contents list of its `##` and `###` headings, placed before the first `##` section ([meta/authoring.md](../meta/authoring.md#page-shape)). `0` turns the list off. |
| `status-notes` | the default texts | A `[status-notes]` section with one [status note](../meta/glossary.md#status-note) text per status: `specified`, `changed` and `implemented`, each the bold label without `**` and `>`, such as `specified = "Ще не зроблено."`. A status left out keeps its default text ([status-notes.md](status-notes.md)). `check` reports an unknown status, an empty text or one with spaces at its start or end (it could never match a bold label), and two statuses with the same text, and the setting then keeps its defaults; `list` and `build` stop on them. |

The problems `check` reports for `status-notes`:

- `"status-notes" must be a table of status note texts by status`
- `"status-notes" has an unknown status: "done"`
- `"status-notes" text of "specified" must be non-empty text without leading or trailing spaces`, for an empty text, one with spaces at its start or end, and a value that is not text
- `"status-notes" gives "implemented" and "specified" the same text: "Built."`

## Versioning

The `[versioning]` section says which [backend](glossary.md) gives the versions of the docs, that is, which part of docspecsite reads them from the project's version control ([versioning-backends.md](versioning-backends.md)).
It is optional, and so is each key in it.
Each backend has a section of its own, `[versioning.<backend>]`, with its own keys; only the section of the backend in use is read, so the section of another backend is ignored without a warning.
In the section in use, an unknown key and a value of the wrong kind are treated like those at the top level: `check` reports them, and `list` and `build` stop on a wrong value and warn about an unknown key.

| Key | Default | Meaning |
| -- | -- | -- |
| `backend` | `"auto"` | Where versions come from: `"auto"` (the one backend that recognizes the checked repo, or no versions when none does), `"git"`, `"none"` (no version control), the name a separately installed package gives its backend (such as `"hg"`), or, for a backend its package gives no name, its import path, `"<package.module>:<Class>"`, which says where the backend is inside the package and which that package's documentation gives. A name that no installed backend has, or an import path that cannot be loaded, is a problem for `check`, which then goes on as with `"auto"`; `list`, `build` and `backlinks` stop on it. |

### `[versioning.git]`

| Key | Default | Meaning |
| -- | -- | -- |
| `versions` | `"commits"` | `"commits"`: every commit that touches a doc is a version of it. `"tags"`: only the versions current at tags ([versioning-backends.md](versioning-backends.md#versions-from-tags-only)). |
| `tag-pattern` | none | Required with `versions = "tags"`, so a project always says which tags are its releases: without it, `check` reports a problem and `list`, `backlinks` and `build` stop. The tags that count: a pattern matched against the whole tag name, where `*` stands for any run of characters and `?` for one character, such as `"v*"`. With `versions = "commits"` it has no effect. |
| `file-link` | `"{source-url}/blob/{revision}/{path}"` | The [link pattern](glossary.md) for a file on the repo host: its address, with placeholders that docspecsite fills in ([DS-42](versioning-backends.md#requirements)). `{source-url}` is the `source-url` setting, `{revision}` the full commit id, and `{path}` the file's path from the repo root. Change it for a host with other addresses, such as GitLab's `"{source-url}/-/blob/{revision}/{path}"`. |
| `dir-link` | `"{source-url}/tree/{revision}/{path}"` | The same for a directory; GitLab: `"{source-url}/-/tree/{revision}/{path}"`. |

A pattern with a placeholder other than these three is a wrong value.

### `[versioning.none]`

| Key | Default | Meaning |
| -- | -- | -- |
| `file-link` | none | The link pattern for a file on the repo host, with `{source-url}` and `{path}` as for git, such as `"{source-url}/blob/main/{path}"`. Without it, there are no source links. Without version control there is no revision, so a pattern with `{revision}` is a wrong value. |
| `dir-link` | none | The same for a directory. |

A backend from another package documents its own keys; its section is named after the backend's name, also when `backend` gives its import path.
