# The cast file and the facts

## `<id>.cast.yaml` — `cast-list/cast-v1`

What people said about the agents and what was decided. `scripts/build.mjs` writes it on the first run and keeps it
up to date (it is read again on every run); its comments and layout stay. Edit it by hand, or fill the workbook and read
it back with `--from` / `--take`. A problem in it is an error with its line.

```yaml
format: cast-list/cast-v1
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

In Excel, fill the **Declared** sheet (who, key, value, source) and the **Decision** column of **Patterns** (`accepted` /
`aceito`, `rejected` / `rejeitado`; **Scope** and **Why** beside it). Then:

```
node scripts/build.mjs <agents-folder> --from <filled>.xlsx                 the changes, each with a key (d1…, p1…)
node scripts/build.mjs <agents-folder> --from <filled>.xlsx --take d1,p1    writes the chosen ones (or --take all)
```

A line deleted or a decision cleared is a change too.

## `<id>.facts.json` — `cast-list/facts-v1`

`--facts` writes what was seen, for a model to read before it adds what people declared:

```json
{ "format": "cast-list/facts-v1",
  "agents": [ { "id": "shipping", "schemaName": "cr7b2_shipping", "displayName": "Shipping",
                "facts": { "trigger:OnUnknownIntent": [ { "file": "topics/Fallback.topic.mcs.yml", "line": 7 } ] },
                "children": [], "unknown": [] } ] }
```
