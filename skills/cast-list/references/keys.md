# Keys

GENERATED from dev/cast-list/src/labels.ts and microsoft.ts by tools/assets.mjs — do not edit.

Every fact cast-list finds is a key. The keys below have a name; any other key keeps its kind and value
(«Connector shared_office365»), and a kind cast-list does not know stays as it is.

## A. Conversation — Conversa

| Key | Name | Nome |
|---|---|---|
| `trigger:OnConversationStart` | Greeting | Boas-vindas |
| `trigger:OnUnknownIntent` | Fallback (when it does not understand) | Fallback (quando não entende) |
| `trigger:OnEscalate` | Escalation to a person | Escalonamento para humano |
| `trigger:OnError` | Error handling | Tratamento de erro |
| `trigger:OnRecognizedIntent` | A topic of its own, by intent | Tópico próprio, por intenção |
| `trigger:OnSelectIntent` | Disambiguation («did you mean…») | Desambiguação («você quis dizer…») |
| `trigger:OnSignIn` | Sign-in | Login |
| `trigger:OnGeneratedResponse` | Reviews the generated answer | Revisa a resposta gerada |
| `trigger:OnActivity` | On every message | Em toda mensagem |
| `setting:generative=on` | Generative orchestration on | Orquestração generativa ligada |
| `setting:generative=off` | Generative orchestration off | Orquestração generativa desligada |
| `topics:with-model-description` | Topics described for the model | Tópicos descritos para o modelo |
| `reaches:<value>` | A topic leads to it (part of trigger:<value>) <value> | Um tópico leva a ele (parte de trigger:<valor>) <valor> |
| `calls:topic:<value>` | Calls the topic (one not found) <value> | Chama o tópico (não encontrado) <valor> |
| `trigger:<value>` | Trigger <value> | Gatilho <valor> |
| `setting:<value>` | Setting <value> | Configuração <valor> |

## B. Integrations — Integrações

| Key | Name | Nome |
|---|---|---|
| `connector:<value>` | Connector <value> | Conector <valor> |
| `operation:<value>` | Operation <value> | Operação <valor> |
| `connref:<value>` | Connection reference <value> | Referência de conexão <valor> |
| `mcp:<value>` | MCP server <value> | Servidor MCP <valor> |
| `flow:<value>` | Flow <value> | Fluxo <valor> |

## C. Knowledge — Conhecimento

| Key | Name | Nome |
|---|---|---|
| `trigger:OnKnowledgeRequested` | Before searching knowledge | Antes de buscar no conhecimento |
| `node:SearchAndSummarizeContent` | Generative answers from knowledge | Respostas generativas sobre o conhecimento |
| `node:SearchKnowledgeSources` | Searches the knowledge sources | Busca nas fontes de conhecimento |
| `yaml-only:triggerCondition` | Search condition only in YAML (the editor may erase it) | Condição de busca só no YAML (a tela pode apagar) |
| `knowledge:SharePointSearchSource` | Knowledge in SharePoint | Conhecimento no SharePoint |
| `knowledge:<value>` | Knowledge <value> | Conhecimento <valor> |

## D. Orchestrator — Orquestrador

| Key | Name | Nome |
|---|---|---|
| `trigger:OnRedirect` | Takes a call from the orchestrator | Recebe chamada do orquestrador |
| `trigger:OnToolSelected` | Child chosen as a tool | Filho escolhido como ferramenta |
| `setting:connectable` | Can be called by an orchestrator | Pode ser chamado por um orquestrador |
| `calls:<value>` | Calls <value> | Chama <valor> |
| `child:<value>` | Child <value> | Filho <valor> |
| `var-in:<value>` | Receives from the orchestrator <value> | Recebe do orquestrador <valor> |
| `var:<value>` | Global variable <value> | Variável global <valor> |

## E. Governance — Governança

| Key | Name | Nome |
|---|---|---|
| `instructions:present` | Has instructions | Tem instruções |
| `node:LogCustomTelemetryEvent` | Logs telemetry | Registra telemetria |
| `node:CSATQuestion` | Asks for satisfaction (CSAT) | Pergunta a satisfação (CSAT) |
| `node:<value>` | Node <value> | Nó <valor> |
| `model:<value>` | Model <value> | Modelo <valor> |
| `auth:<value>` | Sign-in <value> | Login <valor> |

## Microsoft patterns — Padrões Microsoft

| Key | Name | Nome |
|---|---|---|
| `ms:<value>` | Microsoft pattern: <value> | Padrão Microsoft: <valor> |

## Declared — Declarado

| Key | Name | Nome |
|---|---|---|
| `declared:kpi` | KPI declared | KPI declarado |
| `declared:owner` | Owner declared | Dono declarado |
| `declared:<value>` | Declared: <value> | Declarado: <valor> |

## The Microsoft patterns

From [microsoft/skills-for-copilot-studio](https://github.com/microsoft/skills-for-copilot-studio/blob/main/patterns). With a mark in the YAML, cast-list finds them (`ms:<id>`);
the others only a person can say (in the cast file, `declared` with the key `ms:<id>`).

| Pattern | How cast-list knows |
|---|---|
| `orchestrator-variables` — Orchestrator-Generated Variables | an OnRecognizedIntent topic with an AutomaticTaskInput that has shouldPromptUser: false |
| `rai-error-handling` — RAI Error Handling | the OnError topic reads System.Error.SubCode |
| `knowledge-hold-message` — Knowledge Hold Message | an OnKnowledgeRequested topic that sends a message |
| `prevent-tool-call-leaks` — Prevent Tool Call Leaks | an OnGeneratedResponse topic that sets System.ContinueResponse |
| `dynamic-topic-redirect` — Dynamic Topic Redirect | a BeginDialog whose dialog is a =Switch( expression |
| `channel-aware-behavior` — Channel-Aware Behavior | a condition or SetVariable that reads System.Activity.ChannelId (not a tool input) |
| `date-context` — Date Context | the instructions use Today() or Now() |
| `line-breaks-in-messages` — Line Breaks in Messages | <br /> inside a SendActivity or Question |
| `conversation-history-variable` — Conversation History Variable | declared only |
| `chain-of-thought-logging` — Chain of Thought Logging | declared only |
| `deterministic-mcp-calls` — Deterministic MCP Calls | declared only |
| `prevent-child-agent-responses` — Prevent Child Agent Responses | declared only |
| `jit-glossary` — JIT Glossary | declared only |
| `jit-user-context` — JIT User Context | declared only |
| `teams-production-hardening` — Teams Production Hardening | declared only |
