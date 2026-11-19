---
title: Versioning and releases
summary: Releases are named with semantic versions (vMAJOR.MINOR.PATCH) whose meaning is tied to the compatibility of the project's public interface; the git tag is the only place a version is defined, and the build reads it from the tag.
layer: architecture
status: specified
components: [deploy]
tags: [versioning, releases, semver]
related:
  - architecture/decisions/BASE-0005-semver-from-git-tags.md
---

# Versioning and releases

A **release** is a git tag `vMAJOR.MINOR.PATCH` on `main` ([SemVer](https://semver.org/), semantic versioning).
Why this scheme: [BASE-0005](decisions/BASE-0005-semver-from-git-tags.md) ([architecture decision record](../meta/glossary.md#adr)).

## What each part means

The version describes compatibility of the project's **public interface**: whatever others depend on, such as an HTTP API, a library's programming interface, a command line or a file format.
The project's own architecture docs say what its public interface is and how an incompatible change is recognized.

| Bump | When |
| -- | -- |
| **MAJOR** | The public interface changes incompatibly: something is removed or renamed, an input becomes required, an output changes shape. |
| **MINOR** | New features, including backward-compatible additions to the interface. |
| **PATCH** | Fixes and internal changes with no new features and an unchanged interface. |

Before `v1.0.0`, the interface is not considered stable: incompatible changes bump MINOR.

## Where the version lives

- The **git tag** is the only source of truth; no file in the repo holds the version.
- The build derives the version from the tag, so what it builds reports the same version.
- Builds from untagged commits get a development version derived from the last tag and the commit id.
