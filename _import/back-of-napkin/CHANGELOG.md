# Changelog

## 0.1.0 — 2026-11-01

First version: a drawing says what it is for (`kind pitch`, `arch`, `decision`, `data`, `timeline` or `story`) and
follows that purpose's arc — one story with a beginning and an end, stroke by stroke, with a highlight at the end.

- `SKILL.md` picks the purpose and reads only its arc (`arcs/<kind>.md`); the same cheat sheet as chalk-talk.
- The build is chalk-talk's engine (0.17.2, from its npm package); ours refuses a drawing with no purpose, a lesson
  (chalk-talk's) and a Mermaid file, and the engine says what each purpose usually misses (exit 3).
- `references/` (text and recipe) from chalk-talk 0.17.2, for a step outside the cheat sheet.
- Six fictional examples, one per purpose; the check, a Linux check, the gallery and the zip use chalk-talk's kit.
