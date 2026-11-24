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

## <Rule these cases pin down>

<One sentence: which rule these cases pin down, linking the section of the behavior or ui doc that owns it, such as [<Capability name>](<relative path to behavior/same/path.md>#<section>).>

```gherkin
Feature: <Rule these cases pin down>
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
