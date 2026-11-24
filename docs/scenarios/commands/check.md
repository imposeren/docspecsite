---
title: The check command — scenarios
summary: Exact cases for the characters that file and directory names may not contain, the anchors of links to a directory, warnings in the check and `check --strict`, an unknown component in `code-components`, and docs whose page would take the address of a page either renderer generates.
layer: scenarios
components: [checks, code-reference]
tags: [cli]
related:
  - behavior/commands/check.md
  - behavior/configuration.md
  - behavior/docs-format.md
  - behavior/site.md
  - scenarios/commands/build.md
---

# The check command — scenarios

These scenarios pin down parts of `docspecsite check` in [The check command](../../behavior/commands/check.md#what-the-check-reports).
The first are the check's rules on which characters file and directory names under `docs/` may not contain, and how it takes a link to a directory ([DSR-20](../../behavior/commands/check.md#requirements)).
Then come the check's warnings and its `--strict` option, an unknown component in the `[code-components]` setting ([configuration.md](../../behavior/configuration.md#settings)), and docs whose page would take the address of a generated page.
The check's rules on a doc's title and on symlinks have scenarios of their own ([docs-format.md](../docs-format.md), [doc-symlinks.md](../doc-symlinks.md)).

## File and directory names

The check reports a name under `docs/` that contains `#`, `%` or `?`, since these characters have a meaning in web addresses and break links to the rendered page ([DSR-20](../../behavior/commands/check.md#requirements)).

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

A link to a directory leads to that directory's `index.md` on the site, so the check looks for the link's anchor in that `index.md` ([check.md](../../behavior/commands/check.md#what-the-check-reports)).

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

The check prints its warnings after the problems and still exits with 0 when there is no problem; `--strict` makes warnings count as problems ([check](../../behavior/commands/check.md#what-the-check-reports)).
The warning in these cases is the one for `implemented` in a scenario doc's `status` ([DSR-53](../../behavior/docs-format.md#layers-without-a-build-status)).

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

## Unknown components in code-components

Every component that the `[code-components]` setting gives must be in the repo's component list: `check` reports an unknown one ([configuration.md](../../behavior/configuration.md#settings)).

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
```

## Docs at the address of a generated page

A doc whose page would take the address of a page that either [renderer](../../behavior/site.md#renderers) generates is a problem, whatever the `renderer` setting ([check.md](../../behavior/commands/check.md#what-the-check-reports)).

```gherkin
Feature: Docs at the address of a generated page
  As a docs author
  I want the check to report a doc whose page would clash with a generated page of either renderer
  So that changing the renderer never breaks my site

  Scenario Outline: A doc at an address the standard renderer generates
    Given a project whose "[site]" section sets "renderer" to "<renderer>"
    And a doc "<doc>"
    When I run the check
    Then it reports that the page of "<doc>" would take the address of <page>

    Examples:
      | renderer | doc                    | page                       |
      | sphinx   | docs/search.md         | the search page            |
      | internal | docs/search.md         | the search page            |
      | internal | docs/genindex.md       | the general index          |
      | internal | docs/_static/notes.md  | the site's static files    |

  Scenario: A doc at the address of the status board, with the standard renderer
    Given a project whose "[site]" section sets "renderer" to "sphinx"
    And a doc "docs/status.md"
    When I run the check
    Then it reports that the page of "docs/status.md" would take the address of the status page

  Scenario: A doc at a code page address of the standard renderer
    Given a doc "docs/reference/code/pkg/api/index.md"
    When I run the check
    Then it reports that the page of "docs/reference/code/pkg/api/index.md" would take the address of the code reference pages
```

## See also

- [behavior/commands/check.md](../../behavior/commands/check.md#what-the-check-reports) — the `check` command, its options and its output.
