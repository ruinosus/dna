# AGENTS.md — how work is tracked in this project

This project uses [DNA](https://github.com/ruinosus/dna) (Domain Notation of
Anything) to track its own lifecycle: Stories, Features, Epics and Issues are
declarative YAML documents in the board scope under `.dna/`, written and
transitioned via the `dna sdlc` CLI. This file was materialized by `dna init`
and is itself a live `agents.md/v1` instance the DNA SDK parses and
round-trips byte-faithfully.

## SDLC protocol — work is tracked in-repo via `dna sdlc`

The flow is **story-first**: file the Story before the work, narrate while
building, verify before closing.

```bash
dna sdlc brief                          # session start — what's in flight
dna sdlc hooks install                  # one-time per clone — commit trailers
dna sdlc feature create f-my-area --title "..." --desc "..."   # parent Feature
dna sdlc story create s-my-work --feature f-my-area --desc "..." \
  --ac "Given/When/Then ..." --dod "code+tests+docs ..."   # AC + DoD required
dna sdlc story start s-my-work --plan "plan of attack"      # plan gate
dna sdlc story comment s-my-work --body "decided X because Y"  # narrate as you go
dna sdlc test-guide create tg-my-work --verifies Story/s-my-work --step "run :: expect"
dna sdlc test-run record tg-my-work --outcome pass          # test gate for done
dna sdlc story pr s-my-work             # gh pr create, pre-filled FROM the story
dna sdlc story done s-my-work           # only after the PR merges
```

While a story is active, every commit is stamped with `Work-Item:` +
`dna-sdlc[bot]` trailers by the versioned hook — that is the provenance
seal linking git history to the work item (`dna sdlc story commits s-x`).

## Conventions

- **Story-first.** Non-trivial work starts with `dna sdlc story create`
  (AC + DoD are mandatory at create time) and `story start` (the plan
  gate — substantial work gets a real plan via `--plan-file`, not a
  one-liner).
- **Narrate as you go.** Status changes record *that* something happened,
  not *what*. Post `dna sdlc story comment` for each meaningful step or
  decision — the timeline is what stakeholders and future sessions read.
- **Gapless definition of done.** Never mark a story `done` with a gap:
  finish to market standard, or keep it `in-progress` / decompose into
  tracked child stories. `story done` requires a passing TestRun
  (`--allow-no-tests` is for recorded exceptions only).
- **Review = open PR; done = merged.** `story review` expects an open PR
  on the branch; a story in `review` with no PR is stale. Once a PR is
  approved, stop pushing to its branch — further work goes to a new branch.
- **Surface IDs.** Print full slug IDs in backticks (`s-foo`, `i-012-bar`)
  so they are paste-able into `dna sdlc story show` / `git log --grep`.

## Do not

- **Never hand-edit `.dna/**.yaml` for status changes** — the CLI is the
  canonical write path (validation, timeline and journey events fire there).
- **Never do non-trivial work without an active story** — unstamped commits
  are invisible to `story commits` / `story show`; absence is signal.
- **Never mark a story `done` with a gap** — finish to market standard or
  keep it `in-progress` / decompose into tracked child stories.

## Learn more

- Skill: the `dna-sdlc-cli` skill (agentskills.io SKILL.md format) is
  materialized by `dna init` into your agent tool's skills directory —
  `.claude/skills/`, `.github/skills/`, `.cursor/skills/` or
  `.opencode/skills/` — with the full workflow. Same content everywhere.
- Docs: <https://ruinosus.github.io/dna/> — CLI reference, Kinds guide,
  SDLC guide ("Your git log is your SDLC").
