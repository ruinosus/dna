# AGENTS.md — Acme engineering conventions

This file was projected by `dna init --from` out of Acme's onboarding pack.
It is a live `agents.md/v1` instance — the canonical instruction surface
read by 28+ agent tools — and it replaces the default AGENTS.md that
`dna init` would otherwise embed.

## How we work

- **Story-first.** Non-trivial work starts on the board (`dna sdlc story
  create` with `--ac`/`--dod`) before the first line of code.
- **Narrate as you go.** Post `dna sdlc story comment` for each meaningful
  step or decision; the timeline is what reviewers and future sessions read.
- **Small PRs.** One story, one branch, one reviewable PR. The PR is born
  from the story (`dna sdlc story pr`).
- **Tests before done.** `story done` requires a passing TestRun — record it
  with `dna sdlc test-run record`.

## House rules

- Follow the `acme-conventions` skill (projected next to this file into your
  tool's skills directory) for the full checklist.
- Prefer editing existing modules over adding new ones; keep public
  surfaces documented.
- Never commit generated artifacts without reviewing them first.
