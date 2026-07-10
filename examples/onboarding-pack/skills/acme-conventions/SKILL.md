---
name: acme-conventions
description: "Use when working in an Acme project and you need the house engineering conventions \u2014 branch naming, review checklist, definition of done, and how work is tracked on the DNA board."
---

# Acme engineering conventions

This skill carries the conventions Acme distributes to every consumer
project through its onboarding pack (`dna init --from`). It is a generic
example — replace the content with your team's real conventions.

## Branching + commits

- Branch names: `feat/<story-slug>`, `fix/<issue-slug>`.
- Commits are small and message-first: one line of intent, then context.
- While a story is active, the git hook stamps `Work-Item:` trailers —
  never remove them.

## Review checklist

Before opening a PR:

1. The story's acceptance criteria are all demonstrably met.
2. Tests cover the new behavior (happy path + at least one failure mode).
3. Docs are updated when a public surface changed.
4. `dna sdlc story pr <s-...>` — the PR is born from the story.

## Definition of done

Code merged + CI green + docs updated + a passing TestRun recorded on the
board (`dna sdlc test-run record`). A story in `review` with no open PR is
stale; `done` before the merge is a lie.
