# The review file and the facts

## `<id>.review.yaml` — `kind: AgentReview`

What people said about the agents and what was decided. `scripts/build.mjs` writes it on the first run and keeps it
up to date (it is read again on every run); its comments and layout stay. Edit it by hand, or fill the workbook and read
it back with `--from` / `--take`. A problem in it is an error with its line.

```yaml
apiVersion: github.com/ruinosus/dna/v1
kind: AgentReview
metadata:
  name: Customer service agents
agents:                      # the roles of the last run (an agent the profile does not name keeps its role here)
  - { id: main-orchestrator, role: orchestrator }
  - { id: returns, role: specialist, types: [ transaction ] }   # types a person gives win over the profile's
blocks:                      # the blocks of text of the last run, so a block keeps its id across small edits
  - id: links
    text: |
      Links:
      - Format links as [title](url), never the bare URL.
declared:                    # what a document or a person says — always with its source
  - { agent: returns, key: kpi, value: "time to answer < 2 min", source: "backlog, epic 12" }
  - { agent: shipping, key: "trigger:OnEscalate", value: "yes", source: "handoff, section 4" }
decisions:                   # what the team decided about a pattern
  - { key: "trigger:OnEscalate", status: accepted, scope: platform, why: "Nobody is left without a person" }
```

- **blocks** and the roles are written by the run; **types** are written only by a person (the ones the profile works
  out are not kept, so a change in the profile still holds).
- **declared**: `key` is either something only people know (`kpi`, `owner`, any word: it becomes `declared:<key>`) or a
  fact key (`trigger:OnEscalate`, `references/keys.md`) when a document claims the agent does it. `value` `no` / `não` /
  `false` claims it does **not**. A claim never changes what the YAML shows: when they disagree, it is a conflict.
- **decisions**: `status` is `accepted` or `rejected`; `scope` is `platform` (every agent), `specialist`,
  `orchestrator` or `type:<id>` (the specialists of a type — «tipo:<name>» in the workbook); `why` says it. An accepted pattern is checked on every agent of its scope on the next run — even when
  its share would no longer make it a pattern. A rejected one is shown and nobody is off it.

## The workbook back

## A spreadsheet from outside

`--declared <table.csv|.xlsx>` (more than once is fine) reads a table the team already has — the admin center's
inventory download, the team's list — and proposes a `declared:` line per agent and column, with the source
`<file> › line <n>` (`<file> › <sheet> › line <n>` for an .xlsx). The agent's column is found by its values; the key is
the column's title in lower case with `-` (`Linha de base` → `linha-de-base`; `Dono`/`Equipe`/`Squad` → `team`, the inventory's `Owner` → `owner`, `KPI`/`Indicador`
→ `kpi`). Listed with keys (`d1`…), written with `--take`, like the workbook below. Two tables saying the same key of
the same agent: the later one holds.

In Excel, fill the **Declared** sheet (who, key, value, source) and the **Decision** column of **Patterns** (`accepted` /
`aceito`, `rejected` / `rejeitado`; **Scope** and **Why** beside it). Then:

```
node scripts/build.mjs <agents-folder> --from <filled>.xlsx                 the changes, each with a key (d1…, p1…)
node scripts/build.mjs <agents-folder> --from <filled>.xlsx --take d1,p1    writes the chosen ones (or --take all)
```

A line deleted or a decision cleared is a change too.

## `<id>.facts.json` — `agent-review/facts-v1`

`--facts` writes what was seen, for a model to read before it adds what people declared:

```json
{ "format": "agent-review/facts-v1",
  "agents": [ { "id": "shipping", "schemaName": "cr7b2_shipping", "displayName": "Shipping",
                "facts": { "trigger:OnUnknownIntent": [ { "file": "topics/Fallback.topic.mcs.yml", "line": 7 } ] },
                "children": [], "unknown": [] } ] }
```

An orchestrator's agent also has `contract` — a line per connected-agent action: `calls` (the schema name it calls),
`name` (the action's name for it), `history` (it passes the conversation history), `inputs`, `description` (the
routing description), `file` and `line` — and every agent has `flows`: `id` (the `workflowId`), `name`, `folder`,
`uses` (`http:<host>`, `connector:<api>`, `operation:<api>/<op>`, `child-flow`), `returns`, `called` and `file`.

## The facts of the contract, the flows and what nobody uses

| Key | On which agent | From |
|---|---|---|
| `called-with:history` | the one called | the orchestrator's action has `historyType: ConversationHistory` |
| `called-with:input:<name>` | the one called | each input the orchestrator's action passes |
| `routing:described` | the one called | the action has a `modelDescription` |
| `flow-uses:http:<host>`, `flow-uses:connector:<api>`, `flow-uses:operation:<api>/<op>`, `flow-uses:child-flow` | the one whose node calls the flow | the actions of `workflow.json`, at any depth |
| `flow-returns` | the same | the flow has a `Response` action |
| `orphan:topic:<name>`, `orphan:action:<name>`, `orphan:variable:<name>`, `orphan:flow:<name>` | the one that has it | nothing can reach it (see SKILL.md, step 2) |
| `disabled:node:<kind>`, `disabled:<topic\|action\|variable\|knowledge>:<name>` | the one that has it | `disabled: true` on a node; `state` or `status: Inactive` on a component |

| `telemetry:event:<form>` | the one that logs it | a `LogCustomTelemetryEvent` node; the form is its `eventName` with the agent's own name as `{agent}` (part of `node:LogCustomTelemetryEvent`) |
| `telemetry:field:<form>/<field>` | the same | each field of the node's `properties` record (part of its event) |

Every agent also has `telemetry` in `<id>.facts.json`: `name` (as written), `form`, `fields` (absent when the record is
a formula), `file` and `line`. An event spelt another way counts as the most common form in the comparison.

The contract's facts cite the orchestrator's file (`<orchestrator>/actions/X.mcs.yml`). `orphan:` and `disabled:` are
never a pattern nor a solo, and what an unused flow calls is not a fact.
