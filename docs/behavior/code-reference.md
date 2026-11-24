---
title: Code reference
summary: The code reference generated from a project's Python code and docstrings for its latest version only — `code:` links and `Docs:` lines between docs and code, Sphinx roles in docstrings, "described in" backlinks, and the code lookup command agents use instead.
layer: behavior
status: [implemented, changed]
milestone: first-release
priority: must
components: [code-reference]
tags: [requirements, reference, rendering]
related:
  - scenarios/code-reference.md
  - behavior/requirements.md
  - behavior/site.md
  - behavior/commands/check.md
  - behavior/commands/build.md
  - behavior/web-api-reference.md
  - architecture/docs-tooling.md
  - architecture/site.md
  - meta/linking.md
---

# Code reference

docspecsite generates reference pages from a project's Python code and its docstrings, and links docs and code both ways: docs point at code with `code:` links, docstrings point at docs with `Docs:` lines and at other code with Sphinx roles.
Unlike the hand-written docs, the code reference shows only the latest version of the code.
It is one part of the [site](site.md); the code check that validates its references is in [check.md](commands/check.md#requirements).

## Requirements

> **Changed, not built yet.** The site and the code check find the target of a role by docspecsite's older rules: with or without a leading `.`, a target is looked up as written, then in the docstring's class, then in its module, whatever kind of element the role names, and never by the end of an element's dotted path.

These requirements are part of the [DSR-n](../meta/glossary.md#dsr-n) numbering listed in [requirements.md](requirements.md):

- **DSR-13** `code:` links and `Docs:` docstring lines resolve as described in [meta/linking.md](../meta/linking.md#code-links).
  `web-api:` links are part of the HTTP API reference ([web-api-reference.md](web-api-reference.md)).
- **DSR-34** Docstrings refer to code with Sphinx's Python roles: `` :mod:`…` ``, `` :class:`…` ``, `` :func:`…` ``, `` :meth:`…` ``, `` :attr:`…` ``, `` :data:`…` ``, `` :exc:`…` `` and `` :obj:`…` ``, also with the `py:` domain (`` :py:meth:`…` ``).
  A role's target is found as Sphinx, whose roles these are, finds it (in its version 9.2), from the docstring's place: its class (the class itself for the class docstring, the enclosing class for a member's docstring) and its module.
  A target without a leading `.` is looked up as written, as a full dotted path (`` :class:`docspecsite.build.SiteBuilder` ``), then among the definitions of the docstring's module, then among the members of its class (`` :meth:`attempt` `` in any docstring of `SiteBuilder`); the kind of element the role names does not matter.
  A `:mod:` target is found only as a module's full dotted path.
  A target with a leading `.` is looked up first among the members of the docstring's class, then among the definitions of its module, then as written (`` :meth:`.attempt` `` in any docstring of `SiteBuilder`).
  When none of these finds it, any element whose dotted path ends with the target, its `.` included, counts, so `` :class:`.SiteBuilder` `` finds `docspecsite.build.SiteBuilder` from a docstring anywhere in the code.
  With a leading `.`, only an element of the kind the role names counts: `:func:` a function; `:meth:` a method, also a class or static method, or else a property; `:attr:` an attribute or a property, or else a method; `:class:` a class, an exception or a type alias, or else module data or an attribute; `:exc:` an exception or a class; `:data:` module data; `:mod:` a module; `:obj:` any element.
  When the end of the dotted path matches several elements, the role leads to one of them, and the build warns that more than one element matches; a longer target, such as `.build.SiteBuilder`, or the full dotted path picks one.
  A name the module only imports is not among its definitions: without a leading `.` it is not found that way, and with one, the element is found where it is defined only through the end of its dotted path.
  A target is found only when the code reference shows it, as for `code:` links: a private member is not.
  A target `<class>.__init__` stands for how the class is constructed: it leads to the `__init__` entry when the code reference shows one, else to the class.
  A role reads as its target is written, without a leading `.` (`` :meth:`.attempt` `` reads `attempt()`), and a `:func:` or `:meth:` role adds `()` after the name, as Sphinx shows it.
  `~` before the target shows only the last part of the path (`` :class:`~docspecsite.build.SiteBuilder` `` reads `SiteBuilder`), and `Text <target>` sets the text.
  Each role renders as a link to the element on the code reference.
  Other roles are shown as written.
  A target that is not found is shown as written (without `~`) with the "no longer exists" marker and is a build warning; plain `check` does not look at it, the code check does ([DSR-36](commands/check.md#requirements)).
  The site, with either [renderer](site.md#renderers), and the code check find targets by these rules, so they agree on every role.
  A name from another package, such as `pathlib.Path`, stays plain text, without a marker or a warning.
- **DSR-18** Code reference pages are generated from the **code itself and its docstrings** (structure, signatures, types, members, inheritance), rendered through the same pipeline, **for the latest version of the code only**, and so is their hand-written entry page. Older code is read with the version control or an IDE.
- **DSR-19** Code reference pages show "described in" backlinks from docs' `code:` fields.
- **DSR-31** A query command for agents: print the API of a code module or class (signatures with types, docstrings, base classes, inherited members) as Markdown, from the code, without rendering.
  It is not a docspecsite command: a project provides it with its own lookup tools, chosen for its languages.

## See also

- [site.md](site.md) — the rest of the site, and how parts link to each other ([DSR-35](site.md#rendering)).
- [meta/linking.md](../meta/linking.md#code-links) — how `code:` links and `Docs:` lines are written.
- [Architecture](../architecture/docs-tooling.md) — how it is built.
