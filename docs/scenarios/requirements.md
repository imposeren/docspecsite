---
title: Docs system requirements — scenarios
summary: Exact cases for the docs check's rules on a doc's title — text before it, a doc without one, a second level-1 heading, docs whose front matter does not load, and the heading a page shows.
layer: scenarios
status: specified
components: [checks]
tags: [checks]
related:
  - behavior/requirements.md
  - behavior/commands.md
  - scenarios/status-notes.md
---

# Docs system requirements — scenarios

These scenarios pin down the rule on a doc's title in [Docs system requirements](../behavior/requirements.md#checks) (DS-52): the title is the doc's first level-1 heading, written as `# Import` or as a line underlined with `===`; it comes right after the front matter, with only blank lines between them; and a doc has exactly one level-1 heading.
The exact problem lines and hints are in [commands.md](../behavior/commands.md#check).
The other requirements are pinned down by [commands.md](../behavior/commands.md) and the tests.

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

## See also

- [behavior/requirements.md](../behavior/requirements.md#checks) — DS-52, the rule on a doc's title.
- [behavior/commands.md](../behavior/commands.md#check) — the problem lines and hints of the check.
- [scenarios/status-notes.md](status-notes.md) — how the title and the sections below it get their status.
