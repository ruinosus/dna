# Changelog

## 1.0.0 — 2026-11-01

The five skills become one plugin, **house-lights**, in one repository.

- **One install:** `/plugin install house-lights@house-lights` brings chalk-talk, back-of-napkin, dress-rehearsal,
  gates-and-handoffs and service-blueprint.
- **Two new names:** stage-door is **gates-and-handoffs**, front-of-house is **service-blueprint**. The file formats
  keep their ids (`stage-door/v1`, `front-of-house/v1`): every file made before still opens.
- **One command:** `npx house-lights <skill> <file>`, with each skill's own options and exit codes. The packages
  `back-of-napkin`, `stage-door`, `front-of-house` and `dress-rehearsal` move to it; `chalk-talk` stays the engine's
  package.
- **The engine of chalk-talk 0.18.1 everywhere:** dress-rehearsal, gates-and-handoffs and service-blueprint drew
  their lessons with the engine of 0.14.1; now every skill takes it from this repository, in the same commit.
- One gallery: https://ruinosus.github.io/house-lights/, with a page per skill.
- The npm package `chalk-talk` 0.19.0: the same engine as 0.18.1, now built in this repository.

Before 1.0.0, each skill's history is in `dev/<skill>/CHANGELOG.md` and its tags are `<skill>-v<version>`.
