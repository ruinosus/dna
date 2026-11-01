# Changelog

## 0.2.0 — 2026-11-01

The skill's own checks and pictures move to chalk-talk's kit.

- The drill is read by the kit's YAML reader (`chalk-talk/kit`), with the same messages and the same lines, the
  drawings' lines included.
- The check plays each example to the end in a headless browser over the DevTools pipe (no `--dump-dom`), and the
  gallery's pictures are taken the same way. The zip and the name audit come from the kit.
- The drawings use chalk-talk 0.14.1's contract.

## 0.1.0 — 2026-10-30

First version: a drill made from an incident runbook (format `dress-rehearsal/v1`), checked on its graph, played in one
offline HTML page (clock, scenes, injects, choices with consequences, who is in the room, impact, the runbook's
passages, chalk-talk drawings) with a debrief of what the runbook does not say; the facilitator's script; two fictional
examples; evals; the gallery; the npm package.
