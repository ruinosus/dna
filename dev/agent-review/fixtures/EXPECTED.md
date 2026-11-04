# EXPECTED — RH fixture agents (ground truth)

Six FICTIONAL Copilot Studio agents for a fictional online shop ("RH"), laid out like an agent cloned
with the VS Code Copilot Studio extension. Local files only; nothing was pushed or cloned. Content is pt-BR.

Root: `cast-fixtures/agents/<agent>/`. Shared publisher prefix: `cr7b2`.
Every agent has `settings.mcs.yml` with `GenerativeActionsEnabled: true`, `recognizer.kind: GenerativeAIRecognizer`,
`authenticationMode: None`, `language: 1046` (pt-BR).

## Ground-truth table

| Agent (schemaName) | Role | Trigger kinds present (topic file) | Connectors (connection ref API name : operationId) | MCP actions | Knowledge source types (+ triggerCondition) | Generative answers | Telemetry | Instructions | Global variables | Relation to orchestrator |
|---|---|---|---|---|---|---|---|---|---|---|
| `rh-orquestrador` (`cr7b2_rhOrquestrador`) | orchestrator | OnConversationStart (Greeting), OnUnknownIntent (Fallback), OnEscalate (Escalate), OnError (OnError), OnRecognizedIntent (ClassificarSolicitacao); plus OnToolSelected in the inline child agent `agents/SobreRH/agent.mcs.yml` (AgentDialog) | none (no `connectionreferences.mcs.yml`) | none | none (no `knowledge/`) | no | yes (OnError) | yes | `CategoriaSolicitacao` (UseInAIContext, default `Outro`, set by ClassificarSolicitacao via AutomaticTaskInput, `shouldPromptUser: false`) | is the orchestrator. 5 connected agents in `actions/` (TaskDialog + InvokeConnectedAgentTaskAction, `historyType: ConversationHistory`, each passes `CategoriaSolicitacao = =Global.CategoriaSolicitacao`): AgenteFerias → `cr7b2_rhFerias`, AgenteBeneficios → `cr7b2_rhBeneficios`, AgenteFolha → `cr7b2_rhFolha`, AgenteAdmissao → `cr7b2_rhAdmissao`, AgenteFacilities → `cr7b2_rhFacilities`. Plus 1 inline child agent `SobreRH` (AgentDialog, no knowledge). `isAgentConnectable` not set |
| `rh-ferias` (`cr7b2_rhFerias`) | specialist (baseline, "typical") | OnConversationStart (Greeting), OnUnknownIntent (Fallback → BeginDialog `cr7b2_rhFerias.topic.Escalate`), OnEscalate (Escalate), OnError (OnError), OnRecognizedIntent (ConsultarPoliticaFerias), OnRedirect (RecebimentoOrquestrador) | `shared_office365` : `SendEmailV2` (actions/EnviarResumoFerias) | none | 1 × SharePointSearchSource (PoliticaFeriasAusencias); triggerCondition: no | yes (ConsultarPoliticaFerias: CreateSearchQuery + SearchAndSummarizeContent → `cr7b2_rhFerias.knowledge.PoliticaFeriasAusencias`) | yes (OnError) | yes | `CategoriaSolicitacao` (UseInAIContext, `isExternalInitializationAllowed: true`, default `=Blank()`) | connected agent called by orchestrator action `AgenteFerias`; receives `CategoriaSolicitacao` in OnRedirect topic; `isAgentConnectable: true` |
| `rh-beneficios` (`cr7b2_rhBeneficios`) | specialist (same pattern as ferias) | OnConversationStart, OnUnknownIntent (→ Escalate), OnEscalate, OnError, OnRecognizedIntent (ConsultarGuiaBeneficios), OnRedirect | `shared_office365` : `SendEmailV2` (actions/AbrirInclusaoDependente; `To` is a ManualTaskInput) | none | 1 × SharePointSearchSource (GuiaBeneficios); triggerCondition: no | yes | yes (OnError) | yes | `CategoriaSolicitacao` (same as ferias) | connected agent called by `AgenteBeneficios`; OnRedirect; `isAgentConnectable: true` |
| `rh-folha` (`cr7b2_rhFolha`) | specialist — **DIVERGENCE: no OnEscalate topic** | OnConversationStart, OnUnknownIntent (Fallback ends with CancelAllDialogs, does NOT reference an Escalate topic), OnError, OnRecognizedIntent (ConsultarCalendarioFolha), OnRedirect. **No OnEscalate.** | `shared_office365` : `SendEmailV2` (actions/EnviarCalendarioFolha) | none | 1 × SharePointSearchSource (CalendarioRegrasFolha); triggerCondition: no | yes | yes (OnError) | yes | `CategoriaSolicitacao` (same as ferias) | connected agent called by `AgenteFolha`; OnRedirect; `isAgentConnectable: true` |
| `rh-admissao` (`cr7b2_rhAdmissao`) | specialist — **SOLO features: extra connector + MCP** | OnConversationStart, OnUnknownIntent (→ Escalate), OnEscalate, OnError, OnRecognizedIntent (ConsultarGuiaAdmissao), OnRedirect | `shared_office365` : `SendEmailV2` (actions/EnviarChecklistAdmissao) **and** `shared_sharepointonline` : `GetItems` (actions/ConsultarDocumentosAdmissao — the only agent using this connector) | **1**: actions/AdmissaoMCP (TaskDialog + InvokeExternalAgentTaskAction + ModelContextProtocolMetadata, `operationId: InvokeMCP`, connection ref API name `shared_rhadmissaomcp`, a custom connector with `customConnectorId`) | 1 × SharePointSearchSource (GuiaAdmissao); triggerCondition: no | yes | yes (OnError) | yes | `CategoriaSolicitacao` (same as ferias) | connected agent called by `AgenteAdmissao`; OnRedirect; `isAgentConnectable: true`. `connectionreferences.mcs.yml` has 3 entries (office365, sharepointonline, MCP custom connector) |
| `rh-facilities` (`cr7b2_rhFacilities`) | specialist — **DIVERGENCES: YAML-only triggerCondition; no telemetry** | OnConversationStart, OnUnknownIntent (→ Escalate), OnEscalate, OnError (**without** LogCustomTelemetryEvent), OnRecognizedIntent (ConsultarGuiaUnidades), OnRedirect | `shared_office365` : `SendEmailV2` (actions/EnviarInstrucoesAcesso) | none | 1 × SharePointSearchSource (GuiaUnidades); **triggerCondition: yes** — `=Or(IsBlank(Global.CategoriaSolicitacao), Global.CategoriaSolicitacao = "Facilities")` | yes | **no** (no LogCustomTelemetryEvent in any file) | yes | `CategoriaSolicitacao` (same as ferias; also read by the knowledge triggerCondition) | connected agent called by `AgenteFacilities`; OnRedirect; `isAgentConnectable: true` |

### Summary of deliberate variations (what a pattern-finder should detect)

- Majority pattern (5 specialists): Greeting/Fallback/OnError/OnRedirect + one generative-answers topic + Outlook `SendEmailV2` + one SharePoint knowledge source + telemetry in OnError + received global variable.
- `OnEscalate`: present in 5 of 6 agents (orchestrator, ferias, beneficios, admissao, facilities); **missing in `rh-folha`**.
- `LogCustomTelemetryEvent`: present in 5 of 6 agents; **missing in `rh-facilities`**.
- Knowledge `triggerCondition`: only in `rh-facilities`.
- `shared_sharepointonline` connector action and MCP action: only in `rh-admissao`.
- `shared_office365` (`SendEmailV2`): all 5 specialists, not the orchestrator.
- Generative answers (`SearchAndSummarizeContent`): all 5 specialists, not the orchestrator.
- `InvokeConnectedAgentTaskAction` and `AgentDialog`: only in the orchestrator.
- `OnRedirect` topic + `isExternalInitializationAllowed` variable + `isAgentConnectable: true`: all 5 specialists, not the orchestrator.
- `connectionreferences.mcs.yml`: all 5 specialists, not the orchestrator.

### File counts

| Agent | topics | actions | knowledge | variables | agents/ | connectionreferences |
|---|---|---|---|---|---|---|
| rh-orquestrador | 5 | 5 | 0 | 1 | 1 | no |
| rh-ferias | 6 | 1 | 1 | 1 | 0 | yes (1 ref) |
| rh-beneficios | 6 | 1 | 1 | 1 | 0 | yes (1 ref) |
| rh-folha | 5 | 1 | 1 | 1 | 0 | yes (1 ref) |
| rh-admissao | 6 | 3 | 1 | 1 | 0 | yes (3 refs) |
| rh-facilities | 6 | 1 | 1 | 1 | 0 | yes (1 ref) |

## Format uncertainties and what was chosen

1. **Connected agent vs. child agent.** The plugin's add-other-agents skill and the schema show two different representations. Orchestrator → separate agent = `TaskDialog` in `actions/` with `action.kind: InvokeConnectedAgentTaskAction` + `botSchemaName`. Inline child = `AgentDialog` in `agents/<Name>/agent.mcs.yml` with `beginDialog.kind: OnToolSelected`. Because they differ, the fixtures have both: 5 connected-agent actions and 1 child agent (`SobreRH`). The skill puts connected-agent TaskDialogs in `actions/`, or optionally in `topics/`. `actions/` was chosen.
2. **Called-side (specialist) setup for connected agents.** The skill says the called agent needs an `OnRedirect` topic with `inputType: {}`/`outputType: {}` that copies `System.Activity.Value.<x>` into `Global.<x>`, and a global variable with "Receive values from other agents". Each specialist has `topics/RecebimentoOrquestrador.topic.mcs.yml` (OnRedirect). The UI toggle was mapped to schema property `isExternalInitializationAllowed: true` (from `VariableNoKind`). That mapping is inferred; I found no fixture that shows it. `configuration.isAgentConnectable: true` (from `BotConfiguration`) was added to the specialists' settings, also inferred.
3. **Global variable file shape.** The schema's `GlobalVariableComponent` requires a nested `variable:` object. The plugin template and add-global-variable skill instead use a flattened file (top-level `name`, `aIVisibility`, `scope`, `defaultValue`, `schemaName`, `kind`). The flattened template shape was used, with `isExternalInitializationAllowed` at the same top level. `aIVisibility` uses schema enum values (`UseInAIContext`). The add-global-variable skill text says `HideFromAIContext`, but the schema enum is `Hidden`. That value is not used here.
4. **`connectionreferences.mcs.yml` shape.** The reference fixtures have no such file. It was built from schema `ConnectionReferencesSourceFile`: root `kind: ConnectionReferencesSourceFile`, plus `connectionReferences[]` with `id` (required), `connectionReferenceLogicalName` (required), `connectorId` and `displayName`. A real cloned file has no `kind` (seen in 1.9.4), so the fixtures leave it out too and the file is known by its name, like `settings.mcs.yml`. Logical names follow the fixture pattern `<schemaName>.<connectorApiName>.<suffix>`, with the suffix `shared-office365-<guid>` style. The action's `connectionReference` equals the logical name exactly.
5. **MCP custom connector identity.** `shared_rhadmissaomcp` is invented, and so are its `connectorId` and `customConnectorId` (a GUID). The fixture `agent-with-mcp-action` uses `shared_custommcp` with no connection-reference file to compare against. The MCP action has one `ManualTaskInput` (`=System.Activity.ChannelId`), like the fixture's `userid` input, and no AutomaticTaskInput, as the skill requires.
6. **Knowledge file naming and reference string.** The repo has three conventions. The add-knowledge skill names the file `knowledge/<Name>.knowledge.mcs.yml`. The orchestrator-variables pattern and conversation-init template reference it as `<schemaName>.knowledge.<name>`. The add-generative-answers skill references it as `<schemaName>.topic.<Name>_<suffix>` ("filename without .mcs.yml"). Chosen: file `knowledge/<Name>.knowledge.mcs.yml`, referenced in `SearchSpecificKnowledgeSources` as `<schemaName>.knowledge.<Name>`. A real clone may use a different file name or schema name.
7. **Display-name metadata.** The fixtures use `mcs.metadata` (`componentName`, `description`) on actions and agent.mcs.yml. The skills use `# Name:` comments on knowledge and variables. Chosen: `mcs.metadata` on topics, actions and knowledge; `# Name:` comments on variables and on the child AgentDialog, following their templates.
8. **Where instructions live.** The reference fixtures put `instructions` in `agent.mcs.yml` (GptComponentMetadata), not in `settings.mcs.yml`, so they are in agent.mcs.yml here. `agent.mcs.yml` also has `displayName`, which the fixtures have but schema `GptComponentMetadata` does not list. It was kept to match the fixtures.
9. **`settings.mcs.yml` has no root `kind`.** This matches the reference fixtures. It is BotEntity-shaped, and `cdsBotId` (required by the schema) is omitted as it is in the fixtures. The plugin's light validator reports `[FAIL] No 'kind'` for this file, and it reports the same for the reference fixture's settings file.
10. **`triggerCondition` with a runtime variable.** The int-reference skill and knowledge-guide say arbitrary Power Fx in `triggerCondition`, including `Global.*`, works at runtime as YAML-only. The orchestrator-variables pattern's pitfalls say `triggerCondition` cannot reference runtime variables. The fixture follows the int-reference/knowledge-guide form (`=Or(IsBlank(Global.CategoriaSolicitacao), Global.CategoriaSolicitacao = "Facilities")`). Whether it works at runtime is unverified. Only the structure matters for these tests.
11. **`.mcs/` folder not included.** A real VS Code clone also writes `.mcs/conn.json` (tenant and environment IDs) and other hidden state. It was left out on purpose. Fake IDs would make these folders look pushable to the plugin's tooling, and the repo's eval fixtures leave it out as well.
12. **Escalate topic contents.** No template exists for it. It uses `OnEscalate` with an `intent` (`displayName`, `includeInOnSelectIntent: false`, `triggerQueries`) and one `SendActivity`. All of these properties are confirmed in the schema (`OnEscalate.intent` → `Intent`).
13. **Classification topic is not a separate agent.** In the orchestrator, `ClassificarSolicitacao` is an `OnRecognizedIntent` topic with `intent: {}`, routed by `modelDescription`. It follows the orchestrator-variables pattern. The connected-agent actions read the resulting global through a `ManualTaskInput` with a Power Fx value (`=Global.CategoriaSolicitacao`). ManualTaskInput with an expression is shown in the MCP fixture. For a connected agent it is inferred.

## Wave 1 (agent-review 1.3): the text of the instructions and the types

Added by `gen_fixtures.py` (the `WAVE1` table) to the instructions of the five specialists, as separate paragraphs:

| Agent | Links block | Answer size | No emojis | Other | Type signals |
|---|---|---|---|---|---|
| rh-ferias | the shared block | «no máximo 3 bullets» | yes | a copy of its knowledge topic, `ConsultarPoliticaFerias Copy` (its text is left out) | flow action `AbrirCasoWorkday` → **transaction** |
| rh-beneficios | the shared block | «no máximo 3 bullets» | yes | «Responda somente com base no conhecimento publicado» **and** `aISettings.useModelKnowledge: true` (a contradiction) | flow action → **transaction** |
| rh-folha | **variation**: one line less («link de ação no topo…»), «no máximo 5 links» | none | yes | — | topic `Desambiguar` (`OnSelectIntent`) → **triage** (the only one) |
| rh-admissao | the shared block | «no máximo 5 frases» | yes | link to `https://portal.empresa.example/rh/ajuda` | flow action → **transaction**; help link + generative answers → **guidance** (two types) |
| rh-facilities | the shared block | **twice**: «no máximo 3 bullets» and «no máximo 5 frases» | **no** | help link | help link + generative answers → **guidance** |
| rh-orquestrador | — | — | yes | — | (orchestrator, no type) |

- The three transaction specialists call **one** flow of the solution (`flowId 7d1c2a4e-…`), so the flow is not a solo.
- With the 1.2 findings unchanged, the triage topic is a new solo (only folha has `OnSelectIntent`).
- Inferred, to confirm in a real clone: how the editor names a copied topic (`<Name> Copy`), and the values of
  `aISettings.contentModeration` (the schema gives only its type).

## Wave 2 (agent-review 1.4): the orchestrator's contract, the flows, what nobody uses

Added by `gen_fixtures.py` (the `WAVE2` table and the orchestrator's `connected` list):

| Where | What | What it should give |
|---|---|---|
| orchestrator `actions/AgenteFolha` | `historyType: NoHistory`, no inputs (`inputType: {}`) | folha off the patterns «receives the history» and «receives «CategoriaSolicitacao»» (4 of 5) |
| orchestrator `actions/AgenteAdmissao` | `modelDescription: Admissão.` (9 characters) | a short routing description |
| orchestrator `actions/AgenteMobilidade` (new, 6th action) | calls `cr7b2_rhMobilidade`, an agent that is not in the folder | «calls one that is not in the folder» |
| ferias, beneficios, admissao `workflows/AbrirCasoWorkday-7d1c2a4e-3b5f-4c6d-8e9f-0a1b2c3d4e5f/` (the folder ends in the whole GUID, as cloned) | `metadata.yml` (`workflowId` = the flow action's `flowId`, `jsonFileName`, the name in `name`) + `workflow.json` (with a byte-order mark, as saved on Windows): trigger `Request` (`kind: Skills`), `Http` POST to `https://workday.empresa.example/chamados` inside a `Scope`, `Response` (`kind: Skills`) | `flow-uses:http:workday.empresa.example` and `flow-returns`: patterns of the transaction type |
| admissao, its copy of that flow | no `Response` | «the flow «Abrir caso no Workday» of rh-admissao returns nothing» |
| facilities `workflows/ListarUnidades-3f2a9c1d-5e6f-4a7b-8c9d-0e1f2a3b4c5d/` | `OpenApiConnection` to `shared_commondataserviceforapps` (`ListRecords`), no node calls its `workflowId` | `orphan:flow:ListarUnidades`; its connector is not a solo |
| facilities `topics/AvisoAntigo.topic.mcs.yml` | `OnRecognizedIntent` with `intent: {}`, no `modelDescription`, nobody calls it | `orphan:topic:AvisoAntigo` |
| folha `variables/PreferenciaAntiga.mcs.yml` | a global variable no other file names | `orphan:variable:PreferenciaAntiga`, not a solo |
| ferias `topics/Escalate` | a second `SendActivity` with `disabled: true` | `disabled:node:SendActivity`, with the file and the line |

File counts change: orchestrator 6 actions; ferias, beneficios and admissao 1 workflow folder each; facilities 7 topics
and 1 workflow folder; folha 2 variables.

Inferred, to confirm in a real clone:
- how a whole disabled topic appears (`state: Inactive` or another property): the fixtures disable a node only;
- whether each agent's clone brings the flows it uses or only the solution's: the fixtures put the flow in each agent;
- the type of the answer action in a flow called by an agent: `Response` with `kind: Skills`.

## Wave 3 (agent-review 1.5): the telemetry by name, what fired, and declared from a spreadsheet

Added by `gen_fixtures.py` (the `WAVE3` table and three tables beside `agents/`):

| Where | What | What it should give |
|---|---|---|
| admissao `topics/OnError` | `eventName: rh_admissao_onerror`, no `ConversationId` in `properties` | counted as `{agent}_OnError` (the form 5 agents write) and asked: «é o mesmo evento?»; off `telemetry:field:{agent}_OnError/ConversationId` |
| every other agent that logs | `<Key>_OnError` (`RhFerias_OnError`…) with `Agente`, `ErrorMessage`, `ErrorCode`, `TimeUTC`, `ConversationId` | `telemetry:event:{agent}_OnError` and its 5 fields: parts of `node:LogCustomTelemetryEvent`, never solos |
| `examples/telemetria.csv` | the query of `references/telemetry.md`: `agente,evento,vezes`, the agent by display name, `TopicStart` for each connected one | «O evento «RhFolha_OnError» de rh-folha não disparou em 30 dias»; «rh-facilities não tem nenhuma linha na telemetria» |
| `examples/inventario.csv` | the admin center's download: 6 agents by name and schema name, an agent of another environment (`cr7b2_rhMobilidade`), a canvas app, an agent flow; admissao with no owner | `declared:owner`, `environment`, `created-on`, `last-published`; the app and the flow left out; Mobilidade listed as naming nobody |
| `examples/equipe.csv` | `;`, `Agente;KPI;Dono`, facilities with no KPI, a row «Sobre o RH» (the orchestrator's child, not a folder) | `declared:kpi` and `declared:owner`; after `--take all` the KPI rule misses only facilities |

With the example profile: 24 to look at (22 + the spelling + the field); with the demo review file and the telemetry, 27.

Inferred, to confirm in a real clone and a real export:
- the shape of `properties` (a Power Fx record `={…}`), and whether `cloud_RoleInstance` carries the agent's name;
- the exact titles of the inventory download (`Item name`, `Item type`, `Schema name`, `Owner`…), and whether the owner
  comes as a name, an e-mail or an id.
