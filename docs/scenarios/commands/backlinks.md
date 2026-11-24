---
title: The backlinks command — scenarios
summary: Exact cases for the backlinks of a path that names a doc template.
layer: scenarios
components: [queries]
tags: [cli]
related:
  - behavior/commands/backlinks.md
  - scenarios/commands/index.md
---

# The backlinks command — scenarios

These scenarios pin down a case of `docspecsite backlinks` in [The backlinks command](../../behavior/commands/backlinks.md#options-and-output): a path that names a doc template, which is not a doc.
Output into a pipe that closes early has its cases with what all commands share ([index.md](index.md#output-into-a-pipe-that-closes-early)).

## Backlinks of a doc template

A doc template is not a doc, so `backlinks` does not look it up ([backlinks.md](../../behavior/commands/backlinks.md#options-and-output)).

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

- [behavior/commands/backlinks.md](../../behavior/commands/backlinks.md) — the `backlinks` command, its options and its output.
