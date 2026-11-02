---
name: cast-list
description: Compares a team's Copilot Studio agents with each other, from the folders the VS Code extension clones — what most of them do (a pattern to agree on, of the platform or of the specialists), who is off a pattern, what only one has (innovation or debt), the team's rules not met, and what people say that the YAML contradicts — with the file and line behind each finding. Delivers a map that opens offline, an Excel workbook to fill in decisions, a lesson that draws the cast, and a cast file that keeps what was decided, so the next run checks it. Runs on Node alone — no model, no install, no network. Use when someone wants to find patterns across Copilot Studio agents, define architecture or delivery standards from evidence, check a new agent against the accepted ones, or see which agents escalate, log telemetry or use which connectors ("compare our Copilot Studio agents", "which of our agents is off the pattern?", "compara os agentes do Copilot Studio", "o que se repete entre os especialistas?").
license: MIT
compatibility: Needs code execution and Node.js 18 or later; nothing to install. Chrome, Chromium or Edge, when installed, lets the script check the lesson's drawing. The Microsoft skills for Copilot Studio are recommended, not needed.
metadata:
  version: "1.2.1"
---

# cast-list: what the agents have in common, and who is off it

The agents are cloned from Copilot Studio (the VS Code extension writes a folder per agent, with `agent.mcs.yml`).
`scripts/build.mjs` reads them, compares them and makes the map, the workbook, the lesson and the cast file — **with no
model**. You run it, read what it found, and help the person decide. You never edit an agent.

Paths below are relative to this skill's folder (the folder this file is in). Write in the person's language and pass
`--lang pt` for Portuguese (`en` is the default).

**The outputs hold the client's data** (agent names, connectors, instructions). They stay in the client's environment:
never paste them anywhere else, never commit them to a public repository.

## 1. Run it

```
node scripts/build.mjs <agents-folder> --all [--profile <team>.cast.yaml] [--lang pt] [--out <folder>]
```

- `<agents-folder>` holds the cloned agents (any depth: a folder with `agent.mcs.yml` is an agent; a child agent in
  `agents/<Name>/` stays with its parent; hidden folders such as `.mcs/` are never read).
- The **profile** is the team's standard, private to the team (`references/profile.md`): who is the orchestrator, how
  common a fact must be to be a pattern (70% of a role, with at least 3 agents, by default), the rules every agent of a
  role must follow, focus areas, what to leave out. With no profile, the orchestrator is whoever calls another agent.
- It writes `<id>.html` (the map), `<id>.xlsx`, `<id>.lesson.html` and `<id>.cast.yaml`, named by the folder. The cast
  file is read again on every run: what people declared and decided stays.

Exit 1 with `✗ file:line` is a broken profile or cast file: fix the line. Exit 3 is a lesson the reviewer did not pass.

## 2. Read what it found

The `!` lines are what to look at (`references/keys.md` names every fact), in this order:

- **What people said and the YAML do not agree** — a declared fact the agent does not have, or the other way round.
  What was seen wins; the contradiction is the finding.
- **Off a pattern** — «1 especialista não escala para humano (frete): é intencional?». With an accepted pattern:
  «corrigir?».
- **Rules not met** — from the profile.
- **Only one has it** — innovation to spread, or debt to remove: only the person knows.
- **Not understood** — files the analysis could not read (broken YAML, a kind Copilot Studio does not have). The rest
  was read anyway. Only the kind's name may leave the client's environment, typed, to improve the extractor.

## 3. Add what only people know — optional, with a model

The YAML does not hold KPIs, owners or intentions. When the person gives you documents (a handoff, the backlog):

1. `node scripts/build.mjs <agents-folder> --facts` writes `<id>.facts.json`: what was seen, with file and line.
2. Read **at most two** sources. For each thing they say about an agent, add a line to `declared:` in `<id>.cast.yaml`
   (`references/format.md`) with its **source**: `kpi`, `owner`, or a fact key such as `trigger:OnEscalate` when the
   document claims the agent does it. Never change a fact the YAML shows; a claim the YAML contradicts becomes a finding.
3. Run step 1 again.

## 4. Ask, then decide — once, all together

One message, numbered, from the `!` lines: **at most 6 questions, one thing each, each with your bet** («I'd say the
frete specialist skipping escalation is an oversight — the other four escalate»). Never ask without a bet.

Write a **decision** only when the person decides: in `decisions:` of the cast file (`key`, `status: accepted|rejected`,
`scope: platform|specialist|orchestrator`, `why`), or they fill the workbook's **Decision** column and **Declared**
sheet in Excel:

```
node scripts/build.mjs <agents-folder> --from <filled>.xlsx              lists the changes, each with a key
node scripts/build.mjs <agents-folder> --from <filled>.xlsx --take all   writes them to the cast file
```

Run again: an accepted pattern is now checked on every agent of its scope, even a new one — that is the quality gate.

## 5. Deliver

End with a short summary: how many agents; **the main patterns by name** — what the specialists do in common, and
what the platform does (behaviours first: escalation, error handling, telemetry; settings last) — **who is off what**
(by name), the open decisions with your bet, and the files. A count alone («22 patterns») tells the person nothing. The map's «Para olhar» / «To look at», the Matrix (filter by role and focus area; a click shows the file and
line), the Patterns cards and the Microsoft tab are where the person continues.

If the Microsoft skills for Copilot Studio are installed (`/plugin marketplace add microsoft/skills-for-copilot-studio`),
use them to explain a kind or a reference pattern; cast-list works without them.

## Never

- Never edit, push or publish an agent — this skill only reads them.
- Never decide a pattern for the person, or write a declared fact without its source.
- Never take the outputs out of the client's environment, or put a client's names in a public place.
- Never edit the generated files; change the cast file or the profile and run again.
