---
title: "BASE-0003: docker compose as the single entry point"
summary: Every project task (docs, dev stack, tests, CI steps) is defined as a docker compose service, so the host needs only Docker and git.
layer: architecture
status: implemented
milestone: foundation
priority: must
decision: accepted
date: 2026-11-16
components: [dev-environment]
tags: [adr, docker, compose]
related:
  - architecture/dev-environment.md
---

# BASE-0003: docker compose as the single entry point

## Context

The project should be runnable on any machine and in CI with the same commands, and the same artifacts should be what is released.

## Options considered

1. **Host-native tooling** (language toolchains, local databases) — fastest iteration, but drifts between machines and CI.
2. **Dev containers** — good IDE integration, but tied to specific editors.
3. **docker compose services** for every task — one definition used by humans, agents and CI.

## Decision

Option 3.
`compose.yaml` defines tool services (docs) and the application stack; native toolchains stay optional for speed and IDE support. Design: [dev-environment.md](../dev-environment.md).

## Consequences

- Docker is mandatory for contributors.
- File ownership in bind mounts must be handled (containers run as host UID/GID).
