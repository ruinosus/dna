# Copilot kits — a complete flow installed as instances

A **copilot kit** is a directory of DNA instances — typically a `KindDefinition`
for the domain, an `Agent` that speaks for it, and a `Copilot` whose
`spec.surfaces[]` declares the guided flow (state key, canvas keys, blocked
persistence tools, and the wizard's `steps[]`). Installing the kit is what makes
the flow exist: no code ships, because the runtime that reads these instances is
already generic — the surface middleware projects the agent's patches into
shared state, and a portal can render the wizard straight from the declaration
crossed with the target Kind's registered schema.

```bash
dna copilot install copilot-kits/contrato-intake --scope my-scope
dna copilot install <dir> --dry-run     # list the plan, write nothing
dna copilot install <dir> --approve     # the operator approves the Kind on the spot
dna copilot install <dir> --json        # machine-readable output
```

## What `dna copilot install` does

`dna copilot install` scans the directory for DNA instances (YAML with
`apiVersion` / `kind` / `metadata.name`; anything else — README, fixtures — is
skipped with a note), orders them so definitions land before their consumers
(`KindDefinition` → `PromptTemplate` → `Agent` → `Copilot`), and writes each one
through `kernel.write_instance`. That last part is the point: every guard the
write door has — schema validation, tombstones, layer policy — fires exactly as
it would for any other write. The installer re-implements nothing.

Two refusals are deliberately loud:

- **An unparseable `KindDefinition` is refused before anything is written.**
  The registration funnel parses Kind definitions with `TypedKindDefinition`
  and warn-skips what does not parse — which means a definition missing a
  required field (the measured case: `spec.alias`) would write fine, list as
  approved, and *never govern anything*: a phantom Kind, discovered in another
  process's logs. The installer validates with the same parser first and names
  the missing field to the person who can fix it.
- **A `KindDefinition` without `approved_by` installs INERT.** Authoring a Kind
  and putting it into effect are two acts by two actors. Without approval the
  Kind stays an instance — auditable, listable — and registers nothing. Passing
  `--approve` stamps the operator (`git config user.email`) as approver at
  install time: running the command with the flag *is* the human act, in a
  self-hosted deployment. In a hosted deployment, approval stays in the portal.

## Anatomy of a kit

The showcase kit at `copilot-kits/contrato-intake` is the proof that a complete
flow is data:

| file | kind | what it declares |
|---|---|---|
| `kind-contrato.yaml` | `KindDefinition` | the domain record (schema, storage, required fields) |
| `agent-contrato.yaml` | `Agent` | the copilot's voice and instructions |
| `copilot-contrato.yaml` | `Copilot` | mounts, serving, and `spec.surfaces[]` — the flow itself |

The surface entry carries the flow's contract: `state_key` / `tool_name` /
`canvas_keys` bind it to the generic draft middleware, `blocked_persist_tools`
keeps memory-writing tools out of the flow's threads, `kind` names the target
Kind, and `steps[]` declares the wizard (each step's `fields` name properties
of the target Kind's schema; a `gate: true` step only advances by explicit
human action). A consuming portal renders the wizard from that declaration —
see the `Copilot` Kind reference for the full field list.
