---
title: The build command — scenarios
summary: Exact cases for the revision a build shows by default, for the source links of changed code in a preview and of a symlinked code directory, for body links whose target is found or not found, for unknown components in `code-components` in the build, and for choosing the renderer that draws the site.
layer: scenarios
components: [site, code-reference]
tags: [cli, rendering]
related:
  - behavior/commands/build.md
  - behavior/configuration.md
  - behavior/site.md
  - architecture/docs-tooling.md
  - architecture/site.md
  - scenarios/commands/check.md
---

# The build command — scenarios

These scenarios pin down parts of `docspecsite build` in [The build command](../../behavior/commands/build.md#what-the-build-does).
The first is which [revision](../../behavior/glossary.md) a build shows when no `--ref` is given, with or without a preview of the working tree (the files as they are now on disk), built with `--include-worktree`.
The second is which code pages of such a preview link to their source.
The third is which link targets count as found, and how a body link (a link in a doc's text) whose target is not found is shown.
Further cases cover the source links of a path in `code-dirs` that is a symlink, unknown components in the `[code-components]` setting ([configuration.md](../../behavior/configuration.md#settings)), and which [renderer](../../behavior/site.md#renderers) draws the site.

## Building what is checked out

When no `--ref` is given, a build shows the commit that is checked out, and a preview adds only the uncommitted changes as the working copy ([build.md](../../behavior/commands/build.md#what-the-build-does), the `--ref` and `--include-worktree` options).

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

With both `--ref` and `--include-worktree`, the working copy is everything in which the working tree differs from that ref ([build.md](../../behavior/commands/build.md#what-the-build-does), the `--ref` option).

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

A code page whose file is new or changed in the working tree has no source links in a preview, and the pages of unchanged files keep theirs ([build.md](../../behavior/commands/build.md#what-the-build-does), the `--include-worktree` option).

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
[build.md](../../behavior/commands/build.md#what-the-build-does) says which targets are found.
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

In a preview, a file under `docs/` that is not a Markdown file counts as found also when it is not committed yet ([build.md](../../behavior/commands/build.md#what-the-build-does), which targets are found).

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

The warning about a link whose target is not found is given only for the latest version of the linking doc ([build.md](../../behavior/commands/build.md#what-the-build-does)).

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

## Source links of a symlinked code directory

When a code directory is a symlink to a directory inside the repo, the code's files are in the repo at the path of that directory, so the source links use that path ([build.md](../../behavior/commands/build.md#what-the-build-does)).

```gherkin
Feature: Source links of a symlinked code directory
  As a reader
  I want each source link of the code reference to open the file that holds the code
  So that a symlinked code directory does not lead me to a path the repo host does not show

  Scenario: Source links use the path the symlink leads to
    Given a project with "source-url" set and "code-dirs" set to "src"
    And "src" is a symlink to the directory "lib/python" in the repo
    And "lib/python/pkg/__init__.py" holds the package "pkg"
    And the site is built
    When I open the code page of "pkg"
    Then it links each element to its source in "lib/python/pkg/__init__.py" at the built revision
```

## Unknown components in code-components

Every component that the `[code-components]` setting gives must be in the repo's component list: `build` warns about an unknown one and leaves it out ([build.md](../../behavior/commands/build.md#what-the-build-does)).

```gherkin
Feature: Unknown components in code-components
  As a docs author
  I want a mistyped component in docspecsite.toml reported
  So that code pages never carry a component that has no page

  Background:
    Given a project whose "[code-components]" gives "example.api" the components "backend" and "backned"
    And "backend" is in the component list and "backned" is not

  Scenario: The build warns and leaves the unknown component out
    When I build the site
    Then the build warns:
      """
      warning: docspecsite.toml: "code-components" of "example.api" has an unknown component: "backned"; ignored
      """
    And the code pages of "example.api" show the component "backend" only

  Scenario: A docs-only build says nothing about it
    When I build only the docs part of the site
    Then the build gives no warning about "backned"
```

## Choosing the renderer

The `renderer` setting in the `[site]` section chooses the renderer that draws the site, and `--renderer` overrides it for one build: the option wins, then the setting, then the standard renderer, `sphinx` ([build.md](../../behavior/commands/build.md#what-the-build-does), the `--renderer` option; the setting: [configuration.md](../../behavior/configuration.md#site)).

```gherkin
Feature: Choosing the renderer
  As a docs author
  I want to choose which renderer draws my project's site, for the project and for one build
  So that I can keep the older renderer until the new site suits me, and compare both sites of the same docs

  Scenario: Without a setting or an option, the standard renderer draws the site
    Given a project whose "docspecsite.toml" has no "[site]" section
    When I build the site
    Then the site is drawn by the "sphinx" renderer
    And the site has a search page

  Scenario: The setting chooses the renderer
    Given a project whose "[site]" section sets "renderer" to "internal"
    When I build the site
    Then the site is drawn by the "internal" renderer
    And the site has no search page

  Scenario: The option wins over the setting
    Given a project whose "[site]" section sets "renderer" to "internal"
    When I build the site with --renderer sphinx
    Then the site is drawn by the "sphinx" renderer

  Scenario: Both sites of the same revision side by side
    When I build the site with --renderer internal into "site-internal"
    And I build the same revision with --renderer sphinx into "site-sphinx"
    Then both directories hold a page for every version of every doc
    And each holds only the files of its own build

  Scenario: An unknown renderer in the option is a command-line error
    When I build the site with --renderer mkdocs
    Then the build does not start
    And the exit code is 2

  Scenario: An unknown renderer in the setting stops the build
    Given a project whose "[site]" section sets "renderer" to "mkdocs"
    When I build the site
    Then the build stops with an error about the "renderer" setting
    And the exit code is 1

  Scenario: The check reports an unknown renderer in the setting
    Given a project whose "[site]" section sets "renderer" to "mkdocs"
    When I run the check
    Then it reports a problem on "docspecsite.toml" about the "renderer" setting
```

### Rebuilding with the standard renderer

The standard renderer draws the whole site on every build, and the count of pages taken from the cache is 0 ([DSR-24](../../behavior/site.md#building), [build.md](../../behavior/commands/build.md#what-the-build-does)).

```gherkin
Feature: Rebuilding with the standard renderer
  As a docs author
  I want every build to draw the whole site afresh
  So that no page is stale after a change to a doc it links to

  Scenario: A rebuild without changes draws every page again
    Given the site was built with the "sphinx" renderer
    When I build the site again without changing anything
    Then the last line counts every page as rendered afresh and 0 taken from the cache

  Scenario: A changed heading reaches the pages that link to it
    Given the site was built with the "sphinx" renderer
    And the doc "docs/guides/usage.md" links to the heading "Install" of "docs/guides/setup.md"
    When the heading "Install" is removed from "docs/guides/setup.md"
    And I build the site again
    Then the build warns about the link to the heading in "guides/usage.md"
```

### A failure inside the standard renderer

A failure inside the documentation tool that concerns no single page stops the whole build, and the output directory is left as it was ([build.md](../../behavior/commands/build.md#what-the-build-does)).

```gherkin
Feature: A failure inside the standard renderer
  As a docs author
  I want a failed build to leave my last good site in place
  So that a broken build never leaves half a site behind

  Scenario: The build stops and keeps the earlier site
    Given the site was built into "site"
    And the documentation tool fails while drawing the next build
    When I build the site into "site" with the "sphinx" renderer
    Then the build prints one error line
    And the exit code is 1
    And "site" holds the files of the earlier build
```

## See also

- [behavior/commands/build.md](../../behavior/commands/build.md#what-the-build-does) — the `build` command, its options and its output.
- [architecture/docs-tooling.md](../../architecture/docs-tooling.md#history-model) — how the history, the working copy and link markers are built.
