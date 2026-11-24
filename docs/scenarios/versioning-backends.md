---
title: Where versions come from — scenarios
summary: Exact cases for choosing where versions come from — automatic choice, git, no version control, a backend from another package, versions from tags only, link patterns and backend checks.
layer: scenarios
status: draft
components: [versioning]
tags: [versioning, configuration]
related:
  - behavior/versioning-backends.md
  - behavior/site.md
  - architecture/versioning-backends.md
---

# Where versions come from — scenarios

These scenarios pin down [Where versions come from](../behavior/versioning-backends.md): how the [versioning backend](../behavior/glossary.md) (the part of docspecsite that reads the project's version control) is chosen, what a site without version control looks like, versions from tags only, link patterns, and backend checks.
The rules every version follows once a backend has given it (version pages, pickers, old-version warnings) are in [behavior/site.md](../behavior/site.md#rendering), not here.

## Choosing a backend

The `backend` setting chooses where versions come from, and `auto` picks the one backend that recognizes the project ([What a project can choose](../behavior/versioning-backends.md#what-a-project-can-choose), [DS-40](../behavior/versioning-backends.md#requirements)).

```gherkin
Feature: Choosing where versions come from
  As a docs author
  I want docspecsite to read versions from my project's version control, or to work without one
  So that my project gets a site whatever version control it uses

  Scenario: A git project without the setting builds as before
    Given a project at the top of a git repository
    And its docspecsite.toml has no versioning section
    When I build the site
    Then the build says "versioning: git (auto)"
    And every commit that touches a doc is a version of it

  Scenario: A folder without version control gets a site without versions
    Given a project folder that no installed backend recognizes
    And its docspecsite.toml has no versioning section
    When I build the site
    Then the build says "versioning: none (auto)"
    And each doc has one page, with no version picker, no diffs and no old-version warning

  Scenario: Two backends recognize the folder
    Given a project folder that both the git backend and an installed Mercurial backend recognize
    And its docspecsite.toml does not set backend
    When I run any docspecsite command
    Then it stops with an error that names both backends and asks for backend to be set

  Scenario: A backend chosen by name does not fall back
    Given a project folder that is not a git repository
    And its docspecsite.toml sets backend to "git"
    When I run any docspecsite command
    Then it stops with an error saying the folder is not a git repository

  Scenario: The none backend ignores git
    Given a project at the top of a git repository
    And its docspecsite.toml sets backend to "none"
    When I build the site
    Then the build says "versioning: none"
    And each doc has one page, built from the file on disk, including uncommitted changes

  Scenario: A backend from another package, by its name
    Given a package installed next to docspecsite that gives its backend the name "hg"
    And a project in a Mercurial repository whose docspecsite.toml sets backend to "hg"
    When I build the site
    Then the versions come from the Mercurial history

  Scenario: A backend from another package, by its import path
    Given a package installed next to docspecsite with a backend that it gives no name
    And docspecsite.toml sets backend to that backend's import path
    When I build the site
    Then the build uses that backend

  Scenario Outline: An unknown backend
    Given docspecsite.toml sets backend to "<value>", which no installed package provides
    When I run "<command>"
    Then <outcome>

    Examples:
      | value              | command | outcome                                                                     |
      | svn                | build   | it stops with an error naming the backend setting                           |
      | missing.module:Cls | list    | it stops with an error naming the backend setting                           |
      | svn                | check   | it reports a problem on docspecsite.toml and checks the docs as with "auto" |

  Scenario: Settings of a backend not in use are ignored
    Given docspecsite.toml sets backend to "none"
    And it has a versioning.git section with a key git does not know
    When I check the docs
    Then no problem is reported for the versioning.git section

  Scenario: An unknown key in the settings of the backend in use
    Given the git backend is in use
    And the versioning.git section has the key "tag-patern"
    When I check the docs
    Then a problem on docspecsite.toml names the unknown key
```

## Building without version control

With `none`, each doc has one version, the file on disk, and the site has no older versions ([DS-41](../behavior/versioning-backends.md#requirements)).

```gherkin
Feature: Building without version control
  As a docs author
  I want a project without version control to get a working site
  So that I can use docspecsite before, or without, putting the project under version control

  Background:
    Given docspecsite.toml sets backend to "none"

  Scenario: Asking for an older state is an error
    When I build the site with --ref main
    Then the build stops with a command-line error and exit code 2

  Scenario: Previewing uncommitted changes changes nothing
    When I build the site with --include-worktree
    Then the site is the same as without --include-worktree

  Scenario: Hidden files under docs are not copied
    Given docs/ holds the image "diagram.png" and the file ".notes"
    When I build the site
    Then the site holds "diagram.png" and not ".notes"

  Scenario: The code reference comes from disk
    Given code-dirs names a directory with a Python package
    When I build the site
    Then the code reference shows that package as it is on disk

  Scenario: The git check is not available
    When I run check with --optional-checks git:staged
    Then the command stops with a command-line error that lists the available checks

  Scenario: Source links need a link pattern
    Given source-url is set and versioning.none sets no link pattern
    When I build the site
    Then code reference pages have no source links

  Scenario: A link pattern without a revision
    Given versioning.none sets file-link to "{source-url}/blob/main/{path}"
    When I build the site
    Then each code reference page links to its source file under the main branch on the repo host

  Scenario: A link pattern cannot name a revision
    Given versioning.none sets file-link to "{source-url}/blob/{revision}/{path}"
    When I check the docs
    Then a problem on docspecsite.toml says the pattern names a revision
```

## Versions from tags only

With `versions = "tags"`, a doc's versions are the ones current at the project's matching tags ([DS-38](../behavior/versioning-backends.md#versions-from-tags-only)).

```gherkin
Feature: Versions from tags only
  As a reader
  I want each doc's versions to be the ones of the project's releases
  So that a long history gives only the versions that matter

  Background:
    Given the git backend is in use with versions set to "tags" and tag-pattern set to "v*"

  Scenario: A doc's versions are the ones current at matching tags
    Given a doc changed in commits A and B, in that order
    And tag "v1" is on commit A, tag "nightly" on commit B, and tag "v2" on a later commit that does not touch the doc
    When I build the site
    Then the doc has two versions: commit A under "v1", and commit B under "v2"

  Scenario: Tags that keep the same version give it once
    Given a doc changed only in commit A
    And tags "v1" and "v2" are on commits at or after A
    When I build the site
    Then the doc has one version, commit A, shown under "v1"

  Scenario: A link in a release's version leads to the linked doc at that release
    Given doc X's version under tag "v1" links to doc Y
    And doc Y changed both before and after tag "v1"
    When I open doc X's version under "v1"
    Then the link leads to doc Y's version current at "v1"

  Scenario: The picker shows tag names, and addresses keep commit ids
    When I open a doc's version picker
    Then each version shows its tag name and commit message
    And each version's page address has its commit's short id

  Scenario: Switching between commits and tags keeps addresses
    Given a site built with versions set to "commits"
    When I rebuild it with versions set to "tags"
    Then every version page of the tags build has the same address as in the commits build
```

## Link patterns

Links to files on the project's web host follow the backend's link patterns, which a project can change ([DS-42](../behavior/versioning-backends.md#requirements)).

```gherkin
Feature: Link patterns
  As a docs author on a host other than GitHub
  I want links to repo files to follow my host's addresses
  So that source links work on my host

  Scenario: GitLab links
    Given the git backend is in use with source-url "https://gitlab.example.com/group/project"
    And versioning.git sets file-link to "{source-url}/-/blob/{revision}/{path}"
    When I build the site
    Then each code reference page links to its source file under "https://gitlab.example.com/group/project/-/blob/<commit>/"
```

## Backend checks

A backend offers optional checks of its own, such as `git:staged` ([DS-43](../behavior/versioning-backends.md#requirements), [Rules and limits](../behavior/versioning-backends.md#rules-and-limits)).

```gherkin
Feature: Backend checks
  As a docs author
  I want the commit hook to stop commits that delete or rename docs
  So that old versions and outside links keep working

  Scenario: The git check rejects a staged delete
    Given the git backend is in use
    And a doc is staged as deleted in git
    When I run check with --optional-checks git:staged
    Then a problem names the deleted doc
    And the exit code is 1

  Scenario: Optional checks of docspecsite and the backend together
    Given the git backend is in use
    When I run check with --optional-checks code,git:staged
    Then both the code check and the git check run
```

## Settings for versions from tags

`versions = "tags"` requires `tag-pattern` ([Versions from tags only](../behavior/versioning-backends.md#versions-from-tags-only)).

```gherkin
Feature: Settings for versions from tags
  As a project maintainer
  I want a clear error when the tag settings are incomplete
  So that a site is never built from the wrong set of tags

  Scenario: Versions from tags need a tag pattern
    Given the settings set versions to "tags" without a tag-pattern
    When I check the docs
    Then a problem on docspecsite.toml says that tag-pattern is required with versions set to "tags"
    And building the site stops with the same error
```

## See also

- [Behavior](../behavior/versioning-backends.md) — the plain-language description.
- [Architecture](../architecture/versioning-backends.md) — how backends plug in.
