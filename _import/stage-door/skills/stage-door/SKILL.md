---
name: stage-door
description: Turns how a team works — scattered in PDFs, slides, wikis or someone's head — into one clear, checkable way of working (stages, phases, gates and who approves them, roles, outputs) and delivers it as a .way.yaml file, a map page that opens offline, an Excel workbook (stages, gates, RACI, outputs, a gate checklist) and a lesson that walks it by drawing. Reads an edited workbook back as proposed changes. Use when someone wants to map, document, review or explain a team's process, delivery flow, stage-gate, RACI or "way of working" ("turn our process PDF into a flow", "who approves what in our delivery?", "make an onboarding map of how we work", "monta o nosso fluxo de entrega").
license: MIT
compatibility: Needs code execution and Node.js 18 or later; nothing to install. Chrome, Chromium or Edge, when installed, lets the script check the lesson's drawing.
metadata:
  version: "0.3.0"
---

# stage-door: a team's way of working, clear and checkable

You read what the team has (documents, slides, what the person tells you), write **one file**, `<id>.way.yaml`, that
says how the work goes — and `scripts/build.mjs` checks it and makes what the person needs from it. You write only the
`.way.yaml`; never write the map, the workbook or the lesson yourself.

Paths below are relative to this skill's folder (the folder this file is in). Write to the person in their language,
and pass `--lang pt` to the script for Portuguese (`en` is the default).

## 1. Read, then draft — betting, never inventing

Read everything the person gave you. Then write the whole `.way.yaml` at once: lanes, roles, phases, stages in order
(each with its lane, the roles that take part, its key question, what it **receives** — an earlier output by id, or
something from outside — what it **delivers** and its **metrics**), gates (after which stage, who approves, what must be
ready, **what comes out of it**, where it goes back), and numbers if the material has them. The format is
`references/format.schema.json`; `examples/` has three finished files — open the one closest to yours.

- **Sort the words out as you go** (`references/words.md`): an activity is not a stage, a ritual (planning, daily,
  review) is neither a stage nor an activity, an environment is not a phase, a person is not a role. The material will mix them; the file must not.
- **Bet what the material implies** (a "sign-off by the TL" is a gate the Tech Lead approves) and remember the bet: you
  will say it in the questions.
- **Never invent** a stage, a role, an output, a gate, a person or a number. What the material does not say stays out
  of the file and becomes a question.
- The person's own words for names (their stage names, their acronyms), ids in lowercase `a-z0-9-`.

## 2. Check

```
node scripts/build.mjs <id>.way.yaml --check [--lang pt]
```

`--check` writes nothing — no map, workbook or lesson before the questions are answered. Lines with `✗` break the format at the line they name: fix them yourself and run again — never show the person a file
that does not pass. Lines with `!` are what does not hold (`references/look.md`): they become your first questions.

## 3. Ask what is missing — once, all together

One message with every question, numbered, the check's points first, each with your bet and where it comes from
(`references/questions.md`). **One thing per question** — "what does Testing deliver, and who approves it?" is two
questions; and at most 6 in a round. More than 6 open? Ask the 6 that matter most now and keep the rest for the
next round — never squeeze two into one, and nothing asked outside the numbered list. Then stop and wait. Apply the answers, check again, and ask again only about what the
answers opened. What the person skips stays out and goes in your summary as an open point.

If the material answers everything and the check says nothing to look at, skip to step 4 and say so.

## 4. Make what they need

```
node scripts/build.mjs <id>.way.yaml --all [--lang pt] [--out <folder>]
```

- `<id>.html` — **the map**: phases on top, who leads in the rows, the stages in order, the gates; a stage or a gate
  opens its detail (where each input comes from, who receives each output); a **Stages** tab with the table teams know
  (comes in, delivers, roles, metrics; the gate as a row); tabs for roles (RACI), gates and outputs; downloads for the
  workbook, the file and a PNG.
- `<id>.xlsx` — **the workbook**: Summary, Stages, Gates, Roles (RACI), Outputs, KPIs, a Gate checklist and the
  **Thread** (who delivers each output and who receives it).
- `<id>.lesson.html` — **the lesson** (chalk-talk): the flow drawn stroke by stroke, a chapter per phase.

`--html`, `--xlsx` and `--lesson` make one each. End with a short summary: what the flow is in one sentence, the files,
what is still open, and that the `.way.yaml` is the source — the one to keep in version control.

## 5. The way back: someone edited the workbook

```
node scripts/build.mjs <id>.way.yaml --from <edited.xlsx> [--lang pt]
```

prints each change the workbook makes, one per line with its key; `(ask first)` marks the ones that remove something or
change who approves or what a gate checks. **Show the changes and let the person choose** — never take them all on your
own. Then write the chosen ones:

```
node scripts/build.mjs <id>.way.yaml --from <edited.xlsx> --take <key>,<key>…   # or --take all, when they say so
```

and run step 4 again so the map, the workbook and the lesson match the file.

## Never

- Never invent what the material and the person did not say — ask.
- Never put a person's name as a role or a lane, an environment as a phase, an activity or a ritual as a stage.
- Never edit the generated `.html`, `.xlsx` or `.lesson.html`: change the `.way.yaml` and build again.
- This maps how the work *should* go. It does not track items moving through it, nor decide a gate: say so if asked.
