---
title: Docs system requirements — scenarios
summary: Exact cases for the docs check's rules on a doc's title (text before it, a doc without one, a second level-1 heading, docs whose front matter does not load, and the heading a page shows), on characters that file names may not contain, and on the anchors of links to a directory.
layer: scenarios
status: [implemented, changed, specified]
components: [checks]
tags: [checks]
related:
  - behavior/requirements.md
  - behavior/commands.md
  - scenarios/status-notes.md
---

# Docs system requirements — scenarios

These scenarios pin down the rule on a doc's title in [Docs system requirements](../behavior/requirements.md#checks) (DS-52): the title is the doc's first level-1 heading, written as `# Import` or as a line underlined with `===`; it comes right after the front matter, with only blank lines between them; and a doc has exactly one level-1 heading.
They also pin down which characters file and directory names under `docs/` may not contain, and how the check takes a link to a directory ([DS-20](../behavior/requirements.md#checks)).
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

## File and directory names

> **Changed, not built yet.** Names with `#` and `%` are reported, with the message `name contains "#" or "%", which break links to the rendered page`; names with `?` are not reported.

The check reports a name under `docs/` that contains `#`, `%` or `?`, since these characters have a meaning in web addresses and break links to the rendered page ([DS-20](../behavior/requirements.md#checks)).

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

> **Not built yet.**

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

## See also

- [behavior/requirements.md](../behavior/requirements.md#checks) — DS-52, the rule on a doc's title, and DS-20, the rules on names and links.
- [behavior/commands.md](../behavior/commands.md#check) — the problem lines and hints of the check.
- [scenarios/status-notes.md](status-notes.md) — how the title and the sections below it get their status.
