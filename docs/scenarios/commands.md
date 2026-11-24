---
title: Commands — scenarios
summary: Exact cases for the revision a build shows by default, for the source links of changed code in a preview and of a symlinked code directory, for body links whose target is found or not found, for input that docspecsite cannot use, for unknown components in `code-components`, for the backlinks of a doc template, for output into a pipe that closes early, for the characters that file names may not contain, for the anchors of links to a directory, and for warnings in the check and `check --strict`.
layer: scenarios
components: [site, code-reference, checks, queries]
tags: [cli, rendering]
related:
  - behavior/commands.md
  - behavior/configuration.md
  - architecture/docs-tooling.md
---

# Commands — scenarios

These scenarios pin down parts of `docspecsite build` in [Commands](../behavior/commands.md#build), cases of `backlinks` and `list`, and how the check and the build treat input they cannot use.
The first is which [revision](../behavior/glossary.md) a build shows when no `--ref` is given, with or without a preview of the working tree (the files as they are now on disk), built with `--include-worktree`.
The second is which code pages of such a preview link to their source.
The third is which link targets count as found, and how a body link (a link in a doc's text) whose target is not found is shown.
Further cases cover the source links of a path in `code-dirs` that is a symlink, unknown components in the `[code-components]` setting ([configuration.md](../behavior/configuration.md#settings)), and input that docspecsite cannot use, such as a file name that is not UTF-8.
The cases of `backlinks` are a path that names a doc template and, with `list`, output into a pipe that closes early.
Then come the check's rules on which characters file and directory names under `docs/` may not contain, and how it takes a link to a directory ([DSR-20](../behavior/commands.md#checks)).
The last cases are the check's warnings and its `--strict` option.
The rest of the commands is pinned down by [commands.md](../behavior/commands.md) and the tests; the check's rules on a doc's title and on symlinks have scenarios of their own ([docs-format.md](docs-format.md), [doc-symlinks.md](doc-symlinks.md)).

## Building what is checked out

When no `--ref` is given, a build shows the commit that is checked out, and a preview adds only the uncommitted changes as the working copy ([commands.md](../behavior/commands.md#build), the `--ref` and `--include-worktree` options).

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

With both `--ref` and `--include-worktree`, the working copy is everything in which the working tree differs from that ref ([commands.md](../behavior/commands.md#build), the `--ref` option).

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

A code page whose file is new or changed in the working tree has no source links in a preview, and the pages of unchanged files keep theirs ([commands.md](../behavior/commands.md#build), the `--include-worktree` option).

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

In a preview, a file under `docs/` that is not a Markdown file counts as found also when it is not committed yet ([commands.md](../behavior/commands.md#build), which targets are found).

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

The warning about a link whose target is not found is given only for the latest version of the linking doc ([commands.md](../behavior/commands.md#build)).

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

When a code directory is a symlink to a directory inside the repo, the code's files are in the repo at the path of that directory, so the source links use that path ([commands.md](../behavior/commands.md#build)).

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

Every component that the `[code-components]` setting gives must be in the repo's component list: `check` reports an unknown one ([configuration.md](../behavior/configuration.md#settings)), and `build` warns and leaves it out ([commands.md](../behavior/commands.md#build)).

```gherkin
Feature: Unknown components in code-components
  As a docs author
  I want a mistyped component in docspecsite.toml reported
  So that code pages never carry a component that has no page

  Background:
    Given a project whose "[code-components]" gives "example.api" the components "backend" and "backned"
    And "backend" is in the component list and "backned" is not

  Scenario: The check reports the unknown component
    When I run the check
    Then the output includes:
      """
      docspecsite.toml: "code-components" of "example.api" has an unknown component: "backned" (add it to architecture/components.md)
      """

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

## Input that cannot be used

Input that docspecsite cannot use gives one problem or warning naming the file and the reason, is left out, and the rest goes on ([commands.md](../behavior/commands.md#input-that-cannot-be-used)).

```gherkin
Feature: Input that cannot be used
  As a docs author
  I want input that docspecsite cannot use reported and left out
  So that one odd file never ends a command with an error trace or keeps the rest from being checked or built

  Background:
    Given a project with "code-dirs" set to "src" and the package "src/pkg"

  Scenario Outline: <case>
    Given <input>
    When I <action>
    Then <result>
    And no error trace is shown

    Examples:
      | case                                | input                                                                                          | action                            | result                                                                                                                                                                      |
      | A package name, in the check        | the package directory "src/a.b"                                                                | run the check with the code check | the output includes `src/a.b: directory name "a.b" is not a valid Python package name`, and the docstrings of "pkg" are still checked                                        |
      | A package name, in the build        | the package directory "src/a.b"                                                                | build the site                    | the build warns `warning: src/a.b: directory name "a.b" is not a valid Python package name; left out`, and "pkg" still gets its pages                                       |
      | An empty code: target, in the check | the link "[see](code:)" on line 3 of a docstring in "src/pkg/api.py"                           | run the check with the code check | the output includes `src/pkg/api.py:3: empty code: target`                                                                                                                  |
      | An empty code: target, in the build | the link "[see](code:)" on line 3 of a docstring in "src/pkg/api.py"                           | build the site                    | the build warns `warning: src/pkg/api.py:3: empty code: target; left out`, and the code page of "pkg.api" shows "see" as text, with no link and no marker                    |
      | A file name, in the check           | a file "docs/guides/caf\xe9.png", whose name has the byte "e9" in place of "é"                 | run the check                     | the output includes `docs/guides/caf\xe9.png: name is not valid UTF-8, which breaks links to the rendered page`                                                             |
      | A file name, in the build           | a committed file "docs/guides/caf\xe9.png", whose name has the byte "e9" in place of "é"       | build the site                    | the build warns `warning: docs/guides/caf\xe9.png: name is not valid UTF-8, which breaks links to the rendered page; left out`, and the site has no copy of the file        |
      | A doc name, in the build            | a committed doc "docs/guides/caf\xe9.md", whose name has the byte "e9" in place of "é"         | build the site                    | the build warns `warning: docs/guides/caf\xe9.md: name is not valid UTF-8, which breaks links to the rendered page; left out`, and the doc has no pages                     |
      | A doc name, in the listing          | a doc "docs/guides/caf\xe9.md", whose name has the byte "e9" in place of "é"                   | list the docs                     | the listing has a line for `guides/caf\xe9.md`                                                                                                                              |
      | A commit subject                    | a commit to "docs/guides/setup.md" whose subject is "caf" followed by the byte "e9"            | build the site                    | the version picker of "guides/setup.md" shows that commit's subject as "caf�", with no warning                                                                              |
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

## Output into a pipe that closes early

When the program that reads the output of `list` or `backlinks` stops reading early, the command stops writing and keeps its exit code ([commands.md](../behavior/commands.md#list)).

```gherkin
Feature: Output into a pipe that closes early
  As a docs author
  I want to read only the first lines of a listing
  So that cutting the output short gives no error

  Background:
    Given a project with more docs than fit in the pipe's buffer

  Scenario: list into a pipe that reads one line
    When I run "docspecsite list | head -1"
    Then I see the first line of the listing
    And no error trace
    And list exits with exit code 0

  Scenario: backlinks into a pipe that reads one line
    Given more docs link to "docs/guides/setup.md" than their lines fit in the pipe's buffer
    When I run "docspecsite backlinks docs/guides/setup.md | head -1"
    Then I see the first linking doc
    And no error trace
    And backlinks exits with exit code 0
```

## File and directory names

The check reports a name under `docs/` that contains `#`, `%` or `?`, since these characters have a meaning in web addresses and break links to the rendered page ([DSR-20](../behavior/commands.md#checks)).

```gherkin
Feature: Checking file and directory names
  As a docs author
  I want docspecsite to report names that cannot be linked to
  So that every doc can be reached from other docs and on the site

  Scenario Outline: A name with a character that breaks links
    Given a doc "docs/guides/<name>" listed in "docs/guides/index.md"
    When I run the check
    Then the output includes:
      """
      docs/guides/<name>: name contains "#", "%" or "?", which break links to the rendered page
      """

    Examples:
      | name     |
      | c#.md    |
      | 50%.md   |
      | faq?.md  |

  Scenario: A directory name with a question mark
    Given a directory "docs/what?" with an index.md
    When I run the check
    Then the check reports a problem on "docs/what?" saying that its name contains "#", "%" or "?"
```

## Links to a directory

A link to a directory leads to that directory's `index.md` on the site, so the check looks for the link's anchor in that `index.md` ([commands.md](../behavior/commands.md#check)).

```gherkin
Feature: Checking links to a directory
  As a docs author
  I want the check to find a missing heading in a link to a directory
  So that such a link never leads to a place on the page that is not there

  Background:
    Given a directory "docs/guides" whose "index.md" has the heading "## Setup"

  Scenario Outline: A link to a heading of the directory's index passes
    Given the doc "docs/import.md" links to "<link>"
    When I run the check
    Then the check reports no problem for that link

    Examples:
      | link           |
      | guides/#setup  |
      | guides#setup   |

  Scenario Outline: A link to a heading the directory's index does not have
    Given the doc "docs/import.md" links to "<link>" on line 7
    When I run the check
    Then the output includes:
      """
      docs/import.md:7: no heading "#install" in docs/guides/index.md
      """

    Examples:
      | link             |
      | guides/#install  |
      | guides#install   |
```

## Warnings in the check

The check prints its warnings after the problems and still exits with 0 when there is no problem; `--strict` makes warnings count as problems ([check](../behavior/commands.md#check)).
The warning in these cases is the one for `implemented` in a scenario doc's `status` ([DSR-53](../behavior/docs-format.md#layers-without-a-build-status)).

```gherkin
Feature: Warnings in the check
  As a docs author
  I want the check to show warnings without failing, unless I ask it to
  So that a commit hook passes on them while CI can stop on them

  Scenario: A warning alone does not fail the check
    Given a scenario doc "docs/scenarios/import.md" with status implemented
    And no doc has a problem
    When I run the check
    Then the output is the warning line for "docs/scenarios/import.md", starting with "warning: "
    And the exit code is 0

  Scenario: Warnings come after the problems
    Given a scenario doc "docs/scenarios/import.md" with status implemented
    And the doc "docs/guides/setup.md" has a broken link
    When I run the check
    Then the problem line for "docs/guides/setup.md" comes first, and the warning line after it
    And the exit code is 1

  Scenario: --strict makes a warning fail the check
    Given a scenario doc "docs/scenarios/import.md" with status implemented
    And no doc has a problem
    When I run the check with --strict
    Then the output is the warning line for "docs/scenarios/import.md", starting with "warning: "
    And the exit code is 1

  Scenario: --strict passes without warnings or problems
    Given no doc has a problem or a warning
    When I run the check with --strict
    Then nothing is reported
    And the exit code is 0
```

## See also

- [behavior/commands.md](../behavior/commands.md#build) — the `build` command, its options and its output.
- [architecture/docs-tooling.md](../architecture/docs-tooling.md#history-model) — how the history, the working copy and link markers are built.
