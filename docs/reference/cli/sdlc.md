# `dna sdlc`

Declarative lifecycle tracking (Roadmap/Epic/Feature/Story/Issue).

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna sdlc --help`.

## `dna sdlc adr`

ADR-level operations (Architecture Decision Records).

```text
dna sdlc adr [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc adr accept`

Mark ADR status: accepted; stamp accepted_at.

```text
dna sdlc adr accept [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc adr create`

Create a new ADR.

```text
dna sdlc adr create [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--body` | Markdown body (→ spec.body / ADR.md). |
| `--consequences` | Trade-offs that follow (→ spec.consequences). |
| `--context` | WHY we needed to decide (→ spec.context). _(default: `Sentinel.UNSET`)_ |
| `--decision` | WHAT we decided (→ spec.decision). _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--status` | _(default: `proposed`)_ |
| `--title` | Decision headline (→ spec.title). _(default: `Sentinel.UNSET`)_ |

### `dna sdlc adr deprecate`

Mark ADR status: deprecated.

```text
dna sdlc adr deprecate [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc adr propose`

Mark ADR status: proposed.

```text
dna sdlc adr propose [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc adr supersede`

Mark ADR status: superseded by another ADR.

```text
dna sdlc adr supersede [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--by` | ADR name that supersedes this one (→ spec.superseded_by). _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc backfill`

Back-fill Spec/Plan docs from a directory of markdown files.

File naming convention: ``YYYY-MM-DD-<slug>.md`` extracts the date.
Title is the first ``# Heading`` line. Status is parsed from
``**Status**: X`` if present, else uses --default-status.
Authors from ``**Author**: A, B`` if present.

PATTERN is the spec-driven methodology label (free-form):
superpowers, bmad, droid, rfc, adr, custom.

```text
dna sdlc backfill [OPTIONS] PATTERN
```

**Arguments**

| Argument | Required |
| --- | --- |
| `PATTERN` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--default-status` | _(default: `accepted`)_ |
| `--dry-run` | Preview without writing. |
| `--from` | Directory containing markdown files to back-fill from. _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--kind` | Generate Spec or Plan docs (auto: infer from path — specs/ → Spec, plans/ → Plan). _(default: `auto`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc brief`

Session-start briefing — one screen with everything the next session
needs to bootstrap context: in-progress work, open spikes, recent
AgentSessions, recent LessonLearned, and open high/critical Issues.

The cross-session "recall in" command: run it at the START of a session
(yours or another agent's) instead of `current` + `session list` +
`remember` separately. Read-only.

```text
dna sdlc brief [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | Structured output for programmatic use. |
| `--limit` | Max items in the recent-sessions / recent-lessons sections. _(default: `5`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc bug`

Bug-level operations (factual defects with severity).

```text
dna sdlc bug [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc bug create`

File a new Bug.

```text
dna sdlc bug create [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--body` | Markdown body (→ spec.body / BUG.md). |
| `--desc` | One-line description (→ spec.description; derives title). _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--labels` | Comma-separated labels. |
| `--owner` |  |
| `--related-feature` | Feature name (→ spec.related_feature). |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--severity` | _(default: `medium`)_ |
| `--status` | _(default: `open`)_ |
| `--steps` | Comma-separated repro steps (→ spec.repro_steps). |

### `dna sdlc bug regress`

Mark Bug status: regression (reopened defect).

```text
dna sdlc bug regress [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc bug resolve`

Mark Bug status: resolved; stamp closed_at.

```text
dna sdlc bug resolve [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--resolution` | How was it resolved? (timeline summary). |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc bug start`

Mark Bug status: in-progress.

```text
dna sdlc bug start [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc bug triage`

Mark Bug status: triaged.

```text
dna sdlc bug triage [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc bug wontfix`

Mark Bug status: wont-fix.

```text
dna sdlc bug wontfix [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc changelog`

Release notes per scope (Keep a Changelog + SemVer).

```text
dna sdlc changelog [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc changelog release`

Cut a SemVer release: stamp [Unreleased] as <version> (date=today) and
open a fresh [Unreleased]. Inline --added/... merge in first.

```text
dna sdlc changelog release [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--added` | Keep-a-Changelog 'added' entry (repeatable). _(default: `Sentinel.UNSET`)_ |
| `--changed` | Keep-a-Changelog 'changed' entry (repeatable). _(default: `Sentinel.UNSET`)_ |
| `--deprecated` | Keep-a-Changelog 'deprecated' entry (repeatable). _(default: `Sentinel.UNSET`)_ |
| `--fixed` | Keep-a-Changelog 'fixed' entry (repeatable). _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--removed` | Keep-a-Changelog 'removed' entry (repeatable). _(default: `Sentinel.UNSET`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--security` | Keep-a-Changelog 'security' entry (repeatable). _(default: `Sentinel.UNSET`)_ |
| `--version` | SemVer for this release (e.g. 1.4.0). _(default: `Sentinel.UNSET`)_ |

### `dna sdlc changelog show`

Render the scope's changelog (releases, newest first).

```text
dna sdlc changelog show [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc changelog unreleased`

Accumulate changes under [Unreleased] (cut later with `release`).

```text
dna sdlc changelog unreleased [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--added` | Keep-a-Changelog 'added' entry (repeatable). _(default: `Sentinel.UNSET`)_ |
| `--changed` | Keep-a-Changelog 'changed' entry (repeatable). _(default: `Sentinel.UNSET`)_ |
| `--deprecated` | Keep-a-Changelog 'deprecated' entry (repeatable). _(default: `Sentinel.UNSET`)_ |
| `--fixed` | Keep-a-Changelog 'fixed' entry (repeatable). _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--removed` | Keep-a-Changelog 'removed' entry (repeatable). _(default: `Sentinel.UNSET`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--security` | Keep-a-Changelog 'security' entry (repeatable). _(default: `Sentinel.UNSET`)_ |

## `dna sdlc cite`

Bidirectional citation: adds ref_name to caller.spec.references AND
adds caller_ref to Reference.spec.cited_by.

```text
dna sdlc cite [OPTIONS] REF_NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `REF_NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--from` | Kind/name of the doc that cites this reference (e.g. Spec/2026-05-12-foo). _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc current`

Show every SDLC doc currently in-progress (across Stories,
Features, Epics, Issues). Designed for one-line surface in
Claude Code chat — pipe the IDs into the Studio search (⌘K) to
confirm visually.

Output format (compact, copy-paste-friendly):

    🚧 in-progress now (scope: dna-development)
      📖 s-vibe-commit-trace                "Studio commit_ref link..."
      🚀 f-activity-timeline                "Activity Timeline..."

With ``--json`` returns a structured list for programmatic use.

```text
dna sdlc current [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc demand`

Open a demand: Story + journey-discover + status=in-progress, atomic.

The single entry point the agent's `dna-demand-flow` skill uses to
file new work. Equivalent to running `story create` → `story start`
→ `journey enter discover` in one shot, with consistent IDs and a
single timestamp for the trail across Board / Journey.

```text
dna sdlc demand [OPTIONS] TITLE
```

**Arguments**

| Argument | Required |
| --- | --- |
| `TITLE` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--accept` | Acceptance criterion (repeatable). One bullet per --accept. _(default: `Sentinel.UNSET`)_ |
| `--artifact` | Optional path/URL to a methodology artifact (e.g. spec/plan). |
| `--as` | User-story 'As a <role>' slot. |
| `--consult` | Consult the Tático oracle before creating the Story. Surfaces divergence between user intent and pattern the system observes — doesn't block. |
| `--desc` | Multi-line description. Defaults to TITLE if omitted. |
| `--dod` | Definition-of-Done check (repeatable). One bullet per --dod. _(default: `Sentinel.UNSET`)_ |
| `--epic` | Auto-create the Feature under this Epic if missing (else fails loud). |
| `--feature` | Parent Feature name (must exist in scope). _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--json` | Emit machine-readable JSON with the created IDs. |
| `--methodology` | Method the agent will follow. _(default: `superpowers`)_ |
| `--owner` | _(default: `claude-code`)_ |
| `--priority` |  |
| `--reporter` | Who filed the demand (defaults to actor). |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--slug` | Force a specific Story slug (auto-derived from title otherwise). |
| `--so-that` | User-story 'so that <benefit>' slot. |
| `--want` | User-story 'I want <goal>' slot. |

## `dna sdlc epic`

Epic-level operations (Jira/ADO terminology; was 'milestone' in v1.2).

```text
dna sdlc epic [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc epic ship`

Mark Epic status: done, set closed_at, cascade-close Features whose Stories all done.

```text
dna sdlc epic ship [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc epic show`

Show Epic burndown — features + stories with status counts.

```text
dna sdlc epic show [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc epic-reopen`

Reopen a closed Epic — flip status back to planning.

```text
dna sdlc epic-reopen [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--reason` | Why reopen? _(default: `reopened`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--to` | Status to flip back to (default: planning). _(default: `planning`)_ |

## `dna sdlc extract-decisions`

Walk every Story / Feature / Epic / Issue timeline + promote
pre-existing comments that look like decisions. Pure regex —
zero LLM cost. Idempotent: events already typed as 'decision'
or 'status_change' are untouched.

Useful pra retroativamente capturar o "porquê" das decisões que
foram comentadas como `comment` em vez de `decision` durante a
sessão. Output: rows for each promoted event, then a count.

```text
dna sdlc extract-decisions [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--dry-run` | Print matches but don't write. |
| `--help` | Show this message and exit. |
| `--scope` | Scope to walk. _(default: `dna-development`)_ |

## `dna sdlc feature`

Feature-level operations.

```text
dna sdlc feature [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc feature cancel`

Mark a Feature as cancelled with an explicit reason. Used when
scope shifts and the Feature won't ship — preserves the historical
intent while closing the open-work loop.

```text
dna sdlc feature cancel [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--reason` | Why is the Feature cancelled? _(default: `Sentinel.UNSET`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc feature create`

Create a new Feature.

P4 of f-multi-role followups (s-sdlc-feature-create-cli, 2026-05-16).
Closes the gap where Stories had full CRUD via CLI but Features
required manual YAML editing. Unlike `story create`, no --ac/--dod
guard — Features are roadmap nouns, AC + DoD live at the Story
level.


Example:
  dna sdlc feature create f-eval-experiment-pattern \
    --title "Eval Lab → Experiment (Braintrust pattern)" \
    --desc "Promote draft to immutable EvalExperiment + diff view." \
    --priority high --business-value 850 \
    --labels eval,braintrust-pattern

```text
dna sdlc feature create [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--business-value` | WSJF-style scalar (0-1000) — drives roadmap sort. |
| `--desc` | Multi-line description of the Feature's scope. _(default: `Sentinel.UNSET`)_ |
| `--epic` | Optional parent Epic name (for hierarchy). |
| `--help` | Show this message and exit. |
| `--labels` | Comma-separated labels. |
| `--owner` |  |
| `--priority` |  |
| `--reporter` | Actor who filed it. Defaults to DNA_CLI_REPORTER env or 'claude-code'. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--status` | _(default: `discovery`)_ |
| `--target-milestone` | Milestone name this Feature is scheduled into. |
| `--target-package` | Owner/name of the Genome this Feature targets (for the per-Genome roadmap widget). |
| `--title` | Short title shown on roadmap cards. _(default: `Sentinel.UNSET`)_ |

### `dna sdlc feature narrate-all`

Seed `Feature.spec.narrative_line` deterministically across
every Feature that lacks one. Walks children Stories per Feature
and synthesizes a Portuguese past-tense summary. Zero LLM cost.

Default: skip Features that already have a narrative_line
(avoid clobbering hand-curated prose). Pass --overwrite to
re-seed everything.

```text
dna sdlc feature narrate-all [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--only-empty` | Only update Features without an existing narrative_line. |
| `--overwrite` | Force overwrite even if Feature already has a narrative_line. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc feature narrative`

Update Feature.spec.narrative_line — agent-curated 1-sentence
semantic summary shown next to the Feature in Studio's narrative
swimlane. Past-tense voice ("agent shipou X, descobriu Y").

```text
dna sdlc feature narrative [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--line` | One-sentence prose summary of what this Feature has been DOING. _(default: `Sentinel.UNSET`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc feature reopen`

Reopen a closed/cancelled Feature — flip status back to
discovery (or specified). Mirror of feature cancel.

```text
dna sdlc feature reopen [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--reason` | Why reopen? _(default: `reopened`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--to` | Status to flip back to (default: discovery). _(default: `discovery`)_ |

### `dna sdlc feature ship`

Cascade-close a Feature: verify all children Stories are ``done``,
then flip ``status`` to ``done`` + auto-stamp commit_ref + summary
in the timeline. Mirrors ``epic ship`` semantics.

```text
dna sdlc feature ship [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--allow-no-produces` | Silencia o warn de outputs vazios (produces[] + back-refs). |
| `--commit-ref` | Git SHA shipped with this Feature. Auto-detected from HEAD when omitted. |
| `--force` | Mark done even when children Stories aren't all done. |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--summary` | One-line description (lands on the timeline event). |

### `dna sdlc feature show`

Show Feature detail — header + child-Story rollup (status counts + list).

Mirrors `epic show` (i-041) — without it, agents fell back to reading raw
YAML to understand a Feature's state.

```text
dna sdlc feature show [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc feature start`

Move a Feature `discovery` → `in-development` (read-modify-write).

Unlike `feature create` (a full overwrite that would clobber the doc),
this preserves every other field (description, epic, priority,
business_value, labels, …) and stamps a `status_change` event. Use it
when work has clearly started on a Feature still parked in `discovery`.

```text
dna sdlc feature start [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc hooks`

Git hooks that close the git↔SDLC loop (Work-Item trailers).

```text
dna sdlc hooks [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc hooks install`

Wire the repo's versioned hooks dir into this clone.

Sets ``git config core.hooksPath scripts/git-hooks`` — from then on
every ``git commit`` runs the versioned ``prepare-commit-msg``, which
stamps ``Work-Item:`` + the dna-sdlc[bot] provenance trailer whenever
a Story is active (``dna sdlc story start``).

```text
dna sdlc hooks install [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc hooks status`

Show the symbiosis wiring: hooksPath, hook file, active story, coauthor.

```text
dna sdlc hooks status [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc hooks uninstall`

Remove the ``core.hooksPath`` wiring (git falls back to .git/hooks).

```text
dna sdlc hooks uninstall [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

## `dna sdlc initiative`

Initiative-level operations (1-2 quarter investment unit).

Atlassian Jira Align hierarchy: Theme/OKR → **Initiative** → Epic →
Feature → Story → Task. For roadmaps where Epic is granular too far
for C-level strategy review.

```text
dna sdlc initiative [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc initiative cancel`

Cancel an Initiative with a reason.

```text
dna sdlc initiative cancel [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--reason` | Short cancel reason (mandatory). _(default: `Sentinel.UNSET`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc initiative create`

Create a new Initiative.


Example:
  dna sdlc initiative create i-design-system-overhaul-20260526 \
    --title "DNA Studio Design System Overhaul" \
    --desc "Theme Kind + 22 viewers + Cmd+K + cross-device sync." \
    --status done \
    --epic e-helix-extras --epic e-theme-system \
    --outcome-metric "Studio usability score" \
    --target-value "5 Features done · 26 Stories" \
    --priority highest --business-value 850

```text
dna sdlc initiative create [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--business-value` | WSJF-style scalar 0-1000 — drives roadmap sort. |
| `--desc` | Multi-paragraph description of the Initiative goal. _(default: `Sentinel.UNSET`)_ |
| `--epic` | Epic name this Initiative groups. Repeatable. _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--horizon-end` | End of horizon, ISO date. |
| `--horizon-start` | Start of horizon, ISO date (e.g. 2026-Q3 start). |
| `--labels` | Comma-separated labels. |
| `--outcome-metric` | The KR / metric this initiative is targeted at. |
| `--owner` | Actor name accountable (typically PM or Product Lead). |
| `--priority` | Board priority. |
| `--reporter` | Actor who filed it. Defaults to DNA_CLI_REPORTER or claude-code. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--status` | _(default: `proposed`)_ |
| `--target-value` | e.g. '+30% MAU' or '<200ms p95'. |
| `--theme-ref` | Optional Theme/OKR Objective slug (upstream OKR). |
| `--title` | Headline shown on roadmap / cards. _(default: `Sentinel.UNSET`)_ |

### `dna sdlc initiative ship`

Mark an Initiative as done.

```text
dna sdlc initiative ship [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc issue`

Issue-level operations.

```text
dna sdlc issue [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc issue comment`

Append a finding / decision to an Issue timeline without changing status.

Mirrors `story comment` / `spike comment` — bugs accrue investigation notes
+ root-cause decisions over their arc (report→triage→fix→resolve), and that
running trail belongs on the timeline (the FOCUS feed + audit), not only in
the final `resolve` resolution text.

```text
dna sdlc issue comment [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--body` | The comment / finding / decision text. _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--type` | Defaults to 'comment'; decision-shaped bodies auto-promote. |

### `dna sdlc issue file`

File a new Issue with auto-incremented i-NNN-<slug> name.

```text
dna sdlc issue file [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--desc` | _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--owner` |  |
| `--related-feature` | Feature name (optional). |
| `--related-finding` | Finding name (optional, eval-derived). |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--severity` | _(default: `medium`)_ |
| `--slug` | Short kebab-case slug, e.g. 'date-postgres-bug'. _(default: `Sentinel.UNSET`)_ |
| `--type` | _(default: `bug`)_ |

### `dna sdlc issue resolve`

Mark Issue status: resolved, set closed_at + optional resolution text.

```text
dna sdlc issue resolve [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--allow-no-produces` | Silencia o warn de outputs vazios (produces[] + back-refs). |
| `--help` | Show this message and exit. |
| `--resolution` | How was it resolved? |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc issue start`

Mark Issue status: in-progress.

```text
dna sdlc issue start [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc issue triage`

Mark Issue status: triaged.

```text
dna sdlc issue triage [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc journey`

Phase-aware journey ledger — additive over Superpowers/BMAD/Spec Kit.

Records the trail from idea→ship as a sequence of WorkflowEvent
docs pinned to (phase, artifact) pairs. Companion to the Skill at
`.claude/skills/dna-journey/SKILL.md`.

```text
dna sdlc journey [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc journey close-cycle`

Close the current cycle and open the next discover, seeded with
the prior reflect's lessons.

The ouroboros bite — reflect feeds discover. After this command,
the next ``dna sdlc journey transition`` calls will operate on
cycle N+1.

Resolution: looks up the latest ``reflect`` entry for
``parent_ref``. Pulls its referenced Narrative (paragraphs +
decisions + open_items) when available; falls back to the entry
summary. Prints the seed and (unless --show-only) writes a new
``discover`` entry with ``seed_from`` set.

```text
dna sdlc journey close-cycle [OPTIONS] PARENT_REF
```

**Arguments**

| Argument | Required |
| --- | --- |
| `PARENT_REF` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--next-summary` | Optional summary for the new discover entry. |
| `--no-narrative` | Skip the auto-Narrative synthesis. By default a retro Narrative is written summarizing the closed cycle. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--show-only` | Print the seed prompt to stdout without writing a new entry. Useful for previewing. |

### `dna sdlc journey current`

Show the latest open WorkflowEvent. Without --parent, shows the
latest open entry across the whole scope.

```text
dna sdlc journey current [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--parent` | Filter to a specific anchor doc. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc journey enter`

Open a new WorkflowEvent pinning a doc to a phase. The previous
entry for this parent (if any) gets ``ended_at`` stamped.

```text
dna sdlc journey enter [OPTIONS] {discover|specify|plan|build|reflect}
```

**Arguments**

| Argument | Required |
| --- | --- |
| `PHASE` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--artifact` | External methodology artifact path/URL (e.g. docs/superpowers/plans/foo-plan.md). |
| `--force` | Override methodology gates. Requires --reason for honest justification. |
| `--help` | Show this message and exit. |
| `--methodology` | _(default: `ad-hoc`)_ |
| `--parent` | Anchor doc (Feature/f-X or Epic/e-X) grouping siblings. _(default: `Sentinel.UNSET`)_ |
| `--reason` | Reason for --force override. Stored in entry.spec.force_reason for audit. |
| `--ref` | Doc representing this phase (Kind/name, e.g. Plan/foo). _(default: `Sentinel.UNSET`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--skip-from` | Previous phase you skipped to land here (honest about cut corners, e.g. --skip-from discover). |
| `--summary` | 1-2 sentence note about what's happening here. |

### `dna sdlc journey list`

List the full trajectory (oldest first) for a parent ref. Useful
to see "how did we get here" for a Feature/Epic.

For a ``Story/<name>`` parent the trajectory is DERIVED server-side
(s-journey-derived) from the Story's own state + linked artifacts —
the same computation the Studio bar renders. Feature/Epic parents
still list explicit WorkflowEvents (methodology ledger).

```text
dna sdlc journey list [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--parent` | Anchor doc to show the trajectory of. _(default: `Sentinel.UNSET`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc journey transition`

Close the current entry for ``--parent`` and open one in
``next_phase``. Sugar over `journey enter` that auto-fills
skip_from + transitioned_from from the previous entry. Pass
--skip-from explicitly to widen the skip range beyond the
prev entry's phase.

```text
dna sdlc journey transition [OPTIONS] {discover|specify|plan|build|reflect}
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NEXT_PHASE` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--artifact` |  |
| `--auto-stub` | Generate a Plan doc stub at docs/superpowers/plans/<date>-<slug>-plan.md and set entry.methodology_artifact to its path. Use for medium demands deserving a real Plan but not a long design ceremony. |
| `--force` | Override methodology gates. Requires --reason. |
| `--help` | Show this message and exit. |
| `--inline` | Inline plan text (1-3 lines describing the sequence). Stored in entry.inline_plan — cheap alternative to writing a full Plan doc. Use for small demands. |
| `--keep-ref` | Reuse the previous entry's ref for the next entry. |
| `--methodology` | _(default: `ad-hoc`)_ |
| `--parent` | Anchor doc grouping siblings (must match the open entry). _(default: `Sentinel.UNSET`)_ |
| `--reason` | Reason for --force override. Stored in entry.spec.force_reason for audit. |
| `--ref` | Doc representing the NEXT phase. Defaults to previous entry's ref if --keep-ref. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--skip-from` | Override the auto-detected skip-from phase. Use when you want to mark MORE skipped phases than the prev entry implies (e.g. honest self-assessment of cut corners). By default, skipped_phases is computed from prev_phase → next_phase. |
| `--summary` |  |

## `dna sdlc kaizen`

Kaizen — observação de melhoria contínua (arco observed→routed→resolved).

Forma histórica `dna sdlc kaizen <wi> --body "…"` continua valendo
(alias do subcomando `flag`).

```text
dna sdlc kaizen [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc kaizen flag`

Post a ``kaizen`` event onto a work item's timeline AND create
the first-class Kaizen doc twin (s-kaizen-kind).

A flagged kaizen observation shows up live in the FOCUS feed (the
``kaizen`` event-type is part of the unified feed). Does NOT change the
work item's status — it's a running improvement note, optionally linking
the Issue/Story that tracks the fix.

Dual-write: the observation is ALSO persisted as a ``Kaizen`` doc
(``kz-NNN-<slug>``, record plane) so the improvement backlog is
queryable + semantically searchable; the timeline event carries a
``kaizen_doc`` ref back to it.

``<work_item>`` accepts ``Kind/slug`` (e.g. ``Story/s-x``, ``Issue/i-1``)
or a bare slug, which is treated as a Story.

```text
dna sdlc kaizen flag [OPTIONS] WORK_ITEM
```

**Arguments**

| Argument | Required |
| --- | --- |
| `WORK_ITEM` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--body` | The kaizen observation (lands on the timeline event). _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--issue` | Optional Issue/Story slug that captured the improvement (e.g. i-042). Linked on the event so it's traceable. |
| `--label` | Free-form theme tag (repeatable). Lands on the Kaizen doc and is weighted into semantic-search source text. _(default: `Sentinel.UNSET`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc kaizen resolve`

Mark Kaizen status: resolved (fix shipped).

Transição válida a partir de ``observed`` ou ``routed``.

```text
dna sdlc kaizen resolve [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc kaizen route`

Mark Kaizen status: routed (um Issue/Story rastreia o fix).

Transição válida só a partir de ``observed`` (arco do descriptor:
observed → routed → resolved). Grava ``issue`` no doc.

```text
dna sdlc kaizen route [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--issue` | Issue/Story slug que rastreia o fix (e.g. i-042). _(default: `Sentinel.UNSET`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc list`

Tabular list of SDLC docs filtered by status/owner/parent ref.

```text
dna sdlc list [OPTIONS] {Roadmap|Epic|Feature|Story|Issue|Spec|Plan}
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--epic` | Filter Features by spec.epic. |
| `--feature` | Filter Stories by spec.feature. |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--owner` | Filter by spec.owner. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--status` | Filter by spec.status. |

## `dna sdlc narrative`

Project narrative — write cadence reminders + scaffold helpers.

The Narrative Kind itself is created via ``dna doc apply`` against
a NARRATIVE.md bundle (the canonical write path). These commands
are the operator-side ergonomics: telling you when the last one
was written, what's pending since then, and stubbing out the next
one so the friction to write is low.

```text
dna sdlc narrative [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc narrative add-decision`

Append a structured decision to an existing Narrative. The
decision goes into `spec.decisions[]` so Studio renders it in the
yellow callout strip, not just in body markdown.

Use this AT REFLECT TIME (or right after close-cycle) to capture
the WHY of choices the cycle made.

```text
dna sdlc narrative add-decision [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--decision` | 1-sentence summary of WHAT was decided. _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--reason` | WHY — the tradeoff or driving constraint. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--trade-offs` | Optional: what we gave up to make this choice. |

### `dna sdlc narrative add-open-item`

Append an open work item to an existing Narrative. Surfaces in
Studio's sidebar 'ainda em aberto' section.

Use this when reflecting on a cycle that didn't fully close —
something started but didn't ship, a follow-up the next cycle
should pick up, a debt acknowledged.

```text
dna sdlc narrative add-open-item [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--blocker` | What's blocking it (1-liner). |
| `--help` | Show this message and exit. |
| `--owner` | Who's on this (actor name). |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--title` | Short description of the open work item. _(default: `Sentinel.UNSET`)_ |

### `dna sdlc narrative add-paragraph`

Append a paragraph to an existing Narrative. Stored in
`spec.paragraphs[]` so Studio renders it as the lead block in
order.

Use this when shipping mid-cycle progress that deserves a line
on the narrative without waiting for close-cycle synthesis.

```text
dna sdlc narrative add-paragraph [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--text` | Past-tense paragraph of what shipped (no bullets). _(default: `Sentinel.UNSET`)_ |

### `dna sdlc narrative new`

Scaffold a NARRATIVE.md bundle for a new Narrative doc. Writes
the file with FLAT frontmatter (the format the bundle reader
expects) + a body skeleton with the structured-fields headings.
Does NOT apply — review/edit, then run `dna doc apply`.

```text
dna sdlc narrative new [OPTIONS] SLUG
```

**Arguments**

| Argument | Required |
| --- | --- |
| `SLUG` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--intent` | Author intent (drives Studio grouping). _(default: `daily`)_ |
| `--scope` | _(default: `dna-development`)_ |
| `--title` | Optional title; falls back to slug. |

### `dna sdlc narrative status`

Report cadence: how long since the last Narrative was written,
how many SDLC events accumulated since, and a suggestion if it's
time to write one. Prints a short report and exits 0 always.

```text
dna sdlc narrative status [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | _(default: `dna-development`)_ |

## `dna sdlc next`

Snapshot of active work — in-progress epic, pending stories, open issues.

```text
dna sdlc next [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc plan`

Manage Plan docs (implementation plans).

```text
dna sdlc plan [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc plan accept`

Mark Plan status: accepted; stamp accepted_at.

```text
dna sdlc plan accept [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc plan create`

Create a Plan doc (optionally linked to a Story and/or Spec).

Body source: inline ``--body "..."`` for a quick plan, or
``--body-file <plano.md>`` to pour a rich markdown plan (e.g. the output
of the superpowers writing-plans skill) into the Plan body. ``--methodology``
records which method produced it — opt-in, methodology-agnostic.

```text
dna sdlc plan create [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--approach`, `--body` | Plan body / approach (markdown, stored in PLAN.md). |
| `--body-file` | Lê o body de um markdown (plano RICO: superpowers/bmad/à mão). Mutuamente exclusivo com --body. |
| `--help` | Show this message and exit. |
| `--methodology` | Metodologia que produziu o plano (carimba spec.methodology). Opt-in. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--spec` | Parent Spec (spec_ref). |
| `--status` | _(default: `accepted`)_ |
| `--story` | Story this plan attacks (slug or Story/<slug>) — lights up its `plan` phase. |
| `--title` | Human title (→ spec.title). _(default: `Sentinel.UNSET`)_ |

### `dna sdlc plan deprecate`

Mark Plan status: deprecated.

```text
dna sdlc plan deprecate [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc plan propose`

Mark Plan status: proposed.

```text
dna sdlc plan propose [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc plan supersede`

Mark Plan status: superseded.

```text
dna sdlc plan supersede [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--by` | Plan name that supersedes this one (→ spec.superseded_by). _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc pr-footer`

Print the attribution footer block for a hand-made PR body.

Pure formatter (no kernel session, no gh): paste the output at the
end of the PR body você abriu à mão. Template + override
(``$DNA_SDLC_PR_FOOTER``) em ``_git_symbiosis.py``.

```text
dna sdlc pr-footer [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

## `dna sdlc produces`

Attach/list artifacts a work item produced (any Kind — the hub).

```text
dna sdlc produces [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc produces add`

Attach an artifact: dna sdlc produces add <WiKind>/<wi> <Kind>/<name>.

```text
dna sdlc produces add [OPTIONS] WORK_ITEM ARTIFACT
```

**Arguments**

| Argument | Required |
| --- | --- |
| `WORK_ITEM` | yes |
| `ARTIFACT` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--role` | Role hint (visual-spec, plan, investigation, ...). |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc produces list`

Resolved outputs of a work item (produces[] ∪ legacy back-refs).

```text
dna sdlc produces list [OPTIONS] WORK_ITEM
```

**Arguments**

| Argument | Required |
| --- | --- |
| `WORK_ITEM` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc produces rm`

Detach an artifact from a work item's produces[].

```text
dna sdlc produces rm [OPTIONS] WORK_ITEM ARTIFACT
```

**Arguments**

| Argument | Required |
| --- | --- |
| `WORK_ITEM` | yes |
| `ARTIFACT` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc reference`

Reference Kind — create / list / show external sources.

```text
dna sdlc reference [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc reference create`

Create a Reference doc capturing an external source.

```text
dna sdlc reference create [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--content-path` | Path to rich-content sidecar markdown. |
| `--help` | Show this message and exit. |
| `--kind-of` | _(default: `Sentinel.UNSET`)_ |
| `--quote` | Verbatim key quote (max ~500 chars). Repeat for multiple. _(default: `Sentinel.UNSET`)_ |
| `--relevance` | Why this matters for THIS project. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--summary` | 1-2 sentence summary of what this source says. _(default: `Sentinel.UNSET`)_ |
| `--tag` | _(default: `Sentinel.UNSET`)_ |
| `--title` | _(default: `Sentinel.UNSET`)_ |
| `--url` |  |

### `dna sdlc reference list`

List Reference docs (optionally filtered by kind_of).

```text
dna sdlc reference list [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--kind-of` |  |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc reference show`

Show a Reference doc + its citation graph.

```text
dna sdlc reference show [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc spec`

Spec-level operations (design / spec documents).

```text
dna sdlc spec [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc spec accept`

```text
dna sdlc spec accept [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc spec create`

```text
dna sdlc spec create [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--body` | Markdown body (→ spec.body / SPEC.md). |
| `--date` | Date (ISO-8601; → spec.date). Defaults to now. |
| `--desc` | Short description (→ spec.description). |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--status` | _(default: `draft`)_ |
| `--title` | Title (→ spec.title). _(default: `Sentinel.UNSET`)_ |

### `dna sdlc spec deprecate`

```text
dna sdlc spec deprecate [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc spec propose`

```text
dna sdlc spec propose [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc spec supersede`

```text
dna sdlc spec supersede [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--by` | Spec name that supersedes this one (→ spec.superseded_by). _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc spike`

Spike-level operations (time-boxed technical investigations).

```text
dna sdlc spike [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc spike abandon`

Mark Spike status: abandoned.

```text
dna sdlc spike abandon [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc spike answer`

Mark Spike status: answered; stamp completed_at + findings/recommendation.

```text
dna sdlc spike answer [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--findings` | What the spike found (→ spec.findings). |
| `--follow-up-story` | Story this spike hands off to (→ spec.follow_up_story). |
| `--help` | Show this message and exit. |
| `--recommendation` | Recommended next step (→ spec.recommendation). |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc spike comment`

Append a finding / decision to a Spike timeline without changing status.

Mirrors `story comment` — Spikes accrue findings + decisions over their
investigation, and the running trail belongs on the timeline (the FOCUS
feed + audit), not only in the final `answer`.

```text
dna sdlc spike comment [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--body` | The comment / finding / decision text. _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--type` | Defaults to 'comment'; decision-shaped bodies auto-promote. |

### `dna sdlc spike create`

Create a new Spike (time-boxed technical investigation).

```text
dna sdlc spike create [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--body` | Markdown body (→ spec.body / SPIKE.md). |
| `--feature` | Parent Feature name. |
| `--follow-up-story` | Story this spike hands off to (→ spec.follow_up_story). |
| `--help` | Show this message and exit. |
| `--labels` | Comma-separated labels. |
| `--owner` |  |
| `--question` | The ONE question this spike answers (→ spec.question_to_answer). _(default: `Sentinel.UNSET`)_ |
| `--references` | Comma-separated Reference names (→ spec.references). |
| `--research-refs` | Comma-separated Research names (→ spec.research_refs). |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--status` | _(default: `proposed`)_ |
| `--time-box` | Time budget in hours (→ spec.time_box_hours). |
| `--title` | Short title. Derived from --question first line (≤80) when omitted. |

### `dna sdlc spike link`

Attach a Spike's outputs (ADR/Research/HtmlArtifact/Reference) + handoffs
(Story/Feature) so they show up in FOCUS OUTPUTS and the audit graph — never
in limbo. List fields append + dedup; scalar fields are set. Idempotent.

```text
dna sdlc spike link [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--adr` | ADR this spike hands off to (→ follow_up_adr). |
| `--artifact` | HtmlArtifact to attach (→ html_artifacts[]). |
| `--feature` | Parent Feature (→ feature). |
| `--follow-up-story` | Story this spike hands off to (→ follow_up_story). |
| `--help` | Show this message and exit. |
| `--reference` | Reference to attach (→ references[]). |
| `--related-spike` | Related Spike (→ related_spikes[]). |
| `--research` | Research doc to attach (→ research_refs[]). |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--spec` | Spec this spike produced (→ follow_up_spec). |

### `dna sdlc spike start`

Mark Spike status: in-progress.

```text
dna sdlc spike start [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc story`

Story-level operations.

```text
dna sdlc story [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc story block`

Mark Story status: blocked, set blocked_reason.

```text
dna sdlc story block [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--reason` | Why is it blocked? _(default: `Sentinel.UNSET`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc story cancel`

Mark a Story as cancelled with an explicit reason. Same intent
as feature cancel — close the open-work loop without silently
dropping context.

```text
dna sdlc story cancel [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--reason` | Why is the Story cancelled? _(default: `Sentinel.UNSET`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc story check`

Mark specific AC / DoD items DONE **with evidence** — granular
Gapless-DoD closure, vs ``story done``'s blanket auto-backfill (which
stamps ``done_by=story-done-auto`` and no evidence). Select items by
1-based index or text substring; ``--all`` marks every AC + DoD item.

Example:
    dna sdlc story check s-foo --ac 1 --dod "tests" --evidence "PR #42"

```text
dna sdlc story check [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--ac` | Acceptance-criterion to mark done: 1-based index or text substring (repeatable). _(default: `Sentinel.UNSET`)_ |
| `--all` | Mark ALL acceptance_criteria + definition_of_done items done. |
| `--by` | Actor crediting the check (default: DNA_AGENT_OWNER or claude-code). |
| `--dod` | Definition-of-done item to mark done: 1-based index or text substring (repeatable). _(default: `Sentinel.UNSET`)_ |
| `--evidence` | Evidence the item is satisfied (PR #, commit sha, link, or prose). Stored per-item. _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc story comment`

Append a comment / decision event to a Story timeline without
mutating its status. Useful when shipping a Story produces
artifacts beyond the status flip itself.

Auto-promotes comments matching decision patterns to decision
events so the morning narrative drawer's "🧠 decisions" section
captures the WHY without the agent needing to remember --type.

```text
dna sdlc story comment [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--body` | Comment text (lands on the timeline event). _(default: `Sentinel.UNSET`)_ |
| `--commit-ref` | Optional Git SHA to associate. Auto-detected from HEAD when omitted. |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--type` | Event type — 'comment' or 'decision'. When omitted, auto-detected: comments matching decision patterns ('decidi X porque Y', 'optei por...') are promoted to decisions automatically. |

### `dna sdlc story commits`

List every commit tied to a Story — trailers + timeline, merged.

Closes the rastreabilidade loop: "que commits fecharam Story X?"
Two sources, deduped by sha (trailer wins — it carries the subject):

- ``git log --grep "Work-Item: Story/<name>"`` — commits stamped by
  the prepare-commit-msg hook (``dna sdlc hooks install``). This is
  the zero-bookkeeping path; fail-soft when git/repo is unavailable.
- ``spec.timeline[].commit_ref`` (auto-stamped by `story done`) +
  ``spec.timeline[].session_ref`` (linkback to the AgentSession).

```text
dna sdlc story commits [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc story create`

Create a new Story.

AC + DoD guard (2026-05-14): without --ac and --dod the command
refuses. Stories that ship "todo" but don't declare exit criteria
are the root of the silent-skip-DoD pattern user flagged in chat.
Override with --allow-no-ac-dod only for back-compat backfills.

```text
dna sdlc story create [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--ac` | Acceptance criterion (repeatable). Each --ac adds one bullet to spec.acceptance_criteria. Use Given/When/Then prose. _(default: `Sentinel.UNSET`)_ |
| `--ac-source` | Provenance tag for acceptance_criteria (e.g. claude-code, llm-analyst-backfill, human). |
| `--allow-no-ac-dod` | Skip the AC + DoD guard. Use ONLY for back-compat backfills or exceptional grooming. Stories filed without acceptance_criteria + definition_of_done are blocked by default because they ship without exit criteria — see chat 2026-05-14 + memory feedback_story_ac_dod_required. |
| `--business-value` | WSJF-style scalar (0-1000). |
| `--desc` | One-line description. _(default: `Sentinel.UNSET`)_ |
| `--dod` | Definition of Done item (repeatable). Each --dod adds one bullet to spec.definition_of_done. Cover Code/Tests/Docs/CI/UX. _(default: `Sentinel.UNSET`)_ |
| `--dod-source` | Provenance tag for definition_of_done. |
| `--estimate` |  |
| `--feature` | Parent Feature name. _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--labels` | Comma-separated labels. |
| `--owner` |  |
| `--priority` | Board priority (default: medium when set; else field omitted). |
| `--reporter` | Actor who filed it. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--sprint` | Sprint identifier. |
| `--status` | _(default: `todo`)_ |
| `--title` | Short Jira-style title shown on cards. Falls back to first line of --desc (truncated to 80 chars) when omitted. |

### `dna sdlc story done`

Mark Story status: done; auto-stamp commit_ref + optional summary.

```text
dna sdlc story done [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--allow-no-produces` | Silencia o warn de outputs vazios (produces[] + back-refs). |
| `--allow-no-tests` | Pula o test gate (s-sdlc-tests-required-on-done). Use SÓ para exceções registradas — por padrão `story done` exige um TestRun outcome=pass que verifica a Story, espelhando o guard de --ac/--dod do `story create`. |
| `--commit-ref` | Git SHA shipped with this Story. Auto-detected from HEAD when omitted. |
| `--help` | Show this message and exit. |
| `--no-commit` | Story sem código (silencia o aviso de commit de entrega + isenta o test gate). |
| `--no-narrate` | Silencia o warn de narração. |
| `--note` | Narra esta transição (appenda comment inline na MESMA chamada). |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--summary` | One-line description of what shipped (lands on the timeline event). |

### `dna sdlc story groom`

Read-modify-write: update only the board-grade fields passed.

Idempotent — running with no flags is a no-op (other than re-stamping
updated_at, which we skip when nothing else changed).

```text
dna sdlc story groom [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--ac` | Acceptance criterion (repeatable). REPLACES existing list. _(default: `Sentinel.UNSET`)_ |
| `--ac-source` |  |
| `--business-value` |  |
| `--dod` | DoD item (repeatable). REPLACES existing list. _(default: `Sentinel.UNSET`)_ |
| `--dod-source` |  |
| `--help` | Show this message and exit. |
| `--labels` | Comma-separated. Replaces existing. |
| `--priority` |  |
| `--release-target` | Epic name OR 'owner/pkg@semver'. |
| `--reporter` |  |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--sprint` |  |
| `--title` | Retitle the Story (e.g. a cli-create title that came in truncated/desc-shaped — `story pr` builds the PR title from it). |

### `dna sdlc story pr`

Open the Story's PR — ``gh pr create`` pre-filled FROM the story.

Title ``feat(<label>): <título> (<s-x>)``; body = description + AC
como checklist + footer de atribuição (``dna sdlc pr-footer``). O PR
nasce da story, não o contrário — e a URL volta pra timeline.

```text
dna sdlc story pr [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--base` | Base branch do PR (passthrough pro gh; default: o do repo). |
| `--draft` | Abre como draft. |
| `--dry-run` | Só imprime title + body montados; não chama gh. |
| `--head` | Head branch (default: a branch corrente — default do próprio gh). |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc story reopen`

Reopen a closed/cancelled Story — flip status back to todo
(or specified) and clear closed_at + cancelled_reason. Stamps a
status_change event with the reopen reason.

```text
dna sdlc story reopen [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--reason` | Why reopen? _(default: `reopened`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--to` | Status to flip back to (default: todo). _(default: `todo`)_ |

### `dna sdlc story review`

Mark Story status: review.

Also emits a ``build`` journey event — submitting for review means the
implementation is complete. The journey is now DERIVED (s-journey-derived):
``build`` is computed from the timeline status_change to in-progress/review
(or a commit_ref), and finer phases (specify/plan) light up automatically
from AC/DoD + linked Spec/Plan. No WorkflowEvent write needed.

Guard (i-133): review = PR aberto. Checa ``gh pr list --head <branch>``
(fail-soft, ≤3s); sem PR aberto exige ``--no-pr --reason "<por quê>"``.

```text
dna sdlc story review [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--no-narrate` | Silencia o warn de narração. |
| `--no-pr` | Escape do guard de PR (i-133): marca review mesmo sem PR aberto na branch corrente. Exige --reason. |
| `--note` | Narra esta transição (appenda comment inline na MESMA chamada). |
| `--reason` | Por que está marcando review sem PR aberto (vai pro timeline). |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc story show`

Show a Story's full detail — header + AC/DoD + plan + recent timeline.

Reads via the API client (NOT the DB), so it works against any source
(filesystem / Postgres / remote) without local Postgres access. Closes the
gap where agents fell back to raw YAML / direct SQL to read a Story (i-070).

```text
dna sdlc story show [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | Emit the raw spec as JSON. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc story start`

Mark Story status: in-progress.

Plan gate (s-story-start-plan-gate): você não começa sem decidir o
plano de ataque — ``--plan "1-3 linhas"`` (cria Plan inline),
``--plan-doc <nome>`` (linka Plan existente), ou
``--no-plan --skip-reason "..."`` (skip honesto, registrado). Em TTY
interativo sem flag, o CLI pergunta. O artefato nasce no caminho
crítico — ninguém esquece, e a fase `plan` derivada acende sozinha.

Side-effect: stamps ``.dna/active-story.txt`` with ``<scope>:<name>``
so external tools (Claude Code hooks, IDE plugins) can attribute
out-of-band events to the Story currently being worked on.

```text
dna sdlc story start [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--methodology` | Metodologia que produziu o plano (carimba Plan.spec.methodology → jornada mostra a origem). Opt-in. |
| `--no-narrate` | Silencia o warn de narração. |
| `--no-plan` | Pular o `plan` conscientemente (exige --skip-reason). |
| `--note` | Narra esta transição (appenda comment inline na MESMA chamada). |
| `--plan` | Plano de ataque (1-3 linhas). Cria Plan/plan-<story> linkado → fase `plan` acende. |
| `--plan-doc` | Linka um Plan existente (trabalho grande) em vez de criar inline. |
| `--plan-file` | Cria Plan/plan-<story> com o body = conteúdo deste markdown (plano RICO de qualquer metodologia: superpowers, bmad, à mão). |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--skip-reason` | Motivo do skip (com --no-plan) — registrado honestamente na jornada. |

## `dna sdlc task`

Task-level operations (granular sub-Story work items).

```text
dna sdlc task [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc task block`

Mark Task status: blocked, with a reason.

```text
dna sdlc task block [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--reason` | Why is it blocked? (→ spec.blocked_reason). _(default: `Sentinel.UNSET`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc task cancel`

Mark Task status: cancelled.

```text
dna sdlc task cancel [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc task create`

Create a new Task.

```text
dna sdlc task create [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--body` | Markdown body (→ spec.body / TASK.md). |
| `--desc` | One-line description (→ spec.description; derives title). _(default: `Sentinel.UNSET`)_ |
| `--estimate` | Estimated hours (→ spec.estimate_hours). |
| `--feature` | Parent Feature name. |
| `--help` | Show this message and exit. |
| `--labels` | Comma-separated labels. |
| `--owner` |  |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--status` | _(default: `todo`)_ |

### `dna sdlc task done`

Mark Task status: done; stamp closed_at.

```text
dna sdlc task done [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

### `dna sdlc task start`

Mark Task status: in-progress.

```text
dna sdlc task start [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

## `dna sdlc test-guide`

Test guides (roteiros) — declarative test scripts that verify work items.

```text
dna sdlc test-guide [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc test-guide create`

Create a TestGuide. Manual steps via --step, or stub them from a Story's
acceptance_criteria via --from-ac (you then fill in each 'expected'). Pass
--product to scaffold a UI-first product smoke (the lane the done-gate counts).

```text
dna sdlc test-guide create [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--description` | What this guide validates. |
| `--from-ac` | Story name: stub one step per acceptance_criteria (you fill 'expected'). |
| `--help` | Show this message and exit. |
| `--kind-of-test` | _(default: `manual`)_ |
| `--owner` | Actor who owns this guide. |
| `--product` | Scaffold a UI-first PRODUCT smoke: forces kind_of_test=smoke and (with --from-ac) generates leigo-proof steps with a 'where' route + observable 'expected'. The tester marks ✗ ONLY if the product is broken — never author a step that forces a failure. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--step` | A step as 'action :: expected' (repeatable). _(default: `Sentinel.UNSET`)_ |
| `--verifies` | Work item this guide verifies, e.g. 'Story/s-x' (repeatable). _(default: `Sentinel.UNSET`)_ |

## `dna sdlc test-run`

Test runs — execution records of a TestGuide (the verify-phase signal).

```text
dna sdlc test-run [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna sdlc test-run record`

Record a TestRun for a TestGuide. Inherits the guide's `verifies`, then
stamps each verified Story (artifact_produced timeline event + produces[]) —
so the run shows in FOCUS and lights the journey's `verify` phase.

```text
dna sdlc test-run record [OPTIONS] GUIDE
```

**Arguments**

| Argument | Required |
| --- | --- |
| `GUIDE` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--by` | Actor who ran it (default: CLI actor). |
| `--evidence` | Ref/link backing the outcome, e.g. 'HtmlArtifact/ha-x' (repeatable). _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--name` | Run doc name (default: tr-<guide>-<timestamp>). |
| `--note` | Free-text notes on the run. |
| `--outcome` | _(default: `Sentinel.UNSET`)_ |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |
| `--screenshot` | Print de evidência (imagem). Repetível. Uploadado como Asset. _(default: `Sentinel.UNSET`)_ |

## `dna sdlc uncite`

Symmetric removal of a citation link.

```text
dna sdlc uncite [OPTIONS] REF_NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `REF_NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--from` | _(default: `Sentinel.UNSET`)_ |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the SDLC docs (default: dna-development). _(default: `dna-development`)_ |

