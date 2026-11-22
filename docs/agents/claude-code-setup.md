---
title: Claude Code setup
summary: How to use Claude Code in this repo — the project files it loads, the doc skill and the specialized agents; project-specific tools are listed in the architecture docs.
layer: agents
status: implemented
components: [agents]
tags: [agents, claude, setup]
related:
  - agents/working-from-specs.md
  - agents/code-lookup.md
---

# Claude Code setup

## Setup

1. Install [Claude Code](https://claude.com/claude-code) and start it in the repo root; it loads `CLAUDE.md`, which points to this layer.
2. Install the project's own tools (formatters, hooks, review gates), as listed in the architecture docs.
3. Install the language server the project enables as a Claude Code plugin, so agents can look up code ([code-lookup.md](code-lookup.md)).

## Daily use

- Hand Claude a doc as the task: "implement docs/behavior/<area>/<capability>.md".
- `/new-doc`: scaffold a new doc at the right path with correct front matter.
- Use the specialized agents below for spec and design work, so each runs with a focused context and limited edit rights.

## Project Claude files

| Path | Purpose |
| -- | -- |
| `CLAUDE.md` | Always-loaded entry point: project, hard rules, commands, pointers. |
| `.claude/skills/new-doc/SKILL.md` | The `/new-doc` skill. |
| `.claude/agents/spec-writer.md` | Subagent for the spec in every layer: behavior, scenarios, ui and architecture docs, `proposed` ADRs (architecture decision records) and external platform facts; doesn't touch code. |
| `.claude/settings.local.json` | Personal settings (gitignored). |

Guides are written by whoever builds the thing they describe ([working-from-specs.md](working-from-specs.md)), not by a dedicated agent.
