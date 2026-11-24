---
title: Commands — scenarios
summary: Exact cases for what the commands share — input that docspecsite cannot use and output into a pipe that closes early — with the cases of the check, the build and `backlinks` in docs of their own.
layer: scenarios
components: [checks, site, code-reference, queries]
tags: [cli]
related:
  - behavior/commands/index.md
  - scenarios/commands/check.md
  - scenarios/commands/build.md
  - scenarios/commands/backlinks.md
---

# Commands — scenarios

These scenarios pin down what the [commands](../../behavior/commands/index.md) share: how the check and the build treat input they cannot use, such as a file name that is not UTF-8, and how `list` and `backlinks` treat output into a pipe that closes early.
The cases of the check, the build and `backlinks` are in the docs below; the rest of the commands is pinned down by [behavior/commands/](../../behavior/commands/index.md) and the tests.

## Input that cannot be used

Input that docspecsite cannot use gives one problem or warning naming the file and the reason, is left out, and the rest goes on ([index.md](../../behavior/commands/index.md#input-that-cannot-be-used)).

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

## Output into a pipe that closes early

When the program that reads the output of `list` or `backlinks` stops reading early, the command stops writing and keeps its exit code ([index.md](../../behavior/commands/index.md#output-into-a-pipe-that-closes-early)).

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

## Children

- [check.md](check.md) — The characters that file names may not contain, the anchors of links to a directory, warnings in the check with `check --strict`, and an unknown component in `code-components` in the check.
- [build.md](build.md) — The revision a build shows by default, source links of a preview and of a symlinked code directory, body links whose target is found or not found, and unknown components in `code-components` in the build.
- [backlinks.md](backlinks.md) — The backlinks of a doc template.

## See also

- [behavior/commands/](../../behavior/commands/index.md) — what the commands share.
