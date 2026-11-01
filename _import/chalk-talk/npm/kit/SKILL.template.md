---
name: <the-skill>
description: <What it makes, in one sentence> — <what comes out: one file that opens offline, a workbook…>. Use when someone asks to <the requests, in the words people use, in English and Portuguese> ("…", "…"), or <the situation it fits>.
license: MIT
compatibility: Best with code execution and Node.js 18 or later (Chrome, Chromium or Edge, when installed, lets the script check the result first).
metadata:
  version: "0.1.0"
---

<!-- The shape the skills of this kit share (chalk-talk, stage-door, dress-rehearsal, front-of-house). A reference for
a new skill, not a file the skills import: copy it, then replace every <…>. Keep SKILL.md under 500 lines; what the
model only needs sometimes goes in references/. -->

# <the-skill>: <what it does, in a few words>

You write only the **source** (`<id>.<ext>`, a short text a person can read and change); `scripts/build.mjs` checks
it and makes everything else. Never write what the script makes. Paths are relative to this skill's folder.

## 1. Make it first

For an ordinary request **do not ask and do not show a plan: make it.** Decide what is missing yourself — the
reasonable bet, never an invented fact — and say what you chose when you deliver.

Ask first — once, all together, only what is missing — when <the cases where a wrong guess is costly: for a class, a
real decision, data only the person has>, when the request could mean two things, or when the person asks to see the
plan.

## 2. Write the source

<The cheat sheet: the lines of the usual case, each a line that builds (the kit's checks build every example). The
whole format in references/<format>.md, opened only when a line is not in the sheet or a message does not settle a
mistake.>

## 3. Build and check

```
node scripts/build.mjs <id>.<ext>
```

- `✗ <file>:<line>: …` (exit 1, nothing written): fix that line the way the message says.
- `! …` (exit 3): made, but the check found something to fix — fix it and build again.
- `✓ …`: done. `✗ … not checked`: done, but tell the person it was not checked.

At most **two** rounds of fixes; then deliver and say in plain words what is left.

## 4. Deliver

The path of what was made (or the file itself where the person downloads files), in one line **what you chose and an
offer to change it**, and one sentence on what to look at first.

## Never

- Never edit `assets/` or the generated `scripts/`.
- Never put HTML, links or scripts in the source.
- Never invent a fact, a number or a quote to fill a gap: ask, or leave it visibly open.
