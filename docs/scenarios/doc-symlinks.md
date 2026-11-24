---
title: Symlinked docs — scenarios
summary: Exact cases for symlinks under docs/, judged by what they lead to — first, for each kind of symlink, what the check, the listings and the site do with it, also inside a symlinked directory; then what is particular to the check (hints, indexes, templates, links, removing a symlink), to the site (versions, previews, the built revision) and to loops of symlinks.
layer: scenarios
components: [checks, site]
tags: [checks, versioning]
related:
  - behavior/doc-symlinks.md
  - behavior/commands.md
---

# Symlinked docs — scenarios

These scenarios pin down [Symlinked docs](../behavior/doc-symlinks.md) ([DS-39](../behavior/doc-symlinks.md#requirements)).
A symlink (a file that only points to another file or directory) under `docs/` is judged by what it leads to, never by its own name.
[The kinds of symlink](#the-kinds-of-symlink) says once, for each kind, what the check, the listings (`list` and `backlinks`) and the site do with it.
The sections after it hold only what is particular to one command: the check's hints and its other rules, the site's versions and previews, and loops of symlinks.
The exact problem lines and hints are in [commands.md](../behavior/commands.md#check).

## The kinds of symlink

What a symlink leads to gives its kind, and the check, the listings and the site each treat every symlink of one kind the same way ([The kinds of symlink](../behavior/doc-symlinks.md#the-kinds-of-symlink)).

```gherkin
Feature: The kinds of symlink
  As a docs author
  I want the check, the listings and the site to treat a symlink by what it leads to, never by its name
  So that one rule tells me what each symlink under docs/ does

  Scenario Outline: A symlink that leads out of the repo or to nothing is a check problem, and the site leaves it out
    Given "docs/<symlink>" is committed as a symlink to "<target>", which is <what the target is>
    When I run the check
    Then the output includes the line:
      """
      docs/<symlink>: symlink to "<target>" leads <where>
      """
    When I list the docs
    Then no path at or below "<symlink>" is listed
    And asking for the backlinks of "docs/<symlink>" says it is not a doc
    When I build the site
    Then the site has nothing at or below "<symlink>"
    And the build gives the warning:
      """
      warning: docs/<symlink>: symlink to an absolute path, outside the repo or to a missing file; left out
      """

    Examples:
      | symlink         | target              | what the target is                            | where           |
      | guides/notes.md | /srv/notes/setup.md | an absolute path                              | out of the repo |
      | guides/notes.md | ../../../notes.md   | a path outside the repo                       | out of the repo |
      | guides/notes.md | out-notes.md        | another symlink, which points out of the repo | out of the repo |
      | guides/flow.png | /srv/img/flow.png   | an image at an absolute path                  | out of the repo |
      | shared          | ../../shared        | a directory outside the repo                  | out of the repo |
      | guides/old.md   | gone                | a path that does not exist                    | to nothing      |
      | guides/old      | gone                | a path that does not exist                    | to nothing      |
      | guides/old.png  | gone                | a path that does not exist                    | to nothing      |
      | guides/old.md   | other-old.md        | another symlink, whose target does not exist  | to nothing      |
      | guides/old.png  | old.png             | the symlink itself, so the chain loops        | to nothing      |

  Scenario Outline: A symlink that leads to a doc or to a directory with docs is a check problem, and has no pages
    Given "docs/<symlink>" is committed as a symlink to "<target>", which is <what the target is>
    When I run the check
    Then the output includes the line:
      """
      docs/<symlink>: symlink to "<target>" leads <where>
      """
    When I list the docs
    Then no path at or below "<symlink>" is listed
    And asking for the backlinks of "docs/<symlink>" says it is not a doc
    When I build the site
    Then the site has no page at or below "<symlink>" in any version
    And the site has <on the site> at or below "<symlink>"
    And the build gives no error and no warning for "docs/<symlink>"

    Examples:
      | symlink             | target                 | what the target is                                      | where                    | on the site                   |
      | guides/alias.md     | setup.md               | a doc                                                   | to a doc                 | nothing                       |
      | guides/setup-copy   | setup.md               | a doc                                                   | to a doc                 | nothing                       |
      | guides/setup.png    | setup.md               | a doc                                                   | to a doc                 | nothing                       |
      | reference/shared.md | ../../vendor/shared.md | a doc outside docs/                                     | to a doc                 | nothing                       |
      | howto               | guides                 | a directory inside docs/ that holds only docs           | to a directory with docs | nothing                       |
      | shared              | ../vendor/shared       | a directory with only "img/flow.png" and "img/notes.md" | to a directory with docs | only the image "img/flow.png" |

  Scenario Outline: A symlink that leads to another file or to a directory without docs is allowed, and the site gets what it leads to
    Given "docs/<symlink>" is committed as a symlink to "<target>", which is <what the target is>
    When I run the check
    Then the check reports no problem at or below "docs/<symlink>"
    When I list the docs
    Then no path at or below "<symlink>" is listed
    And asking for the backlinks of "docs/<symlink>" says it is not a doc
    When I build the site
    Then the site's "<site file>" is the file "<file>", not the text of the link
    And the site has no page at or below "<symlink>"
    And the build gives no warning for a path at or below "docs/<symlink>"

    Examples:
      | symlink         | target                   | what the target is                         | site file       | file                 |
      | guides/flow.png | ../../static/flow.png    | an image outside docs/                     | guides/flow.png | static/flow.png      |
      | guides/alias.md | flow.png                 | the image "docs/guides/flow.png"           | guides/alias.md | docs/guides/flow.png |
      | guides/flow.png | ../../static/current.png | a symlink to the image "static/flow.png"   | guides/flow.png | static/flow.png      |
      | img             | ../static/img            | a directory with only the image "flow.png" | img/flow.png    | static/img/flow.png  |
```

### Inside a symlinked directory

The symlinks and files inside a directory that a symlink leads to are judged by the same rule, followed from the directory's symlink ([How a symlink is followed](../behavior/doc-symlinks.md#how-a-symlink-is-followed)).

```gherkin
Feature: Inside a symlinked directory
  As a docs author
  I want what lies inside a symlinked directory to be judged by the same rule
  So that a directory of shared files works like a single symlinked file

  Scenario: A ".md" file inside a symlinked directory is no doc, and the directory is one problem
    Given a committed directory "vendor/shared" outside docs/ that holds "index.md", "notes.md" and "diagram.png"
    And "docs/shared" is committed as a symlink to "../vendor/shared"
    When I run the check
    Then the output includes the line:
      """
      docs/shared: symlink to "../vendor/shared" leads to a directory with docs
      """
    And the check reports no problem for a path inside "docs/shared"
    When I list the docs
    Then no path under "shared/" is listed
    And asking for the backlinks of "docs/shared/notes.md" says it is not a doc
    When I build the site
    Then the site has no page for "shared/index" or "shared/notes"
    And the site's "shared/diagram.png" is the image "vendor/shared/diagram.png"
    And the build gives no error and no warning for a path at or below "docs/shared"

  Scenario: A symlink inside a symlinked directory that leads to a doc counts as a doc inside
    Given a committed file "vendor/notes.md" outside docs/
    And a committed directory "static/img" outside docs/ that holds only the image "flow.png" and a symlink "notes" to "../../vendor/notes.md"
    And "docs/img" is committed as a symlink to "../static/img"
    When I run the check
    Then the output includes the line:
      """
      docs/img: symlink to "../static/img" leads to a directory with docs
      """
    And the check reports no problem for a path inside "docs/img"
    When I build the site
    Then the site's "img/flow.png" is the image "static/img/flow.png"
    And the site has nothing at "img/notes"
    And the build gives no error and no warning for a path at or below "docs/img"

  Scenario: A symlink inside a symlinked directory that leads to an image is allowed, and followed too
    Given a committed image "static/logo.png" outside docs/
    And a committed directory "static/img" outside docs/ that holds only the image "flow.png" and a symlink "logo.png" to "../logo.png"
    And "docs/img" is committed as a symlink to "../static/img"
    When I run the check
    Then the check reports no problem for "docs/img"
    And the check reports no problem for "docs/img/logo.png"
    When I build the site
    Then the site's "img/flow.png" is the image "static/img/flow.png"
    And the site's "img/logo.png" is the image "static/logo.png"
    And the build gives no warning for a path at or below "docs/img"

  Scenario Outline: A symlink inside an allowed symlinked directory that leads out of the repo or to nothing is reported at its path below it, and left out
    Given a committed directory "static/img" outside docs/ that holds only the image "flow.png" and a symlink "logo.png" to "<target>", which is <what the target is>
    And "docs/img" is committed as a symlink to "../static/img"
    When I run the check
    Then the check reports no problem for "docs/img"
    And the output includes the line:
      """
      docs/img/logo.png: symlink to "<target>" leads <where>
      """
    When I build the site
    Then the site's "img/flow.png" is the image "static/img/flow.png"
    And the site has no "img/logo.png"
    And the build gives a warning that names "docs/img/logo.png"

    Examples:
      | target        | what the target is         | where           |
      | /srv/logo.png | an absolute path           | out of the repo |
      | gone.png      | a path that does not exist | to nothing      |
```

## The check

The check reports a symlink of the first four kinds (one that leads out of the repo, to nothing, to a doc or to a directory with a doc inside) with a hint that depends on where it leads, and asks nothing more of a symlink ([What the check reports](../behavior/doc-symlinks.md#what-the-check-reports), [Listings and links](../behavior/doc-symlinks.md#listings-and-links) for links to a symlink).

```gherkin
Feature: Symlinks in the check
  As a docs author
  I want the check to say how to replace a symlink it reports, and to ask nothing more of a symlink
  So that every doc has its own text and its own history

  Scenario Outline: A symlink that leads to docs inside docs/ gets the hint to link to them instead
    Given "docs/<symlink>" is a symlink to "<target>", which is <what the target is>
    When I run the check
    Then the output includes:
      """
      docs/<symlink>: symlink to "<target>" leads <where>
        hint: link to "<linked>" in the text instead, and remove the symlink
      """

    Examples:
      | symlink          | target         | what the target is                            | where                    | linked               |
      | guides/alias.md  | setup.md       | the doc "docs/guides/setup.md"                | to a doc                 | docs/guides/setup.md |
      | guides/setup.png | setup.md       | the doc "docs/guides/setup.md"                | to a doc                 | docs/guides/setup.md |
      | guides/alias.md  | other-alias.md | a symlink to the doc "docs/guides/setup.md"   | to a doc                 | docs/guides/setup.md |
      | howto            | guides         | the directory "docs/guides", which holds docs | to a directory with docs | docs/guides          |

  Scenario Outline: A symlink that leads to docs outside docs/ gets the hint to move them to its place
    Given "docs/<symlink>" is a symlink to "<target>", which is <what the target is>
    When I run the check
    Then the output includes:
      """
      docs/<symlink>: symlink to "<target>" leads <where>
        hint: move "<old place>" to "docs/<symlink>", and put the symlink at "<old place>" instead
      """

    Examples:
      | symlink             | target                 | what the target is                                             | where                    | old place        |
      | reference/shared.md | ../../vendor/shared.md | a doc outside docs/                                            | to a doc                 | vendor/shared.md |
      | shared              | ../vendor/shared       | a directory outside docs/ that holds "index.md" and "notes.md" | to a directory with docs | vendor/shared    |

  Scenario: The hint to move a doc adds ".md" to a symlink's name that lacks it
    Given a file "vendor/shared.md" outside docs/
    And "docs/guides/setup-copy" is a symlink to "../../vendor/shared.md"
    When I run the check
    Then the output includes:
      """
      docs/guides/setup-copy: symlink to "../../vendor/shared.md" leads to a doc
        hint: move "vendor/shared.md" to "docs/guides/setup-copy.md", and put the symlink at "vendor/shared.md" instead
      """

  Scenario: A symlink that leads to nothing gets the hint to remove it
    Given "docs/guides/old.md" is a symlink to "gone.md"
    And there is no "docs/guides/gone.md"
    When I run the check
    Then the output includes:
      """
      docs/guides/old.md: symlink to "gone.md" leads to nothing
        hint: remove the symlink; its target does not exist
      """

  Scenario: A symlink that leads out of the repo gets no hint
    Given "docs/guides/notes.md" is a symlink to "/srv/notes/setup.md", an absolute path
    When I run the check
    Then the output includes the line:
      """
      docs/guides/notes.md: symlink to "/srv/notes/setup.md" leads out of the repo
      """
    And no hint follows that line

  Scenario: A symlink needs no entry in an index
    Given "docs/guides/alias.md" is a symlink to "setup.md"
    And "docs/guides/index.md" does not list "alias.md"
    When I run the check
    Then the check does not ask "docs/guides/index.md" to list "alias.md"

  Scenario Outline: A symlinked directory needs no index.md and no entry in an index
    Given a directory "<directory>" outside docs/ that holds <what it holds>
    And "docs/<symlink>" is a symlink to "../<directory>"
    And "docs/index.md" does not list "<symlink>/"
    When I run the check
    Then the check does not ask for a "docs/<symlink>/index.md"
    And the check does not ask "docs/index.md" to list "<symlink>/"

    Examples:
      | symlink | directory     | what it holds                |
      | shared  | vendor/shared | "notes.md" and no "index.md" |
      | img     | static/img    | only images                  |

  Scenario Outline: A symlink inside the doc templates is not reported
    Given "docs/meta/templates/<name>" is a symlink to "<target>", which is <what the target is>
    When I run the check
    Then the check reports no problem for "docs/meta/templates/<name>"

    Examples:
      | name    | target                    | what the target is              |
      | note.md | behavior-doc.md           | a doc template                  |
      | shared  | ../../../vendor/templates | a directory with ".md" files    |
      | extra   | /srv/templates            | a directory at an absolute path |
      | old.md  | gone.md                   | a path that does not exist      |

  Scenario Outline: A link to a doc reached through a symlink is broken, with a message that says why
    Given "docs/guides/alias.md" is a symlink to "setup.md"
    And a directory "vendor/shared" outside docs/ that holds "notes.md" and "diagram.png"
    And "docs/shared" is a symlink to "../vendor/shared"
    And line 12 of the doc "docs/index.md" links to "<link>"
    When I run the check
    Then the output includes:
      """
      docs/index.md:12: broken link: <message>
      """

    Examples:
      | link            | message                                                         |
      | guides/alias.md | docs/guides/alias.md is a symlink, not a doc                    |
      | shared/         | docs/shared is a symlinked directory of docs                    |
      | shared/notes.md | docs/shared/notes.md is inside a symlinked directory, not a doc |

  Scenario: A link to another file inside a symlinked directory with docs resolves
    Given a directory "vendor/shared" outside docs/ that holds "notes.md" and "diagram.png"
    And "docs/shared" is a symlink to "../vendor/shared"
    And a doc links to "shared/diagram.png"
    When I run the check
    Then the check reports no broken link for "shared/diagram.png"

  Scenario: A link to a symlink that leads to nothing is broken
    Given "docs/guides/old.png" is a symlink to "gone.png"
    And there is no "docs/guides/gone.png"
    And a doc links to "guides/old.png"
    When I run the check
    Then the check reports a broken link for "guides/old.png"
```

### Removing and renaming a symlink

A symlink is never a doc, so the `git:staged` check (which reports docs deleted or renamed in the next commit) passes over a path that was a symlink in the last commit ([DS-39](../behavior/doc-symlinks.md#requirements)).

```gherkin
Feature: Removing and renaming a symlink
  As a docs author
  I want to remove or rename a symlink under docs/ without a check problem
  So that the rule never to delete or rename docs does not hold back a symlink, which never was a doc

  Scenario: Removing a symlink is allowed
    Given the git backend is in use
    And "docs/guides/alias.md" was committed as a symlink to "setup.md"
    And its removal is staged in git
    When I run check with --optional-checks git:staged
    Then the check reports no problem for "docs/guides/alias.md"

  Scenario: Renaming a symlink is allowed
    Given the git backend is in use
    And "docs/guides/alias.md" was committed as a symlink to "../../static/flow.png", an image outside docs/
    And its move to "docs/guides/flow.png" is staged in git
    When I run check with --optional-checks git:staged
    Then the check reports no problem for "docs/guides/alias.md"
    And the check reports no problem for "docs/guides/flow.png"
```

### A symlinked image in the check

A symlink that leads to a file that is not a doc, such as an image, is allowed ([Other files under docs/](../behavior/doc-symlinks.md#other-files-under-docs)).

```gherkin
Feature: A symlinked image in the check
  As a docs author
  I want the check to accept a symlink that leads to an image
  So that I can keep shared files, such as images, outside docs/

  Scenario: Other files under docs/ may be symlinks
    Given "docs/guides/flow.png" is a symlink to an image outside docs/
    When I run the check
    Then the check reports no problem for "docs/guides/flow.png"
```

## The site

The site has no pages for a symlink, and keeps a doc's versions only where its path was a doc ([On the site](../behavior/doc-symlinks.md#on-the-site)); a symlink it cannot follow is left out, and links to it are not found ([Other files under docs/](../behavior/doc-symlinks.md#other-files-under-docs)).

```gherkin
Feature: Symlinks on the site
  As a docs author
  I want the site to hold only docs that have their own text and history, and the files my docs show
  So that no page stands for a link in place of a doc

  Scenario: A doc that was a symlink in an earlier commit has pages from the commit that made it a file
    Given a commit that adds "docs/guides/setup.md" as a symlink to "install.md"
    And a later commit that replaces the symlink with a regular file
    And a third commit that changes "docs/guides/setup.md"
    When I build the site
    Then "guides/setup.md" has two versions: the commit that made it a file, and the third commit
    And it has no version for the commit in which it was a symlink

  Scenario: A doc that was replaced by a symlink has no pages
    Given two commits that change the regular file "docs/guides/setup.md"
    And a later commit that replaces it with a symlink to "install.md"
    When I build the site
    Then the site has no page for "guides/setup.md" in any version

  Scenario: A preview shows a symlink replaced by a file as a new doc
    Given "docs/guides/alias.md" is a symlink to "setup.md" at the built revision
    And in the working tree "docs/guides/alias.md" is a regular doc that is not committed yet
    When I build the site with --include-worktree
    Then "guides/alias.md" has one version, the "working copy (uncommitted)" version

  Scenario: A preview has no working copy of a doc replaced by a symlink
    Given two commits that change the regular file "docs/guides/setup.md"
    And in the working tree "docs/guides/setup.md" is a symlink to "install.md" that is not committed yet
    When I build the site with --include-worktree
    Then "guides/setup.md" has the versions of both commits
    And it has no "working copy (uncommitted)" version

  Scenario Outline: A target that the built revision does not have counts as a missing one
    Given "docs/<symlink>" is committed as a symlink to "<target>"
    And the built revision has no "<missing>"
    When I build the site
    Then the site has nothing at or below "<symlink>"
    And the build gives a warning that names "docs/<symlink>"

    Examples:
      | symlink         | target                | missing         |
      | guides/flow.png | ../../static/gone.png | static/gone.png |
      | img             | ../static/img         | static/img      |

  Scenario: A preview leaves out a symlinked image whose target git ignores
    Given "docs/guides/flow.png" is committed as a symlink to "../../build/flow.png"
    And the working tree has a "build/flow.png" that git ignores
    When I build the site with --include-worktree
    Then the site has no "guides/flow.png"
    And the build gives a warning that names "docs/guides/flow.png"

  Scenario: A link to a symlink that the build leaves out is shown as not found
    Given "docs/guides/flow.png" is committed as a symlink to "/srv/img/flow.png", an absolute path
    And the latest version of the doc "docs/guides/setup.md" links to "flow.png"
    When I build the site
    Then the page of "guides/setup.md" shows that link's text with the marker "not found" and no link
```

### A symlinked image in a preview

The site gets the file a symlink leads to; in a preview, it reads that file as it is in the working tree (the files on disk) ([Other files under docs/](../behavior/doc-symlinks.md#other-files-under-docs)).

```gherkin
Feature: A symlinked image in a preview of the working tree
  As a docs author
  I want a preview to show a symlinked image as it is now on disk
  So that I see my change to the image before I commit it

  Scenario: A preview reads a symlinked image from the working tree
    Given "docs/guides/flow.png" is committed as a symlink to "../../static/flow.png"
    And an uncommitted change to "static/flow.png"
    When I build the site with --include-worktree
    Then the site's "guides/flow.png" is the changed image
```

## Symlink loops

No loop of symlinks makes the check or the build run forever or report the same thing twice ([Symlink loops](../behavior/doc-symlinks.md#symlink-loops)).

```gherkin
Feature: Symlink loops
  As a docs author
  I want check and build to finish when symlinks form a loop
  So that one wrong symlink never hangs my commit hook or my CI

  Scenario: A symlinked directory that links back to docs/
    Given "docs/shared" is a symlink to "../vendor/shared"
    And "vendor/shared" holds "logo.png" and a symlink "back" to "../../docs"
    When I run check
    Then check finishes and reports no problem for "docs/shared"
    And the output includes:
      """
      docs/shared/back: symlink to "../../docs" leads to nothing
        hint: remove the symlink; its target does not exist
      """
    When I build the site
    Then the build finishes
    And the site has "shared/logo.png"
    And the site has nothing at or below "shared/back"
    And the build warns "docs/shared/back: symlink to an absolute path, outside the repo or to a missing file; left out"

  Scenario: A symlink to a directory it lies in
    Given "docs/guides/up" is a symlink to ".."
    When I run check
    Then check finishes
    And the output includes:
      """
      docs/guides/up: symlink to ".." leads to nothing
        hint: remove the symlink; its target does not exist
      """

  Scenario: Symlinks that point to each other
    Given "docs/a.md" is a symlink to "b.md"
    And "docs/b.md" is a symlink to "a.md"
    When I run check
    Then check finishes
    And it reports each of them once, with the hint "remove the symlink; its target does not exist"
```

## See also

- [behavior/doc-symlinks.md](../behavior/doc-symlinks.md) — DS-39, the rule on symlinks to docs, directories and other files.
- [behavior/commands.md](../behavior/commands.md#check) — the problem lines and hints of the check.
- [commands.md](commands.md) — links to a symlinked doc on the site.
