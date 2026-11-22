---
title: Versions from tags only
summary: Planned — a setting that makes a doc's versions the ones current at the repo's tags, so a long history gives far fewer versions.
layer: behavior
status: specified
milestone: later
priority: could
components: [site]
tags: [requirements, versioning]
related:
  - behavior/requirements.md
  - meta/versioning.md
---

# Versions from tags only

By default every commit that touches a doc is a version of it ([DS-4](requirements.md#versioning)), so a doc with a long history has many versions, pages and diffs.
A project that releases with tags can choose to keep only the versions that were current at a tag.

This requirement continues the numbering of [requirements.md](requirements.md):

- **DS-38** With the tag setting on, a doc's versions are, for each tag on the ref's first-parent history, the newest commit at or before the tag that touches the doc. A tag whose commit does not touch the doc keeps the version the doc had then, and tags that keep the same version give it once.

## Not decided yet

- The setting's name, and whether it can limit the tags by a pattern.
- Whether commits after the newest tag show as versions too.
