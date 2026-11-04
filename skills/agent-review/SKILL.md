---
name: agent-review
description: Compares a team's Copilot Studio agents with each other, from the folders the VS Code extension clones — what most of them do, in their YAML and in the text of their instructions (a pattern to agree on, per role and per type), who is off a pattern, what only one has (innovation or debt), the team's rules not met, and what people say the YAML contradicts — with the file and line of each. Delivers an offline map, an Excel workbook to decide in, a lesson, the agents as a team, Mermaid diagrams for the docs, and a review file that keeps the decisions. Node alone: no model, no install, no network. Use when someone wants to find patterns across Copilot Studio agents, define standards from evidence, check a new agent against the accepted ones, see which agents escalate, log telemetry or use which connectors, or bring in a spreadsheet about them ("compare our Copilot Studio agents", "which of our agents is off the pattern?", "compara os agentes do Copilot Studio", "o que se repete entre os especialistas?").
license: MIT
compatibility: Needs code execution and Node.js 18 or later; nothing to install. Chrome, Chromium or Edge, when installed, lets the script check the lesson's drawing. The Microsoft skills for Copilot Studio are recommended, not needed.
metadata:
  version: "2.1.0"
---

# agent-review: what the agents have in common, and who is off it

The agents are cloned from Copilot Studio (the VS Code extension writes a folder per agent, with `agent.mcs.yml`).
`scripts/build.mjs` reads them, compares them and makes the map, the workbook, the lesson, the agents as a team, the
topology and the review file — **with no model**. You run it, read what it found, and help the person decide. You never edit an agent.

Paths below are relative to this skill's folder (the folder this file is in). Write in the person's language and pass
`--lang pt` for Portuguese (`en` is the default).

**The outputs hold the client's data** (agent names, connectors, instructions). They stay in the client's environment:
never paste them anywhere else, never commit them to a public repository.

## 1. Run it

```
node scripts/build.mjs <agents-folder> --all [--profile <team>.standard.yaml] [--lang pt] [--out <folder>]
```

- `<agents-folder>` holds the cloned agents (any depth: a folder with `agent.mcs.yml` is an agent; a child agent in
  `agents/<Name>/` stays with its parent; hidden folders such as `.mcs/` are never read). The flows in
  `workflows/<Name>-<id>/` (`metadata.yml` and the `workflow.json` definition) are read too.
- The **profile** is the team's standard, private to the team (`references/profile.md`): who is the orchestrator, how
  common a fact must be to be a pattern (70% of a role, with at least 3 agents, by default), the rules every agent of a
  role must follow, focus areas, what to leave out — and what to look for in the text: **markers** (a pattern of words,
  with the value it captures, «no máximo 3 bullets»), the **official blocks** the team pastes in every agent, and the
  **types** of specialist (transaction, guidance, triage…), so patterns are also found within each type. With no
  profile, the orchestrator is whoever calls another agent, and the shared blocks of text are still found.
- It writes `<id>.html` (the map), `<id>.xlsx`, `<id>.lesson.html`, `<id>.team.html` (the agents as a team), `<id>.topology.html` (who
  calls whom), `<id>.diagrams.md` with `<id>.diagrams/*.mmd` (what was read, in plain Mermaid) and `<id>.review.yaml`, named
  by the folder. The review
  file is read again on every run: what people declared and decided stays.
- `--evals <folder>` adds the **evaluations** of Copilot Studio's Evaluate tab (its CSV exports, «Evaluate <name>
  <date>.csv»): who passed how many, by method — the counts only, never what was asked or answered.
- `--telemetry <export.csv|.xlsx>` adds **what fired**: the result of one query the person runs in Application Insights
  and exports (`references/telemetry.md` has it, ready to copy). Read on that run only; nothing goes over the network.

Exit 1 with `✗ file:line` is a broken profile or review file: fix the line. Exit 3 is a lesson the reviewer did not pass.

## 2. Read what it found

The `!` lines are what to look at (`references/keys.md` names every fact), each group under a `▸` line with how many:
**Contradictions** (the first two below), **Contract and telemetry** (the contract, the flows, the events), **Off
pattern** (off a pattern, a rule set in different ways, a type with one specialist), **Rules**, **Only one has it**,
**Unused** and **Not understood**. The map shows the same groups, with «Only one has it» and «Unused» folded at first.
What each says:

- **What people said and the YAML do not agree** — a declared fact the agent does not have, or the other way round.
  What was seen wins; the contradiction is the finding.
- **The text against the setup** — a rule with `when` and `not`: «beneficios tem «Só o conhecimento», mas também
  «Conhecimento geral do modelo ligado»».
- **The orchestrator's contract** — what each connected-agent action passes (the conversation history, the inputs,
  the routing description) is a fact of the specialist it calls, so «1 especialista não recebe o histórico da conversa
  do orquestrador (folha): é intencional?» is an ordinary off-pattern. Its own findings: a call to an agent not in the
  folder («O orquestrador chama «X», que não está na pasta» — maybe not cloned, maybe gone), a specialist no
  orchestrator calls, and a routing description under 80 characters (the model routes by it).
- **A flow that returns nothing** — a flow an agent calls with no `Response`: «O fluxo «X» de admissao não devolve nada».
  What a flow calls (connectors, operations, HTTP hosts, another flow) is compared like any fact; the map's Agents tab
  shows each chain, agent → flow → system.
- **An event spelt another way** — the events are compared by their **form**, the name with the agent's own name
  taken out («RhFerias_OnError» and «RhFolha_OnError» are «‹nome›_OnError»). Two forms that are the same with
  no case, `_`, `-`, `.` or space count as the most common one, and the other is asked about: «admissao registra
  «rh_admissao_onerror»; os outros, «‹nome›_OnError»: é o mesmo evento?» — a different name breaks whoever queries
  the telemetry. An event is part of logging telemetry, and each field of its record (`properties: "={A: x}"`) is part
  of the event: «1 especialista registra «‹nome›_OnError» sem «ConversationId» (admissao)». A name or a record made by a
  formula cannot be read: the name goes to «not understood», the record leaves that agent out of the fields.
- **What did not fire** (with `--telemetry`) — «O evento «X» de folha não disparou em 30 dias», and «facilities não
  tem nenhuma linha na telemetria: está ligado ao Application Insights?».
- **Off a pattern** — «1 especialista não escala para humano (folha): é intencional?». With an accepted pattern:
  «corrigir?». A **variation** of a shared block — «1 especialista tem uma variação do bloco oficial «Formatação de
  links» (folha): alinhar?» — and the map shows the words that went and came. Off a type's pattern: «1 especialista de
  transação…»; a type's pattern never blames who is not of the type.
- **A text rule set in different ways** — «4 especialistas definem «Tamanho da resposta» de 2 jeitos: unificar?» — or
  **twice in one agent** — «qual vale?».
- **A type with one specialist** — nothing to compare within it.
- **Rules not met** — from the profile.
- **Only one has it** — innovation to spread, or debt to remove: only the person knows.
- **Nobody uses it, or it is switched off** — a topic nobody can reach (no description, no phrases, no topic calls
  it), a tool the model cannot choose (no description), a global variable no file names, a flow no node calls, a node
  with `disabled: true`, a component with `state: Inactive`: «remover ou ligar?». Never a pattern nor a solo, and a
  switched-off node is not a fact (a disabled telemetry node is no telemetry). The map's «Sem uso» / «Unused» tab and
  sheet list them with the file.
- **Not understood** — files the analysis could not read (broken YAML, a kind Copilot Studio does not have). The rest
  was read anyway. Only the kind's name may leave the client's environment, typed, to improve the extractor.

### The text: what it can and cannot tell

- It reads the instructions and the descriptions the model reads (topics, actions), cut into blocks. Two blocks are
  the same when nearly all their 5-word runs match; a **variation** when at least half of the smaller one is in the
  other (a copy that lost a line). Numbers and links do not count as differences in that measure — the diff shows them.
- **Text, not meaning:** the same rule written in other words is another block. Saying two texts mean the same is a
  person's call — or the model's, as declared facts (step 3).
- Copies and tests left in the editor (`… Copy`, `test`) and per-language copies are left out.
- **Not in the clone:** the texts of prompt actions. Say so when the team asks about them.

### The flows: what it reads and what it does not

It reads which connectors, operations and HTTP hosts a flow calls, whether it calls another flow, and whether it
answers the agent — walking scopes, conditions, switches and loops. It does **not** read what the flow does with them
(its expressions, its logic), and it does **not** look for secrets in a flow: that is for the team's security tools.
Say both when the team asks.
- **A marker** is a JavaScript regular expression, case does not matter (`'(no máximo|at most)\s*(\d+)\s*bullets?'`,
  in single quotes in YAML); `value: "$2 bullets"` keeps what it captured. Try it with `--check`: a regex that does not
  compile is `✗ profile:line`.

## 3. Add what only people know

The YAML does not hold KPIs, owners or intentions.

**From a spreadsheet, with no model.** Most teams already have one: the **inventory** the Power Platform admin center
downloads (Manage › Inventory, or Manage › Copilot Studio › Download: name, schema name, owner, environment, last
published…), or the team's own list with the KPI and the owner. Any `.csv` (`,` or `;`) or `.xlsx`:

```
node scripts/build.mjs <agents-folder> --declared inventario.csv --declared equipe.xlsx          lists what they say, each with a key
node scripts/build.mjs <agents-folder> --declared inventario.csv --declared equipe.xlsx --take all   writes it to the review file
```

- The agent's column is found by its values (the schema name, the folder or the display name); when two columns name
  the agents differently, or none does, it asks for `--agent-column "<title>"`.
- Every other column with a value becomes `declared:<column>` (`Dono`, `Equipe` and `Squad` become `team`, the inventory's `Owner` becomes `owner`, `KPI` and
  `Indicador` become `kpi`), with the file and the line as its source. The inventory's apps and flows are left out; a row
  of an agent not in the folder is listed; importing again changes nothing; nothing is removed.

**From documents, with a model.** When the person gives you documents (a handoff, the backlog):

1. `node scripts/build.mjs <agents-folder> --facts` writes `<id>.facts.json`: what was seen, with file and line.
2. Read **at most two** sources. For each thing they say about an agent, add a line to `declared:` in `<id>.review.yaml`
   (`references/format.md`) with its **source**: `kpi`, `owner`, or a fact key such as `trigger:OnEscalate` when the
   document claims the agent does it. Never change a fact the YAML shows; a claim the YAML contradicts becomes a finding.
3. Run step 1 again.

## 4. Ask, then decide — once, all together

One message, numbered, from the `!` lines: **at most 6 questions, one thing each, each with your bet** («I'd say the
folha specialist skipping escalation is an oversight — the other four escalate»). Never ask without a bet.

Write a **decision** only when the person decides: in `decisions:` of the review file (`key`, `status: accepted|rejected`,
`scope: platform|specialist|orchestrator`, `why`), or they fill the workbook's **Decision** column and **Declared**
sheet in Excel:

```
node scripts/build.mjs <agents-folder> --from <filled>.xlsx              lists the changes, each with a key
node scripts/build.mjs <agents-folder> --from <filled>.xlsx --take all   writes them to the review file
```

Run again: an accepted pattern is now checked on every agent of its scope, even a new one — that is the quality gate.

## 5. Deliver

End with a short summary: how many agents; **the main patterns by name** — what the specialists do in common, and
what the platform does (behaviours first: escalation, error handling, telemetry; settings last) — **who is off what**
(by name), the orchestrator's contract when there is one (who gets what; a call to one not in the folder; a short
routing description), a flow that returns nothing, the telemetry (an event spelt another way, a field missing and,
with the export, what did not fire and who has no line), **what nobody uses or is switched off** (each by name and agent —
the «Unused» list, even when nobody asked), the open decisions with your bet, and the files. A count alone («22 patterns») tells the person nothing. The map's «Para olhar» / «To look at», the Matrix (filter by role and focus area; a click shows the file and
line), the Patterns cards and the Microsoft tab are where the person continues.

### The team: the agents as HR

`<id>.team.html` shows the same agents as people, for whoever thinks in HR terms (`references/team.md` says how each
part is read):
- **the staff board:** on the staff, being hired (called and not in the folder, or in another environment), with no
  owner and never published (with the inventory), with a development plan, in good standing;
- **the org chart**, by type;
- **the post** of each role and type: the accepted patterns and the profile's rules, as requirements;
- **a résumé** each — shown as a résumé, or as a sheet with every field's source: the first sentence of its instructions, its manager, team, owner, tools, conduct, goal, and the
  performance from the telemetry (topic starts, errors logged, what did not fire; the goal is never measured from it);
- **certifications**, with `--evals`, and the **access only it has in its type** («does the post need it?»);
- **the development plan (PDI):** what «to look at» says about that one alone, as actions.

When the person asks about it ("como está o time?"), name who is in a plan and their first items, who has no
owner, who was never published and who is being hired, by name. Say what a missing table would add (the inventory,
the team spreadsheet, the export). Never invent a goal, an owner or a number the files do not have.

### The topology

`<id>.topology.html` puts the agents on one screen, to show in a meeting: the customer, the orchestrator, the specialists by
type, the flows and the systems, with the traffic moving along the arrows in proportion to each one's topic starts
(only with `--telemetry`; the arrows into flows and systems are structure, never a measured volume). **Lenses** light
who follows a pattern (green), who is off (red) and what is to decide (amber); the **walkthrough** follows each call of
the orchestrator step by step and stops where it breaks («Folha é chamado SEM o histórico…»); a click on someone opens
its card — the fingerprint of its instructions and what it meets of its post — with its résumé a link away. Point the
person to it when they want to show the agents to others.

### The diagrams

`--diagrams` (also in `--all`) writes what was read as plain Mermaid, for the team's docs — a PR, a wiki, a README, VS
Code: it shows on GitHub with nothing of ours. `<id>.diagrams.md` has the summary, «to look at» in words and each
diagram in a ```mermaid block with a sentence on what it shows; `<id>.diagrams/` has each one alone. They come from the
same data as the topology page, so the two never disagree:

- **the topology** (a flowchart): the customer, the orchestrators, the specialists by type, the flows and the systems;
  thick arrows are calls (with what is missing, a short routing description, and the topic starts with `--telemetry`),
  thin ones what each one uses, dashed what nobody calls or is not in the folder;
- **a sequence per call of the orchestrator**: the customer → the orchestrator → the specialist → its flows and systems
  → back, with ⚠ where it breaks and the routing description quoted as it is;
- **a lens per pattern** (and the contract, the telemetry, what nobody uses): who follows it, who is to look at, who is
  off, in words and colour;
- **the anatomy of each type**: its patterns, accepted or candidate, and who is off each one.

Each `.mmd` carries `%% title`, `%% # chapter` and `%% > narration` (comments for Mermaid): visual-explainer and visual-pitch
draw it as a lesson or present it. Point the person to the `.md` when they want to put the agents in their documentation;
it holds the client's data, like every output.

If the Microsoft skills for Copilot Studio are installed (`/plugin marketplace add microsoft/skills-for-copilot-studio`),
use them to explain a kind or a reference pattern; agent-review works without them.

## Never

- Never edit, push or publish an agent — this skill only reads them.
- Never decide a pattern for the person, or write a declared fact without its source.
- Never take the outputs out of the client's environment, or put a client's names in a public place.
- Never edit the generated files; change the review file or the profile and run again.

## In Claude Code

With the dna plugin, `/compare-agents <agents-folder> [--profile <team>.standard.yaml] [--lang pt]` runs the comparison (`--check`,
nothing written) — with the profile given, or the only one beside the agents (it says which; with two, it asks) — and
shows the summary and «to look at» in a pane, a button per group. After it, when an agent's `.mcs.yml` in that folder
is written or edited, the comparison runs again and a toast says what came to look at or went away; the edit is never
refused.
