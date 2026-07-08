# Guardrail

A Guardrail declares a hard safety, compliance, or policy rule that must be
enforced on every turn of an agent's conversation. It is stored as a bundle
rooted on a `GUARDRAIL.md` marker file.

Unlike Skills (which are on-demand procedural know-how), Guardrails are
flattened directly into the agent's system prompt so the rules are always in
view. Each Guardrail carries a `severity` (`low`, `medium`, `high`, `critical`)
and a list of `rules` that the Agent template renders inline.

**Helix-native kind — not guardrails.ai.** This is not a binding for the
`guardrails.ai` runtime validator library. It is inspired by the tripwire /
input-output guardrail pattern from the OpenAI Agents SDK
(https://openai.github.io/openai-agents-python/guardrails/) but implemented
natively as a composable document kind. No external runtime is required;
enforcement is purely prompt-level.

**Composition:** referenced by Agents via `dep_filters.guardrails`
(alias `guardrails-guardrail`).
