# Actor

An Actor is a UML-canonical participant in the system — a human user, an
external system, or a time/schedule trigger. Actors describe WHO or WHAT
initiates or collaborates with agents, separating role identity from the
agents that fulfill that role. Canonical api version:
`github.com/ruinosus/dna/v1`.

**Actor types.** The `actorType` field disambiguates:
- `human` — a person or role (e.g. "support specialist", "admin")
- `system` — an upstream service or external system triggering behavior
- `time` — a scheduled or cron-like trigger

**Composition.** Actors are referenced by UseCases (as `primary_actor` and
`supporting_actors`) and by Agents through `dep_filters.actors`.
Actors are NOT prompt targets on their own — they are structural metadata
that lets manifests document and wire the cast of characters around an
agent without embedding role descriptions in prompts.

**Storage.** Flat YAML file at `actors/<name>.yaml`.
