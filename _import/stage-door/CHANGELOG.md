# Changelog

## 0.2.0 — 2026-10-30

- **The thread between stages.** An input points to the output of an earlier stage or gate (`from: <id>`) or comes from
  outside (`name: …`); a plain text still reads, and links by itself when it is an output's name.
- **Gates have outputs** (the decision, what was approved), and **stages and gates have metrics**.
- The map: a **Stages** tab (comes in, delivers, roles, metrics; the gate as a row); the detail says where each input
  comes from and who receives each output, and lights the stages tied to the one picked.
- The workbook: where each input comes from, Metrics and Description in Stages, What comes out and Metrics in Gates,
  and a **Thread** sheet; the way back reads them.
- The check: an input from nowhere, one that arrives late, an output nobody receives, a gate with nothing coming out
  (only when the file describes inputs). The lesson says what each stage receives.
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
  downloads); the workbook (`.xlsx`: Summary, Stages, Gates, Roles (RACI), Outputs, KPIs, Gate checklist); the lesson
  (`.lesson.html`, chalk-talk's player); `--from edited.xlsx` and `--take` for the way back.
- Three fictional examples (feature delivery, Scrum, service desk), evals, the gallery and the npm package.
