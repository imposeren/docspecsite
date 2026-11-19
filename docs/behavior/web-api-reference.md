---
title: HTTP API reference
summary: Planned — the HTTP API reference rendered from a project's committed web API schema, with one page per schema version, resolved `web-api:` links and a check that the committed schema is up to date.
layer: behavior
status: specified
milestone: web-api-reference
priority: must
components: [site, checks]
tags: [requirements, reference, web-api]
related:
  - behavior/requirements.md
  - meta/linking.md
---

# HTTP API reference

A project with a web API commits its schema (an OpenAPI file) to the repo, and docspecsite renders the reference from it.
Until this is built, `docspecsite check` reports every `web-api:` link as a problem, since it cannot be resolved.

These requirements continue the numbering of [requirements.md](requirements.md):

- **DS-26** The HTTP API reference is rendered from the web API schema **committed in the repo**, one page per commit that changed the schema, with the same version picker and old-version warning as other docs.
- **DS-27** A check fails when the committed web API schema is out of date with the code.

And the part of DS-13 about `web-api:` links: a `web-api:<operationId>` link resolves to that operation on the reference page, and `docspecsite check` reports operation ids that are not in the current schema ([meta/linking.md](../meta/linking.md#code-links)).

## Not decided yet

- Where the schema file lives and how a project names it in `docspecsite.toml`.
- How DS-27 runs: docspecsite cannot export a schema from a project's code, so the project's own tooling has to provide it.
