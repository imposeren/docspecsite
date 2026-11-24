---
title: Docs format — scenarios
summary: Exact cases for the docs check's rule on a doc's title (text before it, a doc without one, a second level-1 heading, docs whose front matter does not load) and the heading a page without one shows, and for scenario docs, whose build status, milestone, priority and status notes are ignored and which name the docs they give cases for.
layer: scenarios
components: [checks]
tags: [checks]
related:
  - behavior/docs-format.md
  - behavior/commands.md
  - scenarios/status-notes.md
  - architecture/docs-tooling.md
---

# Docs format — scenarios

These scenarios pin down two rules of [Docs format](../behavior/docs-format.md): where a doc's title is, and what sets a scenario doc apart, since it has no [build status](../meta/glossary.md#build-status).
The exact problem lines and hints are in [commands.md](../behavior/commands.md#check).
The other rules of the docs format are pinned down by [commands.md](../behavior/commands.md) and the tests.

## A doc's title

These cases pin down the rule on a doc's title, [DS-52](../behavior/docs-format.md#requirements): the title is the doc's first level-1 heading, written as `# Import` or as a line underlined with `===`; it comes right after the front matter, with only blank lines between them; and a doc has exactly one level-1 heading.

```gherkin
Feature: Checking a doc's title
  As a docs author
  I want docspecsite to check that each doc starts with its title and has only one
  So that every doc's title is where readers and tools look for it

  Scenario: A title right after the front matter passes
    Given a doc whose front matter is followed by a blank line and the heading "# Import"
    And the doc has no other level-1 heading
    When I run the check
    Then the check reports no problem for the doc

  Scenario: A heading underlined with "===" is a title
    Given a doc whose front matter is followed by the line "Import" underlined with "==="
    And the doc has no other level-1 heading
    When I run the check
    Then the check reports no problem for the doc

  Scenario: Text before the title
    Given a doc "docs/import.md" whose line 9, right after the front matter, is "Some text"
    And its line 11 is the heading "# Import"
    When I run the check
    Then the output for the doc is:
      """
      docs/import.md:9: the doc does not start with its title heading
        hint: move this text below "# Import", or remove it
      """

  Scenario: An HTML comment before the title is text
    Given a doc whose line 9, right after the front matter, is "<!-- generated -->"
    And its line 11 is the heading "# Import"
    When I run the check
    Then the check reports a problem on line 9 saying that the doc does not start with its title heading

  Scenario: A doc without a title
    Given a doc "docs/import.md" with the front matter title "Import"
    And its text after the front matter starts on line 9 with "## Details"
    And the doc has no level-1 heading
    When I run the check
    Then the output for the doc is:
      """
      docs/import.md:9: the doc does not start with its title heading
        hint: add the title "# Import" right after the front matter
      """

  Scenario: A doc without a title or a front matter title
    Given a doc whose front matter has no title
    And the doc has no level-1 heading
    When I run the check
    Then the check reports that the doc does not start with its title heading
    And its hint is to add a "#" title heading right after the front matter

  Scenario: An empty doc has no title
    Given a doc "docs/import.md" with the front matter title "Import" and no text after its front matter
    When I run the check
    Then the check reports a problem on the doc's first line saying that the doc does not start with its title heading
    And its hint is to add the title "# Import" right after the front matter

  Scenario: A second level-1 heading
    Given a doc "docs/import.md" with the title "# Import"
    And its line 20 is the heading "# Export"
    When I run the check
    Then the output for the doc is:
      """
      docs/import.md:20: "# Export" is a second level-1 heading; a doc has one, its title
        hint: write it as "## Export"
      """

  Scenario: A second level-1 heading underlined with "==="
    Given a doc "docs/import.md" with the title "# Import"
    And its line 20 is "Export", underlined with "===" on line 21
    When I run the check
    Then the output for the doc is:
      """
      docs/import.md:20: "Export" is a second level-1 heading; a doc has one, its title
        hint: write it as "## Export"
      """

  Scenario: A "#" heading inside a block quote is not a second one
    Given a doc with the title "# Import"
    And a block quote in its text holds the line "# Example"
    When I run the check
    Then the check reports no problem for the doc

  Scenario: The first level-1 heading is the title even after other text
    Given a doc with status "implemented"
    And its text after the front matter starts with "Some text"
    And its later heading "# Import" is followed by "> **Not built yet.**"
    When I run the check
    Then the check reports that the doc does not start with its title heading
    And it reports that the status note is right under the doc's title

  Scenario: The title is not checked when the front matter does not load
    Given a doc whose front matter is not valid YAML
    And the doc has no level-1 heading
    When I run the check
    Then the check reports the front matter problem
    And it reports no problem about the doc's title

  Scenario: A page without a title shows the front matter title
    Given a doc with the front matter title "Import" and no level-1 heading
    When I build the site
    Then the doc's page shows "Import" as its heading
```

## Docs without a build status

These cases pin down the first part of [DS-53](../behavior/docs-format.md#layers-without-a-build-status): in a scenario doc, docspecsite ignores a build status (`specified`, `changed`, `implemented`), the `milestone` and `priority` fields and status notes, and warns about `implemented`.
How listings and the site show a doc without a status is in [status-notes.md](status-notes.md#listing-partly-built-docs).
Every scenario doc below names a current behavior doc in its `related` front-matter field unless the case says otherwise.

```gherkin
Feature: Ignoring the build status of a scenario doc
  As a docs author
  I want docspecsite to read a scenario doc as if it had no build status, milestone, priority or status notes
  So that whether its cases are built is read only from the doc that owns their rules

  Scenario: An agreed scenario doc without a status passes
    Given a scenario doc without "status", "milestone" or "priority"
    When I run the check
    Then the check reports no problem and no warning for the doc

  Scenario Outline: A scenario doc may be a draft, deprecated or a redirect
    Given a scenario doc with status <status>
    When I run the check
    Then the check reports no problem about the doc's status

    Examples:
      | status       |
      | draft        |
      | [draft]      |
      | deprecated   |
      | redirect     |

  Scenario: An implemented status gives one warning
    Given a scenario doc "docs/scenarios/import.md" with status implemented
    When I run the check
    Then the output for the doc is:
      """
      warning: docs/scenarios/import.md:1: "implemented" in "status" is ignored: the "scenarios" layer has no build status, and the value can mislead a reader once the doc that owns the rules changes and nobody updates it
      """

  Scenario Outline: An implemented status in a list gives one warning
    Given a scenario doc with status <status>
    And one of its sections starts with "> **Changed, not built yet.**"
    When I run the check
    Then the check gives one warning for the doc, about "implemented" in "status"
    And it reports no problem for the doc

    Examples:
      | status                 |
      | [implemented]          |
      | [implemented, changed] |
      | [draft, implemented]   |

  Scenario Outline: Other build statuses are ignored without a warning
    Given a scenario doc with status <status>
    When I run the check
    Then the check reports no problem and no warning for the doc

    Examples:
      | status               |
      | specified            |
      | changed              |
      | [specified, changed] |

  Scenario: What is left of the status is checked as in any doc
    Given a scenario doc with status [draft, specified]
    When I run the check
    Then the check reports no problem and no warning for the doc
    And the doc is listed with the status draft

  Scenario Outline: A status written with no value is still a problem
    Given a scenario doc "docs/scenarios/import.md" whose front matter has the line <line>
    When I run the check
    Then the check reports the same problem about "status" as for a behavior doc with that line

    Examples:
      | line         |
      | "status:"    |
      | "status: []" |

  Scenario: A milestone and a priority in a scenario doc are ignored
    Given a scenario doc with milestone "someday", which the roadmap does not list, and priority "high"
    When I run the check
    Then the check reports no problem and no warning for the doc

  Scenario: Status notes in a scenario doc are ordinary notes
    Given a scenario doc with status draft
    And the first note line right after its title "# Import" is "> **Built.**"
    And its section "## Export" starts with "> **Not built yet.**"
    When I run the check
    Then the check reports no problem and no warning for the doc

  Scenario: The directory decides the layer
    Given a doc in docs/scenarios/ with status implemented whose "layer" field says behavior
    When I run the check
    Then the check reports that its "layer" does not match its directory
    And it gives the warning about "implemented" in "status"

  Scenario: Docs of other layers still need a status
    Given a behavior doc without "status"
    When I run the check
    Then the check reports that the required field "status" is missing
```

```gherkin
Feature: Ignored values in listings and on the site
  As a docs author
  I want listings and the site to show a scenario doc as if it had no build status, milestone or priority
  So that no view suggests that its cases are built or planned on their own

  Background:
    Given a scenario doc "docs/scenarios/import.md" with status implemented, milestone "later" and priority "must"

  Scenario: list reads the doc as one without a status
    When I list the docs with status implemented
    Then the doc is not listed
    When I list the docs in the scenarios layer
    Then the doc is listed with an empty status

  Scenario: list reads the doc as one without a milestone or a priority
    When I list the docs with milestone "later" or with priority "must"
    Then the doc is not listed

  Scenario: The site reads the doc as one without a status
    When the site is built
    Then the status board does not list the doc
    And the doc's page shows no status badge
    And its line in llms.txt has no "status:" part

  Scenario: An older version is read the same way
    Given an older version of the doc had status [implemented, specified]
    When the site is built
    Then the page of that older version shows no status badge
```

## The docs a scenario doc gives cases for

These cases pin down the second part of [DS-53](../behavior/docs-format.md#layers-without-a-build-status): a scenario doc without `status` (an agreed one) or with `status: draft` names in its `related` front-matter field at least one behavior or ui doc that is neither `deprecated` nor `redirect`.

```gherkin
Feature: Checking the docs a scenario doc gives cases for
  As a docs author
  I want docspecsite to report a scenario doc that names no current doc whose rules it gives cases for
  So that every case can be traced to the rule it belongs to

  Scenario Outline: A current behavior or ui doc in related passes
    Given a scenario doc without "status" whose related list is <related>
    And "behavior/import.md" and "ui/import.md" have status implemented
    When I run the check
    Then the check reports no problem for the doc

    Examples:
      | related                                         |
      | [behavior/import.md]                            |
      | [ui/import.md]                                  |
      | [architecture/import.md, behavior/import.md]    |
      | [behavior/import.md#import]                     |

  Scenario: An empty related list
    Given a scenario doc "docs/scenarios/import.md" with status draft and the related list []
    When I run the check
    Then the output for the doc is:
      """
      docs/scenarios/import.md:1: "related" names no behavior or ui doc that is neither deprecated nor redirect
        hint: add to "related" the behavior or ui docs whose rules this doc gives cases for
      """

  Scenario: A related list with docs of other layers only
    Given a scenario doc without "status" whose related list is [architecture/import.md, scenarios/export.md]
    When I run the check
    Then the check reports that "related" names no behavior or ui doc that is neither deprecated nor redirect

  Scenario: A related list with a deprecated behavior doc only
    Given a scenario doc without "status" whose related list is [behavior/import.md]
    And "behavior/import.md" has status deprecated
    When I run the check
    Then the check reports that "related" names no behavior or ui doc that is neither deprecated nor redirect
    And its hint also offers to write "status: deprecated" if they are all deprecated

  Scenario: A related entry that is not a doc does not count
    Given a scenario doc without "status" whose related list is [behavior/gone.md]
    And there is no doc "behavior/gone.md"
    When I run the check
    Then the check reports a broken link to "behavior/gone.md"
    And it reports that "related" names no behavior or ui doc that is neither deprecated nor redirect

  Scenario: A missing related list is a missing field
    Given a scenario doc without "status" and without "related"
    When I run the check
    Then the check reports that the required field "related" is missing
    And no other problem about "related" is reported

  Scenario: A related field that is not a list
    Given a scenario doc without "status" whose related field is the single path "behavior/import.md"
    When I run the check
    Then the check reports that "related" must be a list of strings
    And no other problem about "related" is reported

  Scenario Outline: Docs the rule does not apply to
    Given <doc> whose related list is []
    When I run the check
    Then the check reports no problem about "related"

    Examples:
      | doc                                     |
      | a scenario doc with status deprecated   |
      | a scenario doc with status redirect     |
      | the scenario index "scenarios/index.md" |
      | a behavior doc                          |
```

## See also

- [behavior/docs-format.md](../behavior/docs-format.md#requirements) — DS-52, the rule on a doc's title.
- [behavior/commands.md](../behavior/commands.md#check) — the problem lines and hints of the check.
- [behavior/docs-format.md](../behavior/docs-format.md#layers-without-a-build-status) — DS-53, the docs without a build status.
- [scenarios/status-notes.md](status-notes.md) — how the title and the sections below it get their status, and how a doc without a status is listed and shown.
