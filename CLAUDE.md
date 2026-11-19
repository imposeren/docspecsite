# docspecsite — Claude Code guide

docspecsite checks a repo's docs and renders every version of every doc from git history to a static site.
Repo: https://github.com/imposeren/docspecsite.

**This project is documentation-driven: `docs/` is the spec. Code follows docs.**

## Start here

- Doc map: `docs/index.md`.
  Agent guide: `docs/agents/index.md` (read it before non-trivial work).
- Read **summaries first** and go deeper only as needed: `docs/agents/reading-strategy.md`.
- The same part of the system lives at the **same relative path** in each layer: `docs/behavior/…` (what), `docs/scenarios/…` (exact cases, Gherkin), `docs/architecture/…` (how), plus decisions in `docs/architecture/decisions/`.
- `docs/reference/code/` and `docs/reference/web-api/` are **generated** (from the code and docstrings, and from the committed HTTP API schema). Never hand-edit them. `docs/reference/external/` is hand-written: facts about the third-party platforms the project depends on.
  Link to it with `code:<dotted.path>` and `web-api:<operationId>`.
- Glossaries: `docs/meta/glossary.md` (doc terms), `docs/behavior/glossary.md` (product), `docs/architecture/glossary.md` (technical).
  Spell out or link terms on first use.
- Hosting and operations: `<where they are documented, if not in this repo>` (delete this line if they are in this repo).
- Step-by-step procedures: `docs/guides/`. Screens and flows: `docs/ui/`. Milestones: `docs/roadmap.md` (docs carry `milestone` + `priority`).
- How docs are written: `docs/meta/index.md`. Templates: `docs/meta/templates/`.
- ADRs are numbered `<PREFIX>-NNNN`; this repo's prefix is `adr-prefix` in `docspecsite.toml`, and `BASE-*` ADRs come from the template, listed in `external-adr-prefixes` (`docs/meta/structure.md#adr-ids`).

## Hard rules

1. Docs before (or with) code; code must not contradict an `implemented` doc.
2. **Never delete or rename files under `docs/`.**
   Replace them with a redirect doc (`status: redirect`, `redirect_kind:`, `redirect_to:`, `reason:`).
3. Write docs as the target state in present tense.
   No TODOs, change requests or bug reports in docs.
4. Keep `status` honest: `specified` = to do, `implemented` = true in the code.
5. A technical choice not covered by an ADR (architecture decision record, in `docs/architecture/decisions/`) → write a `decision: proposed` ADR and ask.
6. Every doc has front matter (`title, summary, layer, status, components, tags, related`); components come from `docs/architecture/components.md`.
7. Body links are relative to the file; front-matter paths are relative to `docs/`.
   All links must resolve.
8. Don't commit unless asked.
   Each commit becomes a permanent doc version, so subjects for doc changes describe the spec change (`spec: …`).
9. Before handing code over for review or proposing a commit, run the commit hooks (`prek run` on the staged change) and the tests, get it reviewed in a fresh context against the docs it implements, and check behavior changes live (`docs/agents/working-from-specs.md#implementing-a-specified-doc`, step 6).
   Say if the review was skipped, and why.

## Design and planning (superpowers skills)

Design → specs → plan, as in `docs/agents/working-from-specs.md#designing-before-specifying`; it overrides the skills' defaults.
Design notes and plans go to `notes/design/` and `notes/plans/` (not committed), never `docs/superpowers/`.

## Commands (via docker compose; see docs/architecture/dev-environment.md)

```
docker compose run --rm docs-check                         # validate docs
docker compose run --rm docs list --status specified       # what's left to do
docker compose run --rm docs-build && docker compose up docs-serve   # site on http://127.0.0.1:8071
```

Status: <one line on what works today and what is specified but not built.>

## Agents and skills

- `spec-writer` agent — behavior, scenarios and ui docs (no code, no architecture).

- `architect` agent — architecture docs, `proposed` ADRs, external platform facts (no code).

- `/new-doc` — scaffold a doc at the right mirrored path with valid front matter.
