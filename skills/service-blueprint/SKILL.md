---
name: service-blueprint
description: Turns what a team knows about a customer journey — interviews, support tickets, survey comments, internal process docs — into a service blueprint that is clear and checkable — each moment the customer lives and how they feel, what they see, and who makes it happen on stage, backstage and in the systems, with promises, pains and actions — delivered as a .blueprint.yaml file, a map page that opens offline, an Excel workbook and a lesson that walks the journey by drawing. Use when someone wants to map a customer or user journey, build a service blueprint, find where customers suffer and who owns it, or prepare a journey review ("blueprint our returns process from these interviews", "where does our onboarding hurt?", "monta o blueprint da devolução").
license: MIT
compatibility: Needs code execution and Node.js 18 or later; nothing to install. Chrome, Chromium or Edge, when installed, lets the script check the lesson's drawing.
metadata:
  version: "1.5.0"
---

# service-blueprint: what the customer lives, and who makes it happen behind

You read what the team has about a journey and write **one file**, `<id>.blueprint.yaml`; `scripts/build.mjs` checks it
and makes the map, the workbook and the lesson. You write only the `.blueprint.yaml`.

Paths below are relative to this skill's folder (the folder this file is in). Write in the person's language and pass
`--lang pt` for Portuguese (`en` is the default).

## 1. Read, then draft — betting, never inventing

Read all of it (interviews, tickets, survey comments, the internal flow). Then write the whole file at once
(`references/format.md`; `examples/` has two finished blueprints):

- **Moments** are what the customer does, in their order, in the customer's words («Waits for news — 6 days of
  nothing»), grouped in **phases**. 4 to 10 is usual.
- **How they feel** (1–5) goes in the file only when the material gives it (a score, a survey). A complaint tells you
  where it hurts, not how much: leave `feels` out and ask, with your bet («I'd say 2 of 5 — 4 of 6 complained»).
- **Who makes it happen**: on stage (what the customer sees: a person, a screen, an email), backstage (people they do not
  see), the systems and partners. **Actors** are roles or areas — never a person's name.
- **Evidence**: what the customer gets or keeps at that moment (a screen, an email, a receipt). A wait with no evidence
  is often the problem itself.
- **Promises** say what was promised, **within** how long and who **owns** it. **Pains** quote what customers said, with
  the **source** («3 of 10 interviews»). **Actions** say what changes, at which moment, with an owner.
- **Never invent** a pain, a number, a promise or an owner the material does not have: what is missing becomes a
  question. Bet what the material implies and say it in your questions.

## 2. Check

```
node scripts/build.mjs <id>.blueprint.yaml --check [--lang pt]
```

`✗` lines break the format at the line they name: fix them yourself. `!` lines are what does not hold
(`references/look.md`) — often exactly what the team needs to see; they become your questions, and some stay as the
blueprint's findings.

## 3. Ask what is missing — once, all together

One message, numbered, **each with your bet** and where it comes from (even «only a guess»): who owns this promise, in
how long, how the customer feels here, what they receive while they wait, what would change at the worst moment. At most 6; one
thing per question — a question that ends with a second one («Is there a deadline? If so, who owns it?») is two: keep the
second for the next round. A question with no bet is not allowed either: when the material is silent, bet the usual
answer and say it is only a guess. Wait, apply, check again. What the person skips stays as a finding.

## 4. Make what they need

```
node scripts/build.mjs <id>.blueprint.yaml --all [--lang pt] [--out <folder>]
```

- `<id>.html` — **the map**: the phases, the line of how the customer feels, the five layers with the three lines
  (interaction, visibility, internal), ⚠ failure points and ⏱ waits; a moment opens its detail; tabs for pains and
  actions, and promises; downloads for the workbook, the file and a PNG; «To look at» on top.
- `<id>.xlsx` — **the workbook**: Summary, Blueprint, Pains and actions, Promises, Systems.
- `<id>.lesson.html` — **the lesson** (chalk-talk): the journey walked moment by moment.

End with a short summary: the journey in one sentence, **the worst moment and who owns it (or that nobody does)**, the
files, and what is still open.

## Never

- Never invent what the material and the person did not say — ask.
- Never put a person's name as an actor, or a number on a feeling nobody reported.
- Never edit the generated files; change the `.blueprint.yaml` and build again.
