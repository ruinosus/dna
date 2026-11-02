# The profile — `cast-list/profile-v1`

The team's standard, written so a run can check it. **Private**: it names the team's agents. Pass it with
`--profile <file>`; with none, the defaults below hold. A field that is not one of these (a typo) is an error with its
line, so a misspelled `treshold` never goes unnoticed.

```yaml
format: cast-list/profile-v1
name: Customer service agents          # the title of the map and the lesson
roles:
  orchestrator: [main-orchestrator]    # agent folders by name, or "*"
  specialist: "*"                      # everyone not named elsewhere
threshold: 0.7                         # a pattern: in at least 70% of a role's agents…
min_agents: 3                          # …when the role has at least 3 agents
rules:                                 # what every agent of a role must have
  - { id: escalate, role: specialist, has: "trigger:OnEscalate", says: "Every specialist escalates to a person" }
  - { id: kpi, role: specialist, has: "declared:kpi", says: "Every specialist has a KPI" }
focus_areas:                           # filters on the map
  - { id: reliability, name: Reliability, facts: ["trigger:OnError", "node:LogCustomTelemetryEvent"] }
ignore: ["trigger:OnConversationStart"] # facts left out everywhere
microsoft_patterns: on                 # off leaves the ms: facts out
```

| Field | Default | What it does |
|---|---|---|
| `roles` | the orchestrator is whoever calls another agent; the rest are specialists | An agent named here has that role; then the role in the cast file; then `"*"`; then the default. A name with no folder is told in «to look at». |
| `threshold`, `min_agents` | 0.7, 3 | A pattern of a role. It is the **platform's** when the other role has it too. With one orchestrator there is no majority among orchestrators: what only it does is shown apart. |
| `rules` | none | `role` is `orchestrator` or `specialist`; `has` is a key (`references/keys.md`), `declared:<thing>` for what only people know. |
| `focus_areas` | none | Each a filter of the matrix. |
| `ignore` | none | Keys that say nothing for this team. |

The keys are the same in any language; only the screen words change with `--lang`.
