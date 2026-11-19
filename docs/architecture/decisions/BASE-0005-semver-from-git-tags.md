---
title: "BASE-0005: Semantic versions tied to public-interface compatibility, defined only by git tags"
summary: Releases are tagged vMAJOR.MINOR.PATCH, with MAJOR reserved for incompatible changes to the project's public interface; the tag is the single source of truth and the build reads the version from it.
layer: architecture
status: specified
decision: accepted
date: 2026-11-16
components: [deploy]
tags: [adr, versioning, releases, semver]
related:
  - architecture/versioning.md
---

# BASE-0005: Semantic versions tied to public-interface compatibility, defined only by git tags

## Context

Releases need names, and what a version means has to be defined.
A project has a public interface that others depend on (an HTTP API, a library, a command line, a file format), so "incompatible change" is something a release can be judged by.
Package managers can bump a version in a project file but do not choose a scheme.

## Options considered

**Scheme**

1. **SemVer** (`v1.4.2`): MAJOR/MINOR/PATCH by compatibility; meaningful when something depends on you.
2. **CalVer** (`v2026.11.0`): by release date; simple for continuously deployed apps, but says nothing about compatibility.
3. **No versions**, commit ids only: releases and rollbacks have no names.

**Source of truth**

1. **The git tag**, with the build deriving the version from it: nothing to edit per release.
2. **A project file** (such as a package manifest), bumped and then tagged: two places to keep in sync.

## Decision

- **SemVer**, with MAJOR defined by incompatible changes to the project's public interface; before `v1.0.0`, incompatible changes bump MINOR.
- **The git tag** `vMAJOR.MINOR.PATCH` on `main` is the only source of truth; the build derives the version from it.
- Details: [versioning.md](../versioning.md).

## Consequences

- Whoever tags a release decides the bump by checking how the public interface changed since the last tag; a check can later flag a change that looks incompatible.
- No version-bump commits.
- How each project recognizes an incompatible change (e.g. a diff of a committed API schema) is part of its own architecture docs.
