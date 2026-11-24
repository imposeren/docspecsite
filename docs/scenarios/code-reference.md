---
title: Code reference — scenarios
summary: Exact cases for how a Sphinx role in a docstring finds its target — from the docstring's class and module, by the end of a dotted path, with several matches, another package's name and a target that is not found — on the site and in the code check alike.
layer: scenarios
components: [code-reference]
tags: [rendering, checks]
related:
  - behavior/code-reference.md
  - behavior/commands/check.md
  - architecture/docs-tooling.md
  - architecture/site.md
---

# Code reference — scenarios

These cases cover how a role in a docstring, such as `` :class:`.SiteBuilder` ``, finds the code element it leads to.
The site, with either renderer, and the code check (`check --optional-checks code`) find targets by the same rules, so each case holds for both, except which of several matching elements a role leads to; how a role reads and the "no longer exists" marker are not covered here.

## Finding the target of a role

A role's target is looked up from the docstring's place, and a target with a leading `.` falls back to any element whose dotted path ends with it; a target that is not found is another package's name, shown as plain text, or gets the "no longer exists" marker ([DSR-34](../behavior/code-reference.md#requirements)).
The examples use a package `example` with the modules `example.build`, defining the class `SiteBuilder` with the method `attempt`, and `example.ui`, which imports `SiteBuilder` from `example.build`.

```gherkin
Feature: Finding the target of a role
  As a docs author
  I want a role in a docstring to find its target as Sphinx finds it
  So that the site and the code check agree with the documentation tool I know

  Scenario: A target without a leading dot is looked up in the docstring's class
    Given a docstring of "example.build.SiteBuilder" holds the role ":meth:`attempt`"
    When I build the site
    Then the role leads to "example.build.SiteBuilder.attempt"

  Scenario: A target with a leading dot is found by the end of its dotted path
    Given a docstring in "example.ui" holds the role ":class:`.SiteBuilder`"
    When I build the site
    Then the role leads to "example.build.SiteBuilder"
    And the build gives no warning about it

  Scenario: A target without a leading dot is not found by the end of its dotted path
    Given a docstring in "example.ui" holds the role ":class:`SiteBuilder`"
    When I build the site
    Then the role shows the "no longer exists" marker
    And the build warns about it

  Scenario: The end of a dotted path counts only for the kind the role names
    Given a docstring in "example.ui" holds the role ":func:`.SiteBuilder`"
    When I build the site
    Then the role shows the "no longer exists" marker

  Scenario: Several elements whose dotted path ends with the target
    Given the module "example.widgets" also defines a class "SiteBuilder"
    And a docstring in "example.ui" holds the role ":class:`.SiteBuilder`"
    When I build the site
    Then the role leads to one of the two classes
    And the build warns that more than one element matches ".SiteBuilder"

  Scenario: A longer target picks one of several elements
    Given the module "example.widgets" also defines a class "SiteBuilder"
    And a docstring in "example.ui" holds the role ":class:`.build.SiteBuilder`"
    When I build the site
    Then the role leads to "example.build.SiteBuilder"
    And the build gives no warning about it

  Scenario: Another package's name stays plain text
    Given a docstring in "example.ui" holds the role ":class:`pathlib.Path`"
    When I build the site
    Then the role shows "pathlib.Path" as plain text without a marker
    And the build gives no warning about it

  Scenario: A bare name that is not found shows the marker
    Given a docstring in "example.ui" holds the role ":exc:`ValueError`"
    When I build the site
    Then the role shows the "no longer exists" marker
    And the build warns about it

  Scenario: A private member of the project's own code shows the marker
    Given the class "example.build.SiteBuilder" has the private method "_flush"
    And a docstring in "example.ui" holds the role ":meth:`example.build.SiteBuilder._flush`"
    When I build the site
    Then the role shows the "no longer exists" marker
    And the build warns about it
```

## The code check finds targets as the site does

The code check follows the same rules, passes over another package's name, and warns about a role whose target matches several elements ([check.md](../behavior/commands/check.md#what-the-check-reports)).

```gherkin
Feature: The code check finds targets as the site does
  As a docs author
  I want the code check to find the target of a role as the site does
  So that a role the check passes never shows a marker on the site

  Scenario: A target found by the end of its dotted path passes the code check
    Given a docstring in "example.ui" holds the role ":class:`.SiteBuilder`"
    When I run the check with the code check
    Then no problem is reported for the role

  Scenario: A target not found by the site is a problem in the code check
    Given a docstring in "example.ui" holds the role ":class:`SiteBuilder`"
    When I run the check with the code check
    Then a problem on "src/example/ui.py" names the target "SiteBuilder"

  Scenario: Another package's name passes the code check
    Given a docstring in "example.ui" holds the role ":class:`pathlib.Path`"
    When I run the check with the code check
    Then no problem is reported for the role

  Scenario: A private member of the project's own code is a problem in the code check
    Given the class "example.build.SiteBuilder" has the private method "_flush"
    And a docstring in "example.ui" holds the role ":meth:`example.build.SiteBuilder._flush`"
    When I run the check with the code check
    Then a problem on "src/example/ui.py" names the target "example.build.SiteBuilder._flush"

  Scenario: Several matching elements are a warning in the code check
    Given the module "example.widgets" also defines a class "SiteBuilder"
    And a docstring on line 12 of "src/example/ui.py" holds the role ":class:`.SiteBuilder`"
    When I run the check with the code check
    Then it warns "src/example/ui.py:12: more than one code element for .SiteBuilder: example.build.SiteBuilder, example.widgets.SiteBuilder"
```

## See also

- [behavior/code-reference.md](../behavior/code-reference.md#requirements) — the rules these cases pin down.
- [architecture/docs-tooling.md](../architecture/docs-tooling.md#code-reference) — the lookup that the code check and the `internal` renderer share.
