---
title: <Capability name> — scenarios
summary: <One sentence: which situations these scenarios cover.>
layer: scenarios
status: draft
components: [<component>]
tags: []
related:
  - behavior/<same/path>.md
  - architecture/<same/path>.md
---

# <Capability name> — scenarios

<One paragraph: what is covered here and what is deliberately not.>

```gherkin
Feature: <Capability name>
  As a <role>
  I want <goal>
  So that <benefit>

  Background:
    Given <shared precondition>

  Scenario: <one specific behavior>
    Given <context>
    When <action>
    Then <observable outcome>

  Scenario Outline: <behavior with variations>
    Given <context with "<param>">
    When <action>
    Then <outcome with "<result>">

    Examples:
      | param | result |
      | ...   | ...    |
```

## See also

- [Behavior](<relative path>) — the plain-language description.
