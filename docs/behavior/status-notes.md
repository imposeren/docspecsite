---
title: Partly built docs
summary: A doc that is only partly built lists several statuses and gives the sections that differ a status note; docspecsite checks that the list and the status notes agree, finds such a doc under each of its statuses, and shows all of them on the site.
layer: behavior
status: implemented
code: [docspecsite.docs.DocStatus, docspecsite.check.StatusNoteCheck, docspecsite.markdown.MarkdownText.get_section_notes, docspecsite.problems.Problem]
milestone: later
priority: should
components: [checks, queries, site]
tags: [requirements, status, checks]
related:
  - scenarios/status-notes.md
  - behavior/requirements.md
  - behavior/docs-format.md
  - behavior/commands.md
  - behavior/site.md
  - architecture/docs-tooling.md
  - meta/lifecycle.md
---

# Partly built docs

A doc can be partly built: some of its sections are true in the code, others are not yet ([meta/lifecycle.md](../meta/lifecycle.md#partly-built-docs)).
Its [status](../meta/glossary.md#status) in the [front matter](../meta/glossary.md#front-matter) is then a list, such as `status: [implemented, specified]`, and each section that differs from the first value carries a [status note](../meta/glossary.md#status-note) such as `> **Not built yet.**` among its [section notes](../meta/glossary.md#section-note).
`docspecsite check` checks that the list and the status notes agree, `docspecsite list` finds the doc under each of its statuses, and the site shows all of them.
On the site, as on GitHub and in an editor, a status note reads like any other note.
Docs in a [layer without a build status](../meta/lifecycle.md#layers-without-a-build-status), today the scenario docs, are never partly built: docspecsite ignores their [build status](../meta/glossary.md#build-status) and status notes ([DSR-53](docs-format.md#layers-without-a-build-status)).

## Statuses

A doc's `status` is one of `draft`, `specified`, `changed`, `implemented`, `deprecated` and `redirect`; `changed` means the doc now describes a new form of something and the code still does an older form of it.
A doc's title is its first level-1 heading, written `# Import` or underlined with `===`, and it comes right after the front matter ([DSR-52](docs-format.md#requirements)).
The title and its text up to the next heading, the doc's [document brief](../meta/glossary.md#document-brief), belong to no section and carry no status note: the doc's whole `status` describes them, so the brief may mention built and unbuilt parts alike.
For status, every other heading starts a section of its own, whatever the heading's level.
A section is the heading and its text up to the next heading of any level, so a `##` section does not include the `###` sections below it.
In a partly built doc's list, the first value is the status of every section without a status note, and each further value is the status of the sections whose status note gives it.

| Status note (default text) | The section is |
| -- | -- |
| `> **Not built yet.**` | `specified` |
| `> **Changed, not built yet.**` | `changed` |
| `> **Built.**` | `implemented` |

These are the texts docspecsite ships; a project can set its own in its settings file, `docspecsite.toml`, for example to write its docs in another language ([configuration.md](configuration.md)).

Text may follow the status note on the same line, such as what still works the old way.

## Requirements

These requirements are part of the [DSR-n](../meta/glossary.md#dsr-n) numbering listed in [requirements.md](requirements.md):

- **DSR-44** `status` is a single value, or a list of distinct values from `implemented`, `specified` and `changed`.
  A list with one value, such as `status: [specified]`, means the same as that single value and is not a problem.
  `draft`, `deprecated` and `redirect` are never combined with other statuses: each may be written as a single value or as a one-value list (`status: [draft]`).
  Any other `status`, such as one with an unknown value (`[implemented, done]`), a number (`5`) or an empty list (`[]`), is a problem on the doc's first line, without a hint, and the doc's status notes are then not checked:

  ```
  "status" must be one of: draft, specified, changed, implemented, deprecated, redirect, or a list of distinct values from: implemented, specified, changed
  ```

  In a layer without a build status, this rule applies to what is left of the `status` field once [DSR-53](docs-format.md#layers-without-a-build-status) has ignored the build statuses.

- **DSR-45** A section's notes are the note lines (lines starting with `>`) that come right after its heading, before any other content: a paragraph, list, table, code block or subheading.
  Each note line is one note, also when several follow each other without a blank line between them.
  Their order does not matter.
  The doc's title, its first level-1 heading ([DSR-52](docs-format.md#requirements)), and its text up to the next heading belong to no section, so a status note right after the title is a problem ([DSR-46](#requirements)).
  A status note is a section note that starts with one of the project's status note texts in bold, exactly as written: the defaults above, or the ones the project sets.
  Its section then has the status note's status.
  A section is the heading and its text up to the next heading of any level.
  The sections under deeper headings below it do not get that status: each has the doc's first status unless it has a status note of its own, whatever the status of any heading above it.
  The title stays the title when text comes before it, and the check reports that text; each later level-1 heading is a section like any other heading, and the check reports it ([DSR-52](docs-format.md#requirements)).
  A section note with any other bold label, or with none, is ordinary text, not a problem, so new kinds of section notes do not break existing docs.

- **DSR-46** The check reports a problem in each case below.
  None of these concerns a status note or a build status that [DSR-53](docs-format.md#layers-without-a-build-status) ignores.
  Each problem names the statuses involved and carries a hint ([DSR-51](commands.md#checks)).
  A problem about a status note is reported on the status note's line, a problem about the `status` list on the doc's first line, where the front matter starts.
  Problems and hints name a section by its heading quoted with its `#` marks, exactly as written in the file (`"## Import"`), so a heading with the same words at another level is not mistaken for it, and the quoted text can be searched for in the file.
  A heading written without `#` marks, underlined with `===` or `---` on the next line, is quoted by its first line as written.
  A hint that changes `status` names the change and the whole field as it then reads: a list, or the single value when one is left (`"status: implemented"`).
  The examples show the message after `docs/<path>:<line>: ` and the hint line under it:

  - `draft`, `deprecated` or `redirect` combined with other statuses:

    ```
    "draft" is combined with other statuses in "status"
      hint: write "status: draft", or remove "draft" from "status" so it reads "status: specified"
    ```

  - a value that appears twice in the `status` list:

    ```
    "specified" is listed twice in "status"
      hint: remove the duplicate "specified" from "status" so it reads "status: [implemented, specified]"
    ```

  - each value after the first that no section's status note gives:

    ```
    "changed" is in "status", but no section has a "Changed, not built yet." status note
      hint: add a "> **Changed, not built yet.**" status note to a section, or remove "changed" from "status" so it reads "status: [implemented, specified]"
    ```

  - each status note after the first in one section, which may have at most one; this is the only problem reported for that status note, and its status still counts as given by a status note, so the problem above is not reported for it:

    ```
    status note "Changed, not built yet." ("changed") in the section "## Import", which already has the status note "Not built yet." ("specified")
      hint: keep one status note in the section "## Import"
    ```

  - a status note whose status is not in the doc's `status`:

    ```
    status note "Changed, not built yet." ("changed") in a doc whose "status" is "[implemented, specified]"
      hint: add "changed" to "status" so it reads "status: [implemented, specified, changed]", or remove the status note from the section "## Export"
    ```

  - a status note that gives the doc's first status, which its section already has without it:

    ```
    status note "Not built yet." ("specified") gives the status the section "### Backend checks" already has from "status: [specified, implemented]"
      hint: remove the "Not built yet." status note from the section "### Backend checks"
    ```

  - any status note in a doc with a single status:

    ```
    status note "Not built yet." ("specified") in a doc with the single status "implemented"
      hint: add "specified" to "status" so it reads "status: [implemented, specified]", or remove the status note from the section "## Import"
    ```

    When adding the status note's status would not give a valid `status`, because the doc's single status is that same status or is `draft`, `deprecated` or `redirect`, the hint only offers removing the status note:

    ```
    status note "Not built yet." ("specified") in a doc with the single status "specified"
      hint: remove the status note from the section "## Import"
    ```

  - a status note right under the doc's title, which is not a section; this is the only problem reported for that status note:

    ```
    status note "Not built yet." ("specified") right under the doc's title "# Import"
      hint: set the doc's "status" instead
    ```

- **DSR-47** `list --status S` lists a doc whose `status` has `S` anywhere in it.
  A doc without a `status`, also one whose `status` [DSR-53](docs-format.md#layers-without-a-build-status) ignores as a whole, matches no `--status`.
  The text output shows a list of statuses comma-separated, in the doc's order and without spaces (`implemented,specified`), and so does `llms.txt`, the plain-text listing of all docs for agents ([DSR-16](site.md#navigation-and-indexes)).
  In `--format json` (JSON, a data format for scripts), `status` stays a string (`"implemented"`) for a single status and is a list of strings (`["implemented", "specified"]`) for a list; a list with one value is shown as that single value, as a string.
  For a doc without a `status`, the text output leaves the status column empty (two tabs follow its path), `--format json` gives `"status": null` (`null` is JSON's word for no value), and `llms.txt` leaves out the doc's `status:` part ([DSR-16](site.md#navigation-and-indexes)).

- **DSR-48** The status board ([DSR-15](site.md#navigation-and-indexes)) lists a doc under each status it has, in that status's [milestone](../meta/glossary.md#milestone) and [priority](../meta/glossary.md#priority) groups.
  Entries on the index pages (the status board, tag and component pages) show all of a doc's statuses.
  A doc without a `status` is not on the status board, and its entries on the tag and component pages show no status.

- **DSR-49** A doc's page shows one status badge (a label with the status name) for each of its statuses, in the doc's order.
  The status notes in its body are shown as written, like any other note.
  A doc without a `status` has no status badge.

- **DSR-50** A project can replace the default text of each status note in `docspecsite.toml`; the texts must differ from each other, and the default text of a status the project replaced no longer counts as a status note, while the defaults of the other statuses still do.

A milestone counts as reached only when all its docs with priority `must` have the single status `implemented` ([meta/lifecycle.md](../meta/lifecycle.md#using-status-as-a-task-list)); docspecsite does not compute it.

## See also

- [scenarios/status-notes.md](../scenarios/status-notes.md) — exact cases for the check, `list` and the site.
- [commands.md](commands.md) — the `check` and `list` output.
- [architecture/docs-tooling.md](../architecture/docs-tooling.md#statuses-and-status-notes) — how docspecsite reads statuses and status notes.
