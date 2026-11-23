---
title: Commands — scenarios
summary: Exact cases for the revision a build shows by default, for the source links of changed code in a preview of the working tree, for body links whose target is found or not found, and for the backlinks of a doc template.
layer: scenarios
status: [specified, implemented, changed]
components: [site, code-reference]
tags: [cli, rendering]
milestone: hardening
priority: must
related:
  - behavior/commands.md
  - architecture/docs-tooling.md
---

# Commands — scenarios

These scenarios pin down three parts of `docspecsite build` in [Commands](../behavior/commands.md#build), and one case of `backlinks`.
The first is which [revision](../behavior/glossary.md) a build shows when no `--ref` is given, with or without a preview of the working tree (the files as they are now on disk), built with `--include-worktree`.
The second is which code pages of such a preview link to their source.
The third is which link targets count as found, and how a body link (a link in a doc's text) whose target is not found is shown.
The case of `backlinks` is a path that names a doc template.
The rest of the commands is pinned down by [commands.md](../behavior/commands.md) and the tests; the check's rules have scenarios of their own ([requirements.md](requirements.md), [doc-symlinks.md](doc-symlinks.md)).

## Building what is checked out

> **Changed, not built yet.** Without `--ref`, a build still shows the branch `main`, whatever is checked out; a preview on another branch then shows everything in which the working tree differs from `main` as the working copy.

```gherkin
Feature: Building what is checked out
  As a docs author
  I want a build to show the commit I have checked out
  So that the site matches the files I am working on, on any branch

  Background:
    Given a git repository checked out on the branch "feat/x"
    And two commits on "feat/x" only, not on "main", that change the doc "docs/guides/setup.md"

  Scenario: A build without --ref shows the checked-out commit
    When I build the site without --ref
    Then the versions of "guides/setup.md" include both commits of "feat/x"

  Scenario: A preview without uncommitted changes has no working copy
    Given no uncommitted changes
    When I build the site with --include-worktree and no --ref
    Then the versions of "guides/setup.md" include both commits of "feat/x"
    And no doc has a "working copy (uncommitted)" version

  Scenario: A preview shows only uncommitted changes as the working copy
    Given an uncommitted change to the doc "docs/guides/setup.md"
    When I build the site with --include-worktree and no --ref
    Then "guides/setup.md" has a "working copy (uncommitted)" version with that change
    And no other doc has one
```

### A preview measured against a named ref

> **Built.**

```gherkin
Feature: A preview measured against a named ref
  As a docs author
  I want a preview with --ref to show everything my files change compared with that ref
  So that I can read all the changes of my branch against another one in one place

  Scenario: A preview with --ref shows the branch's commits as the working copy too
    Given a git repository checked out on the branch "feat/x"
    And a commit on "feat/x" only, not on "main", that changes the doc "docs/guides/setup.md"
    And an uncommitted change to the doc "docs/guides/usage.md"
    When I build the site with --ref main and --include-worktree
    Then the committed versions of "guides/setup.md" do not include the commit of "feat/x"
    And "guides/setup.md" has a "working copy (uncommitted)" version with the change of that commit
    And "guides/usage.md" has a "working copy (uncommitted)" version with the uncommitted change
    And no other doc has one
```

## Previewing the working tree

```gherkin
Feature: Previewing the working tree
  As a docs author
  I want a preview of my working tree to link only to source that matches what it shows
  So that a source link never leads to code other than the code on the page

  Scenario: Code changed in the working tree gets no source links
    Given a project with "source-url" and "code-dirs" set
    And an uncommitted new module "pkg/new.py" and an uncommitted change to "pkg/a.py"
    And "pkg/b.py" is unchanged
    When I build the site with --include-worktree
    Then the code pages of "pkg.new" and "pkg.a" have no source links
    And the code page of "pkg.b" links each element to its source at the built revision
```

## Links whose target is not found

A body link whose target is not found gets the same marker, whatever the link names, such as a doc, an image, another file or a directory.
This goes for every body link other than a `code:` link; the marker is not used for the `related` and `redirect_to` entries of the front matter or for `Docs:` lines in code.
[commands.md](../behavior/commands.md#build) says which targets are found.
The marker is shown in every version, and the warning is given only for the latest version of the linking doc.

```gherkin
Feature: Links whose target is not found
  As a reader
  I want a link to something that does not exist to say so
  So that I am not sent to a page that is not there

  Scenario Outline: A link to a missing target
    Given the text of the latest version of a doc links to "<target>"
    And "<target>" does not exist in the built revision
    When I build the site
    Then the doc's page shows the link's text with the marker "not found" and no link
    And the build warns about an unresolvable link

    Examples:
      | target              |
      | img/flow.png        |
      | missing.md          |
      | ../src/pkg/gone.py  |

  Scenario: An old version's link to a file that no longer exists
    Given the text of an old version of a doc links to "../src/pkg/old.py"
    And "src/pkg/old.py" was renamed after that version
    When I build the site
    Then that version's page shows the link's text with the marker "not found" and no link

  Scenario: A link to a symlinked doc is not found
    Given "docs/guides/alias.md" is committed as a symlink to "setup.md"
    And the text of the latest version of another doc links to "alias.md"
    When I build the site
    Then that doc's page shows the link's text with the marker "not found" and no link
    And the build warns about an unresolvable link

  Scenario: An uncommitted doc template is not found in a preview
    Given an uncommitted new doc template "docs/meta/templates/note.md"
    And an uncommitted change that makes the text of the doc "docs/meta/index.md" link to "templates/note.md"
    When I build the site with --include-worktree
    Then the working copy version of "meta/index.md" shows that link's text with the marker "not found" and no link
```

### Uncommitted files in a preview

> **Built.**

```gherkin
Feature: Uncommitted files in a preview
  As a docs author
  I want a preview to find the images I have not committed yet
  So that I can check a new image on the site before I commit it

  Scenario: An uncommitted image is found in a preview
    Given an uncommitted new image "docs/guides/flow.png"
    And an uncommitted change that makes the doc "docs/guides/setup.md" link to "flow.png"
    When I build the site with --include-worktree
    Then the working copy version of "guides/setup.md" links to the image
    And it shows no "not found" marker
```

### Warnings for the latest version only

> **Built.**

```gherkin
Feature: Warnings about links for the latest version only
  As a docs author
  I want the build to warn only about links I can still fix
  So that old versions, which never change, do not fill the output with warnings

  Scenario: A link in an old version gives no warning
    Given the text of an old version of a doc links to "../src/pkg/old.py"
    And "src/pkg/old.py" was renamed after that version
    And the latest version of the doc does not link to it
    When I build the site
    Then the build gives no warning for that link
```

## Backlinks of a doc template

A doc template is not a doc, so `backlinks` does not look it up ([commands.md](../behavior/commands.md#backlinks)).

```gherkin
Feature: Backlinks of a path that is not a doc
  As a docs author
  I want backlinks to tell me when a path names no doc
  So that I do not take an empty list for "nothing links to it"

  Scenario: A doc template is not a doc
    Given the doc template "docs/meta/templates/behavior-doc.md"
    When I ask for the backlinks of "docs/meta/templates/behavior-doc.md"
    Then the command says "not a doc: docs/meta/templates/behavior-doc.md"
    And the exit code is 2
```

## See also

- [behavior/commands.md](../behavior/commands.md#build) — the `build` command, its options and its output.
- [architecture/docs-tooling.md](../architecture/docs-tooling.md#history-model) — how the history, the working copy and link markers are built.
