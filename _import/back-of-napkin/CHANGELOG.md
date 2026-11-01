# Changelog

## 0.2.0 — 2026-11-01

Present it, or take it to PowerPoint — with chalk-talk 0.18.0.

- The drawing is built with `--present`: it opens presenting, one chapter at a time on the whole screen, a clicker's
  PageDown to move on and the speaker notes in a window of their own.
- `--pptx static|steps|video|all` and `--settings`: a slide per chapter, per beat or a video of each chapter drawing
  itself, the narration as speaker notes; `--slides <folder>` for Claude's Slides type. `SKILL.md` offers it in one
  line when delivering.
- `scripts/pptx.mjs` (pptxgenjs, MIT) comes from chalk-talk's npm package.
- The check builds the pitch with `--present --pptx`, and so does the Linux check; two evals: «quero o PowerPoint do
  pitch» and «apresentar ao cliente» (built with `--present`).

## 0.1.0 — 2026-11-01

First version: a drawing says what it is for (`kind pitch`, `arch`, `decision`, `data`, `timeline` or `story`) and
follows that purpose's arc — one story with a beginning and an end, stroke by stroke, with a highlight at the end.

- `SKILL.md` picks the purpose and reads only its arc (`arcs/<kind>.md`); the same cheat sheet as chalk-talk.
- The build is chalk-talk's engine (0.17.2, from its npm package); ours refuses a drawing with no purpose, a lesson
  (chalk-talk's) and a Mermaid file, and the engine says what each purpose usually misses (exit 3).
- `references/` (text and recipe) from chalk-talk 0.17.2, for a step outside the cheat sheet.
- Six fictional examples, one per purpose; the check, a Linux check, the gallery and the zip use chalk-talk's kit.
