# Skill

A Skill is a modular, progressively-disclosed unit of know-how. It is stored
as a bundle rooted on a `SKILL.md` marker file plus optional `scripts/`,
`references/`, and `assets/` directories. The shape is compatible with
Anthropic's Agent Skills format
(https://docs.anthropic.com/en/docs/agents/skills).

Skills are NOT flattened into the agent's system prompt. Instead, the harness
(e.g. DeepAgents' `SkillsMiddleware`) exposes a short catalogue of
`{name, description}` entries in the system prompt; the agent decides when to
read the full `SKILL.md` on demand via the `read` tool. This keeps the context
window lean while still giving the agent access to deep procedural knowledge.

**Composition:** Agents reference Skills via their `dep_filters.skills`
(alias `agentskills-skill`). A single Skill can be shared across many agents
or modules, resolved either locally or from remote dependencies via the
resolver ports.
