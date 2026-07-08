# Soul

A Soul defines an agent's personality, voice, and guiding principles as prose
— not code. It is stored as a bundle on disk: `SOUL.md` (the canonical body)
plus optional `STYLE.md` and `soul.json` metadata. Canonical spec:
https://soulspec.org.

When an agent references a Soul via `dep_filters.soul`, the kernel flattens
the Soul content directly into the agent's system prompt every turn
(`flatten_in_context=true`). Souls are great when you want several agents to
share a voice: the Soul is the ethos, the agents are the tools.

**Key fields:** `soul_content` (the prose body), `style` overrides, optional
labels for multi-persona sets.

**Divergences from canonical soulspec.org:** the helix implementation does
not ship `IDENTITY.md` or `HEARTBEAT.md` auxiliary files. Everything lives in
the single bundle directory and helix treats the Soul as pure prompt content
rather than an evolving runtime artifact.
