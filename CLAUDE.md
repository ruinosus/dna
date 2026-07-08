# CLAUDE.md

**Read [`AGENTS.md`](AGENTS.md) first** — it is the agent-agnostic source of
truth for this repo: what DNA is, layout, build/test commands, conventions,
and the `dna sdlc` work-tracking protocol. This file adds only what is
specific to Claude Code; nothing here duplicates it.

## Claude Code specifics

- **Skill `dna-sdlc-cli`** (`.claude/skills/dna-sdlc-cli/SKILL.md`) — the
  full SDLC workflow conventions (story-first, plan gate, narration, test
  gate, `story pr`, git trailers). It loads automatically from this
  checkout; clones installed as a plugin get it via the bundled marketplace
  (`.claude-plugin/marketplace.json`, plugin `dna`). Invoke it before any
  lifecycle operation.
- **Session start:** run `dna sdlc brief` (one-screen bootstrap: in-flight
  work, open spikes, recent lessons) before picking up work.
- **Once per clone:** `dna sdlc hooks install`, so your commits carry the
  `Work-Item:` trailer while a story is active.
- **The `dna` binary** comes from the CLI venv: after the
  `packages/cli` install in AGENTS.md, run it from the repo root (default
  source `./.dna`), e.g. `packages/cli/.venv/bin/dna sdlc current`.
