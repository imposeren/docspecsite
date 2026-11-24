---
title: Code reference
summary: The code reference generated from a project's Python code and docstrings for its latest version only — `code:` links and `Docs:` lines between docs and code, Sphinx roles in docstrings, "described in" backlinks, and the code lookup command agents use instead.
layer: behavior
status: implemented
milestone: first-release
priority: must
components: [code-reference]
tags: [requirements, reference, rendering]
related:
  - behavior/requirements.md
  - behavior/site.md
  - behavior/commands.md
  - behavior/web-api-reference.md
  - architecture/docs-tooling.md
  - meta/linking.md
---

# Code reference

docspecsite generates reference pages from a project's Python code and its docstrings, and links docs and code both ways: docs point at code with `code:` links, docstrings point at docs with `Docs:` lines and at other code with Sphinx roles.
Unlike the hand-written docs, the code reference shows only the latest version of the code.
It is one part of the [site](site.md); the code check that validates its references is in [commands.md](commands.md#checks).

## Requirements

These requirements are part of the [DS-n](../meta/glossary.md#ds-n) numbering listed in [requirements.md](requirements.md):

- **DS-13** `code:` links and `Docs:` docstring lines resolve as described in [meta/linking.md](../meta/linking.md#code-links).
  `web-api:` links are part of the HTTP API reference ([web-api-reference.md](web-api-reference.md)).
- **DS-34** Docstrings refer to code with Sphinx's Python roles: `` :mod:`…` ``, `` :class:`…` ``, `` :func:`…` ``, `` :meth:`…` ``, `` :attr:`…` ``, `` :data:`…` ``, `` :exc:`…` `` and `` :obj:`…` ``, also with the `py:` domain (`` :py:meth:`…` ``).
  A target is a full dotted path (`` :class:`docspecsite.build.SiteBuilder` ``), or starts with `.` and is looked up from the docstring's place: first among the members of its class (the class itself for the class docstring, the enclosing class for a member's docstring), then among the definitions of its module (`` :meth:`.attempt` `` in any docstring of `SiteBuilder`).
  A target without a leading `.` that is no full dotted path of an element is looked up the same way, as Sphinx does: `` :meth:`attempt` `` works like `` :meth:`.attempt` ``.
  A name the module only imports is not found that way: a reference to code defined elsewhere uses that code's own dotted path.
  A target is found only when the code reference shows it, as for `code:` links: a private member is not.
  A target `<class>.__init__` stands for how the class is constructed: it leads to the `__init__` entry when the code reference shows one, else to the class.
  A role reads as the full dotted path of the element it leads to (`` :meth:`.attempt` `` in `SiteBuilder` reads `docspecsite.build.SiteBuilder.attempt`).
  `~` before the target shows only the last part of that path (`` :class:`~docspecsite.build.SiteBuilder` `` and `` :meth:`~.attempt` `` read `SiteBuilder` and `attempt`), and `Text <target>` sets the text.
  Each role renders as a link to the element on the code reference; the role names the kind of element for readers, and docspecsite does not check that it matches.
  Other roles are shown as written.
  A target that is not found is shown as written (without `~`) with the "no longer exists" marker and is a build warning; plain `check` does not look at it, the code check does ([DS-36](commands.md#checks)).
- **DS-18** Code reference pages are generated from the **code itself and its docstrings** (structure, signatures, types, members, inheritance), rendered through the same pipeline, **for the latest version of the code only**, and so is their hand-written entry page. Older code is read with the version control or an IDE.
- **DS-19** Code reference pages show "described in" backlinks from docs' `code:` fields.
- **DS-31** A query command for agents: print the API of a code module or class (signatures with types, docstrings, base classes, inherited members) as Markdown, from the code, without rendering.
  It is not a docspecsite command: a project provides it with its own lookup tools, chosen for its languages.

## See also

- [site.md](site.md) — the rest of the site, and how parts link to each other ([DS-35](site.md#rendering)).
- [meta/linking.md](../meta/linking.md#code-links) — how `code:` links and `Docs:` lines are written.
- [Architecture](../architecture/docs-tooling.md) — how it is built.
