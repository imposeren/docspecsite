# docspecsite — Claude Code guide

docspecsite checks a repo's docs against the docs-driven method and renders every version of every doc from git history as a static site; projects use it through a prek hook and a Docker image pinned to a release tag. Repo: https://github.com/imposeren/docspecsite.

**This project is documentation-driven: `docs/` is the spec. Code follows docs.**

## Start here

- Doc map: `docs/index.md`.
  Agent guide: `docs/agents/index.md` (read it before non-trivial work).
- Read **summaries first** and go deeper only as needed: `docs/agents/reading-strategy.md`.
- The same part of the system lives at the **same relative path** in each layer: `docs/behavior/…` (what), `docs/scenarios/…` (exact cases, Gherkin), `docs/architecture/…` (how), plus decisions in `docs/architecture/decisions/`.
- The module pages of `docs/reference/code/` are **generated** during the build from the code and docstrings; the hand-written `index.md` is the entry page.
  Link to them with `code:<dotted.path>`.
- Glossaries: `docs/meta/glossary.md` (doc terms), `docs/behavior/glossary.md` (docspecsite terms), `docs/architecture/glossary.md` (technical).
  Spell out or link terms on first use.
- Step-by-step procedures: `docs/guides/`. Milestones: `docs/roadmap.md` (docs carry `milestone` + `priority`).
- How docs are written: `docs/meta/index.md`. Templates: `docs/meta/templates/`.
  `docs/meta/` and `docs/agents/` are a copy of the template's; change them in the template first, then sync them here.
- ADRs are numbered `<PREFIX>-NNNN`; this repo's prefix is `DSS` (`adr-prefix` in `docspecsite.toml`), and `BASE-*` ADRs come from the template (`external-adr-prefixes = ["BASE"]`) (`docs/meta/structure.md#adr-ids`).
- A rule that docspecsite enforces lives in two places: the rule in the template's `docs/meta/`, the enforcement here (`docs/architecture/quality-gate.md#review-before-commit`).

## Hard rules

1. Docs before (or with) code; code must not contradict an `implemented` doc.
2. **Never delete or rename files under `docs/`.**
   Replace them with a redirect doc (`status: redirect`, `redirect_kind:`, `redirect_to:`, `reason:`).
3. Write docs as the target state in present tense.
   No TODOs, change requests or bug reports in docs.
4. Keep `status` honest: `specified` = to do, `changed` = to do over an older form, `implemented` = true in the code; a partly built doc lists several and gives the sections that differ status notes (`docs/meta/lifecycle.md#partly-built-docs`).
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
docker compose run --rm test                               # tests (pytest arguments may follow)
docker compose run --rm lint                               # ruff check
docker compose run --rm format                             # ruff format
docker compose run --rm typecheck                          # pyrefly, strict
docker compose run --rm docs-check                         # validate docs (from this source)
docker compose run --rm docs check --optional-checks code  # also validate references in the code (if the project uses it)
docker compose run --rm docs list --status specified       # what's left to do
docker compose run --rm docs list --status changed         # what's left to redo
docker compose run --rm docs-build && docker compose up docs-serve   # site on http://127.0.0.1:8071
docker compose build dev                                   # after a change to pyproject.toml or uv.lock
docker build -t docspecsite:runtime .                      # the image other repos build
prek run                                                   # commit hooks on the staged change
```

Commit hooks run `pyrefly` and `docspecsite check` through `uv run` on the host; `uv run <tool>` is also a faster shortcut for the commands above.

Status: check, list, backlinks, build, the code reference, the Docker image and the prek hook work; the HTTP API reference is specified but not built.

## Agents and skills

- `spec-writer` agent — the spec in every layer: behavior, scenarios, ui and architecture docs, `proposed` ADRs, external platform facts (no code).

- `/new-doc` — scaffold a doc at the right mirrored path with valid front matter.
