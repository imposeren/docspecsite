---
title: Working with AI agents
summary: Entry point for AI agents (and people using them) — the hard rules, how to read docs economically, how to turn specs into work, and Claude Code setup.
layer: agents
status: implemented
components: [agents]
tags: [overview, agents, claude]
related:
  - meta/index.md
---

# Working with AI agents

The root `CLAUDE.md` is a short, always-loaded entry point; this layer holds the details.
Agents should read this page fully, then only the deeper docs their task needs.

## Hard rules

1. **Docs are the spec.**
   Read the relevant docs before changing code; change docs before (or together with) code.
   Never let code contradict an `implemented` doc.
2. **Never delete or rename files under `docs/`.**
   Use a redirect doc ([meta/versioning.md](../meta/versioning.md#no-delete-no-rename)).
3. **Specs, not tickets.**
   Write docs as the target state, in present tense; no "TODO", "fix", "will add" ([meta/lifecycle.md](../meta/lifecycle.md)).
4. **Keep `status` honest.**
   Code that makes a doc true → `implemented`; a doc edited to describe new behavior → `specified`.
5. **Don't silently make technical decisions.**
   If a task requires a choice not covered by an existing ADR ([architecture decision record](../meta/glossary.md#adr)), write a `decision: proposed` ADR and ask; check [architecture/decisions/index.md](../architecture/decisions/index.md) first.
6. **Run the docs checks** after editing docs (the command is in [architecture/docs-tooling.md](../architecture/docs-tooling.md)).
7. **Commit only when asked.**
   Every commit becomes a permanent doc version; commit subjects for docs describe the spec change.

## Children

- [reading-strategy.md](reading-strategy.md) — How to find and read only the docs you need.
- [working-from-specs.md](working-from-specs.md) — Turning `specified` docs into code; writing new specs and ADRs.
- [code-lookup.md](code-lookup.md) — Looking up code through the project's language server, and the default server per language.
- [claude-code-setup.md](claude-code-setup.md) — Setting up and using Claude Code in this repo: project files, skills, agents.
