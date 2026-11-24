---
title: HTTP API reference
summary: The HTTP API reference rendered from a project's committed web API schema, with one page per schema version, resolved `web-api:` links and a check that the committed schema is up to date.
layer: behavior
status: [specified, implemented]
milestone: web-api-reference
priority: must
components: [site, checks]
tags: [requirements, reference, web-api]
related:
  - behavior/requirements.md
  - behavior/site.md
  - behavior/code-reference.md
  - meta/linking.md
---

# HTTP API reference

A project with a web API commits its schema (an OpenAPI file) to the repo, and docspecsite renders the reference from it.
Until this is built, `docspecsite check` reports every `web-api:` link as a problem, since it cannot be resolved.

## Requirements

These requirements are part of the [DSR-n](../meta/glossary.md#dsr-n) numbering listed in [requirements.md](requirements.md):

- **DSR-26** The HTTP API reference is rendered from the web API schema **committed in the repo**, one page per commit that changed the schema, with the same version picker and old-version warning as other docs.
- **DSR-27** A check fails when the committed web API schema is out of date with the code.

And the part of [DSR-13](code-reference.md#requirements) about `web-api:` links: a `web-api:<operationId>` link resolves to that operation on the reference page, and `docspecsite check` reports operation ids that are not in the current schema ([meta/linking.md](../meta/linking.md#code-links)).

### Looking up the schema

> **Built.**

- **DSR-30** A query command for agents: print one part of the committed web API schema (an operation, the operations of a tag, or a schema) as Markdown with references resolved, without rendering.
  It is not a docspecsite command: a project provides it with its own lookup tools, chosen for its API schema.

## Not decided yet

- Where the schema file lives and how a project names it in `docspecsite.toml`.
- How DSR-27 runs: docspecsite cannot export a schema from a project's code, so the project's own tooling has to provide it.
