---
name: dna-sdlc-cli
description: "Use whenever work in this project needs SDLC tracking (Epic, Feature, Story, Issue, Spec, Plan, Spike, TestGuide/TestRun), or the user asks to file/start/narrate/close lifecycle docs, open a story PR, or wire the git hooks. Operate via the `dna sdlc` CLI \u2014 never edit `.dna/` YAMLs by hand for status changes; the CLI is the canonical write path (validation, timeline events and the derived journey fire correctly)."
---

# DNA SDLC CLI — the work tracker for this project

This project tracks its own lifecycle as DNA documents: Stories, Features,
Epics and Issues are first-class YAML documents in the board scope under
`.dna/` (the CLI's default source `./.dna` — run `dna` from the project
root, no env var needed; the sole board scope is auto-detected, or set
`DNA_SDLC_SCOPE`). Don't manually edit those YAMLs when changing status —
the CLI is the canonical write path.

## ⚖️ Maxim — zero gaps (the supreme rule)

**Never ship an activity with a gap.** Every Story/Feature/Epic/Issue is
either finished to market standard with no gaps, or it **stays
`in-progress`** until it is. There is no "ship with a TODO for later"
without a tracked Story covering it.

Before `story done`, the work must satisfy its own AC + DoD — close them
granularly with evidence:

```bash
dna sdlc story check s-foo --ac 1 --dod "tests" --evidence "PR #42"
dna sdlc story check s-foo --all --evidence "commit abc123 + CI green"
```

When a gap appears mid-story:

1. **Small + adjacent** (lint fix, doc tweak): include in the same Story.
2. **Medium + orthogonal**: file a follow-up Story; current one goes
   `dna sdlc story block s-foo --reason "waiting on s-foo-followup"`.
3. **Large + systemic**: file a Feature; the Story stays blocked until its
   first covering Story ships.

## Vocabulary

| Kind | Equivalent | Slug prefix | Verb group |
|------|------------|-------------|------------|
| Initiative / Roadmap | Initiative | free-form | `initiative` |
| Epic | Epic | `e-...` | `epic` |
| Feature | Feature | `f-...` | `feature` |
| Story | User Story | `s-...` | `story` |
| Issue | Bug/Task/Question | `i-NNN-...` (auto-numbered) | `issue` |
| Spec / Plan | RFC / implementation plan | free-form | `spec` / `plan` |
| Spike | time-boxed investigation | `sp-...` | `spike` |
| TestGuide / TestRun | test script / execution record | `tg-...` / `tr-...` | `test-guide` / `test-run` |

Story statuses: `needs-triage | todo | in-progress | review | done | blocked
| deferred | cancelled`. Issue arc: `file → triage → start → resolve`.

**Command shape:** *listing* is `dna sdlc list <Kind>` (capital-K:
`list Story --status in-progress`, `list Issue`); *acting on one doc* is
`dna sdlc <noun> <verb> <name>` (`story start`, `issue resolve`,
`feature`/`epic` verbs via their groups). There is no `story list`. When
unsure: `dna sdlc <noun> --help`.

## Session start

```bash
dna sdlc brief      # one-screen bootstrap: in-flight work, spikes, lessons, hot issues
dna sdlc current    # every doc currently in-progress
dna sdlc next       # snapshot of active work
```

## The story-first lifecycle

### 1. File it — AC + DoD are required at create time

```bash
dna sdlc story create s-my-work \
  --feature f-parent \
  --desc "what and why, one line" \
  --priority high --labels cli,docs --reporter my-agent \
  --ac "Given/When/Then acceptance criterion" \
  --dod "code + tests green + docs updated"
```

The CLI refuses Stories without `--ac`/`--dod` (exit criteria are not
optional). `--ac`/`--dod` are repeatable. Bugs/tasks are Issues:
`dna sdlc issue file --slug my-bug --type bug --severity high --desc "..."`.

### 2. Start it — the plan gate

```bash
dna sdlc story start s-my-work --plan "plan of attack in 1-3 lines"   # inline Plan
dna sdlc story start s-my-work --plan-file plan.md                    # rich multi-section plan
dna sdlc story start s-my-work --no-plan --skip-reason "1-line hotfix"  # honest, recorded skip
```

Substantial work gets a real plan (`--plan-file`), not a one-liner. Side
effect: `story start` stamps `.dna/active-story.txt`, which the git hook
reads (below).

### 3. Build — narrate as you go

Status changes record *that* something happened, not *what*. Post a comment
for each meaningful step or decision — the timeline is what stakeholders
(and future sessions) read:

```bash
dna sdlc story comment s-my-work --body "now refactoring the cache to LRU"
dna sdlc story comment s-my-work --body "decided maxsize=64 because scans are heavy" --type decision
```

`--type` auto-detects decision-shaped comments; `--commit-ref` ties a note
to a SHA (auto-detected from HEAD). The transition verbs (`start`, `review`,
`done`) warn when the timeline went mute — narrate inline with `--note "..."`.

### 4. Verify — the test gate

`story done` **requires a passing TestRun** that verifies the Story
(mirroring the AC/DoD guard at create):

```bash
dna sdlc test-guide create tg-my-work --description "what it validates" \
  --verifies Story/s-my-work --step "run X :: expect Y" --step "run Z :: expect W"
dna sdlc test-guide create tg-my-work --from-ac s-my-work   # or stub steps from the AC
dna sdlc test-run record tg-my-work --outcome pass --note "all green locally + CI"
```

Escape hatch `story done --allow-no-tests` is for recorded exceptions only.

### 5. PR — born from the story, review = open PR

```bash
dna sdlc story pr s-my-work              # gh pr create, pre-filled FROM the story
dna sdlc story pr s-my-work --dry-run    # print title + body, no gh call
dna sdlc pr-footer s-my-work             # just the attribution footer, for hand-made PRs
dna sdlc story review s-my-work          # requires an open PR on the branch (or --no-pr --reason)
```

`story pr` assembles title (`feat(<label>): <title> (<s-x>)`), body
(description + AC as a checklist) and the attribution footer, then stamps
the PR URL back onto the timeline. **PR ready = stop pushing to its
branch** — squash-merge captures the branch at the merge click; commits
pushed after approval are silently dropped. Further work goes to a new
branch off the merged base.

### 6. Done — only after merge

```bash
dna sdlc story done s-my-work --summary "what shipped"
```

A Story in `review` with no open PR is stale; `done` before the merge is a
lie. `done` auto-stamps `commit_ref`, warns on empty outputs (link
artifacts via `dna sdlc produces add`), and honors the test gate.

## Git symbiosis — trailers close the git↔SDLC loop

```bash
dna sdlc hooks install    # one-time per clone → git config core.hooksPath scripts/git-hooks
dna sdlc hooks status     # show wiring: hooksPath, active story, coauthor
```

While a Story is active, every `git commit` is stamped with
`Work-Item: Story/<name>` + the `dna-sdlc[bot]` co-author trailer. No
active story → no stamp (absence is signal). The way back needs no
bookkeeping:

```bash
dna sdlc story show s-my-work      # header + AC/DoD + plan + recent timeline
dna sdlc story commits s-my-work   # every commit tied to the Story (trailers + timeline)
```

## Surface IDs in chat (always)

When starting or shipping a doc, print the **full slug ID in backticks**
(`s-foo-bar`, `i-012-some-bug`) so the human can paste it into
`dna sdlc story show` / `git log --grep`. After a chunk of work, list each
ID touched with its transition (`s-foo: todo → done`).

## Other verbs (one-liners — `dna sdlc <verb> --help`)

`epic` / `feature` / `initiative` (parents; `feature` rolls up child
Stories) · `spike` (investigation arc: comment → answer with findings +
follow-up) · `adr` / `spec` / `plan` (design docs, ADR-style statuses) ·
`kaizen` (continuous-improvement observations) · `journey` (phase ledger —
derived; rarely needs manual writes) · `demand` (Story + journey-discover
in one shot) · `produces` / `cite` (link artifacts / sources) ·
`changelog` (release notes per scope) · `extract-decisions` (mine timelines).

## When NOT to use this skill

- Reading documents programmatically (use the SDK: `Kernel.quick(...)` /
  `mi.all("Story")` — see the dna-sdk docs).
- Bulk renames/deletes (use `dna doc` + a git commit, not the SDLC verbs).
