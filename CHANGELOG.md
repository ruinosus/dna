# Changelog

## 1.4.0 — 2026-11-02

cast-list reads what the orchestrator passes each agent, what each flow calls, and what nobody uses.

- **The orchestrator's contract.** What each connected-agent action passes — the conversation history, the inputs,
  the routing description — is a fact of the agent it calls, so «1 specialist does not receive the conversation
  history from the orchestrator» is an ordinary off-pattern. Its own findings: a call to an agent not in the folder, a
  specialist no orchestrator calls, a routing description under 80 characters. The map's orchestrator card and the
  workbook's **Routing** sheet have a row per call.
- **Inside the flows.** `workflows/<Name>-<id>/` (`metadata.yml` and `workflow.json`, the definition in
  `properties.definition` or `definition`) is read, scopes, conditions, switches and loops included: the connectors,
  operations and HTTP hosts a flow calls, another flow, and whether it answers the agent. A flow that returns nothing
  is told; the Cast tab draws each chain, agent → flow → system. A JSON that does not read goes to «not understood».
  Neither the flow's logic nor its secrets are read.
- **What nobody uses, and what is switched off.** A topic nobody can reach, a tool the model cannot choose, a global
  variable no file names, a flow no node calls, a node with `disabled: true`, a component with `state: Inactive`:
  «remove or switch on?», in a new **Unused** tab and sheet, never a pattern nor a solo. A switched-off node is not a
  fact: a disabled telemetry node is no telemetry.
- The lesson says the contract in «what is missing» and what nobody uses in «what to decide». An eval
  (`cast-list-contract-pt`, 2/2). The example agents show all of it, and the earlier ones are unchanged.

## 1.3.0 — 2026-11-02

cast-list reads the text of the instructions, and compares by type of agent.

- **The text.** The instructions and the descriptions the model reads are cut into blocks. A block two agents or more
  share is a fact; a copy that lost a line is a **variation** (half of the smaller one in the other), and the map
  shows the words that went and came. A block keeps its id across small edits (the cast file keeps it). It compares
  text, not meaning; copied, test and per-language topics are left out.
- **What the team looks for**, in the profile: **markers** — a regular expression and the value it captures («at most
  3 bullets») — so a rule written in different ways by a role («unify?») or twice in one agent («which one holds?»)
  is told; the domain of each link and an e-mail are found with no marker; and the **official blocks** the team pastes
  everywhere, checked on every agent with or without a majority.
- **Types** of specialist (transaction, guidance, triage…), from what each one's YAML and text show — one may be of
  two: patterns are also found within each type (scope `type:<id>`), a pattern of a type never blames who is not of
  it, and a type with one agent is told. The matrix groups its columns by type (a type filter; one of two types in
  both), the workbook has the types and a Text sheet, the lesson draws the cast by type.
- **The text against the setup:** a rule with `when` and `not` — «asks for the knowledge alone» with the model's
  general knowledge on. Four settings are read now: general knowledge, content moderation, semantic search, web
  browsing.
- An eval for the text (`cast-list-text-pt`, 2/2). The example agents and profile show all of it.

## 1.2.1 — 2026-11-02

cast-list, finished after its first run in the cloud.

- **One fact, asked once.** A topic that calls another (the fallback leading to escalation) is now known by what the
  called topic is for — `reaches:OnEscalate` — and is a part of that fact, not a pattern of its own: an agent with no
  escalation is off once (not also for «its fallback does not lead there»), the fact's decision covers its part, and an
  agent that has the escalation topic but whose fallback never reaches it is still found, as the part. The map shows
  the part right under its fact and in its detail.
- **Readable names.** Connectors, their operations, MCP servers and the agents an orchestrator calls are named as the
  files name them — «Conector Office 365 Outlook», «Chama Bodega Azul - Cupons» — on the map, the workbook, the lesson
  and «to look at»; the technical key stays in the Key column and the detail.
- **A lesson you can read from the back of the room.** What repeats and what to decide show the five that matter most
  in bigger letters, and «and N more on the map» for the rest; contradictions come first in what to decide.

## 1.2.0 — 2026-11-02

- **cast-list, the sixth skill: Copilot Studio agents compared.** Point it at the folders the VS Code extension clones
  and it says what most agents do (a pattern — the platform's when the orchestrator has it too, the specialists'
  otherwise), who is off a pattern, what only one has (innovation or debt), the team's rules not met, and what a
  handoff or the backlog says that the YAML does not — with the file and line behind each finding. A map that opens
  offline (filters by role and focus area, a click shows the evidence), a workbook to decide in (Decision column,
  Declared sheet, read back with `--from` / `--take`), a lesson that draws the cast, and a cast file that keeps what
  was decided, so the next run checks every agent against the accepted patterns. It runs on Node alone — no model, no
  install, no network — so it fits a client's locked-down machine; with a model, `--facts` is the way in. A child
  agent's facts are the child's; a file it cannot read is told and never stops it. The Copilot Studio schema and its
  reader are inside (`vendor/microsoft`, MIT), to tell a real kind from a made-up one; 8 of Microsoft's 15 reference
  patterns are recognised in the YAML. `npx house-lights cast-list agents/ --all`.

## 1.1.0 — 2026-11-02

- **gates-and-handoffs: more than one approves, or only sometimes.** A gate lists its `approvals` —
  `[{ by: tl }, { by: seg, when: change to payments }]` — all of them needed; `when` is the condition as people say it.
  `approver: tl` stays the shorthand of one, so every file made before reads and writes back the same. A second gate
  after the same stage is still refused, and now says to use `approvals`. The map shows «+ SEG if change to payments»
  under the gate and lists who approves in its detail; the workbook has a row per approval, a «When» column (only when
  some approval has a condition), «A (if …)» in the RACI and a checklist item that may not apply; the lesson says it.
  As the market does it (Azure DevOps, GitLab, ServiceNow, ITIL): one decision, a list of approvals, the condition on
  the approval.
- The engine is the hubs Ways engine 0.259.0.

## 1.0.1 — 2026-11-02

What the first run of all five in the cloud found.

- **PowerPoint (back-of-napkin, chalk-talk):** a slide's title is at the title placeholder's index 0, as PowerPoint
  numbers it: python-pptx's `slide.shapes.title`, the outline and screen readers find it (pptxgenjs numbered it 100).
  The build checks it the same way.
- **The words on screen:** the list of a course's lessons is labelled in the recipe's language too (it said
  «Lessons»); a check makes sure a pt lesson has no English word on screen.
- **dress-rehearsal:** «escalar a instância» is scaling up, not escalating: only «escalar» to someone (para, ao, à…),
  «escalar o incidente» or «escalar» alone asks «escalar para quem?». A choice can cite a numbered step under a
  heading («Passos 4»), and the game shows that step; citing only the heading of a list of steps asks which one.
- **service-blueprint:** with no `feels` at all, the «Sente» lane says «ninguém disse como o cliente se sente» instead of a
  flat red line; a moment nobody said it of gets no point on the line.
- The npm package `chalk-talk` 0.19.1 carries the player and PowerPoint fixes.

## 1.0.0 — 2026-11-01

The five skills become one plugin, **house-lights**, in one repository.

- **One install:** `/plugin install house-lights@house-lights` brings chalk-talk, back-of-napkin, dress-rehearsal,
  gates-and-handoffs and service-blueprint.
- **Two new names:** stage-door is **gates-and-handoffs**, front-of-house is **service-blueprint**. The file formats
  keep their ids (`stage-door/v1`, `front-of-house/v1`): every file made before still opens.
- **One command:** `npx house-lights <skill> <file>`, with each skill's own options and exit codes. The packages
  `back-of-napkin`, `stage-door`, `front-of-house` and `dress-rehearsal` move to it; `chalk-talk` stays the engine's
  package.
- **The engine of chalk-talk 0.18.1 everywhere:** dress-rehearsal, gates-and-handoffs and service-blueprint drew
  their lessons with the engine of 0.14.1; now every skill takes it from this repository, in the same commit.
- One gallery: https://ruinosus.github.io/house-lights/, with a page per skill.
- The npm package `chalk-talk` 0.19.0: the same engine as 0.18.1, now built in this repository.

Before 1.0.0, each skill's history is in `dev/<skill>/CHANGELOG.md` and its tags are `<skill>-v<version>`.
