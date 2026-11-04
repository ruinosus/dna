---
name: dress-rehearsal
description: Turns a team's incident runbook (or a post-mortem) into a playable incident drill — one HTML file that opens offline, with a clock, scenes, things that come in, choices with consequences, who is in the room and the impact — and a debrief that shows what the runbook does not say (who tells the customers, who has the access, escalate to whom). Use when someone wants to rehearse, drill, practice or test an incident runbook or on-call procedure, run a tabletop exercise or a «wheel of misfortune», or train new people for on-call ("make a drill from our checkout runbook", "monta um ensaio de incidente com esse runbook").
license: MIT
compatibility: Needs code execution and Node.js 18 or later; nothing to install.
metadata:
  version: "1.11.0"
---

# dress-rehearsal: test your runbook by playing it

You read the team's runbook and write **one file**, `<id>.drill.yaml`: the incident as scenes the players go through,
the choices at each one and what each costs. `scripts/build.mjs` checks it and makes the game — a page with a clock,
the scene, what just came in, the choices, who is in the room and the impact — and a debrief at the end. You write only
the `.drill.yaml`; never write the game page yourself.

Paths below are relative to this skill's folder (the folder this file is in). Write in the person's language and pass
`--lang pt` for Portuguese (`en` is the default).

## 1. Read the runbook, then draft — betting, never inventing

Read the runbook (and any post-mortem or alert the person gives). Save the drill **beside the runbook's folder** with
`from:` pointing at the runbook file, so the game can show each passage and the check can see the marks exist. Write
the whole drill at once (`references/format.md`; `examples/` has two finished drills with their runbooks):

- **The opening** is what really starts it: the alert, the page, the message. `clock` is when the player comes in.
- **A scene is what the players see now** (a dashboard, a message, a result); its **choices** are what a person would
  really consider there — the runbook's step, and the tempting wrong ones (the shortcut, «it's probably nothing», the
  fix that takes an hour). Each choice cites the runbook's mark it follows (`runbook: §2`; a numbered step under a heading is the heading and
  its number, `runbook: Steps 4`), costs `minutes`, adds
  impact (`lost`), may need an access (`needs`) that only some role `can`, may bring someone in (`calls`), may tell the
  people affected (`notifies`). 2 to 4 choices per scene; 6 to 12 scenes; at least one end that resolves and one that
  gets worse.
- **Roles** are who could be in the room (the player `you: true`, on-call, incident lead, the team that can deploy,
  communications). An access the runbook gives to someone the player is not is the heart of a drill: put it on that role.
- **The situation is fiction; the team is not.** The scenario's numbers (42% of payments failing, 03:12, 150 lost
  orders) are made up for the exercise — say once that they are. What you **never invent** is the team's world: a
  system, a tool, a procedure, a person or an access the material does not have. Use what it says; ask the rest.
- **Bet** consequences the runbook implies (reverting takes minutes; deleting the wrong files breaks the database) and
  say them in your questions. The tempting wrong choices are yours to imagine, as long as they use what the team has.
- **`gaps`**: every thing the runbook does not say that a player will need (who tells the customers, who has the access,
  escalate to whom, when), each with the part of the runbook it was missing from. These are the drill's real product.
- A drawing (`draw:`, chalk-talk's text) is optional: one or two scenes where a picture says it faster (a graph going up).

## 2. Check

```
node scripts/build.mjs <id>.drill.yaml --check [--lang pt]
```

`✗` lines break the game at the line they name (a choice to no scene, a scene with no way on, a drawing that does not
read): fix them yourself. `!` lines are what does not hold (`references/look.md`): they become questions.

## 3. Ask what is missing — once, all together

One message, numbered questions, **each with your bet** and where it comes from — even when the runbook gives nothing,
bet the usual answer and say it is only a guess («I'd guess the incident lead — only a guess»); not betting is not the
same as not inventing: who can do what (the accesses), who tells
the people affected and when, escalate to whom, what really happens if they choose X. At most 6; **one thing per
question** — «who turns it on, and how?» is two; keep the second for the next round. Wait. Apply the answers, check again. What the person skips stays a gap.

If the runbook answers everything and the check finds nothing, say so and go on.

## 4. Make the game

```
node scripts/build.mjs <id>.drill.yaml --all [--lang pt] [--out <folder>]
```

- `<id>.drill.html` — **the game**: open it and play (alone, or projected for the team: each role decides its part).
  No score — the clock and what was left behind are the score. The end shows the debrief: the numbers, the timeline,
  what the runbook did not say, play again, and `debrief.md` and the improvements as `.csv` to download.
- `<id>.facilitator.md` — **the facilitator's script**, every scene and path (spoilers).

End with a short summary: the drill in one sentence, the files, **the gaps found** (the runbook's fixes), and how to run
it (alone in 10 minutes, or as a 30-minute team session).

## Never

- Never invent what the runbook and the person did not say — ask, or leave it as a gap.
- Never make a drill that cannot be lost: there is always a tempting choice that makes it worse.
- Never edit the generated page; change the `.drill.yaml` and build again.
