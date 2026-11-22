---
title: Working from specs
summary: How agents (and people) design new work with the user, turn specified docs into code, write or change specs, and record technical decisions as ADRs.
layer: agents
status: implemented
components: [agents]
tags: [agents, workflow, adr, project-management]
related:
  - meta/lifecycle.md
  - architecture/decisions/index.md
---

# Working from specs

## Implementing a `specified` doc

1. Read it and its counterparts ([reading-strategy.md](reading-strategy.md)).
   Scenarios are the acceptance criteria.

2. If anything needed to build it is ambiguous or missing, **fix the spec first** (or ask) — don't encode a guess only in code.

3. Write tests from the scenarios first, then the code:

   - a change to existing logic starts with a test that fails — run it and see it fail before changing the code;
   - new code (a new function, class or module) also gets its tests first, but don't run them while they can only fail on a missing import or attribute; run them once the code exists.

   Add `Docs: <path>` lines to docstrings of the main code elements, and `code:` entries to the doc.
   If the project validates the references in its code (`Docs:` lines, and references to other code in docstrings), run the code check once the implementation is done (`docker compose run --rm docs check --optional-checks code`).

4. Set the doc's `status: implemented` (and its parents' if all their children are done).
   When only some sections are built, the doc's `status` lists the statuses that are left and the sections not built yet keep their [status notes](../meta/lifecycle.md#status-notes); a built section loses its status note.

5. Write or update the [guides](../guides/index.md) for any new procedure it introduces (setup, migration, release step): whoever builds a thing writes its guide.

6. Run the checks — stage the change and run `prek run` (the commit hooks, on the staged files only), and the tests — then get the change reviewed before proposing a commit ([quality-gate.md](../architecture/quality-gate.md#review-before-commit)):

   - a review in a fresh context (in Claude Code, `/code-review` or an equivalent review skill) checks the change against the docs it implements: does the code do what they say, are statuses honest, does nothing contradict an `implemented` doc;
   - a change to behavior is also checked live: run the changed command or endpoint and look at its output;
   - fix what the review finds, and say in the summary what it found and what was left; if the review was skipped, say so and why.

## Changing what the system does

Edit the docs to describe the **new target state** in every layer concerned (behavior → scenarios → ui → architecture), set them to `changed` (for what the code already implements in an older form) or `specified` (for what is new), or mark only the sections that change ([meta/lifecycle.md](../meta/lifecycle.md#partly-built-docs)), and commit them together with a subject like `spec: <what changed>`.
That commit is the change request; implementing it follows the steps above.

## Designing before specifying

New design work (a feature, a component, a cross-cutting change) is first worked out with the user in a **design note**, and only then written down as specs.
In Claude Code this is the superpowers `brainstorming` skill, then `writing-plans`; the rules below replace those skills' default locations and steps.

1. **Design note:** `notes/design/YYYY-MM-DD-<topic>-design.md`.
   One design may cover several specs; it ends with the list of docs to create or change (path and layer; the `spec-writer` agent writes them).
   It is a disposable working note: `notes/` is not in git, and nothing under `docs/` links to it.
2. **Specs:** once the user approves the design, the listed docs are written as usual (the [meta rules](../meta/index.md), the agents' own rules), with the note as input, not as the spec.
   They stand on their own and don't copy the note's structure; technical choices become `proposed` ADRs ([below](#decision-records-adrs)).
   Where the note conflicts with existing docs or ADRs, the conflict goes to the user instead of the note winning.
   Then a fresh subagent that has not seen the design or the code reads the behavior, scenario and ui docs the `spec-writer` lists in its report, and rewrites what a non-developer user would not understand.
   Its rewrite is checked for meaning: another fresh subagent compares the text before and after it and lists every rule, case, condition, default or message that was lost, added or changed; each one is fixed or goes to the user.
   Then a builder check on the specs: a fresh subagent that can read the code, and look up its symbols and their uses with the language server where the project has one, reads the new and changed specs as the planner of their implementation would, and lists every place where it would have to guess: a missing message or rule, a case two requirements answer differently, a planned code location that does not fit the code; each one is fixed in the spec or goes to the user.
   The user reviews the specs after these steps, so they read the text once, in its final form; each step is its own commit on the spec branch, so its changes show as a plain diff.
3. **Plan:** only once those docs are `specified`, an implementation plan in `notes/plans/YYYY-MM-DD-<topic>.md` that cites them as its spec; then [implementing](#implementing-a-specified-doc) as above.

### Thinking ahead

Every design, in a design note or written straight into specs, questions each assumption it would fix in place:

- **Future readiness.** Where the design depends on one tool, provider, format or service (a version control system, a database, a host, a file format), ask whether a second one is plausible.
  If it is, design the seam: a small interface the rest talks to, with today's choice as one implementation, and the way another one is added (built in, or registered by a separate package).
  If the seam is not worth building yet, the design must not block it, and a later-milestone doc proposes it.
- **Personal preference.** A value that another reasonable project could choose differently (a directory name, a file name, a naming pattern, a limit, a default behavior) is a setting with a sensible default, not a constant.
  Leave a value fixed only when changing it would break the method or other projects; the doc says why.
- **Names that leave room.** A generic word (backend, plugin, provider, handler, source) gets the domain it belongs to, in terms, headings, and settings or code names outside a namespace, whenever another thing of its kind is plausible.
- Group settings by what they belong to: options of one part go in its own section (for example `[versioning.git]` for the git backend), and an option that only applies with another one goes under it.

## Writing a new doc

Use the `/new-doc` skill (Claude Code) or copy a [template](../meta/templates/index.md); place it at the mirrored path; list it in the parent `index.md` with a one-line description; add `related:` links both ways.

## Decision records (ADRs)

An ADR records **one technical decision**: context, options considered, what was chosen, consequences.
Unlike other docs it keeps its reasoning forever; when a decision changes, a **new** ADR supersedes the old one ([meta/lifecycle.md](../meta/lifecycle.md#adrs)).
Its ID uses this repo's prefix and the next number of that prefix ([meta/structure.md](../meta/structure.md#adr-ids)).

Agents:

- **check** existing ADRs before proposing a technology or approach — don't re-litigate an `accepted` one without new information;
- when a task needs a decision no ADR covers (new library, service, data store, protocol, infra change), **write an ADR with `decision: proposed`**, options and a recommendation, and ask the maintainer instead of deciding silently in code;
- when an accepted ADR is implemented, set its `status: implemented`.

Small, easily reversible choices inside one module do not need an ADR.
