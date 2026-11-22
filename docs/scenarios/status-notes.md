---
title: Partly built docs — scenarios
summary: Exact cases for partly built docs — a status list with status notes that the check accepts or reports with hints, `list` filtering and output, and the statuses shown on the site.
layer: scenarios
status: implemented
milestone: later
priority: should
components: [checks, queries, site]
tags: [status, checks]
related:
  - scenarios/requirements.md
  - behavior/status-notes.md
  - architecture/docs-tooling.md
---

# Partly built docs — scenarios

These scenarios pin down [Partly built docs](../behavior/status-notes.md): a doc whose [status](../meta/glossary.md#status) is a list, such as `[implemented, specified]`, with a [status note](../meta/glossary.md#status-note) (a [section note](../meta/glossary.md#section-note) such as `> **Not built yet.**` right after a heading) on each section that differs from the first status.
Each heading below the title starts a section of its own, so a status note does not cover its subsections, the sections under the deeper headings below it.

```gherkin
Feature: Checking partly built docs
  As a docs author
  I want docspecsite to check that a doc's statuses and its status notes agree
  So that the docs say honestly which parts are built

  Scenario: A status list with a matching status note passes
    Given a doc with status [implemented, specified]
    And its section "## Import" starts with "> **Not built yet.**"
    When I run the check
    Then the check reports no problem for the doc

  Scenario: A list with one value means that value
    Given a doc with status [specified] and no status notes
    When I run the check
    Then the check reports no problem for the doc

  Scenario: A changed doc on its own passes
    Given a doc with status changed and no status notes
    When I run the check
    Then the check reports no problem for the doc

  Scenario: A status note may be followed by more text
    Given a doc with status [implemented, changed]
    And its section "## File name" starts with "> **Changed, not built yet.** Exports still use the old file name."
    When I run the check
    Then the check reports no problem for the doc

  Scenario: A listed status without a status note
    Given a doc "docs/import.md" with status [implemented, specified, changed]
    And one of its sections starts with "> **Not built yet.**"
    And none of its sections starts with "> **Changed, not built yet.**"
    When I run the check
    Then the output for the doc is:
      """
      docs/import.md:1: "changed" is in "status", but no section has a "Changed, not built yet." status note
        hint: add a "> **Changed, not built yet.**" status note to a section, or remove "changed" from "status" so it reads "status: [implemented, specified]"
      """

  Scenario: A status note whose status is not listed
    Given a doc with status [implemented, specified]
    And one of its sections starts with "> **Not built yet.**"
    And its section "## Export" starts with "> **Changed, not built yet.**"
    When I run the check
    Then the check reports a problem on that status note's line saying that "changed" is not in the doc's status
    And its hint is to add "changed" to "status" so it reads "status: [implemented, specified, changed]", or to remove the status note from the section "## Export"

  Scenario: A status note that repeats the status its section already has
    Given a doc with status [specified, implemented]
    And its section "## Import" starts with "> **Built.**"
    And its section "## Export" has no status note
    And the subsection "### Backend checks" of "## Export" starts with "> **Not built yet.**"
    When I run the check
    Then the check reports a problem on the "Not built yet." status note's line saying that the section "### Backend checks" is already specified
    And its hint is to remove the "Not built yet." status note from the section "### Backend checks"

  Scenario: A status note in a doc with a single status
    Given a doc "docs/import.md" with status implemented
    And its section "## Import" starts, on line 12, with "> **Not built yet.**"
    When I run the check
    Then the output for the doc is:
      """
      docs/import.md:12: status note "Not built yet." ("specified") in a doc with the single status "implemented"
        hint: add "specified" to "status" so it reads "status: [implemented, specified]", or remove the status note from the section "## Import"
      """

  Scenario: A subsection has its own status
    Given a doc with status [implemented, specified]
    And its section "## Import" has no status note
    And the subsection "### Backend checks" of "## Import" starts with "> **Not built yet.**"
    When I run the check
    Then the check reports no problem for the doc

  Scenario: A status note that repeats a single status
    Given a doc with the single status specified
    And its section "## Import" starts with "> **Not built yet.**"
    When I run the check
    Then the check reports a problem on that status note's line saying that the doc has the single status "specified"
    And its hint is only to remove the status note from the section "## Import"

  Scenario: Hints can be left out
    Given a doc "docs/import.md" with status implemented
    And its section "## Import" starts, on line 12, with "> **Not built yet.**"
    When I run the check without hints
    Then the output for the doc is:
      """
      docs/import.md:12: status note "Not built yet." ("specified") in a doc with the single status "implemented"
      """

  Scenario: A status note right under the title
    Given a doc with status implemented
    And the first note line right after its title "# Import" is "> **Not built yet.**"
    When I run the check
    Then the check reports one problem, on that status note's line, saying that the status note is right under the doc's title
    And its hint is to set the doc's "status" instead

  Scenario: A status listed twice
    Given a doc with status [implemented, specified, specified]
    And one of its sections starts with "> **Not built yet.**"
    When I run the check
    Then the check reports a problem on the doc's first line saying that "specified" is listed twice
    And its hint is to remove the duplicate "specified" from "status" so it reads "status: [implemented, specified]"

  Scenario: A section's status note does not cover its subsections
    Given a doc "docs/import.md" with status [specified, implemented]
    And its section "## Import" starts with "> **Built.**"
    And the subsection "### Backend checks" of "## Import" starts, on line 14, with "> **Not built yet.**"
    When I run the check
    Then the output for the doc is:
      """
      docs/import.md:14: status note "Not built yet." ("specified") gives the status the section "### Backend checks" already has from "status: [specified, implemented]"
        hint: remove the "Not built yet." status note from the section "### Backend checks"
      """

  Scenario: A later # heading is a section
    Given a doc with status [implemented, specified] and the title "# Import"
    And its later heading "# Export" starts with "> **Not built yet.**"
    When I run the check
    Then the check reports no problem about the doc's statuses or status notes

  Scenario: A status that cannot be part of a list
    Given a doc with status [draft, specified]
    When I run the check
    Then the check reports a problem on the doc's first line saying that "draft" is combined with other statuses in "status"
    And its hint is to write "status: draft", or remove "draft" from "status" so it reads "status: specified"

  Scenario: A status of the wrong shape
    Given a doc whose status is 5, [] or [implemented, done]
    When I run the check
    Then the check reports one problem on line 1 saying that "status" must be one of the statuses, or a list of distinct values from implemented, specified and changed
    And the problem has no hint
    And no problem is reported for the doc's status notes

  Scenario: Status note text in a code block is not a status note
    Given a doc with status implemented
    And one of its sections starts with a code block whose first line is "> **Not built yet.**"
    When I run the check
    Then the check reports no problem for the doc

  Scenario: Status note text further down a section is an ordinary note
    Given a doc with status implemented
    And a note line "> **Not built yet.**" in the middle of one of its sections
    When I run the check
    Then the check reports no problem for the doc

  Scenario: A status note after another section note counts
    Given a doc with status [implemented, specified]
    And its section "## Import" starts with the note line "> **Experimental.** The format may change."
    And the next note line, with nothing in between, is "> **Not built yet.**"
    When I run the check
    Then the check reports no problem for the doc

  Scenario: A note after other content is not a status note
    Given a doc with status [implemented, specified]
    And its section "## Import" starts with a paragraph
    And the paragraph is followed by the note line "> **Not built yet.**"
    And no other section has a status note
    When I run the check
    Then the check reports a problem on the doc's first line saying that no section has a "specified" status note
    And its hint is to add a "> **Not built yet.**" status note to a section, or remove "specified" from "status" so it reads "status: implemented"

  Scenario: Two status notes in one section
    Given a doc with status [implemented, specified, changed]
    And its section "## Import" starts with the note lines "> **Not built yet.**" and "> **Changed, not built yet.**"
    When I run the check
    Then the check reports a problem on the "Changed, not built yet." status note's line saying that the section "## Import" already has a status note
    And its hint is to keep one status note in the section "## Import"
    And no problem says that no section has a "Changed, not built yet." status note

  Scenario: A note with an unknown label is ordinary text
    Given a doc with status implemented
    And one of its sections starts with the note line "> **Deprecated soon.** Use the new import."
    When I run the check
    Then the check reports no problem for the doc

  Scenario: A project's own status note text counts, and the default no longer does
    Given the settings file docspecsite.toml sets the status note text for "specified" to "Ще не зроблено."
    And a doc with status [implemented, specified] has a section whose first note is "> **Ще не зроблено.**"
    And another section of it has the note "> **Not built yet.**"
    When I run the check
    Then no problem is reported
    And the second section's note is ordinary text

Feature: Listing partly built docs
  As a docs author
  I want to find a partly built doc under each of its statuses
  So that a listing of what is left to do includes it

  Scenario: Filtering by a status the list has
    Given a doc with status [implemented, specified]
    When I list the docs with status specified
    Then the doc is listed
    When I list the docs with status implemented
    Then the doc is listed too

  Scenario: A list with one value is listed as that value
    Given a doc with status [specified]
    When I list the docs as JSON
    Then the doc's status is the string "specified"

  Scenario: Text output shows every status
    Given a doc with status [implemented, specified]
    When I list the docs
    Then the doc's line shows the status "implemented,specified"

  Scenario: JSON output keeps the shape of the status
    Given a doc with status [implemented, specified]
    And another doc with status implemented
    When I list the docs as JSON
    Then the first doc's status is the list ["implemented", "specified"]
    And the other doc's status is the string "implemented"

Feature: Partly built docs on the site
  As a reader
  I want to see every status of a partly built doc
  So that I know which parts are built

  Scenario: The status board lists the doc under each status
    Given a doc with status [implemented, changed], milestone later and priority should
    When the site is built
    Then the status board lists the doc under implemented and under changed, each time in the later milestone's should group

  Scenario: The page shows every status
    Given a doc with status [implemented, changed]
    When I open the doc's page
    Then it shows the status badges implemented and changed, in that order
    And its section with a status note shows that note as an ordinary note
```
