# Changelog

## 0.5.0 — 2026-11-12

The map's downloads work when it is embedded (DNA 2.5.0): inside an iframe the Excel, YAML and PNG go to the parent
page as a `dna:download` message, and the page downloads them itself when no parent answers.

## 0.4.0 — 2026-11-12

The map reads as a flow (DNA 2.4.0): arrows between the stages, a visible cue and **Fit to width** when the map is
wider than its box, each gate also in the row of whoever approves it, the approver on its own line, a legend, the
reason of a mark on hover, and `--no-look` for a published map (`To look at` folded, no marks).

## 0.3.0 — 2026-11-01

The explainer's review no longer hangs in cloud sandboxes.

- The headless browser is chalk-talk's kit (`chalk-talk/kit`, from its npm package): it talks to the browser over the
  DevTools pipe instead of `--dump-dom`, which hung until a timeout on some machines. It finds Playwright's Chromium,
  runs without the sandbox as root on Linux, and tries the next browser when one fails. A review that could not run
  now says «not checked».
- The gallery's pictures are taken over the same pipe. The zip, the name audit and a Linux check
  (`npm run linux`) come from the kit.
- The explainer uses chalk-talk 0.14.1 and its engine (chains, the new props, a figure over a figure found by the
  review).

## 0.2.0 — 2026-10-30

- **The thread between stages.** An input points to the output of an earlier stage or gate (`from: <id>`) or comes from
  outside (`name: …`); a plain text still reads, and links by itself when it is an output's name.
- **Gates have outputs** (the decision, what was approved), and **stages and gates have metrics**.
- The map: a **Stages** tab (comes in, delivers, roles, metrics; the gate as a row); the detail says where each input
  comes from and who receives each output, and lights the stages tied to the one picked.
- The workbook: where each input comes from, Metrics and Description in Stages, What comes out and Metrics in Gates,
  and a **Thread** sheet; the way back reads them.
- The check: an input from nowhere, one that arrives late, an output nobody receives, a gate with nothing coming out
  (only when the file describes inputs). The explainer says what each stage receives.
- A fourth example, the initiative portfolio; the three others now carry the thread.

## 0.1.1 — 2026-10-30

- Smaller: `scripts/engine.mjs` 720 KB → 176 KB and the map page 96 KB → 36 KB — the engine's code the skill does
  not use (zod, React, i18n) is left out of the bundles. Nothing else changes.

## 0.1.0 — 2026-10-30

First version.

- The skill: read a team's material, draft one `.way.yaml` (format `stage-door/v1`) betting and never inventing,
  check it, ask what is missing once and all together, then make what the person needs.
- `scripts/build.mjs`: `--check` (each problem with its line; what does not hold as «to look at»); the map (`.html`,
  offline: grid of phases × who leads, stage and gate detail, Roles (RACI), Gates and Outputs tabs, Excel / YAML / PNG
  downloads); the workbook (`.xlsx`: Summary, Stages, Gates, Roles (RACI), Outputs, KPIs, Gate checklist); the explainer
  (`.explainer.html`, chalk-talk's player); `--from edited.xlsx` and `--take` for the way back.
- Three fictional examples (feature delivery, Scrum, service desk), evals, the gallery and the npm package.
