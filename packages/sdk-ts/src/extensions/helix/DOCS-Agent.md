# Agent

A Agent is the primary prompt target in a helix manifest — it is
what actually runs when a user (or another agent) talks to the system. It
carries an `instruction` (the agent's main prompt, usually a bundled
`AGENT.md`), a `model` to call, and `dep_filters` that declare which Soul,
Skills, Guardrails, and Actors it composes with.

**Prompt assembly.** Every turn the kernel builds the agent's system prompt
by rendering the `prompt_template`: the instruction body comes first, then
the Soul content (flattened in full), then each Guardrail (name, severity,
and rules). Skills are deliberately NOT flattened — they are exposed via
Agent Skills progressive disclosure so the context window stays lean.

**Priority.** `prompt_target_priority = 10` means Agent wins over
other prompt-target kinds when the harness has to pick one to run.

**Storage.** Bundle-based: `agents/<name>/AGENT.md` with optional
`scripts/`, `references/`, and `assets/` subdirectories. Canonical api
version: `github.com/ruinosus/dna/v1`.
