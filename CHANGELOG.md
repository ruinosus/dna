# Changelog

## 1.9.6 — 2026-11-03

- **What a run makes says its version:** the foot of the map, the RH and the stage («cast-list 1.9.6»), their
  generator tag, and the cast file (`# Written by cast-list 1.9.6.`, renewed on every run), so two runs can be told
  apart.
- **A topic that begins a connected agent** (`<schema>.InvokeConnectedAgentTaskAction.<Name>`) is checked against
  the agent's actions — in `actions/`, `topics/`, or a file of `agents/`, where the extension clones them — and not
  reported as a topic not found. Any `<schema>.<type>.<Name>` other than a topic is read the same way.

## 1.9.5 — 2026-11-03

cast-list, the second run on a real cast (22 files «not understood», down from 96).

- **Flows whose `jsonFileName` is a path** (`workflows/<folder>/workflow.json`, as the extension writes it) are read: the
  file was looked for by the whole path. The rest of those flows' names, connectors and callers come back with them.
- **A topic that begins an action** (`<schema>.action.<Name>`) is checked against the agent's actions, not its topics.
  One not found is named in full, so an action of another agent's prefix (copied from another agent) shows as such:
  «Chama a ação (não encontrada) …».
- **A call without a prefix keeps its whole name:** it showed only its last letter («Chama o tópico (não encontrado) s»).
- **The cast cards no longer spill:** a long path or a GUID wraps inside its card, and a file «not understood» twice
  for the same reason shows once, with ×2.

## 1.9.4 — 2026-11-03

cast-list on agents cloned by the VS Code extension on Windows, after a run on a real cast left 96 files «not
understood».

- **Flows are read again:** a `workflow.json` saved with a byte-order mark (Windows) did not parse, so every flow was
  lost — its name, its connectors and operations, who calls it. Every file now drops the mark before it is read. The
  name comes from `name` in `metadata.yml`, and a folder ending in a whole GUID gives the flow's short name.
- **Uploaded knowledge counts:** each `knowledge/files/*.mcs.yml` (only its metadata) is a knowledge source
  («Conhecimento em arquivo enviado»); the document beside it and the agent's `icon.png` are not read and no longer
  show as «not understood».
- **`connectionreferences.mcs.yml` without a kind** is known by its name, as cloned, so the access review has its
  connections.
- **«Not understood» says why** in the cast card too, as the sheet does (`a telemetry event whose name is a formula`).
- The example agents are cloned the same way: flows with a byte-order mark and a GUID folder, a real `metadata.yml`,
  connection references without a kind, an icon each.

## 1.9.3 — 2026-11-03

- **The résumé says where each fact came from:** team, owner, hiring, publishing and environment carry their source
  (`inventario.csv › linha 6`) in small letters under the value, as the sheet does beside it.
- **The stage's arrow labels never sit on a node,** with a lens or without; with a lens, only the arrows that touch
  someone it lights say something.
- **Short names in the follow spot too:** its buttons and its steps say «O orquestrador encaminha para Frete». One rule
  for the shared part of the names (`shortNames`) serves the stage, its scenes and the RH.

## 1.9.2 — 2026-11-03

- **The RH's résumé has two views:** as a résumé — the paper one of the prototype, with a face, the name, the post and
  the stamp on top, the facts in two columns and the sources at its foot — and as the sheet, every field with its
  source beside it. It opens as a résumé; one click turns it.

## 1.9.1 — 2026-11-03

cast-list's RH and stage, after a test in claude.ai.

- **The RH's org chart** shows one of two types once, in its first, with «also orientação»; the staff board, the org
  chart and the stage leave out the part of the names every one shares («Bodega Azul - »), and the one not in the
  folder is no longer cut.
- **The stage:** a lens closes the scene and a scene turns the lens off; the follow spot is the size of the node; the
  caption sits below the stage, never over it; knowledge sources are on stage and in the scenes («Consulta
  «Conhecimento no SharePoint»»).
- **Connectors by name:** when the files give none (a flow's connection names only the API), a common Microsoft
  connector goes by Microsoft's name — `shared_commondataserviceforapps` is «Microsoft Dataverse».
- **The post's requirements:** a fact whose name is already a sentence is said as it is («Recebe «X» do
  orquestrador»), not inside «Tem «…»».
- **The example evaluations** are named in kebab-case (`evaluate-bodega-azul-pedidos-2026-10-30.csv`); the name the
  Evaluate tab gives, with spaces, reads the same.

## 1.9.0 — 2026-11-03

cast-list reads the evaluations and reviews the access.

- **`--evals <folder>`** reads the exports of Copilot Studio's Evaluate tab («Evaluate <name> <date>.csv»): who is
  named by the file, a row passes when every method passes, each method counted. **The counts only:** what was asked,
  answered and explained is the client's conversation and never reaches an output. The résumé gets «Certifications»,
  the staff board «with no evaluation», and who has one gets `eval:run`, so a rule `has: "eval:*"` asks for it. A file
  that names nobody, or is not an export, is told and left out.
- **The review of access:** within each type of two or more, a connector, an MCP server or what a flow reaches that
  only one has is asked about on the résumé and the stage's card — does the post need it? With a decision `rejected`
  on that key in the type's scope, it becomes a cleanup item of the plan.
- The examples get two exports of the Evaluate tab (`examples/avaliacoes/`), written by the fixtures' generator.

## 1.8.0 — 2026-11-03

cast-list puts the cast on a stage.

- **`--plot` (in `--all` too) writes `<id>.plot.html`:** the light plot, to show in a meeting. The customer, the
  orchestrators, the specialists by type, the flows (one node however many share one) and the systems they reach, in
  columns; the same run gives the same stage.
  - **The traffic:** dots along the arrows, as many as the log of each one's topic starts in the export; the arrows
    into flows and systems are structure, never a measured volume; one with no line in the telemetry has a dashed
    arrow and «no telemetry». With reduced motion, nothing moves.
  - **The arrows say what is wrong:** «NO history · NO «Category»» in red, «routed by «Coupons.»» in amber, «returns
    nothing», «calls it, but it is not in the folder»; a flow nobody calls, and what only it reaches, dashed.
  - **Lenses:** the accepted patterns and the first ones someone is off, then Contract, Telemetry and Unused — who
    follows lights green, who is off blinks red, what is to decide shows amber.
  - **The follow spot:** one scene per call of the orchestrator; ← → walk it, space plays it, Esc leaves; it stops
    where the call breaks.
  - **The actor's card:** the fingerprint of its instructions (shared blocks, a variation, its own text) and what it
    meets of its post, with its résumé a link away (the RH opens at `#<id>`).
- **The map** links to the stage when the same run wrote it.

## 1.7.0 — 2026-11-03

cast-list writes the RH of the cast.

- **`--playbill` (in `--all` too) writes `<id>.playbill.html`:** the same cast as people, for whoever thinks in HR
  terms. Everything comes from the files, the telemetry and the tables people gave; a field nothing says stays empty.
  - **The staff board:** on the staff, being hired (called and not in the folder, or in another environment), with no
    owner and never published (with the inventory), with a development plan, in good standing — each with the names.
  - **The org chart** by type, and **the post** of each role and type: the accepted patterns and the profile's rules,
    as requirements; with no decision yet, a proposal.
  - **A résumé each:** the first sentence of its instructions, its manager, team, owner, hiring and publishing dates,
    tools, conduct, goal, and the performance from the telemetry (topic starts, errors logged, what did not fire).
  - **The development plan (PDI):** what «to look at» says about that one alone, as actions — one item per fact, the
    inputs the orchestrator does not pass in one call as one. A solo, a type with one and a marker set in ways across
    the cast are the team's call, not anyone's plan. `references/playbill.md` says how each part is read.
- **The workbook** gets the Staff and PDI sheets; **the map** links to the RH when the same run wrote it.
- **Two keys for who answers for it:** the team spreadsheet's «Dono», «Equipe», «Squad» give `declared:team`; only
  the inventory's `Owner` gives `declared:owner` (until 1.6, «Dono» was the owner).

## 1.6.0 — 2026-11-03

cast-list's «to look at» comes in groups.

- **Groups, each with how many:** Contradictions · Contract and telemetry · Off pattern · Rules · Only one has it ·
  Unused · Not understood — in the command's output (a `▸` line per group; every finding keeps its `!` line), at the
  top of the map and in the workbook's summary. One list decides them, so the three always agree.
- **The map folds «Only one has it» and «Unused» at first:** they are many and rarely urgent; a click opens them. A rule
  not met now comes after what is off a pattern, with its own group.

## 1.5.1 — 2026-11-03

- **cast-list's description fits claude.ai.** It had 1156 characters and claude.ai keeps 1024, so the plugin synced
  with a warning and a cut description. It now has 1017, with the same uses and examples.
- **Every skill's check reads its SKILL.md.** The name, the 1024 characters of the description and the 500 lines were
  checked only for chalk-talk and back-of-napkin; cast-list, dress-rehearsal, gates-and-handoffs and service-blueprint
  check them too.

## 1.5.0 — 2026-11-03

cast-list reads the telemetry by name, what really fires, and what a spreadsheet says about the agents.

- **The telemetry by name.** Each `LogCustomTelemetryEvent` is a fact by its **form** — the name with the agent's own
  name taken out, so «BodegaPedidos_OnError» and «BodegaFrete_OnError» are one event — and each field of its record is
  a fact too. The event is part of logging telemetry and the field part of the event: a field missing is told
  («logs «‹name›_OnError» without «ConversationId»»), and neither is ever a solo. Two spellings that differ only in case
  or separators count as the most common one, and the other is asked about: «the same event?». A name or a record made
  by a formula is not guessed.
- **What fires.** `--telemetry <export>` reads the result of one query in Application Insights
  (`references/telemetry.md`, ready to copy): an event in the YAML that did not fire in the period, and an agent with no
  line at all (is it connected?). Nothing goes over the network; only the agent, the event and the times are read.
- **Declared from a spreadsheet, with no model.** `--declared <table>` reads the Power Platform admin center's
  inventory download or the team's own list (`.csv` with `,` or `;`, or `.xlsx`): the agent's column is found by its
  values, every other column becomes a declared fact with the file and the line, listed with keys and written with
  `--take`. `Dono`/`Owner` is the owner, `KPI`/`Indicador` the KPI; the inventory's apps and flows are left out, and a
  row of an agent not in the folder is listed.
- A **Telemetry** sheet; each card of the map lists its events and the times they fired; the lesson puts a spelling in
  «what to decide» and what did not fire in «what is missing». An eval (`cast-list-telemetry-pt`, 2/2). The example agents
  and three example tables show all of it.

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
