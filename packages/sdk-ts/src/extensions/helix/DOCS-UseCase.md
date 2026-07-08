# UseCase

A UseCase is a UML-canonical use case document: a goal-oriented interaction
between one or more Actors and the system. It composes a primary actor,
supporting actors, and the agent(s) that fulfill the goal, then carries the
classical UML fields: `preconditions`, `main_flow`, `alternate_flows`,
`postconditions`, and `success_criteria`. Canonical api version:
`github.com/ruinosus/dna/v1`.

**Not a prompt target.** A UseCase is purely declarative — it documents how
the manifest's agents and actors are meant to work together to achieve a
business goal. It is structural composition metadata, consumed by tooling
(navigators, doc generators, validators) rather than by the LLM directly.

**When to use.** Reach for UseCases when a helix manifest is complex
enough that the relationship between actors and agents is non-obvious, or
when you need machine-readable traceability from requirements to the agents
that implement them.

**Storage.** Flat YAML file at `use_cases/<name>.yaml`.
