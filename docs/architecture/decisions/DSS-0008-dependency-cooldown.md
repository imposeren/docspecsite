---
title: "DSS-0008: A 14-day dependency cooldown in the uv project"
summary: The project's uv settings set a relative 14-day cooldown with a uv version floor, so uv.lock only takes package versions uploaded at least two weeks before the resolution that wrote it, for direct and transitive dependencies alike.
layer: architecture
status: specified
decision: accepted
date: 2026-11-26
milestone: hardening
priority: should
components: [dev-environment, distribution]
tags: [adr, python, uv, security]
related:
  - architecture/dev-environment.md
  - architecture/decisions/DSS-0002-single-python-toolchain.md
---

# DSS-0008: A 14-day dependency cooldown in the uv project

## Context

docspecsite's dependencies are locked in one `uv.lock` ([DSS-0002](DSS-0002-single-python-toolchain.md)), and the Docker image other repos build installs exactly that lock.
A malicious or broken release that lands in the lock therefore reaches every contributor, the commit hooks and every project that builds the image.

PyPI resolves over 90% of malware reports within 24 hours of the report ([PyPI blog, "Safety & Security Engineer: First Year in Review", 2024-08-16](https://blog.pypi.org/posts/2024-08-16-safety-and-security-engineer-year-in-review/), checked 2026-11-26).
How soon after upload a bad release is reported is not measured there; that most are reported within a few days is an **assumption** this decision rests on.

So far the defence has been a habit: when a version is picked, it should be at least two weeks old.
A habit is not checked, is easy to forget during `uv lock --upgrade`, and does not cover the transitive dependencies a resolution pulls in.

uv supports a **dependency cooldown**: resolution can ignore every distribution uploaded within a span before the resolution runs ([uv docs at tag 0.13.7, "Dependency cooldowns"](https://github.com/astral-sh/uv/blob/0.13.7/docs/concepts/resolution.md#dependency-cooldowns), checked 2026-11-26).
The facts this decision rests on, from that page and trial locks on 2026-11-26:

- The lock stores the span, not a date, so it does not go stale as time passes; uv resolves again only on an upgrade or a changed requirement.
- Single packages can be exempted from the span, or given a shorter one.
- A uv too old to read a span does not use it; a version floor in the project settings makes most such versions stop instead ([dev-environment.md](../dev-environment.md#dependency-cooldown) has the versions).

A solution should be:

- checked automatically, not left to a habit;
- applied to transitive dependencies as well as direct ones;
- the same for every contributor and tool that writes the lock;
- low upkeep on each upgrade.

## Options considered

1. **No cooldown (status quo).**
   The two-week habit stays informal.
   Nothing to configure, and the newest releases are available at once.
   Lost because nothing checks the habit and it does not reach transitive dependencies.
2. **A relative span in the project's uv settings, with a uv version floor.**
   Every resolution of `uv.lock`, by any contributor or tool, applies the same cooldown to direct and transitive dependencies, and the setting is reviewed and versioned with the code.
   Upgrades stay a single command, and a fix needed sooner is let through per package.
   Weaknesses: a resolution run at a different time can give a different lock, so a lock is not reproducible the way option 4's is; every uv that locks must support spans, hence the floor; and when a requirement can only be met by a version inside the span, uv's resolution error does not say that the cooldown excluded the newer versions.
3. **A machine-wide setting in each contributor's own uv configuration.**
   Covers every project on one machine.
   Lost because it is not shared with other contributors or with any automation that locks, so the lock's safety depends on who ran `uv lock`.
4. **A fixed date in the project's uv settings, bumped by hand.** The close second.
   Fully reproducible: the same inputs always give the same lock.
   Lost because each upgrade first needs a date edit; a forgotten bump freezes the dependencies, and a hurried one gives no cooldown at all.

## Decision

Option 2: a relative 14-day cooldown set in the project's uv settings, with a uv version floor.
A shared, automatic cooldown outranks full reproducibility here; the per-package exception is the escape hatch when a newer release is needed sooner.
Fourteen days matches the habit it replaces and leaves room beyond the few days assumed above; if bad releases turn out to be found later than that, the span is lengthened.
How it is set up, and how a package is exempted: [dev-environment.md](../dev-environment.md#dependency-cooldown).

## Consequences

- `uv lock` and `uv lock --upgrade` never take a version uploaded in the last 14 days, for direct or transitive dependencies; the image and `uv sync` follow the lock, so they get the same versions.
- The first lock after the setting is added, and any later upgrade, may move a package released in the last 14 days back to an older version.
- Contributors need a uv at or above the floor; the image already ships one.
- A security fix needed sooner, or a requirement only a newer version meets, is let through for its package alone, as [dev-environment.md](../dev-environment.md#dependency-cooldown) describes.
- Git dependencies are not covered; docspecsite has none.
- The cooldown governs resolving `uv.lock` only.
  Environments that do not install from the lock, such as the one prek builds for the `docs-check` hook in other repos, `uvx`, or `uv run --with`, are built by the consuming repo's own tooling, which docspecsite does not control; they stay outside this decision, and consumers get the cooldown through the Docker image, which installs the lock.
