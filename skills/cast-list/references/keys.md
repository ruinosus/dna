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
| `flow-returns` | The flow returns an answer | O fluxo devolve uma resposta |
| `flow-uses:child-flow` | The flow calls another flow | O fluxo chama outro fluxo |
| `flow-uses:http:<value>` | Flow calls <value> | Fluxo chama <valor> |
| `flow-uses:connector:<value>` | Flow uses the connector <value> | Fluxo usa o conector <valor> |
| `flow-uses:operation:<value>` | Flow uses the operation <value> | Fluxo usa a operação <valor> |
| `connector:<value>` | Connector <value> | Conector <valor> |
| `operation:<value>` | Operation <value> | Operação <valor> |
| `connref:<value>` | Connection reference <value> | Referência de conexão <valor> |
| `mcp:<value>` | MCP server <value> | Servidor MCP <valor> |
| `flow:<value>` | Flow <value> | Fluxo <valor> |

## C. Knowledge — Conhecimento

| Key | Name | Nome |
|---|---|---|
| `trigger:OnKnowledgeRequested` | Before searching knowledge | Antes de buscar no conhecimento |
| `setting:semantic-search=on` | Semantic search on | Busca semântica ligada |
| `setting:semantic-search=off` | Semantic search off | Busca semântica desligada |
| `setting:web-browsing=on` | Web browsing on | Navegação na web ligada |
| `setting:web-browsing=off` | Web browsing off | Navegação na web desligada |
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
| `called-with:history` | Receives the conversation history | Recebe o histórico da conversa |
| `routing:described` | Has a routing description | Tem descrição de roteamento |
| `called-with:input:<value>` | Receives <value> from the orchestrator <value> | Recebe <valor> do orquestrador <valor> |
| `calls:<value>` | Calls <value> | Chama <valor> |
| `child:<value>` | Child <value> | Filho <valor> |
| `var-in:<value>` | Receives from the orchestrator <value> | Recebe do orquestrador <valor> |
| `var:<value>` | Global variable <value> | Variável global <valor> |

## E. Governance — Governança

| Key | Name | Nome |
|---|---|---|
| `setting:model-knowledge=on` | The model's general knowledge on | Conhecimento geral do modelo ligado |
| `setting:model-knowledge=off` | The model's general knowledge off | Conhecimento geral do modelo desligado |
| `instructions:present` | Has instructions | Tem instruções |
| `node:LogCustomTelemetryEvent` | Logs telemetry | Registra telemetria |
| `node:CSATQuestion` | Asks for satisfaction (CSAT) | Pergunta a satisfação (CSAT) |
| `eval:run` | Passed through an evaluation | Passou por uma avaliação |
| `orphan:topic:<value>` | Topic nobody calls <value> | Tópico que ninguém chama <valor> |
| `orphan:action:<value>` | Tool nobody can choose <value> | Ferramenta que ninguém escolhe <valor> |
| `orphan:variable:<value>` | Variable nobody uses <value> | Variável que ninguém usa <valor> |
| `orphan:flow:<value>` | Flow nobody calls <value> | Fluxo que ninguém chama <valor> |
| `disabled:node:<value>` | Switched-off node <value> | Nó desligado <valor> |
| `telemetry:event:<value>` | Logs the event <value> | Registra o evento <valor> |
| `telemetry:field:<value>` | The event carries the field (<event>/<field>) <value> | O evento leva o campo (<evento>/<campo>) <valor> |
| `disabled:<value>` | Switched off <value> | Desligado <valor> |
| `node:<value>` | Node <value> | Nó <valor> |
| `model:<value>` | Model <value> | Modelo <valor> |
| `auth:<value>` | Sign-in <value> | Login <valor> |

## F. Text — F. Texto

| Key | Name | Nome |
|---|---|---|
| `text:<value>` | Text: <value> | Texto: <valor> |

## Microsoft patterns — Padrões Microsoft

| Key | Name | Nome |
|---|---|---|
| `ms:<value>` | Microsoft pattern: <value> | Padrão Microsoft: <valor> |

## Declared — Declarado

| Key | Name | Nome |
|---|---|---|
| `declared:kpi` | KPI declared | KPI declarado |
| `declared:team` | Team declared | Equipe declarada |
| `declared:owner` | Owner declared | Responsável declarado |
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
