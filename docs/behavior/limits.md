---
title: Limits
summary: What docspecsite deliberately does not handle — text that is not UTF-8 beyond the listed cases, links from older versions in a one-part build, and roles in docstring types.
layer: behavior
status: implemented
milestone: hardening
priority: should
components: [checks, site, code-reference]
tags: [limits, utf-8, checks, rendering]
related:
  - behavior/commands/index.md
  - behavior/requirements.md
---

# Limits

docspecsite is built for repos whose docs and code are UTF-8.
Each limit below is a deliberate choice; changing one starts from a new spec.

## Text that is not UTF-8

File names and file contents that are not valid UTF-8 are handled only in the cases [Input that cannot be used](commands/index.md#input-that-cannot-be-used) lists.
Anywhere else, such input is not supported: a command may leave the thing out without a word, warn, or stop.
Known cases:

- A Python source file that is not valid UTF-8: its code is not loaded, and `build` warns that it cannot load the code.

## Other limits

- In a build of one part (`--parts docs` or `--parts code`), a link from an older version of a doc to a file of the part not being built goes to the repository host at that version's commit, also when the file was added later, so such a link can lead to a missing file.
- When `build` cannot place a docstring's links in its source file, it gives no warning about that docstring's empty `code:` targets; `check --optional-checks code` reports that docstring.
- In a preview (`--include-worktree`) of one part, a link to a file of the other part that exists only in the working tree goes to the repository host at the built commit, where that file is not yet present.
- In a docstring, a role or `code:` link in the type of an `Args` or `Returns` entry (`path (:class:`Missing`): …`) is neither checked nor shown as a link.
