# The profile — `kind: AgentStandard`

The team's standard, written so a run can check it. **Private**: it names the team's agents. Pass it with
`--profile <file>`; with none, the defaults below hold. A field that is not one of these (a typo) is an error with its
line, so a misspelled `treshold` never goes unnoticed.

```yaml
apiVersion: github.com/ruinosus/dna/v1
kind: AgentStandard
metadata:
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
| `roles` | the orchestrator is whoever calls another agent; the rest are specialists | An agent named here has that role; then the role in the review file; then `"*"`; then the default. A name with no folder is told in «to look at». |
| `threshold`, `min_agents` | 0.7, 3 | A pattern of a role. It is the **platform's** when the other role has it too. With one orchestrator there is no majority among orchestrators: what only it does is shown apart. |
| `rules` | none | `role` is `orchestrator` or `specialist`; `has` is a key (`references/keys.md`), `declared:<thing>` for what only people know. |
| `focus_areas` | none | Each a filter of the matrix. |
| `ignore` | none | Keys that say nothing for this team. |

## What to look for in the text, and the types

```yaml
rules:
  # a condition and a «not»: the text says one thing, the setup another
  - { id: knowledge-only, when: "text:knowledge-only", not: "setting:model-knowledge=on",
      says: "Who asks for the knowledge alone has the model's general knowledge off" }
markers:                               # JavaScript regular expressions; case does not matter
  - { id: size, name: Answer size, in: instructions,
      pattern: '(at most|up to|no máximo)\s*(\d+)\s*(bullets?|sentences?|frases?)', value: "$2 $3" }
  - { id: no-emoji, name: No emojis, pattern: '(no|never use|sem)\s+emojis?' }
  - { id: knowledge-only, name: Knowledge only, pattern: '(only|somente)[^.]{0,40}(knowledge|conhecimento)' }
blocks:                                # the text the team pastes in every agent of a role
  - id: links
    name: Link formatting
    role: specialist                   # the default
    text: |
      Links:
      - Format links as [title](url), never the bare URL.
types:                                 # a specialist gets every type whose «when» its facts match
  - { id: transaction, name: transaction, when: { any: ["flow:*"] } }
  - { id: guidance, name: guidance, when: { all: ["text:link-domain:*", "node:SearchAndSummarizeContent"], none: ["flow:*"] }, min_agents: 2 }
```

| Field | What it does |
|---|---|
| `rules[].when` / `has` / `not` | A rule is for the agents (of its `role`, or all) that have every key of `when`; it is broken when one lacks `has`, or has `not`. A key may end in `*`. A broken `not` rule is said as a contradiction. |
| `markers` | `in`: `instructions` (the default), `descriptions` (what topics and actions tell the model) or `all`. With no `value`: a fact `text:<id>`. With a `value` (`$1`…`$9` from the regex): `text:<id>=<value>` — agents of a role that set it in different ways are told («unify?»), and one that sets it twice («which one holds?»). Two are built in: `text:link-domain:<host>` for each link in the instructions, `text:email`. In YAML, write a regex in single quotes. |
| `blocks` | The official text. The family of blocks like it (half of it, at least) takes its id and name; every agent of `role` without it, or with a variation, is off it — with or without a majority. With no `blocks`, the blocks two agents or more share are still found, named by their first words. |
| `types` | `when` with `all`, `any` (one of), `none`. A specialist may be of two types; the review file's `types` for an agent win. Patterns are found within each type with its `min_agents` (2 unless said), scope `type:<id>`; a pattern of a type never blames who is not of it. A type with fewer agents is told, and compared in nothing. |

A key in `when`, `has`, `not` or a type must start like a real kind of key (`references/keys.md`): a typo is
`✗ profile:line`, as is a regex that does not compile, an unknown `in`, a type with no `when`, or a rule with
nothing to check.

The keys are the same in any language; only the screen words change with `--lang`.
