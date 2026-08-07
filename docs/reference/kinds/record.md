# Record-plane Kinds

**Record-plane** Kinds are queryable data rows (SDLC work items, research, evidence, audit log, …) — first-class instances you `query`/`count` rather than fold into a prompt.

!!! info "Generated from the registered Kinds"

    Introspected from `Kernel.auto()` by `scripts/gen_kinds_docs.py`.
    Each Kind's spec fields come from its own `schema()`.

## ADR

- **Alias:** `sdlc-adr`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

An ADR captures ONE architectural decision with its context, rationale, and consequences. Convention: one ADR per file, immutable once accepted (subsequent decisions supersede). Follows Nygard / MADR template — Adopt on ThoughtWorks Tech Radar. Studio renders these as the decision log of the project; PMs/architects can scan rationale without reading code.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `alternatives_considered` | array |  | Other options weighed and rejected, with brief why-not. |
| `body` | string |  | Optional full markdown body (ADR.md). When present, takes precedence over the structured fields above for rendering. Useful when the ADR predates this schema. |
| `consequences` | string |  | What follows from this decision — positive AND negative. Future readers need to see the trade-offs, not just the wins. |
| `context` | string | yes | WHY we needed to decide. What forces are in play? What constraints (technical, business, team) shape the choice? 1-3 paragraphs. |
| `covers_features` | array |  | Feature names this decision affects. |
| `created_at` | string |  |  |
| `date` | string |  | Date the decision was accepted (ISO-8601). |
| `deciders` | array |  | Actor names who participated in the decision. |
| `decision` | string | yes | WHAT we decided. Active voice: 'We will X' or 'We chose X over Y'. 1-2 paragraphs. |
| `narrative_origin` | string |  | When extracted from a Narrative.decisions[] entry during Phase 2.2 migration, this points to the source Narrative slug for provenance. |
| `status` | string | yes | Lifecycle: proposed → accepted → deprecated\|superseded. Use `superseded` (not deprecated) when a newer ADR replaces this one — link via `superseded_by`. Um de: `proposed`, `accepted`, `deprecated`, `superseded`. |
| `superseded_by` | string |  | ADR slug that supersedes this one (when status=superseded). |
| `supersedes` | array |  | ADR slugs this one replaces. |
| `tags` | array |  | Free-form tags (e.g. 'persistence', 'auth', 'ui'). |
| `title` | string | yes | Decision headline — start with imperative verb. |
| `updated_at` | string |  |  |

## AgentCatalogEntry

- **Alias:** `a2a-agent-catalog-entry`
- **apiVersion:** `github.com/ruinosus/dna/a2a/v1`
- **Plane:** record

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `client_id` | string | yes | O `client_id` OPACO que esta entrada nomeia. Um `client_id` que seja URL é recusado pelo schema: aquele resolve por CIMD, e o nome dele vem ancorado no domínio que o publica. |
| `client_name` | string | yes | O nome legível — DIGITADO por alguém deste workspace, e a tela diz isso. Não é equivalente ao nome de uma instância CIMD, e apresentá-lo como se fosse seria pior que mostrar o id cru: o id avisa que você não sabe quem é; um nome sem procedência não avisa nada. |
| `notes` | string |  | Por que este agente existe, para quem ler a lista depois. Um campo de contexto humano, nunca de política: nada aqui é lido para decidir. |
| `registered_at` | string |  | Quando foi cadastrado. |
| `registered_by` | string | yes | QUEM cadastrou — o identificador durável da pessoa. Obrigatório porque é ele que torna o rótulo possível: "cadastrado por Maria" é uma frase que o usuário pode pesar; um nome sozinho, num id opaco, não é. |
| `vendor` | string |  | A empresa por trás do agente, se quem cadastrou souber. Também digitado, e também sem prova — pelo mesmo motivo do nome. |

## AgentGrant

- **Alias:** `a2a-agent-grant`
- **apiVersion:** `github.com/ruinosus/dna/a2a/v1`
- **Plane:** record

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `call_count` | integer |  | Quantas chamadas CONCEDIDAS. Só as concedidas, pela mesma razão que a quota não conta recusa: um número que mistura uso e tentativa não responde nem "quanto ele usou" nem "quanto ele tentou". |
| `client_id` | string | yes | O identificador do app que pede — LIDO DO TOKEN verificado, nunca de um campo do pedido. O corpo é do chamador: um `client_id` vindo dali deixaria um agente se passar por outro e usar a concessão alheia, com o token continuando válido e a chamada continuando 200. |
| `client_name` | string |  | O nome LEGÍVEL do agente, como a tela de consentimento o exibe. Ausente quando não há nome confiável — e ausente é o default, porque um `client_id` cru é feio e HONESTO, enquanto um nome fabricado é legível e falso. Numa tela de autorização a segunda coisa é pior. ⚠️ NÃO é auto-declarado. O host só grava aqui um nome que veio ANCORADO: o `client_id` é uma URL HTTPS (CIMD, draft-ietf-oauth-client-id-metadata-instance) e o nome foi lido da instância servido naquela origem. Quem controla `acme.com` é o único que pode declarar um nome em `acme.com`, e disso o DNS e o TLS já dão prova. Aceitar nome de um campo do pedido devolveria o ataque que este desenho existe para fechar: a tela do provedor, com a marca dele, no instante da autorização, exibindo a mentira com aparência oficial. A ORIGEM não é campo: ela se DERIVA do `client_id` (o host da URL), e é isso que a tela deve mostrar com o mesmo peso do nome. Um campo de domínio ao lado poderia divergir do `client_id`, e um domínio que diverge da âncora é exatamente o nome auto-declarado com outra roupa. Pela mesma razão não há campo dizendo "de onde veio o nome": com `client_id` opaco não há nome ancorado possível, então a procedência já está dita pela forma do `client_id`. CONGELADO no instante do pedido, de propósito: o registro guarda o que o humano VIU quando decidiu. Se o terceiro se renomear depois, a tela não troca por baixo de uma decisão já tomada — e a âncora, que se deriva do `client_id`, nunca envelhece. |
| `granted_at` | string |  | Quando um HUMANO concedeu. Ausente enquanto ninguém decidiu. |
| `last_call_at` | string |  | A auditoria — quando este agente agiu pela última vez. |
| `requested_at` | string |  | Quando o agente pediu — o pedido nasce da primeira recusa. |
| `requested_scope_kinds` | array |  | O que o agente PEDIU — separado do que foi concedido, e essa separação é a regra inteira do consentimento: o agente pede, o usuário decide. Um campo só faria pedir ser igual a receber. Serve à tela, que pré-marca o pedido para o humano confirmar ou cortar. Um agente que não declara nada deixa isto vazio, e nada vem marcado: silêncio nunca vira permissão. |
| `revoked_at` | string |  |  |
| `scope_kinds` | array |  | Os Kinds cujas instâncias este agente pode receber. Mesmo vocabulário do `RemoteAgent.data_scope.kinds`, de propósito: é a mesma pergunta nas duas direções, e responder diferente de cada lado seria uma armadilha para quem lê. AUSENTE ou VAZIO significa "nada pode". Ausência FECHA, nunca abre. |
| `state` | string | yes | Tri-estado DE PROPÓSITO, como o `signature_state` do `RemoteAgent`. Um booleano `granted` faria "pediu e ninguém decidiu" parecer "negado", e são coisas diferentes: a primeira precisa APARECER numa tela para alguém decidir; a segunda já foi decidida e não pede nada. Um de: `pending`, `active`, `revoked`. |
| `subject` | string | yes | O usuário que concede — o identificador DURÁVEL dele, não o da sessão. Durável porque a concessão sobrevive ao login: revogar um agente não é deslogar a pessoa, e as duas coisas precisam ser independentes. |

## AgentSession

- **Alias:** `sdlc-agent-session`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A AgentSession captures a developer↔AI coding conversation as a versioned project artifact. Tool-agnostic: works for Claude Code, Cursor, Cline, Codex, Aider via per-tool adapters. Schema is the LCD (lowest-common-denominator) of the major tools' export formats.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `applied_commits` | array |  | Git SHA refs touched in-session. |
| `body` | string |  | Rendered transcript markdown (stored in SESSION.md). |
| `cost_usd` | number |  |  |
| `ended_at` | string |  |  |
| `file_changes` | array |  | Repo-relative paths edited during session. |
| `journey_phase` | string |  | Universal journey phase. AgentSessions usually live in `discover` (brainstorming chats) or `build` (execution chats). The agent stamps this on capture. Um de: `discover`, `specify`, `plan`, `build`, `verify`, `reflect`. |
| `model` | string |  | AI model identifier (e.g. claude-opus-4-7, gpt-5-codex). |
| `participants` | array |  | Actor names (humans + agent identities). |
| `produced_artifacts` | array |  | Refs to docs created/modified during session. |
| `produced_artifacts[].kind` | string | yes |  |
| `produced_artifacts[].name` | string | yes |  |
| `raw_source` | string |  | Provenance pointer — tool-native source path or URL (JSONL file path, sqlite URI, etc). Required for re-derivation. |
| `session_id` | string | yes | Tool-native session identifier (UUID/sqlite-rowid/etc). |
| `started_at` | string | yes |  |
| `summary` | string |  |  |
| `title` | string | yes | Human-readable session title (Jira-style summary). |
| `token_usage` | object |  | {input, output, cache_*} — adapter-specific shape. |
| `tool` | string | yes | Provenance — which AI coding tool produced this session. claude-code \| cursor \| cline \| codex \| aider \| specstory \| other. |
| `tool_specific` | object |  | Escape hatch for per-tool extras (Cline checkpoints, CC git snapshots, etc). |
| `tool_version` | string |  |  |
| `workspace_path` | string |  |  |

## App

- **Alias:** `helix-app`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** record

An App is the NAMED composition of copilots (record plane) — the installable/sellable unit of the spec-app-como-composicao decisions (2026-08-05). A kit is the PACKAGE (how a flow ships); an App is the INSTANCE (how it is used, navigated and charged). It groups existing Copilot docs under one identity (title/description/icon), carries the plan entitlement (``requires_plan`` — enforced by the serving runtime, never by the kernel) and the console renders ``/app/<name>`` from this instance alone. ``copilots`` is a declared RELATION to ``Copilot`` — the write validates existence and pickers come for free (i-040). Since ``spec-app-e-o-servico`` (2026-08-07) an App is also THE SERVICE that runs it — one deployment, identified by ``metadata.name``. Two of the four new fields describe the CODE and are shared by sibling Apps (``service_name``, the ``apps/<name>/`` directory — the same axis ``Solution.services[].name`` addresses — and ``python_module``); two describe the DEPLOYMENT and are per App (``port``, the in-container ``targetPort``, and ``can_sleep``). Code to deployment is 1:N, measured: dna-cloud runs 9 deployable services over 4 ``apps/`` directories, and ``apps/mcp/`` alone serves ``mcp``/``mcp-entra``/``mcp-ws`` — same image, same port, different identity authority. All four optional, because the 2 live Apps predate them. ``can_sleep`` is the one that pays for the change: a container app that cannot sleep carries a fixed replica at ~US$ 90/month forever (measured — the dna-cloud ``copilot`` service was US$ 94,43 of a US$ 230,29 bill), and until now no declaration anywhere answered that question. Absent is never a presumed ``true``: it means the cost question was never asked, which is a finding to report.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `can_sleep` | boolean |  | Este App pode escalar a zero. Fato sobre o DEPLOYMENT e nunca sobre o diretório — dois Apps sobre a MESMA imagem podem responder diferente, e é por isso que a pergunta mora aqui e não em `service_name`. ⭐ É o campo que paga esta mudança sozinho, e o motivo é dinheiro medido: um container app que NÃO dorme carrega uma réplica fixa e custa ~US$ 90/mês, recorrente, para sempre. Medição de 31/07/2026 no dna-cloud - o serviço `copilot`, com `minReplicas: 1`, era US$ 94,43 de uma fatura de US$ 230,29; sozinho, a MAIOR linha da conta, num ambiente que a documentação descrevia como "scale-to-zero, ocioso não cobra". O `CLAUDE.md` do dna-cloud tem um portão escrito com esse número - "antes de propor um container app, a pergunta é: ele pode dormir?" - e até aqui NADA na declaração respondia essa pergunta - a resposta vivia só na cabeça de quem gerou o serviço, e um App novo continuava parecendo grátis. Este campo é onde a pergunta do portão passa a ter onde ser respondida, ANTES de alguém provisionar. Ausente significa que este App NUNCA respondeu a pergunta de custo, e isso é um achado a reportar - jamais um `true` presumido - porque presumir o lado barato esconde exatamente a réplica que ninguém decidiu. |
| `copilots` | array | yes | Os copilotos que COMPÕEM este App, por nome de doc — cada um traz seus fluxos (surfaces) para debaixo desta identidade. A referência é validada na gravação (`spec.relations`). |
| `description` | string |  | Uma linha do que este App faz, na voz do produto. |
| `icon` | string |  | Marca curta (1–2 caracteres ou emoji) para o card e a navegação. Vazio = a inicial do title. |
| `nav_order` | integer |  | Ordem relativa na navegação do console (menor primeiro). Ausente = ordem alfabética. |
| `port` | integer |  | A porta que o processo escuta DENTRO do contêiner — o `targetPort` do Container App, o `container_port` do template. ⚠️ NÃO é a porta publicada no host. Medido no dna-cloud em 07/08/2026 (`infra/bicep/containerapps.bicep`): `mcp`, `rest`, `copilot` e `a2a` escutam todos em 8080, e só o portal difere (3000, Next.js). As portas 8100 / 8102 / 8090 / 8091 / 8182 que aparecem no `docker-compose.dev.yml` são MAPEAMENTO DE HOST para o dev local, e declarar uma delas aqui geraria um `targetPort` apontando para onde nada escuta. O que distingue `mcp` de `mcp-entra` não é a porta — é o ENV (a autoridade de identidade), com a mesma imagem e a mesma porta; é mais uma razão para a identidade do App ser o `metadata.name`, já que `service_name` e `port` colidem entre Apps irmãos por desenho. Declarada e não presumida porque o default de um framework não é um compromisso — o `dna.runtime` serve numa porta, o `dna api serve` em outra, e quem lê a frota precisa saber qual sem abrir o Dockerfile. |
| `python_module` | string |  | O pacote Python sob `src/` que este App importa — a resposta `python_module` do template. Um identificador Python (minúsculas, dígitos, underscore). Fato sobre o CÓDIGO, como `service_name`, e portanto igual entre os Apps que compartilham o diretório: os três Apps de `apps/mcp/` importam o mesmo módulo e diferem só no ambiente. Não é derivável de `service_name` por substituição de traço por underscore sem adivinhar, porque o template pergunta as duas coisas separadamente e um repo real pode responder diferente. |
| `requires_plan` | string |  | O plano MÍNIMO que abre este App (entitlement, decisão do founder em 05/08). Ausente = aberto a qualquer plano. Quem aplica é o runtime que serve; o kernel valida a forma. Um de: `free`, `pro`. |
| `service_name` | string |  | O diretório do CÓDIGO que este App executa — `apps/<service_name>/`, com o Dockerfile e o `src/`. ⚠️ NÃO é a identidade deste App e NÃO é 1:1 com ele: vários Apps compartilham legitimamente um `service_name`, porque compartilham a IMAGEM. Medido no dna-cloud em 07/08/2026 — 9 serviços implantáveis sobre 4 diretórios `apps/`, e `apps/mcp/` sozinho serve `mcp`, `mcp-entra` e `mcp-ws`, as três portas de identidade (mesma imagem, autoridades diferentes). Quem identifica o deployment é o `metadata.name` da instância; este campo diz apenas de qual código ele nasce, e é o mesmo eixo que `Solution.services[].name` (a camada de answers) endereça. O padrão é o do validador do template (`templates/app-container/copier.yml`), copiado para que a recusa aconteça na declaração e não no `azd up`. Ausente significa que este App ainda não diz de que código roda — um fato a reportar, nunca um nome a adivinhar a partir do `metadata.name`, que para 8 dos 9 serviços acima daria o nome errado. |
| `title` | string | yes | O nome que o usuário vê — a identidade do App no console (o doc name é o slug da rota /app/<name>). |

## AuditLog

- **Alias:** `audit-auditlog`
- **apiVersion:** `github.com/ruinosus/dna/audit/v1`
- **Plane:** record

Immutable record of a role-gated HTTP endpoint invocation. Captures actor, roles claimed, operation, target Kind/name, scope/tenant, request_id, outcome, and timestamp. Used by compliance auditors + admins to answer 'who did what when' without parsing application logs.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `actor` | string | yes | Identity that made the request. From claims.email > claims.sub. 'dev-user' in dev-bypass, 'test-user' in test-header mode. |
| `captured_at` | string | yes | UTC ISO-8601 timestamp. |
| `detail` | object |  | Free-form context: which required roles failed, body size, durations, errors. Defensive about PII — don't include request bodies verbatim. |
| `operation` | string | yes | HTTP method + path template, e.g. 'PUT /scopes/{scope}/docs/Agent/{name}' or 'POST /assessments/{name}/run'. |
| `outcome` | string | yes | success = decorator + handler ran clean. denied = 403 from require_role. error = handler raised (500/422/...). Um de: `success`, `denied`, `error`. |
| `remote_ip` | string |  | Best-effort client IP (X-Forwarded-For aware). |
| `request_id` | string |  | Correlation ID (UUIDv4) — joins logs. |
| `roles` | array | yes | Roles claimed at request time (from JWT or DNA_DEV_ROLES). Snapshot — does NOT reflect later role revocations. |
| `target_kind` | string |  | Kind of doc affected (when applicable). Null for non-doc ops like POST /sync/replicate. |
| `target_name` | string |  | Name of doc affected, when applicable. |
| `target_scope` | string |  | Scope of doc affected, when applicable. |
| `target_tenant` | string \| null |  | Tenant the operation routed to (claims.tenant + overrides resolved). Null = base layer write. |
| `user_agent` | string |  | HTTP User-Agent header. |

## Automation

- **Alias:** `dna-automation`
- **apiVersion:** `github.com/ruinosus/dna/automation/v1`
- **Plane:** record

An Automation declares background work as data — ``on`` picks the trigger (cron = 5-field schedule; hook = a kernel lifecycle hook name from KNOWN_HOOK_NAMES; tool = an async dispatch tool the host exposes to the model), ``runner`` picks what executes (an Agent or a Tool by name), plus the shared agent_directive / input / result templating / spoken copy / safety block. Adding or retargeting an automation is writing one YAML, zero deploy. The SDK validates and lists (see ``dna.extensions.automation.query.automations_for``); the HOST executes — the runner contract is an extension point, documented in docs/concepts/builtin-kinds.md.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `agent_directive` | string |  | Dispatch instruction sent to an agent runner (with {arg} placeholders). Optional — a tool runner needs none. |
| `description` | string |  |  |
| `done_message` | string |  | Spoken/UI copy attached to the finished run. Supports {placeholders} from the args. |
| `enabled` | boolean |  | Disabled automations stay declared but hosts must not fire them (automations_for filters them out by default). |
| `input` | object |  | Structured input the host resolves into the runner's context. Hosts may support tokens such as {scope}, {now}, {utc_date}. |
| `labels` | array |  |  |
| `on` | object | yes | The trigger. type=cron → scheduled (5-field cron expression, validated at write); type=hook → a kernel lifecycle hook name (KNOWN_HOOK_NAMES vocabulary, validated at write); type=tool → an async dispatch tool the host exposes to the model. |
| `on.cron` | string |  | 5-field cron 'min hour dom mon dow', e.g. '0 10 * * 1,3,5'. Parsed at write time by the automation write guard (numeric fields, '*', ranges, lists, steps — no JAN/MON name aliases). |
| `on.hook` | string |  | Kernel lifecycle hook that fires this automation, e.g. 'post_save' or 'post_build_prompt'. Must be one of the kernel's KNOWN_HOOK_NAMES — the write guard vetoes unknown names. |
| `on.input_schema` | array |  | Declared args of the dispatch tool (all strings). |
| `on.input_schema[].default` | string |  |  |
| `on.input_schema[].description` | string |  |  |
| `on.input_schema[].name` | string | yes |  |
| `on.input_schema[].required` | boolean |  |  |
| `on.input_schema[].type` | string |  |  |
| `on.primary_input` | string |  | Which input arg carries the main user content fed to an agent runner. Defaults to the first input_schema entry. |
| `on.tool_name` | string |  | The dispatch tool the model sees (e.g. deep_research_async). |
| `on.type` | string | yes | Um de: `cron`, `hook`, `tool`. |
| `result_kind` | string |  | Kind the automation output should be persisted as (e.g. Research, Doc) when the runner produces an instance. |
| `result_spec_template` | object |  | Deterministic persist template — when an agent runner synthesizes but does not persist a doc itself, the host creates a result_kind doc from this template ({arg} fills from the args, {output} from the agent synthesis). |
| `runner` | object | yes |  |
| `runner.expected_output` | string |  | For an agent runner, what the agent should produce. 'slug' = persist a real domain doc (result_kind) and return its slug; 'text'/'json' = return prose/structured output inline. Hosts default to 'text'. Um de: `slug`, `json`, `text`. |
| `runner.kind` | string | yes | Um de: `agent`, `tool`. |
| `runner.model` | string |  | Optional model override for the runner. |
| `runner.ref` | string | yes | Agent name (kind=agent) or Tool name (kind=tool) that executes the automation. |
| `runner.timeout_seconds` | number |  | Wall-clock budget the host should give one run. |
| `running_message` | string |  | Spoken/UI copy returned at dispatch (tool trigger). |
| `safety` | object |  | Loop-safety the HOST enforces for this automation. All fields optional — an absent field falls back to the host default. |
| `safety.cooldown_minutes` | integer |  | Do not re-fire for the same scope within this wall-clock window. |
| `safety.debounce_seconds` | number |  | Coalesce repeated fires within this window into one. |
| `safety.idempotency_key` | string |  | Template, e.g. '{scope}:{utc_date}'. A 2nd fire with the same resolved key is a no-op. |
| `safety.max_fan_out` | integer |  | Cap on instances one fire may produce. |
| `safety.max_fires_per_minute` | integer |  | Circuit-breaker rate cap per (scope, automation). |

## Bug

- **Alias:** `sdlc-bug`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Bug captures a factual defect: repro_steps, severity, environment, status. Distinct from Postmortem (incident — sev1-sev5 outage analysis) e Issue umbrella (enhancement/question/other).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `actual` | string |  |  |
| `body` | string |  |  |
| `created_at` | string |  |  |
| `description` | string |  |  |
| `environment` | string |  |  |
| `expected` | string |  |  |
| `fix_adr` | string |  |  |
| `fix_summary` | string |  |  |
| `found_at` | string |  |  |
| `labels` | array |  |  |
| `owner` | string |  |  |
| `priority` | string |  | Um de: `highest`, `high`, `medium`, `low`, `lowest`. |
| `produces` | array |  | Artifacts this work item produced — any Kind (hub). |
| `produces[].at` | string |  |  |
| `produces[].kind` | string | yes | Artifact Kind (any). |
| `produces[].name` | string | yes | Artifact doc name. |
| `produces[].role` | string |  | Optional role hint (e.g. visual-spec, plan, investigation). |
| `related_feature` | string |  |  |
| `related_finding` | string |  |  |
| `related_story` | string |  |  |
| `reporter` | string |  |  |
| `repro_steps` | array |  |  |
| `resolved_at` | string |  |  |
| `root_cause` | string |  |  |
| `severity` | string | yes | Um de: `low`, `medium`, `high`, `critical`. |
| `status` | string | yes | Um de: `open`, `triaged`, `in-progress`, `resolved`, `wont-fix`, `duplicate`, `regression`. |
| `timeline` | array |  | Append-only activity log. Auto-stamped by the CLI on every status flip / groom / artifact write; populated by AgentSession capture for decision + artifact_produced events. Render in Studio as activity stream. |
| `timeline[].actor` | string | yes | Who triggered the event (Actor name or 'claude-code'). |
| `timeline[].at` | string | yes |  |
| `timeline[].commit_ref` | string |  | Git SHA associated with this event (when relevant). |
| `timeline[].excerpt` | string |  | decision: snippet from the source transcript. |
| `timeline[].fields` | object |  | groom: which fields changed and to what. |
| `timeline[].from` | string |  | status_change: previous status. |
| `timeline[].paths` | array |  | artifact_produced: file paths touched. |
| `timeline[].session_ref` | string |  | Back-link to a AgentSession that produced this event. |
| `timeline[].source` | string |  | Um de: `cli`, `studio`, `mcp`, `agent-session-extracted`, `system`. |
| `timeline[].summary` | string |  | comment/decision: short human-readable text. |
| `timeline[].to` | string |  | status_change: new status. |
| `timeline[].type` | string | yes | Event type. Recognized: status_change, groom, comment, decision, artifact_produced (open vocabulary — new types are additive, e.g. pr_opened). |
| `title` | string | yes |  |
| `updated_at` | string |  |  |

## Changelog

- **Alias:** `sdlc-changelog`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Changelog records release notes per semver version per Keep a Changelog 1.1.0 convention. Six sections: Added, Changed, Deprecated, Removed, Fixed, Security. Latest entry at top (reverse chronological). [Unreleased] section tracks work in flight.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string |  | Optional full markdown CHANGELOG.md. |
| `created_at` | string |  |  |
| `description` | string |  |  |
| `title` | string | yes | Project name typically. |
| `updated_at` | string |  |  |
| `versions` | array |  | Reverse-chronological list of versions. |
| `versions[].added` | array |  | New features. |
| `versions[].changed` | array |  | Changes in existing functionality. |
| `versions[].date` | string |  |  |
| `versions[].deprecated` | array |  | Soon-to-be removed. |
| `versions[].fixed` | array |  | Bug fixes. |
| `versions[].removed` | array |  | Removed in this version. |
| `versions[].security` | array |  | Vulnerability fixes. |
| `versions[].version` | string | yes | SemVer 2.0 (e.g. '1.4.2') or '[Unreleased]'. |

## CognitivePolicy

- **Alias:** `sdlc-cognitive-policy`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `affect` | object |  | Affect vocabulary for the memory/affect engine (ex-AffectPalette). The active palette steers engraphy affect tags. |
| `affect.palette` | array | yes |  |
| `affect.palette[].affect_weight` | number |  |  |
| `affect.palette[].id` | string | yes |  |
| `affect.palette[].semantics` | string | yes |  |
| `affect.palette[].use_when` | array |  |  |
| `allocation` | object |  | Engram allocation (dedup/archival) knobs (ex-AllocationPolicy). |
| `allocation.loser_policy` | string |  | Which of two overlapping engrams loses — the weaker (lower strength) or the newer one. Um de: `weaker`, `newer`. |
| `allocation.overlap_weights` | object |  | How overlap [0,1] is scored (sum 1.0). |
| `allocation.overlap_weights.affect` | number |  | Same affect bonus. |
| `allocation.overlap_weights.area` | number |  | Same area bonus. |
| `allocation.overlap_weights.source_refs` | number |  | Jaccard of shared source_refs. |
| `allocation.threshold` | number |  | Overlap >= this proposes archiving the loser (clamped 0.5-1.0). |
| `created_at` | string |  |  |
| `decay` | object |  | Memory retention/forgetting knobs (ex-DecayPolicy). |
| `decay.default_stability_days` | number |  | Fallback stability when no tier/stability is on the doc. |
| `decay.max_stability_days` | number |  | Per-recall bump ceiling (so frequent recalls don't compound forever). |
| `decay.ranking_formula` | string |  | simple = exponential decay (Sprint 1); actr = log power-law (Sprint 2). Um de: `simple`, `actr`. |
| `decay.relevance_decay_seed` | number |  | Default multiplicative decay per 24h (spec override wins). |
| `decay.stability_tiers` | object |  | Ebbinghaus stability per confidence tier, in days. |
| `decay.stability_tiers.burning` | number |  |  |
| `decay.stability_tiers.faint` | number |  |  |
| `decay.stability_tiers.firm` | number |  |  |
| `embedding` | object |  | Embedding model + dimension + search weights (ex-EmbeddingProfile). ONLY meaningful on the _lib doc — the embedding space is intrinsically global (stored vectors and every query must share one model+dimension); kernel.embedding_profile reads _lib directly and never a scope override. `recall.calibrated_for` points back here. |
| `embedding.dimensions` | integer | yes | Vector dimension. MUST match the pgvector column + every stored embedding — changing it requires a full re-embed. |
| `embedding.language` | string |  | Primary language the recall knobs were calibrated against. |
| `embedding.max_input_tokens` | integer |  | Input ceiling for a single embed call (model-specific). |
| `embedding.model` | string | yes | Embedding model id (must be served by the LiteLLM proxy). |
| `embedding.notes` | string |  |  |
| `embedding.search_weights` | object |  | RRF fusion weights for `cognitive search` (hybrid retrieval). |
| `embedding.search_weights.bm25` | number |  |  |
| `embedding.search_weights.graph` | number |  |  |
| `embedding.search_weights.vector` | number |  |  |
| `engram_strength` | object |  | Initial-strength rules per engraphy trigger (ex-EngramStrengthPolicy). |
| `engram_strength.default_decay_rate_per_day` | number |  |  |
| `engram_strength.default_decay_threshold_days` | integer |  |  |
| `engram_strength.rules` | array | yes |  |
| `engram_strength.rules[].engraphy_intensity` | number |  |  |
| `engram_strength.rules[].initial_strength` | number | yes |  |
| `engram_strength.rules[].when` | string | yes | Trigger predicate |
| `generation` | object |  | Operational params for the memory-gen engines (the ORIGINAL CognitivePolicy body, now one section among peers). |
| `generation.auto_shipped` | object |  | Deterministic ship → engram producer. |
| `generation.auto_shipped.lookback_days` | integer |  | Window of recently-done Stories considered. |
| `generation.auto_shipped.max_emit` | integer |  | Max engrams emitted per run. |
| `generation.backfill` | object |  | Distil done Stories/Features into engrams. |
| `generation.backfill.budget` | integer |  | Max engrams written per backfill run (resumable). |
| `generation.consolidation` | object |  | Episodic → semantic consolidation. |
| `generation.consolidation.min_cluster_size` | integer |  | Min episodic engrams in an area before consolidating. |
| `ingestion` | object |  | WHEN memory is fed, and from WHAT. The workspace's own answer to "how and when are memories created" — the half `recall` (how they are USED) already had. ⭐ WHY THIS IS DATA AND NOT A FLAG. Feeding memory automatically is a judgement about the customer's own material: a legal team may want every decision captured; a support team may want nothing from chat at all. Hard-coding either answer picks a side for people whose work we do not know. Absent, the built-in defaults apply and nothing changes. |
| `ingestion.arbiter_neighbors_cap` | integer |  | Hard cap of the arbiter neighborhood. |
| `ingestion.arbiter_neighbors_multiplier` | integer |  | The arbiter sees a WIDER neighborhood than the reconciliation — `neighbors × multiplier` (capped below). It is deciding a conflict, so it needs more context than the pass that raised it. |
| `ingestion.enabled` | boolean |  | Master switch. `false` stops all automatic feeding — the agent still writes memory when explicitly asked, because that path is the user's own instruction, not a policy decision. |
| `ingestion.engine` | string |  | The reconciliation engine. `pipeline` = two fixed model calls (cheap, predictable). `pipeline-agent` = the hybrid: the fixed skeleton, but the reconciliation may ESCALATE an uncertain fact to the arbiter agent (one bounded round; the arbiter decides, the pipeline applies). `agent` = the named agent reconciles everything (reserved; not yet implemented). Um de: `pipeline`, `pipeline-agent`, `agent`. |
| `ingestion.engine_agent` | string |  | The Agent instance that arbitrates escalations (its instruction is the arbiter's role text). Empty + an escalation = the fact degrades to `none` — uncertainty without a judge never writes. |
| `ingestion.max_arbitrations` | integer |  | Ceiling of arbiter escalations per turn (`pipeline-agent` engine). Beyond it, facts degrade to `none` — uncertainty without budget never writes. |
| `ingestion.max_facts_per_turn` | integer |  | Ceiling of facts extracted per turn. A real conversation does not produce ten durable facts; a model returning ten is inventing — the ceiling turns that into bounded noise. |
| `ingestion.max_transcript_chars` | integer |  | How much transcript feeds the extraction. More does not improve the fact and worsens the bill. |
| `ingestion.min_signal_chars` | integer |  | Below this the turn is skipped without a model call. It exists because most turns of a real conversation are "ok" / "thanks" — extracting from them costs money and yields noise that later SURFACES on its own in the prompt. |
| `ingestion.neighbors` | integer |  | How many existing memories the reconciliation compares each new fact against (the recall k). More sees farther and costs more tokens per turn; fewer is cheaper and can miss a conflict. |
| `ingestion.proposal_markers` | array |  | Regexes that mark a turn as containing a DURABLE assertion — the trigger for the "propose to remember" nudge. EMPTY means the built-in markers apply — and the built-ins are Portuguese-biased (decidimos/prefiro/prazo...), which is exactly why this is data: an English or Spanish workspace declares its own. |
| `ingestion.require_approval` | boolean |  | Whether an automatically extracted memory goes through the human approval gate before being written. ⚠️ `false` is deliberate and is the founder's call (2026-08-03). With reconciliation (a later fact can UPDATE or invalidate an earlier one) a wrong memory costs "until contradicted" rather than "forever" — which is what made the automatic path defensible at all. Set `true` and every extracted fact becomes a card to click; the trail gains coverage and the feature gains friction. |
| `ingestion.sdlc` | object |  | The `sdlc` source cadence — how often the board is read for extraction, and how much of it. |
| `ingestion.sdlc.interval_seconds` | integer |  | Minimum interval between board reads per workspace (default 6h). |
| `ingestion.sdlc.max_items` | integer |  | Stories per digest — a month of board does not hold a hundred durable facts. |
| `ingestion.sources` | array |  | WHERE facts may be extracted from. `chat` = the conversation transcript; `sdlc` = board activity; `kind:<Name>` = instances of a given Kind as they are written. A source absent from this list is NEVER read — the list is an allowlist, not a preference. Widening it is the workspace's decision, and it is the decision that governs what the agent may learn about its people. |
| `ingestion.transcript_messages` | integer |  | How many recent messages (user AND agent) form the extraction material — decisions often complete across the exchange ("pode ser 60 dias?" / "fechado, 60"). |
| `ingestion.trigger` | string |  | `per_turn` extracts as the conversation happens (memory is immediate; costs a model call per qualifying turn). `batch` defers to a scheduled pass (cheap; memory arrives late). `off` disables extraction while leaving the rest of the policy in force. Um de: `per_turn`, `batch`, `False`. |
| `intel` | object |  | Intel-engine tuning (#36 tail) — ranker weights, dedup threshold, feedback strengths and the portal action bar. Engine-wide per workspace; the per-SOURCE `threshold` stays on IntelSource. |
| `intel.action_bar` | number |  | Score at or above which an insight "requires action" in the screens (product judgement, now declarable). |
| `intel.dedup` | object |  |  |
| `intel.dedup.cosine_threshold` | number |  | Above this cosine two insights are "the same". |
| `intel.feedback` | object |  |  |
| `intel.feedback.action_bonus` | number |  |  |
| `intel.feedback.dismiss_penalty` | number |  |  |
| `intel.feedback.sim_threshold` | number |  |  |
| `intel.ranker` | object |  |  |
| `intel.ranker.base` | number |  |  |
| `intel.ranker.evidence_weights` | object |  |  |
| `intel.ranker.evidence_weights.anecdotal` | number |  |  |
| `intel.ranker.evidence_weights.evidence-based` | number |  |  |
| `intel.ranker.evidence_weights.opinion-practice` | number |  |  |
| `intel.ranker.has_action` | number |  |  |
| `intel.ranker.pir_match` | number |  |  |
| `memory` | object |  | Agent-memory governance (ex-MemoryPolicy). Each entry in `policies` keeps the old multi-doc matcher semantics — merged most-specific-wins by dna_shared.cognitive.memory_policy. |
| `memory.policies` | array |  |  |
| `memory.policies[].applies_to` | object |  | Matcher: any of scope/owner/memory_type (absent = wildcard). Most-specific wins. |
| `memory.policies[].applies_to.memory_type` | string |  | Any declared memory type. OPEN, in lockstep with the `Engram` field it matches: a closed enum here would let a workspace declare `preference` on the memory and then be unable to write a policy for it. |
| `memory.policies[].applies_to.owner` | string |  |  |
| `memory.policies[].applies_to.scope` | string |  |  |
| `memory.policies[].defaults` | object |  |  |
| `memory.policies[].defaults.include_agents` | boolean |  |  |
| `memory.policies[].defaults.pinned_budget` | integer |  |  |
| `memory.policies[].defaults.visibility` | string |  | Um de: `shared`, `private`, `pinned`, `archived`. |
| `memory.policies[].remember` | object |  | Topic steering (guidance; hard enforcement stays in the write path / Presidio). |
| `memory.policies[].remember.always` | array |  |  |
| `memory.policies[].remember.never` | array |  |  |
| `methodology` | object |  | SDLC methodology gates. Read through the session kernel's instance port (adapter-agnostic — filesystem, sqlite or Postgres per DNA_SOURCE_URL), so journey transitions honor it wherever the board lives. |
| `methodology.auditor_threshold` | integer |  | Ad-hoc cycles within the window that trigger the "next phase requires superpowers" gate. |
| `methodology.auditor_window` | integer |  | How many recent cycles the auditor looks at. |
| `owner` | string |  |  |
| `pagination` | object |  | REST list pagination defaults/caps (ex-PaginationPolicy). Data-plane ownership — read by dna_shared.pagination_policy, not the cognitive engines. |
| `pagination.default_limit` | integer |  | Page size when the request omits ?limit=. |
| `pagination.max_limit` | integer |  | Hard cap — a larger ?limit= is clamped to this. |
| `recall` | object |  | Recall-tuning knobs for the ecphory engine (ex-RecallPolicy). |
| `recall.calibrated_for` | object |  | Validity envelope — the embedding model/dimension/language the semantic knobs were calibrated for. If the `embedding` section changes, these are stale and must be re-calibrated. |
| `recall.calibrated_for.dimensions` | integer |  |  |
| `recall.calibrated_for.embedding_model` | string |  |  |
| `recall.calibrated_for.language` | string |  |  |
| `recall.injection` | object |  | How the recalled block ENTERS the prompt (the runtime middleware side). `retrieval` shapes the search; `injection` shapes the prompt. Defaults mirror the middleware constants they replace (varredura de valores, 03/08/2026). |
| `recall.injection.cue_max_chars` | integer |  | Ceiling of the cue text — a giant query does not discriminate better, it only costs more. |
| `recall.injection.cue_window` | integer |  | How many recent user messages form the search cue. |
| `recall.injection.max_block_chars` | integer |  | Ceiling for the whole injected block — one long Engram must not eat the window. |
| `recall.injection.min_signal_chars` | integer |  | Below this the user turn triggers no search ("ok", "thanks"). |
| `recall.injection.sticky_overlap` | number |  | Hysteresis — fraction of the previous working set that must survive for the OLD block to be kept (prompt/cache stability, from the JARVIS prior art). |
| `recall.injection.type_labels` | object |  | How each memory TYPE is labeled inside the injected block (`- [LABEL] text`). OPEN map (type → label), merged over the built-ins (procedural→"REGRA (siga)", episodic→"fato ocorrido", semantic→"fato") — open because memory types are open, and the label IS model-facing voice: a workspace in English declares its own. |
| `recall.retrieval` | object |  | Shape of retrieval — how many results, how to diversify and spread. Not coupled to the embedding model nor to memory theory. |
| `recall.retrieval.k` | integer |  | Final working-set size injected per turn. |
| `recall.retrieval.limit_direct` | integer |  | Max direct ecphory hits considered. |
| `recall.retrieval.limit_homophonic` | integer |  | Max homophony-expanded hits considered. |
| `recall.retrieval.mmr_lambda` | number |  | MMR redundancy penalty (diversity vs raw score). |
| `recall.retrieval.search_n` | integer |  | pgvector candidates pulled for the cosine overlay. |
| `recall.retrieval.spread_decay` | number |  | Activation decay per spreading hop. |
| `recall.retrieval.spread_depth` | integer |  | Spreading-activation hops from the direct hits. |
| `recall.semantic` | object |  | Embedding-coupled knobs (model+dimension+language). Cosine only means anything within one embedding space — re-calibrate on change. |
| `recall.semantic.cosine_weight` | number |  | Weight on the raw embedding cosine in the content dimension (calibrated 0.55->0.61, 2026-06-15). |
| `recall.semantic.direct_threshold` | number |  | Ecphory direct gate (mirrors theta_in). |
| `recall.semantic.theta_in` | number |  | Enter the working set when the fresh score >= this. |
| `recall.semantic.theta_out` | number |  | Hold a prior member while its score >= this (hysteresis). |
| `recall.structural` | object |  | Theory-derived weights (Tulving/Nairne/Semon). Stable across model and language. |
| `recall.structural.affect_weight` | number |  |  |
| `recall.structural.co_topics_weight` | number |  |  |
| `recall.structural.content_weight` | number |  |  |
| `recall.structural.novelty_boost` | number |  |  |
| `recall.structural.recency_boost` | number |  |  |
| `recall.structural.saturation_decay` | number |  |  |
| `recall.structural.saturation_threshold` | integer |  | Recent-24h cue count that triggers saturation decay. |
| `recall.structural.source_refs_weight` | number |  |  |
| `recall.structural.summary_partial_weight` | number |  |  |
| `recall.structural.time_weight` | number |  |  |
| `updated_at` | string |  |  |

## Copilot

- **Alias:** `helix-copilot`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** record

A Copilot is a declarative, servable AG-UI copilot backend — a binder that composes one-or-more mounted Agents (each with its own Tools and optional MCPFederation) into a single servable ``/agui`` app. It carries only the copilot-level concerns that don't belong on any single Agent ``mounts`` (where agents serve), ``serving`` (the transport), ``tenant`` (inbound-tenant propagation), ``hitl`` (the approval card for gated write tools), ``knowledge`` (RAG collections + the vector store it may read), ``persistence`` (checkpoint/memory/cache/conversation storage backends), ``hosting`` (self-hosted vs a managed runtime), and ``frontend`` (console hints). Instructions and persona stay on the mounted Agent — a Copilot never re-declares them. One instance emits a servable backend (Agno today), the single evolution point DNA Cloud's copilots consume. Stored as ``copilots/<name>.yaml`` — marketplace-shareable as a bundle. Since ``spec-app-e-o-servico`` (2026-08-07) it also declares where it RUNS and what it is WORTH — ``runs_in`` is an OPTIONAL relation to the ``App`` whose service process serves it (execution, not composition — hence no ``inverse_of``; see the descriptor header), and ``value_per_outcome`` ({human_minutes, hourly_cost, currency}) is the declared worth of one successful outcome. That last one is the single number in the chain that cannot be measured — the manual path is timed by no telemetry — so it must come from someone who knows the business. It is the counterpart of ``App.can_sleep`` — the App declares the cost, the Copilot the yield.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `frontend` | object |  | Frontend console hints for the emitted copilot UI. |
| `frontend.console` | string |  | Which console renders the copilot (e.g. copilotkit). |
| `frontend.panels` | array |  | Named side panels the console mounts alongside the chat. |
| `frontend.suggested_prompts` | array |  | Starter prompts surfaced to the user in an empty console. |
| `hitl` | object |  | Human-in-the-loop approval surface for write tools the mounted agents gate. |
| `hitl.approval_card` | object |  | The card shown to the user when a gated tool pauses for approval. |
| `hitl.approval_card.details_from` | string |  | Path into the pending tool's args used to render the card body (e.g. args.text). |
| `hitl.approval_card.reason_from` | string |  | Path into the pending tool's args used to render the reason line (e.g. args.reason). |
| `hitl.approval_card.title` | string |  | Heading of the approval card. |
| `hosting` | object |  | Deployment/hosting model — beyond the self-hosted AG-UI app we already emit, the hosted (managed-service) variant. mode is a variant selector over ONE agent def (the same agent emits BOTH the per-user AG-UI app AND the single-identity hosted agent, which degrades — strips per-user OBO / per-user memory / HITL). Optional. Flows to the Terraform migration modules (f-copilot-infra-binding). |
| `hosting.env` | object |  | Non-secret config injected into the hosted container (arbitrary keys; secrets ride on refs, never here). |
| `hosting.image` | object |  | Container-image build hints for the hosted variant. |
| `hosting.image.base_image` | string \| null |  | Base image; null → framework default. |
| `hosting.image.port` | integer \| null |  | Serve port; null → framework default (8088 / 8123 / 7777). |
| `hosting.image.registry_hint` | string |  | Target registry — an OPEN set (known values acr \| ghcr \| ecr \| dockerhub). |
| `hosting.image.remote_build` | boolean |  | Build remotely (Foundry ACR remoteBuild) vs locally. |
| `hosting.mode` | string |  | Variant selector — self-hosted (the per-user AG-UI app) or hosted (a container image + manifest on a managed service). Um de: `self-hosted`, `hosted`. |
| `hosting.resources` | object |  | Compute request for the hosted variant (→ sandbox tier). |
| `hosting.resources.cpu` | string |  | CPU request (e.g. "0.5"). |
| `hosting.resources.memory` | string |  | Memory request (e.g. 1Gi). |
| `hosting.stores` | object |  | Managed stores the hosted target requires (langgraph-platform / agentos only — Foundry provisions its own). |
| `hosting.stores.postgres` | string |  | Postgres requirement (e.g. required). |
| `hosting.stores.redis` | string |  | Redis requirement (e.g. required). |
| `hosting.target` | string |  | The hosted runtime — foundry (MS-AF, true managed, first-class), langgraph-platform (SaaS / self-host), agentos (self-host only). Um de: `foundry`, `langgraph-platform`, `agentos`. |
| `interaction` | object |  | The INTERACTION MENU (F6.c of spec-copilot-f6-capacidades): presence-flips-capability blocks — declaring a block IS enabling it, every field has a safe default (the pattern measured in the voice_persona precedent: "{}" works). Only blocks a shipped renderer READS live here (the F4 data-honesty rule); voice landed WITH its renderer (dna-cloud#302 — the Realtime mint + WebRTC button read exactly these fields) and sandbox landed WITH its runtime (dna-cloud#319 — the skills executor merges exactly these numbers); cards still wait for theirs. HITL confirmation is NOT here — it already lives where it always did (the def's tools_requiring_confirmation). |
| `interaction.attachments` | object |  | What the chat input ACCEPTS. Presence of each sub-block enables that attachment family. |
| `interaction.attachments.image` | object |  |  |
| `interaction.attachments.image.max_per_turn` | integer |  |  |
| `interaction.attachments.spreadsheet` | object |  |  |
| `interaction.attachments.text` | object |  |  |
| `interaction.attachments.text.extensions` | array |  |  |
| `interaction.attachments.text.max_chars` | integer |  |  |
| `interaction.sandbox` | object |  | The SCRIPT-EXECUTION face — the limits the copilot's OWNER declares over the isolated machine that runs a skill's scripts (renderer-first rule satisfied by dna-cloud#319, which ships the executor that reads exactly these fields). Presence of this block does NOT turn execution on: the hosting layer does, by holding a sandbox provider's credential — no credential, no execution, and this block has nothing to limit. What the block DOES is lower the ceiling. Every number here is merged DOWNWARD against the host's own operational limits and never upward, which is the property that makes reading an instance safe at all: an instance may be authored by a tenant, and a tenant must not be able to buy more compute by writing YAML. Only what the shipped runtime READS lives here (the F4 rule) — the upload budget is a host constant with no instance reader, so it stays OUT, and declaring it is a validation error rather than a silent no-op. The provider credential never lives in the doc. |
| `interaction.sandbox.allow_internet` | boolean |  | Egress from the sandbox, and it travels downward like the numbers: false switches egress OFF for this copilot even where the host allows it, while true grants nothing the host has not already granted. An instance is never how the internet gets switched on — with egress off the sandbox cannot reach a public database endpoint either, which is half of why running someone's script is affordable. |
| `interaction.sandbox.budget` | object |  | The cost ceiling in the unit the runtime can actually ENFORCE — seconds, by the same reasoning the sibling voice budget used; a currency cap that only notifies is a notification, not a control. |
| `interaction.sandbox.budget.max_execute_seconds` | integer |  | Wall-clock ceiling for ONE command. The maximum is where "run a skill's script" stops and "run a job" starts; a request above it is refused here instead of being silently clamped later. |
| `interaction.sandbox.budget.max_session_seconds` | integer |  | How long the sandbox itself lives. The provider kills it on expiry, which is why this — and not a close() somewhere — is the cost ceiling that holds even when our code forgets. |
| `interaction.suggestions` | object |  | Chips above the chat input. |
| `interaction.suggestions.from_steps` | boolean |  | Derive one chip per wizard step ("fill step X for me") from the surface's declared steps. |
| `interaction.suggestions.static` | array |  |  |
| `interaction.suggestions.static[].message` | string | yes |  |
| `interaction.suggestions.static[].title` | string | yes |  |
| `interaction.voice` | object |  | The VOICE face (spec-interaction-voice; renderer-first rule satisfied by dna-cloud#302): presence of this block is what makes the copilot's voice button exist — no block, no mint, no cost. Only fields the shipped runtime READS (the reference persona shape carried fields nothing consumed — archetype, interruption_tolerance, wake_word — and they stay OUT by the F4 rule). The provider key never lives in the doc; the hosting layer wires it (a secret param, default empty = the face is invisible). |
| `interaction.voice.budget` | object |  | The per-session cost ceiling — the founder's control. Seconds because that is what the runtime can ENFORCE today (a USD cap that only notifies is a measured gap in the reference, not a control). |
| `interaction.voice.budget.max_session_seconds` | integer |  |  |
| `interaction.voice.identity_lock` | string |  | Authored identity assertion spoken-as-context (measured root cause in the reference implementation — a persona without an assertion leaks the vendor's own name). |
| `interaction.voice.style` | string |  | Prosody/tone hint APPENDED to the composed instructions — refinement, never a replacement. |
| `interaction.voice.voice` | string |  | Provider voice id (e.g. marin, cedar). Empty = provider default. |
| `knowledge` | object |  | RAG the copilot may read. Optional — a pure-action copilot declares none. |
| `knowledge.collections` | array |  | Names of the knowledge collections the copilot may query (refs — resolved by the emitter). |
| `knowledge.store` | object |  | WHERE the corpus is embedded + searched — the vector store. Lives inside knowledge so the corpus and its store stay cohesive. Optional; flows to the Terraform migration modules (f-copilot-infra-binding). |
| `knowledge.store.backend` | string \| null | yes | Vector backend — an OPEN set (known values pgvector \| mongo-atlas \| azure-ai-search \| qdrant \| pinecone \| null); emit when built. null = no store (framework default). |
| `knowledge.store.embed` | object |  | The embedding model and its output dimensionality. |
| `knowledge.store.embed.dims` | integer |  | Vector dimensionality (e.g. 1536). |
| `knowledge.store.embed.model` | string |  | Embedding model id (e.g. text-embedding-3-small). |
| `knowledge.store.ref` | string |  | Points at the vector-store infra resource (a Terraform module output — connection string/endpoint). May share the persistence ref (one physical Postgres). |
| `mcp_servers` | array |  | EXTRA MCP servers this copilot federates, with per-copilot tool TRANSFORMS (F6.a of spec-copilot-f6-capacidades). The transform vocabulary is fastmcp's own (ToolTransformConfig / ArgTransformConfig) adopted VERBATIM — rename a tool, rewrite its description, rename/hide arguments — because accuracy comes from the name/description the model READS, and the official shape is validated by fastmcp's Pydantic models at runtime (the schema here stays permissive on the transform block by design: the authority is the official vocabulary, not a hand-copied mirror of it). Credentials never live in the doc: `headers_env` names ENV VARS, the runtime resolves them at build. |
| `mcp_servers[].exclude_tags` | array |  |  |
| `mcp_servers[].headers_env` | object |  | Outbound header name → ENV VAR NAME holding the value (never the value itself): {"X-Api-Key": "CRM_KEY"}. |
| `mcp_servers[].include_tags` | array |  | Allowlist by tag (fastmcp enable(only=True)). |
| `mcp_servers[].name` | string | yes | The server key (also the default tool prefix namespace if the runtime applies one). |
| `mcp_servers[].tools` | object |  | The DE-PARA — original tool name → fastmcp ToolTransformConfig shape ({name, description, enabled, arguments: {old: {name, description, default, hide, required, examples}}}). Permissive here; validated by fastmcp Pydantic at runtime. |
| `mcp_servers[].transport` | string |  | Um de: `streamable_http`, `sse`. |
| `mcp_servers[].url` | string | yes | The MCP endpoint URL. |
| `mounts` | array | yes | The Agents this copilot serves, each at a mount path. At least one is required. |
| `mounts[].agent` | string | yes | Name of the mounted Agent (ref — resolved by the emitter to its base EmitContext). |
| `mounts[].id` | string | yes | Stable identifier for this mount within the copilot. |
| `mounts[].path` | string | yes | The route the mounted agent is served at (e.g. /agui). |
| `persistence` | object |  | Storage/state backends the emitted agent binds — checkpoint (thread/run state), long-term memory, and a LangGraph-only cache. Each slot is {backend, ref}; multiple slots may share one ref (one physical store — distinct tables/objects per framework). Optional — an in-memory copilot declares none. Flows to the Terraform migration modules (f-copilot-infra-binding), killing the hardcoded in-memory default. |
| `persistence.cache` | object |  | LangGraph-only node cache — null on the other targets (Agno / MS-AF have no first-class cache slot). |
| `persistence.cache.backend` | string \| null | yes | Storage backend — an OPEN set (known values postgres \| sqlite \| mongo \| redis \| inmemory \| cosmos \| serialize \| null); emit when built. null = no backend (framework default / in-memory). |
| `persistence.cache.ref` | string |  | Points at an infra resource (a Terraform module output — connection string/endpoint). Multiple slots may share one ref (one physical store). |
| `persistence.checkpoint` | object |  | Thread/run state — survives restart/resume (LangGraph PostgresSaver · Agno PostgresDb · MS-AF serialize-to-column). |
| `persistence.checkpoint.backend` | string \| null | yes | Storage backend — an OPEN set (known values postgres \| sqlite \| mongo \| redis \| inmemory \| cosmos \| serialize \| null); emit when built. null = no backend (framework default / in-memory). |
| `persistence.checkpoint.ref` | string |  | Points at an infra resource (a Terraform module output — connection string/endpoint). Multiple slots may share one ref (one physical store). |
| `persistence.conversation` | object |  | The CONVERSATION contract (spec-conversa-como-dado-do-dna) — WHO a thread belongs to, how its transcript is read back (AG-UI messages) and for how long it is kept. Read by ``dna.runtime.thread_store.resolve_conversation``; the port's transcript half is a READ PROJECTION over whatever the framework already checkpoints, so declaring this slot never makes a turn write twice. It does NOT duplicate ``checkpoint``: the checkpoint stays the framework's engine (replay + pending interrupts) and is keyed by thread id alone, so it can neither answer "list MY conversations" nor refuse a forged thread id. Absent slot = exactly today's behaviour (framework checkpoint only, no ownership, no retention). |
| `persistence.conversation.backend` | string \| null | yes | Storage backend for the thread INDEX (owner, title, counts, where the thread was born) — an OPEN set (known values postgres \| sqlite \| mongo \| redis \| inmemory \| cosmos \| serialize \| null). The transcript itself is NOT stored here; it is projected from the framework's own checkpoint. null = no backend (in-memory index). |
| `persistence.conversation.ref` | string |  | Points at an infra resource (a Terraform module output — connection string/endpoint). Usually the SAME ref as checkpoint — one physical store, distinct tables. |
| `persistence.conversation.retention` | object |  | How long a conversation is KEPT. It rides on this slot because a transcript is user data (volume, PII, a short natural life) while the sibling slots hold the framework's engine and the workspace's curated memory — one retention rule over both would either keep too much or delete the wrong thing. DNA carries the number to whoever holds the connection; it does not run the purge for you (no scheduler ships with the port). Absent = keep indefinitely. |
| `persistence.conversation.retention.max_age_days` | integer |  | Conversations untouched for longer than this are expired. ``dna.runtime.thread_store.retention_cutoff`` is the shared computation, so two hosts cannot read "30 days" two different ways. |
| `persistence.memory` | object |  | Cross-session long-term memory (LangGraph PostgresStore · Agno enable_user_memories · MS-AF mem0 / VectorStore). |
| `persistence.memory.backend` | string \| null | yes | Storage backend — an OPEN set (known values postgres \| sqlite \| mongo \| redis \| inmemory \| cosmos \| serialize \| null); emit when built. null = no backend (framework default / in-memory). |
| `persistence.memory.ref` | string |  | Points at an infra resource (a Terraform module output — connection string/endpoint). Multiple slots may share one ref (one physical store). |
| `policies` | object |  | GOVERNANCE the copilot's OWNER declares (spec-quota-como-politica, dna-cloud 05/08/2026) — distinct from the house's billing: quotas here cap USE of this copilot, whoever pays. Enforcement lives in the serving runtime (the kernel validates shape only): a run that would exceed a declared quota is refused BEFORE the model runs, with the refusal naming the cap. Absent block = no caps. |
| `policies.quotas` | object |  |  |
| `policies.quotas.per_user` | boolean |  | When true, each quota applies PER USER (per verified oid) instead of per copilot — "cada usuário tem N turnos", not "o copiloto todo tem N". |
| `policies.quotas.tokens_per_day` | integer |  | Max model tokens (input+output) per UTC day, across every user of this copilot. |
| `policies.quotas.turns_per_month` | integer |  | Max turns (user messages answered) per calendar month, across every user of this copilot. |
| `runs_in` | string |  | The App whose SERVICE PROCESS serves this copilot, by instance name — the outgoing end of `Solution → App → Copilot`, which until now terminated here. The reference is validated on write (`spec.relations`), so a picker comes for free. OPTIONAL, and measured so: 7 live Copilots against 2 Apps, five of them in no App at all and serving. Absent is therefore not an error, it is an ORPHAN — a copilot whose running process is undeclared — and the count of orphans is what a derived guard reports. This field declares EXECUTION, never composition: `App.copilots` says which copilots are sold and navigated under one identity, and one process legitimately serves copilots belonging to several such identities. That is why it declares no `inverse_of` — see the header. |
| `serving` | object | yes | How the copilot backend is served. |
| `serving.framework` | string |  | The self-hosted serving framework the dna.runtime port builds on; distinct from hosting.target which selects a MANAGED host (foundry/langgraph-platform/agentos). Um de: `langchain`, `maf`, `agno`, `deepagents`. |
| `serving.transport` | string | yes | Wire protocol the copilot backend speaks. Only ag-ui (AG-UI protocol) today. Um de: `ag-ui`. |
| `surfaces` | array |  | The co-edited CANVAS SURFACES this copilot serves (F2 of adr-copiloto-como-dado, dna-cloud) — the archetype measured three times (spikes spike-arquetipo-*) and written once as a runtime (dna-cloud `flow/` + `lib/flow/`): a screen whose form the copilot manipulates through ONE validate-and-echo tool, a projection middleware, a per-thread scope gate and a shared state canvas. Each entry is that machine's configuration as data; the runtime resolves these over its built-in registry, so a workspace can TUNE a surface (its guidance template, its blocked persist tools) without a deploy. DATA-HONESTY BOUNDARY (the nine-sections lesson): entries declare ONLY what the runtime consumes today. Wizard steps, gates, invalidation rules and knowledge slots — the concepts the three measured worlds contributed — enter WHEN the generic renderer that reads them ships (recorded in the ADR as roadmap). A field nobody reads is a form without wires. |
| `surfaces[].blocked_persist_tools` | array |  | Durable-write tools REMOVED from the model's list in a thread of this surface (i-061 — "save" must not bypass the draft door). Tenant-tunable via overlay. |
| `surfaces[].canvas_keys` | array | yes | EVERY state key this surface projects/rehydrates. The console's rehydration allowlist derives from this — a key absent here does not survive a conversation reload. |
| `surfaces[].description` | string \| null |  | What this surface is for — shown wherever surfaces are listed. |
| `surfaces[].guidance_template` | string \| null |  | The PromptTemplate name whose body steers the model toward this surface's tool (directed guidance). The template is the voice-as-data catalog; this names the entry. |
| `surfaces[].kind` | string \| null |  | The target Kind whose instances this surface composes (the wizard derives its fields from this Kind's schema; the review step writes an instance of it). Null for surfaces not bound to one Kind (the memory composer). |
| `surfaces[].name` | string | yes | The surface's identity (matches the runtime's built-in registry key when overriding one). |
| `surfaces[].state_key` | string | yes | The graph-state key that MARKS a thread of this surface (the gate decides by STATE, never by route) and anchors canvas rehydration. Must appear in `canvas_keys`. |
| `surfaces[].steps` | array |  | The surface's WIZARD, declared (F4 of adr-copiloto-como-dado — the visible half). Each step names which of the target Kind's fields it collects; the portal's generic renderer turns this into a stepped screen (stepper + typed inputs derived from the Kind schema + per-field AI affordances + the copilot dock). The concepts came measured from the archetype spikes: linear steps (all three worlds), and a human gate per step (the approved-by-user flag pattern). Conditional steps and invalidation rules remain roadmap — declared here only when the renderer reads them. |
| `surfaces[].steps[].description` | string \| null |  | One sentence under the title. |
| `surfaces[].steps[].fields` | array |  | Which of the target Kind's schema properties this step collects, in render order. A name the Kind does not declare is IGNORED by the renderer (fail-soft) — the Kind is the authority. |
| `surfaces[].steps[].gate` | boolean |  | A HUMAN checkpoint — the wizard only advances past this step by explicit user action (the measured approved-by-user flag, as a flag). |
| `surfaces[].steps[].id` | string | yes | Stable step identity (snake-case). |
| `surfaces[].steps[].title` | string | yes | The step's human title, as rendered. |
| `surfaces[].tool_name` | string | yes | The surface's single validate-and-echo tool — the model's ONLY door into the shared canvas. The tool itself is code (its argument schema is the surface's contract); this names it. |
| `tenant` | object |  | Inbound-tenant handling. When propagate is true, the emitted serving layer derives tenant/oid from request headers into run-state for the mounted tools to read. |
| `tenant.propagate` | boolean |  | Derive tenant from inbound request headers into run-state (default false). |
| `value_per_outcome` | object |  | What ONE successful outcome of this copilot is worth — the reference value used to turn turns into ROI. ⭐ This is the only number in the whole chain that CANNOT be measured: the cost side is exact (tokens are metered, `App.can_sleep` prices the replica) and the turn count is exact, but what a human WOULD have spent doing this by hand exists nowhere in any telemetry. It has to be DECLARED, by someone who knows the business — and without it there is counting, never ROI. Optional for that reason, and absent means exactly "nobody has stated what an outcome is worth", which is a finding rather than a zero: presuming zero would render every copilot in the fleet as pure cost. |
| `value_per_outcome.currency` | string |  | The ISO-4217 code `hourly_cost` is stated in (e.g. USD, BRL). Declared and never defaulted - a rate whose currency is assumed is a rate that is wrong by a factor of five in the first fleet that mixes two. |
| `value_per_outcome.hourly_cost` | number |  | The fully loaded hourly cost of that human, in `currency`. Kept apart from `human_minutes` on purpose - the duration is a fact about the WORK and the rate is a fact about the ORGANISATION, they change for unrelated reasons, and a single pre-multiplied "value" field would make it impossible to say which of the two moved. |
| `value_per_outcome.human_minutes` | number |  | How long the same outcome takes a human, in minutes. The DECLARED estimate of whoever knows the work, never a measurement — no clock in this system times the manual path, which is the whole reason this object exists. |
| `workflow` | object |  | Optional multi-step workflow — agent-framework (MS Agent Framework) target only. When present the emitter emits a WorkflowBuilder chain of the named steps plus a workflow-level human-approval escalation node; absent, a plain single-agent app is emitted. A per-target advanced option (YAGNI for the core). |
| `workflow.chain` | array |  | Ordered workflow step ids. Each becomes a chained agent-executor; the AG-UI adapter surfaces the id as the UI step name. |

## Doc

- **Alias:** `dna-doc`
- **apiVersion:** `github.com/ruinosus/dna/doc/v1`
- **Plane:** record

A Doc is one page of in-product documentation. The marker is ``docs/<name>/DOC.md`` — YAML frontmatter (icon, subtitle, summary, order, locale, enabled, kind_of, category, tags) plus a markdown body that lands in ``spec.body``. The page title is ``metadata.description``. ``kind_of`` follows Diátaxis (tutorial/how_to/reference/explanation); ``category`` groups the sidebar; ``locale`` lets one corpus serve multiple languages. This is the Kind behind ``dna docs list/show``.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string | yes | Markdown body of the page — the DOC.md content below the frontmatter. |
| `category` | string \| null |  | Free-form sidebar grouping (e.g. "Getting started"). Null falls back to a flat list. |
| `enabled` | boolean |  | If false, the page is hidden from listings. |
| `icon` | string |  | Emoji or short string shown next to the title. |
| `kind_of` | enum |  | Diátaxis classification (learning- / task- / information- / understanding-oriented). Null = uncategorized. Um de: `tutorial`, `how_to`, `reference`, `explanation`, `None`. |
| `locale` | string |  | Content locale (e.g. pt-BR, en). ``dna docs`` filters on it. |
| `order` | integer |  | Sort order in the sidebar (ascending). |
| `subtitle` | string |  | One-line subtitle shown under the title. |
| `summary` | string |  | 1-2 sentences for the topic header card / previews. |
| `tags` | array |  | Free-form labels for filtering and search. |

## Engram

- **Alias:** `helix-engram`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** record

An Engram is an affective recall artifact (record plane) — the memory co-pillar's rich, bi-temporal engram. It surfaces unbidden when the current cycle resembles a past one in the same ``area``, carries an evocative ``affect`` (triumph/regret/surprise/wistful/ominous), and is scored by Ebbinghaus-style decay (``relevance_decay_seed``, ``surface_count``, ``confidence_score``) plus Semon-inspired ecphory (``cues_history``, ``homophonic_links``). Bi-temporal — a superseded Engram is invalidated via ``valid_to``/``superseded_by_memory``, never hard-deleted. Renamed from LessonLearned (s-engram-rename, 2026-07-19) — memory is a platform primitive (``github.com/ruinosus/dna/v1``), not sdlc-owned. Authored by the Sage oracle during the deep-sleep ritual (mostly) or manually; written/recalled via ``dna.memory.remember`` / ``recall``. Stored as ``lessons-learned/<name>.yaml`` with body prose in the ``LESSON_LEARNED.md`` bundle marker — storage container/marker names are unchanged by the rename.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `affect` | string | yes | Emotional tone. The five the runtime weights out of the box are `triumph`, `regret`, `surprise`, `wistful` and `ominous` — an affect-tagged memory RESISTS forgetting, and each of those has a measured multiplier in `dna.memory.decay`. ⭐ OPEN ON PURPOSE, in lockstep with `memory_type` (2026-08-03). A closed palette makes the emotional vocabulary of the DOMAIN a constant of the CODE: a workspace whose work has `urgent`, `contested` or `relief` should be able to say so on the day it decides that, and to give that tone a weight through `CognitivePolicy.affect`. ⚠️ The consequence to accept: an unrecognised tone gets the NEUTRAL multiplier (1.0) until a policy assigns one. It is honoured — never dropped — but it does not resist forgetting more than an untagged memory would. Inventing a weight for a name nobody defined would be the system deciding how much a feeling matters. |
| `affect_evidence_refs` | array |  | Concrete refs (rem-X, verdict-Y, Story/s-Z) that back the affect choice. Required for high-stakes affects so the LLM's claim is auditable against actual artifacts in the manifest. |
| `affect_reason` | string |  | Story s-remembrance-affect-reason-required. Concrete justification for the chosen affect — names specific slugs/SHAs/AC counts/state. NOT generic ('Story closed', 'shipped successfully'). Validator rejects writes that lack reason OR have boilerplate. Required for high-stakes affects (regret/ominous/surprise); optional for triumph/wistful but encouraged. |
| `area` | string | yes | Scoped target: Feature/X, Epic/Y, or Roadmap/Z. The LessonLearned surfaces when this area is touched. |
| `claims` | array |  | Structured assertions this memory makes, so two memories can be compared for CONTRADICTION deterministically (s-grafo-2-contradicao). Prose cannot be compared: "the Kind still needs approval" and "the Kind was approved" share almost no vocabulary, which is why lexical overlap (`dna.memory.merge`) finds repetition and never disagreement. Each claim is `(subject, predicate, object)` over the memory's bi-temporal window. Two claims CONTRADICT when they agree on subject and predicate, disagree on object, and their `[valid_from, valid_to)` windows share an instant — TOKI (arXiv:2606.06240 §2.1), nine of Allen's thirteen base relations. `polarity: denies` states an explicit negation, so "not approved" is comparable instead of being prose. `subject` is optional and defaults to the memory's own `Kind/name` referent (`area`, else the first such `source_refs` entry) — a memory already scoped to `KindDefinition/livro` need only declare `{predicate: approval, object: pending}`. ⚠️ A predicate is treated as SINGLE-VALUED at an instant (the functional-dependency rule). That is what makes detection decidable without an ontology — cardinality declarations are degrau 3 of `f-poder-de-grafo`, a founder gate. Use distinct predicates for genuinely multi-valued attributes, or the pass will present them as a conflict for a human to dismiss. It only ever PRESENTS: nothing here overwrites, expires or merges a memory. **When to declare one — the test is SUBSTITUTION, not importance.** Declare a claim when a LATER value of the same `(subject, predicate)` would make this one FALSE. Nothing else; a memory with no claims is the normal case, not a lapse. "the workspace plan is Pro" and "Barna is in Lisbon this week" qualify — a plan replaces the plan, and there is one whereabouts at a time. "Barna likes tea" does NOT: liking tea does not stop him liking coffee, and values that ACCUMULATE never contradict. "met the client on 2026-08-03" does NOT either: an event HAPPENED, and a later meeting does not un-happen it — events and observations belong in `summary` alone. Claiming those two makes the pass report the normal as a conflict, and a pass that flags the normal trains its reader to ignore it, including the time it is right. This is the same rule the verb's faces announce (`dna.memory.contradiction.WHEN_TO_CLAIM`), restated for the OTHER door — a raw `write_instance` on an Engram, which reads this schema and never sees a tool description. |
| `claims[].object` | string \| number \| boolean \| null |  | The asserted value. Absent/null = an EXISTENCE claim, which compares only against another existence claim of opposite polarity. |
| `claims[].polarity` | string |  | `denies` negates: `asserts X` beside `denies X` is a contradiction; beside `denies Y` it is not. Um de: `asserts`, `denies`. |
| `claims[].predicate` | string | yes | The attribute being asserted (`approval`, `status`, `owner`). |
| `claims[].subject` | string |  | What the claim is about — normally `Kind/name`. Defaults to the memory's own referent. |
| `claims[].valid_from` | string |  | Narrows the claim's world-time window; defaults to the memory's `valid_from`. |
| `claims[].valid_to` | string |  | Narrows the claim's world-time window; defaults to the memory's `valid_to`. |
| `confidence_score` | number |  | Semon engram intensity. Multiplies the recall score. Bumps when homophonic LessonsLearned (same area) are filed — engrams reinforce each other. Decays with surface_count for hygiene. |
| `cues_history` | array |  | Semon ecforia trace. Each time the LessonLearned is surfaced via remember(), the cue (query + actor + timestamp) is appended. History of WHY this memory kept getting recalled. |
| `cues_history[].actor` | string |  |  |
| `cues_history[].at` | string |  |  |
| `cues_history[].cue` | string |  |  |
| `encoding_context` | object |  | Snapshot of the conditions at engraphy. semon-recaller scores ecphory candidates by partial-match against this dict. |
| `encoding_context.affect` | string |  |  |
| `encoding_context.area` | string |  |  |
| `encoding_context.co_topics` | array |  | Last 3-5 topic tags active at engraphy. |
| `encoding_context.day_of_week` | string |  |  |
| `encoding_context.engraphed_by` | string |  | Agent slug that decided to engraph (semon-scribe by default). |
| `encoding_context.source_refs` | array |  |  |
| `encoding_context.time_of_day` | string |  | morning\|afternoon\|evening\|night — coarse temporal cue. |
| `homophonic_links` | array |  | Semon homophony — engrams sharing substrate features. Each link records target + resonance score + basis. semon-recaller propagates a small strength boost (+0.02) to neighbors on ecphory (resonance). |
| `homophonic_links[].basis` | string |  | co-area \| co-affect \| co-temporal \| semantic \| manual |
| `homophonic_links[].resonance_score` | number |  |  |
| `homophonic_links[].target_name` | string | yes |  |
| `last_surfaced` | string |  | Auto-stamped on each surfacing; null until first surface. |
| `memory_type` | string |  | What KIND of memory this is. The three CoALA names are the ones the runtime treats specially — `episodic` (what happened), `semantic` (a generalized fact), `procedural` (how to act; the runtime presents it to the model as a RULE to follow, not as an anecdote to consider). ⭐ OPEN ON PURPOSE, and this was a deliberate reversal. It was a closed enum of exactly those three, and a closed enum makes the vocabulary of the DOMAIN a constant of the CODE — which is the one thing this whole system exists to avoid. A workspace whose work has `preference`, `constraint` or `commitment` should be able to say so on the day it decides that, not on the day someone remembers to edit a schema. The runtime honours the distinction WITHOUT knowing the name: an unrecognised type is presented to the model under its own name, because the name IS the information — `[preference]` tells a model more than `[fact]`, and far more than being dropped. ⚠️ The consequence to accept: an unrecognised type gets no special treatment. Only `procedural` is imperative. A workspace that invents `regra_dura` gets `[regra_dura]`, not the RULE framing — because promoting an unknown name to an obligation would put words in the agent's mouth that nobody wrote. Absent = untyped (legacy). |
| `owner` | string |  | ATTRIBUTION: which agent authored this memory (e.g. claude-code, jarvis). Orthogonal to scope + to tenant (tenant separates USERS, owner separates AGENTS). Recall AUDIENCE is governed by `visibility`, NOT by owner (s-agent-memory-phase-0-bridge, 2026-06-02 — supersedes the 2026-05-17 owner-implies-private semantics). When absent: an unowned/project lesson (shared). |
| `relevance_decay_seed` | number |  | Multiplicative decay factor applied per 24h. Default 0.95 (~30% relevance after 14 days). |
| `revisions` | array |  | Reconsolidation log (Nader 2000 / neo-Semon). Append-only when a recall reawakens the engram and the consumer updates the summary. |
| `revisions[].at` | string |  |  |
| `revisions[].by` | string |  |  |
| `revisions[].delta` | string |  |  |
| `source_refs` | array | yes | Pointers to source artifacts (Narrative/X, WorkflowEvent/Y, etc.) that this memory derives from. |
| `summary` | string | yes | 1-2 sentence 'Lembre-se de...' — the recalled essence. |
| `superseded_by_memory` | string |  | Name of the memory that invalidated this one (not `superseded_by` — that's an ADR dep_filter token). Pairs with valid_to for point-in-time audit. |
| `surface_count` | integer |  | Increments on each surface. Damps re-surfacing via the recall scoring formula (dna/memory/decay.py). |
| `surface_when` | array | yes | Triggers that surface this memory unbidden. The four the SDLC engines know are `feature_touched`, `cycle_open`, `session_start` and `oracle_consult`. ⭐ OPEN ON PURPOSE (2026-08-03), and this one was BLOCKING a feature, not merely constraining it. The four names are all SDLC events — nothing in that list honestly describes a memory learned from a CONVERSATION, and a memory extracted from chat was refused at write time with a schema error. The vocabulary of triggers belongs to whoever runs the agent, not to the extension that first needed four of them. ⚠️ The consequence to accept: a trigger no engine knows never fires on its own. It is recorded and honoured as data — and proactive recall finds the memory by RELEVANCE regardless — but nothing will surface it because of that name until something is taught to look for it. |
| `tags` | array |  |  |
| `valid_from` | string |  | World-time validity start (Zep bi-temporal). Default: created_at. |
| `valid_to` | string |  | World-time validity end. Set when superseded/contradicted — the memory is INVALIDATED, never hard-deleted. Default recall excludes valid_to<now. |
| `visibility` | string |  | Recall audience (the customization axis): shared = all agents in scope recall it (cross-agent knowledge, default); private = only `owner` recalls it (an agent's raw working memory); pinned = always injected into working memory at bootstrap, bypassing recall scoring (the Letta 'memory block'); archived = retained + auditable but excluded from default recall (soft-forget). Humans audit ALL regardless of visibility (audit != recall). Phase 0 (2026-06-02). Um de: `shared`, `private`, `pinned`, `archived`. |

## Epic

- **Alias:** `sdlc-epic`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

An Epic groups Features under a single business goal (Jira/ADO terminology). May optionally carry a target_date + target_package + target_version when the Epic is also a dated release; otherwise it's a pure aggregation umbrella. status moves through planning → in-progress → done.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `business_value` | number |  |  |
| `cancelled_reason` | string |  |  |
| `closed_at` | string |  |  |
| `created_at` | string |  |  |
| `definition_of_done` | array |  |  |
| `description` | string |  |  |
| `features` | array |  |  |
| `journey_phase` | string |  | Universal journey phase (discover → specify → plan → build → reflect). Additive layer over Story/Feature/Epic status, Spec phase, etc. Lets the journey ledger pin this doc to one of five universal phases compatible with Superpowers / BMAD / Spec Kit / Kiro. Um de: `discover`, `specify`, `plan`, `build`, `verify`, `reflect`. |
| `labels` | array |  |  |
| `priority` | string |  | Um de: `highest`, `high`, `medium`, `low`, `lowest`. |
| `produces` | array |  | Artifacts this work item produced — any Kind (hub). |
| `produces[].at` | string |  |  |
| `produces[].kind` | string | yes | Artifact Kind (any). |
| `produces[].name` | string | yes | Artifact doc name. |
| `produces[].role` | string |  | Optional role hint (e.g. visual-spec, plan, investigation). |
| `reporter` | string |  |  |
| `status` | string | yes | Um de: `planning`, `in-progress`, `done`, `cancelled`, `deprecated`. |
| `target_date` | string |  |  |
| `target_package` | string |  | owner/name reference to a Genome |
| `target_version` | string |  | Semver to match Genome.spec.version when done |
| `timeline` | array |  | Append-only activity log. Auto-stamped by the CLI on every status flip / groom / artifact write; populated by AgentSession capture for decision + artifact_produced events. Render in Studio as activity stream. |
| `timeline[].actor` | string | yes | Who triggered the event (Actor name or 'claude-code'). |
| `timeline[].at` | string | yes |  |
| `timeline[].commit_ref` | string |  | Git SHA associated with this event (when relevant). |
| `timeline[].excerpt` | string |  | decision: snippet from the source transcript. |
| `timeline[].fields` | object |  | groom: which fields changed and to what. |
| `timeline[].from` | string |  | status_change: previous status. |
| `timeline[].paths` | array |  | artifact_produced: file paths touched. |
| `timeline[].session_ref` | string |  | Back-link to a AgentSession that produced this event. |
| `timeline[].source` | string |  | Um de: `cli`, `studio`, `mcp`, `agent-session-extracted`, `system`. |
| `timeline[].summary` | string |  | comment/decision: short human-readable text. |
| `timeline[].to` | string |  | status_change: new status. |
| `timeline[].type` | string | yes | Event type. Recognized: status_change, groom, comment, decision, artifact_produced (open vocabulary — new types are additive, e.g. pr_opened). |
| `title` | string |  | Human-readable display name (Jira 'summary'). Falls back to description, then to metadata.name slug. |
| `updated_at` | string |  |  |
| `watchers` | array |  |  |

## EvalBaseline

- **Alias:** `eval-eval-baseline`
- **apiVersion:** `github.com/ruinosus/dna/eval/v1`
- **Plane:** record

An EvalBaseline pins one EvalRun as the "known good" reference for an EvalSuite. `dna eval run <suite> --baseline <name>` compares the fresh run against the pinned run and reports regressions (passed → now failing), improvements and unchanged cases — with an exit code a user's CI can gate on. Pin with `dna eval pin <run>`.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `label` | string |  | Human note on why this run is the reference. |
| `pinned_at` | string |  |  |
| `run_name` | string | yes | Name of the pinned EvalRun instance. |
| `suite` | string | yes | Name of the EvalSuite this baseline belongs to. |

## EvalCase

- **Alias:** `eval-eval-case`
- **apiVersion:** `github.com/ruinosus/dna/eval/v1`
- **Plane:** record

An EvalCase is one declarative evaluation scenario. It names a target (default = the kernel's own prompt composition via build_prompt, deterministic and offline; custom targets such as a live LLM are host-registered EvalTargetPorts) and a list of deterministic checks (contains/regex/equals/length) applied to the text the target produced. Grouped by an EvalSuite; executed by the local runner (`dna eval run`), which persists an EvalRun.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `checks` | array | yes | Deterministic assertions applied to the text the target produced. ALL checks must pass for the case to pass. |
| `checks[].case_sensitive` | boolean |  | For contains/not_contains/equals. Default true. |
| `checks[].type` | string | yes | Um de: `contains`, `not_contains`, `regex`, `not_regex`, `equals`, `min_length`, `max_length`. |
| `checks[].value` | string \| integer |  | The needle/pattern (string checks) or the length bound (min_length/max_length). |
| `description` | string |  | What this case verifies (one line). |
| `expected` | string |  | Human-readable note of the expected outcome (shown in reports; not machine-checked). |
| `input` | string |  | Free-form input for custom targets (e.g. the user message an LLM target sends). The prompt target ignores it. |
| `skip` | boolean |  | Declared but not executed (reported as skipped). |
| `skip_reason` | string |  |  |
| `tags` | array |  |  |
| `target` | object |  | What to evaluate. Omitted → the suite's target → {type = prompt}. type=prompt composes the agent's system prompt via build_prompt (deterministic, offline); any other type must be registered by the host as an EvalTargetPort. |
| `target.agent` | string |  | Agent name for the prompt target (omitted → the scope's default agent). |
| `target.scope` | string |  | Scope override for the prompt target (omitted → the scope the suite runs in). |
| `target.type` | string |  | Target type. 'prompt' is built in; custom types are host-registered EvalTargetPorts. |

## EvalRun

- **Alias:** `eval-eval-run`
- **apiVersion:** `github.com/ruinosus/dna/eval/v1`
- **Plane:** record

An EvalRun is the persisted result of one local execution of an EvalSuite — pass/fail/error/skip counts, timestamps, the resolved target, and per-case results with the outcome of every declared check. Written by `dna eval run --save`; compared against a pinned EvalBaseline to detect regressions (`dna eval run --baseline`).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `errored` | integer |  |  |
| `failed` | integer | yes |  |
| `finished_at` | string |  |  |
| `passed` | integer | yes |  |
| `results` | array | yes | Per-case outcomes, in execution order. |
| `results[].case` | string | yes |  |
| `results[].checks` | array |  | Outcome of each declared check. |
| `results[].checks[].detail` | string |  | Why the check failed (or the error). |
| `results[].checks[].passed` | boolean | yes |  |
| `results[].checks[].type` | string | yes |  |
| `results[].checks[].value` | string \| integer |  |  |
| `results[].error` | string |  | Error message when status=error (unknown target type, target raised, case not found). |
| `results[].output_excerpt` | string |  | First chars of the text the target produced (evidence for humans reading the run). |
| `results[].status` | string | yes | Um de: `passed`, `failed`, `error`, `skipped`. |
| `results[].target_type` | string |  | Resolved target type this case ran against. |
| `skipped` | integer |  |  |
| `started_at` | string |  |  |
| `suite` | string | yes | Name of the EvalSuite that was executed. |
| `target` | object |  | The suite-level target the run resolved (per-case overrides are recorded on each result row). |
| `total` | integer | yes |  |

## EvalSuite

- **Alias:** `eval-eval-suite`
- **apiVersion:** `github.com/ruinosus/dna/eval/v1`
- **Plane:** record

An EvalSuite groups EvalCase instances and configures how the local runner executes them — the case list (empty = all cases in the scope), a default target the cases inherit, and stop_on_fail. Run it with `dna eval run <suite>`; each execution can be persisted as an EvalRun and compared against a pinned EvalBaseline.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `cases` | array |  | EvalCase names to run, in order. Empty/omitted = every EvalCase in the scope. |
| `description` | string |  | What this suite evaluates (one line). |
| `labels` | array |  |  |
| `stop_on_fail` | boolean |  | Stop executing remaining cases after the first failed/errored case. Default false. |
| `target` | object |  | Default target for cases that do not declare their own (same shape as EvalCase.target). |
| `target.agent` | string |  |  |
| `target.scope` | string |  |  |
| `target.type` | string |  |  |

## Evidence

- **Alias:** `evidence-evidence`
- **apiVersion:** `github.com/ruinosus/dna/evidence/v1`
- **Plane:** record

An Evidence instance is an immutable audit event record. Captures the event type, SHA-256 hash of the referenced content, timestamp, author, and optional snapshot. Used by the GAIA report pipeline to provide a verifiable audit trail.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `author` | string |  |  |
| `captured_at` | string |  |  |
| `created_at` | string |  |  |
| `document_ref` | string |  | `Kind:name` of the instance whose save triggered this event — the canonical Kind name and the instance name, colon-joined. MEASURED, not inferred — the one runtime producer is the kernel evidence `post_save` handler (`dna/kernel/write/evidence.py`), which writes `f"{kind}:{name}"` straight from the HookContext, and the deleted TypeScript twin wrote the identical form (its test asserted `EvalRun:run1`). The slash-shaped values in some Python test fixtures (`Story/s-x`, `eval-evalrun/my-run`) and the older builder docstring are inert inputs to a pass-through parameter and are NOT the format. Nothing dereferences it today. Declared as a relation with `to: '*'` rather than with a named target: a named one resolves a bare instance NAME, and this is the same composite as `Comment.target_ref` — it needs parsing, not a lookup. Absent on the gaia event shape, which carries source_kind/source_name instead. |
| `event_type` | string | yes | Um de: `document_created`, `document_modified`, `document_deleted`, `eval_run_completed`, `baseline_pinned`, `finding_created`, `finding_status_changed`, `custom`, `gaia.assessment.started`, `gaia.assessment.completed`, `gaia.assessment.failed`, `gaia.pillar.completed`, `gaia.pillar.threshold_breach`, `gaia.report.issued`. |
| `notes` | string |  |  |
| `payload` | object |  |  |
| `sha256` | string |  |  |
| `snapshot` | object |  |  |
| `source_kind` | string |  |  |
| `source_name` | string |  |  |
| `suite` | string |  |  |

## Feature

- **Alias:** `sdlc-feature`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Feature is a shippable unit. It implements one or more UseCases, decomposes into Stories, and is owned by an Actor. Its status reflects the development pipeline: discovery → in-development → done.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `acceptance_criteria` | array |  | Feature-level AC (parent of Story-level AC). |
| `as_a` | string |  | Role: 'As a <role>'. INVEST/user-story format slot. |
| `blocked_reason` | string |  |  |
| `business_value` | number |  |  |
| `closed_at` | string |  |  |
| `created_at` | string |  |  |
| `definition_of_done` | array |  |  |
| `description` | string | yes |  |
| `epic` | string |  | Parent Epic name |
| `estimate` | string |  | T-shirt size or story points (free-form) |
| `i_want` | string |  | Goal: 'I want <goal>'. INVEST/user-story format slot. |
| `journey_phase` | string |  | Universal journey phase (discover → specify → plan → build → reflect). Additive layer over Story/Feature/Epic status, Spec phase, etc. Lets the journey ledger pin this doc to one of five universal phases compatible with Superpowers / BMAD / Spec Kit / Kiro. Um de: `discover`, `specify`, `plan`, `build`, `verify`, `reflect`. |
| `labels` | array |  |  |
| `mockups` | array |  |  |
| `narrative_line` | string |  | One-sentence agent-curated prose summary of what this Feature has been DOING (past-tense, semantic) — shown next to the Feature in Studio's narrative swimlane. Updated by the working agent as scope evolves. Distinct from `description` (intent / problem statement, written once at file-time). |
| `owner` | string |  | Actor name |
| `priority` | string |  | Um de: `highest`, `high`, `medium`, `low`, `lowest`. |
| `produces` | array |  | Artifacts this work item produced — any Kind (hub). |
| `produces[].at` | string |  |  |
| `produces[].kind` | string | yes | Artifact Kind (any). |
| `produces[].name` | string | yes | Artifact doc name. |
| `produces[].role` | string |  | Optional role hint (e.g. visual-spec, plan, investigation). |
| `release_target` | string |  |  |
| `reporter` | string |  |  |
| `so_that` | string |  | Benefit: 'so that <benefit>'. INVEST/user-story format slot. |
| `sprint_ref` | string |  | The Sprint this Feature is committed to — the Sprint instance's NAME, which is also its sprint_id (e.g. '2026-Q2-S2'). |
| `status` | string | yes | Um de: `discovery`, `in-development`, `done`, `cancelled`, `blocked`. |
| `stories` | array |  |  |
| `time_tracking` | object |  |  |
| `time_tracking.logged_h` | number |  |  |
| `time_tracking.original_estimate_h` | number |  |  |
| `time_tracking.remaining_h` | number |  |  |
| `timeline` | array |  | Append-only activity log. Auto-stamped by the CLI on every status flip / groom / artifact write; populated by AgentSession capture for decision + artifact_produced events. Render in Studio as activity stream. |
| `timeline[].actor` | string | yes | Who triggered the event (Actor name or 'claude-code'). |
| `timeline[].at` | string | yes |  |
| `timeline[].commit_ref` | string |  | Git SHA associated with this event (when relevant). |
| `timeline[].excerpt` | string |  | decision: snippet from the source transcript. |
| `timeline[].fields` | object |  | groom: which fields changed and to what. |
| `timeline[].from` | string |  | status_change: previous status. |
| `timeline[].paths` | array |  | artifact_produced: file paths touched. |
| `timeline[].session_ref` | string |  | Back-link to a AgentSession that produced this event. |
| `timeline[].source` | string |  | Um de: `cli`, `studio`, `mcp`, `agent-session-extracted`, `system`. |
| `timeline[].summary` | string |  | comment/decision: short human-readable text. |
| `timeline[].to` | string |  | status_change: new status. |
| `timeline[].type` | string | yes | Event type. Recognized: status_change, groom, comment, decision, artifact_produced (open vocabulary — new types are additive, e.g. pr_opened). |
| `title` | string |  | Human-readable display name (Jira 'summary'). |
| `updated_at` | string |  |  |
| `use_cases` | array |  |  |
| `watchers` | array |  |  |

## HtmlArtifact

- **Alias:** `sdlc-html-artifact`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

An HtmlArtifact stores an HTML page as a first-class, linkable output of a work item (Story/Feature/Epic/Spike). It is a bundle: ARTIFACT.html holds the raw HTML verbatim (byte-faithful round-trip) plus an optional artifact.json companion with structured metadata (title, description, source, created_at) — the same shape as a Soul's SOUL.md + soul.json. Attach one to a work item with ``dna sdlc produces add <WiKind>/<wi> HtmlArtifact/<name>`` so a design doc, roteiro, or report that used to live in chat becomes traceable on the board.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `artifact_json` | object |  | Structured metadata: title, description, source, created_at. |
| `html` | string |  | The raw HTML document (byte-faithful). |

## Initiative

- **Alias:** `sdlc-initiative`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

An Initiative is a strategic investment unit (1-2 quarters) that groups Epics under a measurable outcome. Sits between Theme/OKR (annual) and Epic (multi-sprint). For enterprise roadmaps where Theme→Epic skip loses too much resolution.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string |  |  |
| `business_value` | number |  |  |
| `created_at` | string |  |  |
| `description` | string |  |  |
| `epics` | array |  | Epic names this initiative groups. |
| `horizon_end` | string |  |  |
| `horizon_start` | string |  |  |
| `labels` | array |  |  |
| `outcome_metric` | string |  | What KR/metric this initiative is targeted at. |
| `owner` | string |  | Actor name (PM / Product Lead). |
| `priority` | string |  | Um de: `highest`, `high`, `medium`, `low`, `lowest`. |
| `produces` | array |  | Artifacts this work item produced — any Kind (hub). |
| `produces[].at` | string |  |  |
| `produces[].kind` | string | yes | Artifact Kind (any). |
| `produces[].name` | string | yes | Artifact doc name. |
| `produces[].role` | string |  | Optional role hint (e.g. visual-spec, plan, investigation). |
| `status` | string | yes | Um de: `proposed`, `in-flight`, `done`, `cancelled`, `deferred`. |
| `target_value` | string |  | e.g. '+30% MAU' or '<200ms p95'. |
| `theme_ref` | string |  | Optional Theme/OKR Objective slug. |
| `timeline` | array |  | Append-only activity log. Auto-stamped by the CLI on every status flip / groom / artifact write; populated by AgentSession capture for decision + artifact_produced events. Render in Studio as activity stream. |
| `timeline[].actor` | string | yes | Who triggered the event (Actor name or 'claude-code'). |
| `timeline[].at` | string | yes |  |
| `timeline[].commit_ref` | string |  | Git SHA associated with this event (when relevant). |
| `timeline[].excerpt` | string |  | decision: snippet from the source transcript. |
| `timeline[].fields` | object |  | groom: which fields changed and to what. |
| `timeline[].from` | string |  | status_change: previous status. |
| `timeline[].paths` | array |  | artifact_produced: file paths touched. |
| `timeline[].session_ref` | string |  | Back-link to a AgentSession that produced this event. |
| `timeline[].source` | string |  | Um de: `cli`, `studio`, `mcp`, `agent-session-extracted`, `system`. |
| `timeline[].summary` | string |  | comment/decision: short human-readable text. |
| `timeline[].to` | string |  | status_change: new status. |
| `timeline[].type` | string | yes | Event type. Recognized: status_change, groom, comment, decision, artifact_produced (open vocabulary — new types are additive, e.g. pr_opened). |
| `title` | string | yes |  |
| `updated_at` | string |  |  |

## IntelInsight

- **Alias:** `intel-insight`
- **apiVersion:** `github.com/ruinosus/dna/intel/v1`
- **Plane:** record

An IntelInsight is the dissemination unit of the intelligence layer — a ranked, actionable insight produced from an IntelSource, carrying its headline, cited fact, suggested action, actionability score, matched PIRs, citations, evidence rating and feedback state. The ranker sets the score; the digest suppresses insights below the source threshold; the feedback stage records the state (new/actioned/dismissed/snoozed). Embeddable so a later dedup stage can recall semantically similar insights.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `action` | string \| null |  | The single suggested action. |
| `citations` | array |  | Sources backing the fact — each a {url, title} pair. |
| `citations[].title` | string \| null |  |  |
| `citations[].url` | string | yes |  |
| `created_at` | string \| null |  | ISO-8601 timestamp, stamped by the writer (not defaulted here). |
| `evidence_rating` | string |  | How well-grounded the fact is — evidence-based, opinion/practice, or anecdotal. Um de: `evidence-based`, `opinion-practice`, `anecdotal`. |
| `fact` | string | yes | What happened / the cited fact. |
| `pirs` | array |  | Which Priority Intelligence Requirements this insight matches. |
| `score` | number | yes | Actionability score (0..1). The ranker sets this; the digest suppresses insights scoring below the source's threshold. |
| `source_ref` | string \| null |  | The IntelSource name this insight came from. DECLARED (i-040) — the engine already stamps the source INSTANCE NAME here, which is exactly what a name-addressed relation resolves by, so the declaration types a relation that was already true instead of asking any producer to write differently. Null/absent stays legal — an optional reference that is simply unset is not a dangling one. |
| `state` | string | yes | The feedback disposition — the reader's response to the insight. Um de: `new`, `actioned`, `dismissed`, `snoozed`. |
| `title` | string | yes | The insight headline. |
| `why` | string \| null |  | Why it matters to this source. |

## IntelSource

- **Alias:** `intel-source`
- **apiVersion:** `github.com/ruinosus/dna/intel/v1`
- **Plane:** record

An IntelSource declares one watched portfolio source (a repo, a scope, or an external URL) the DNA observes — its research cadence, actionability threshold, Priority Intelligence Requirements (PIRs) and mute state, as per-tenant declarative data. It is the Direction stage of the intelligence layer — the research → ranked insights → feedback pipeline reads active IntelSources and researches each on its cadence.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `cadence` | string |  | How often the source is researched — manual (on demand), event (on a trigger), daily, or weekly. Um de: `manual`, `event`, `daily`, `weekly`. |
| `muted` | boolean |  | True to pause research on this source without deleting it. |
| `name` | string | yes | The source name, e.g. copiloto-medico. The doc name SHOULD equal this. |
| `notes` | string \| null |  | Free-form operator notes. |
| `pirs` | array |  | Priority Intelligence Requirements — focus areas that get prioritized when researching this source. |
| `threshold` | number |  | Actionability threshold (0..1) below which insights from this source are suppressed. Insights scoring under it are not disseminated. |
| `type` | string | yes | What kind of source this is — a code repo, a DNA scope, or an external URL/feed. Um de: `repo`, `scope`, `external`. |
| `uri` | string \| null |  | Path / URL / scope id the source points at. Null when the name alone identifies it. |

## Issue

- **Alias:** `sdlc-issue`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

An Issue is a human-authored ticket — bug, enhancement, question, or task. Tracked across open → triaged → in-progress → resolved. Optional links to a parent Feature (work it belongs to) and a related Finding (eval-detected origin).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `actual_behavior` | string |  |  |
| `closed_at` | string |  |  |
| `created_at` | string |  |  |
| `description` | string | yes |  |
| `expected_behavior` | string |  |  |
| `github_number` | integer |  | GitHub issue number this doc is bridged to. |
| `github_state` | string |  | Last observed GitHub-side state. Um de: `open`, `closed`. |
| `github_synced_at` | string |  | When the GitHub side was last observed/synced. |
| `github_url` | string |  | Canonical https URL of the GitHub issue. |
| `journey_phase` | string |  | Universal journey phase (discover → specify → plan → build → reflect). Additive layer over Story/Feature/Epic status, Spec phase, etc. Lets the journey ledger pin this doc to one of five universal phases compatible with Superpowers / BMAD / Spec Kit / Kiro. Um de: `discover`, `specify`, `plan`, `build`, `verify`, `reflect`. |
| `labels` | array |  |  |
| `owner` | string |  | Actor name |
| `priority` | string |  | Um de: `highest`, `high`, `medium`, `low`, `lowest`. |
| `produces` | array |  | Artifacts this work item produced — any Kind (hub). |
| `produces[].at` | string |  |  |
| `produces[].kind` | string | yes | Artifact Kind (any). |
| `produces[].name` | string | yes | Artifact doc name. |
| `produces[].role` | string |  | Optional role hint (e.g. visual-spec, plan, investigation). |
| `related_feature` | string |  | Feature name |
| `related_finding` | string |  | Finding name |
| `reporter` | string |  |  |
| `reproduction_steps` | array |  |  |
| `resolution` | string |  |  |
| `severity` | string | yes | Um de: `low`, `medium`, `high`, `critical`. |
| `status` | string | yes | Um de: `open`, `triaged`, `in-progress`, `resolved`, `wont-fix`, `duplicate`. |
| `timeline` | array |  | Append-only activity log. Auto-stamped by the CLI on every status flip / groom / artifact write; populated by AgentSession capture for decision + artifact_produced events. Render in Studio as activity stream. |
| `timeline[].actor` | string | yes | Who triggered the event (Actor name or 'claude-code'). |
| `timeline[].at` | string | yes |  |
| `timeline[].commit_ref` | string |  | Git SHA associated with this event (when relevant). |
| `timeline[].excerpt` | string |  | decision: snippet from the source transcript. |
| `timeline[].fields` | object |  | groom: which fields changed and to what. |
| `timeline[].from` | string |  | status_change: previous status. |
| `timeline[].paths` | array |  | artifact_produced: file paths touched. |
| `timeline[].session_ref` | string |  | Back-link to a AgentSession that produced this event. |
| `timeline[].source` | string |  | Um de: `cli`, `studio`, `mcp`, `agent-session-extracted`, `system`. |
| `timeline[].summary` | string |  | comment/decision: short human-readable text. |
| `timeline[].to` | string |  | status_change: new status. |
| `timeline[].type` | string | yes | Event type. Recognized: status_change, groom, comment, decision, artifact_produced (open vocabulary — new types are additive, e.g. pr_opened). |
| `title` | string |  | Human-readable display name (Jira 'summary'). |
| `type` | string | yes | Um de: `bug`, `enhancement`, `question`, `task`. |
| `updated_at` | string |  |  |
| `watchers` | array |  |  |

## Kaizen

- **Alias:** `sdlc-kaizen`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Kaizen is a continuous-improvement observation noticed while working on something else — a smell, friction, a manual step, a missing test — captured as a first-class doc WITHOUT derailing the task at hand. Arc: observed → routed (an Issue/Story tracks the fix) → resolved (fix shipped). Twin of the `kaizen` timeline event on the originating work item (which carries a ref back to this doc).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `actor` | string |  | Who flagged it. |
| `body` | string | yes | The kaizen observation (what could be better). |
| `created_at` | string |  |  |
| `issue` | string |  | Issue/Story slug tracking the fix. |
| `labels` | array |  | Free-form theme tags (weighted into semantic-search source text). |
| `status` | string | yes | Observation arc: observed (flagged) → routed (fix tracked in `issue`) → resolved (fix shipped). Um de: `observed`, `routed`, `resolved`. |
| `updated_at` | string |  |  |
| `work_item` | string |  | Kind/slug of the work item where this was observed — polymorphic over the work-item family (see relations.work_item). |

## KindNamespace

- **Alias:** `tenant-kind-namespace`
- **apiVersion:** `github.com/ruinosus/dna/tenant/v1`
- **Plane:** record

A KindNamespace records that a workspace owns an apiVersion namespace — the claim the write path checks before letting anyone declare a Kind in it. The namespace is a claimed NAME (`acme.example`), never the workspace id, because the apiVersion participates in every instance's identity and a database id baked into it would make renaming a workspace rewrite the identity of everything it owns. Claims are prefixes and the most specific one wins; a namespace already occupied by a Kind registered from code is RESERVED and cannot be claimed at all. GLOBAL declarative data in `_lib`.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `claimed_at` | string | yes | When the namespace was claimed (ISO 8601). The audit trail is the reason a claim is an instance rather than a config entry. |
| `namespace` | string | yes | The apiVersion PREFIX being claimed — everything before the version segment (`acme.example` claims `acme.example/v1`; a claim is a prefix, so it also covers `acme.example/crm/v1`). Never contains a version and never ends in `/`. |
| `notes` | string \| null |  | Free-form operator note — why this namespace was granted, the ticket it came from. Never read by the enforcement path. |
| `owner` | string | yes | The `workspace_id` of the workspace that owns this namespace. OPAQUE — matched whole, never parsed. It is the same value the kernel `tenant` column carries for that workspace, which is what lets the write path compare a writer to an owner without a lookup. |

## Membership

- **Alias:** `portfolio-membership`
- **apiVersion:** `github.com/ruinosus/dna/portfolio/v1`
- **Plane:** record

A Membership is the RBAC join — a user's role at an org- or project-scope within a tenant's portfolio. It carries the user (email / id), the scope_type (org / project) and scope_ref it applies to, the role from the standard ladder (owner > admin > member > guest, highest-role-wins, org-owner superuser), and an invitation status (invited / active), as per-tenant declarative data. It is distinct from the platform-level TenantMembership (which links a user to a provisioning Tenant); this grants access inside the tenant's own Organization / Project graph.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `invited_at` | string \| null |  | ISO-8601 timestamp of the invite, stamped by the writer (not defaulted here). |
| `role` | string | yes | The role granted at this scope — the standard ladder (owner > admin > member > guest). Resolution is highest-role-wins across a user's memberships, with the org owner a superuser. Um de: `owner`, `admin`, `member`, `guest`. |
| `scope_ref` | string | yes | The Organization or Project name this grant applies to (paired with scope_type). |
| `scope_type` | string | yes | What the grant is scoped to — an Organization (org) or a single Project (project). Um de: `org`, `project`. |
| `status` | string |  | Invitation lifecycle — invited (pending acceptance) or active. Um de: `invited`, `active`. |
| `user` | string | yes | The member's identity — an email or stable user id. |

## Memory

- **Alias:** `mif-memory`
- **apiVersion:** `mif-spec.dev/v1`
- **Plane:** record

A MIF Memory is DNA's byte-faithful passthrough of the external Memory Interchange Format (mif-spec.dev/v1), stored and validated under its owner's namespace exactly as MIF defines it (market-fidelity rule). Frontmatter + Markdown body is a MIF Memory Unit's canonical shape, which is structurally identical to a DNA bundle marker — no custom Reader/ Writer needed. This is the interchange face only; it does NOT replace Engram (github.com/ruinosus/dna/v1 · Engram), DNA's native recall engine — `dna memory export`/`import` (a later story) projects between the two, with DNA-specific fields riding along in `extensions` for a lossless round-trip.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `aliases` | array |  | Alternative names for the memory (§5.2, OPTIONAL). |
| `citations` | array |  | Citation references (§5.4, Level 3 OPTIONAL). |
| `citations[].@type` | string | yes | Um de: `Citation`. |
| `citations[].accessed` | string |  | Access date, ISO 8601. |
| `citations[].author` | any |  | One or more entity references, or plain text. |
| `citations[].citationRole` | string | yes | Relationship to the memory (§5.4.4): supports, refutes, background, methodology, contradicts, extends, derived, source, example, review — or a custom namespaced role. |
| `citations[].citationType` | string | yes | Source category (§5.4.3): article, book, paper, website, documentation, repository, video, podcast, specification, dataset, tool, other — or a custom namespaced type. |
| `citations[].date` | string |  | Publication date, ISO 8601. |
| `citations[].note` | string |  |  |
| `citations[].relevance` | number |  |  |
| `citations[].title` | string | yes |  |
| `citations[].url` | string | yes |  |
| `compressed_at` | string |  | When compression was applied (§5.6, Level 3, ISO 8601). Snake_case in the Markdown frontmatter profile (the JSON-LD projection's `compressedAt` is camelCase — a naming quirk of that derived form, not this one). |
| `content` | string | yes | The memory content in Markdown — the marker body below the frontmatter (title H1, prose, and the optional `## Relationships` / `## Citations` mirror sections all travel as part of this string, exactly as MIF's own §5.1 structure defines). |
| `created` | string | yes | Creation timestamp, ISO 8601 (§4.1). Maps to Engram created_at. NOTE (every date-time field on this Kind): PyYAML's SafeLoader implicitly resolves an UNQUOTED ISO-8601-looking scalar to a Python datetime.datetime at frontmatter parse time (YAML 1.1 !!timestamp implicit tag) — a pre-existing, Kind-agnostic quirk of _parse_frontmatter (dna/kernel/generic_rw.py), not specific to MIF. A real MIF .md file (whose own examples write dates unquoted) will therefore parse date-time fields as datetime objects, which this "type: string" schema then rejects on jsonschema.validate. Quoting the value in frontmatter (created is a quoted string) sidesteps it losslessly — same value, string-typed — and is what the test fixtures do; unquoted MIF input is a known gap for whoever picks up strict date-time validation SDK-wide (out of scope for this story). |
| `embedding` | object |  | Embedding model reference (OPTIONAL). Actual vectors are stored externally or in the JSON-LD projection — the Markdown frontmatter only carries the reference. |
| `embedding.dimensions` | integer |  |  |
| `embedding.model` | string |  |  |
| `embedding.modelVersion` | string |  |  |
| `embedding.normalized` | boolean |  |  |
| `embedding.sourceText` | string |  | The text that was embedded. |
| `embedding.vectorUri` | string |  |  |
| `entities` | array |  | Referenced entities (§7.5/Appendix C, OPTIONAL) — typed pointers into the bundle's `.mif/entities/` definitions, distinct from `relationships` (which point at other MEMORIES, not entities). |
| `entities[].@type` | string | yes | Um de: `EntityReference`. |
| `entities[].entity` | object | yes | Entity identifier object. |
| `entities[].entity.@id` | string | yes | Entity URN, e.g. `urn:mif:entity:person:jane-doe`. |
| `entities[].entityType` | string |  | Entity type classification: `Person`, `Organization`, `Technology`, `Concept`, `File`, or a custom ontology-defined type. |
| `entities[].name` | string |  | Display name for the entity. |
| `entities[].role` | string |  | Role of the entity in the memory context (e.g. author, subject, topic). |
| `extensions` | object |  | Provider-specific extensions (§4.1/§5.2, OPTIONAL) — the vault where DNA's own physics rides along on a round-trip: confidence_score, relevance_decay_seed, surface_count, cues_history, encoding_context, affect, affect_reason, visibility. Namespaced under `x-dna` by convention so other MIF-conformant tools degrade gracefully (ignore what they don't recognize) while a DNA reader recovers everything. |
| `id` | string | yes | MIF Memory Unit identifier — a UUID v4 in the Markdown frontmatter profile (SPECIFICATION.md §5.2/Appendix A). NOT the `urn:mif:` URN form — that's `@id` in the separately-derived JSON-LD projection (§6), never written into this frontmatter. Preserved verbatim so a re-export is stable; on import from Engram, minted once and pinned. |
| `modified` | string |  | Last modification timestamp, ISO 8601 (§4.1, RECOMMENDED). |
| `namespace` | string |  | Hierarchical scope path (§10), e.g. `_semantic/decisions`. Base-type roots use the reserved underscore prefixes (`_semantic`, `_episodic`, `_procedural`); visibility prefixes (`_public`, `_shared`, `_local`, `_system`) are reserved alongside them (§4.4 note, §10.2). Maps loosely to Engram.area. |
| `ontology` | object |  | Reference to the ontology this memory conforms to (§4.3). `id` must match the `ontology.id` declared in the referenced ontology definition; ontology-extended types (§4.2.1) are expressed through the `namespace` axis, not a separate field here. |
| `ontology.id` | string | yes | Ontology identifier. |
| `ontology.uri` | string |  | URI to the ontology definition (not necessarily a resolvable URL — §5.2 notes it may be an identifier only). |
| `ontology.version` | string |  | Semantic version of the ontology, e.g. "1.0.0". |
| `provenance` | object |  | W3C-PROV-aligned source/trust data (§12, OPTIONAL). `wasAttributedTo` maps to Engram.owner; `wasDerivedFrom` maps to Engram.source_refs. additionalProperties left OPEN (`true`) because the real MIF Provenance schema is itself open — PROV graphs are explicitly open-ended (mif.schema.json ProvNode note) — not a DNA-added exception to the strict-schema convention. |
| `provenance.agent` | string |  | Identifier of the agent that created the unit (e.g. claude-3-opus). |
| `provenance.agentVersion` | string |  |  |
| `provenance.confidence` | number |  |  |
| `provenance.sourceRef` | string |  | Reference to the originating source (e.g. `conversation:conv-456`). |
| `provenance.sourceType` | string |  | Um de: `user_explicit`, `user_implicit`, `agent_inferred`, `external_import`, `system_generated`. |
| `provenance.trustLevel` | string |  | Um de: `verified`, `user_stated`, `high_confidence`, `moderate_confidence`, `low_confidence`, `uncertain`. |
| `provenance.wasAttributedTo` | any |  | prov:wasAttributedTo — the agent this unit is attributed to. A string IRI or an open PROV node object. |
| `provenance.wasDerivedFrom` | any |  | prov:wasDerivedFrom — the entity/entities this unit was derived from. A string IRI, an open PROV node object, or an array of either. |
| `provenance.wasGeneratedBy` | any |  | prov:wasGeneratedBy — the activity that produced this unit. A string IRI or an open PROV node object. |
| `relationships` | array |  | Typed edges to OTHER MEMORIES (§8), authoritative in this frontmatter array and mirrored in the body as `## Relationships` markdown links (§5.3/§8.4) — the frontmatter array is the source of truth, the body links are its OKF-legible mirror. The 9 core types SHOULD-recognized for interoperability (Appendix B, kebab-case): `relates-to`, `derived-from`, `supersedes`, `conflicts-with`, `part-of`, `implements`, `uses`, `created-by`, `mentioned-in`. Providers MAY define additional namespaced types (`ns:type`, §8.3) — NOT a closed enum here, matching the spec's own extensibility. derived-from maps to Engram.source_refs; supersedes pairs with `temporal.validUntil` for point-in-time audit. |
| `relationships[].metadata` | object |  | Additional relationship metadata (open — mirrors the spec's own permissive shape for this field). |
| `relationships[].strength` | number |  | Relationship strength (0.0-1.0). |
| `relationships[].target` | string | yes | Bundle-relative path to the target concept (e.g. `/semantic/policy.md`) or a `urn:mif:` identifier. |
| `relationships[].type` | string | yes | Relationship type — a kebab-case token (e.g. `derived-from`) or a custom namespaced type (e.g. `farm:contradicts`). |
| `summary` | string |  | Compressed content summary (§5.6, Level 3, max 500 chars). |
| `tags` | array |  | Classification tags (§4.1, OPTIONAL). 1:1 with Engram.tags. |
| `temporal` | object |  | Bi-temporal validity + decay data (§9, OPTIONAL — RECOMMENDED at Level 2 per §13.2's "temporal metadata" bullet). `validFrom`/`validUntil` map 1:1 to Engram valid_from/valid_to — the second axis DNA and MIF already agree on. NOTE the field is `validUntil`, not `validTo`. |
| `temporal.accessCount` | integer |  |  |
| `temporal.decay` | object |  | Decay model parameters (§9.2). |
| `temporal.decay.currentStrength` | number |  |  |
| `temporal.decay.halfLife` | string |  | ISO 8601 duration, e.g. `P7D`. |
| `temporal.decay.lastReinforced` | string |  |  |
| `temporal.decay.model` | string |  | Um de: `none`, `linear`, `exponential`, `step`. |
| `temporal.decay.strength` | number |  | Alias for currentStrength. |
| `temporal.lastAccessed` | string |  |  |
| `temporal.recordedAt` | string |  | When recorded — transaction time, distinct from `validFrom`'s valid time. |
| `temporal.reinforcementHistory` | array |  | History of reinforcement events that strengthened or weakened the memory. |
| `temporal.reinforcementHistory[].context` | string |  |  |
| `temporal.reinforcementHistory[].event` | string | yes |  |
| `temporal.reinforcementHistory[].strengthDelta` | number |  |  |
| `temporal.reinforcementHistory[].timestamp` | string | yes |  |
| `temporal.ttl` | string |  | Time-to-live, ISO 8601 duration (e.g. `P90D`). |
| `temporal.validFrom` | string \| null |  | When the fact becomes valid. |
| `temporal.validUntil` | string \| null |  | When the fact expires (null = indefinite). |
| `title` | string |  | Human-readable title (§5.2). Optional first-H1 mirror in the body is conventional but not required by the schema. |
| `type` | string | yes | MIF base memory type (§4.2) — CoALA-style taxonomy that maps 1:1 to Engram.memory_type: semantic = declarative facts/ concepts/preferences; episodic = time-bound events/sessions; procedural = how-to/runbooks. This is why the DNA↔MIF projection is lossless on the type axis. (The JSON-LD projection additionally accepts the deprecated `memoryType` alias — irrelevant here since this Kind only carries the Markdown frontmatter profile.) Um de: `semantic`, `episodic`, `procedural`. |

## ModelProfile

- **Alias:** `modelreg-model-profile`
- **apiVersion:** `github.com/ruinosus/dna/modelreg/v1`
- **Plane:** record

A ModelProfile records one LLM model's hard limits and capabilities (instruction_token_cap, context_window, tools_cap, modalities, cost). It is the single source of truth the prompt-budget write guard reads — never hardcode token caps in code; read them from the ModelProfile registry via kernel.model_profile().

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `aliases` | array |  | Alternate ids that resolve to this profile (deployment names, dated snapshots). kernel.model_profile() matches these on pass 2. |
| `context_window` | integer |  | Total context window in tokens. |
| `cost_per_1m_input_usd` | number \| null |  | USD per 1M input tokens (informational). |
| `cost_per_1m_output_usd` | number \| null |  | USD per 1M output tokens (informational). |
| `deprecated` | boolean |  | True when the model is scheduled for removal. |
| `deprecated_message` | string \| null |  | Human guidance shown when a deprecated model is used. |
| `family` | string \| null |  | Model family/lineage for grouping, e.g. 'gpt-realtime'. |
| `instruction_token_cap` | integer \| null |  | Hard cap for the system-instruction/persona in tokens. Null = no cap known (the guard fails open). THE value the prompt-budget guard enforces — never hardcode it in code. |
| `max_output_tokens` | integer \| null |  | Max completion/output tokens per response. |
| `modalities` | array |  | Supported modalities, e.g. [text], [text, audio], [text, image]. |
| `model_id` | string | yes | Canonical model identifier, e.g. 'gpt-realtime-2'. The doc name SHOULD equal the model_id; kernel.model_profile() matches on this field first. |
| `notes` | string \| null |  | Free-form operator notes. |
| `provider` | string | yes | Who serves the model — 'openai', 'anthropic', 'azure', a proxy alias, etc. |
| `realtime` | boolean |  | True for realtime voice models. STRICT marker: the prompt-budget guard VETOES an over-cap write against a realtime profile (voice sessions silently degrade past the cap); chat profiles only warn. |
| `tools_cap` | integer \| null |  | Max number of tools the model accepts per session. |

## Narrative

- **Alias:** `sdlc-narrative`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Narrative is a curated, human-readable summary of project activity. Stored as a NARRATIVE.md bundle with markdown body. Names usually encode the period (ISO date for daily, milestone slug for releases). Replaces ad-hoc 'what happened tonight?' chat scrolling — the agent stamps a Narrative at session end so future readers (CEO, customer, new-hire) can open one page and get the story.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `actor` | string |  | Who wrote this narrative (Actor name, 'claude-code', 'human', etc.). |
| `author_intent` | string |  | What kind of narrative this is. Drives how the morning panel groups multiple narratives — daily stack on the timeline, releases pin as marquee, retros surface in a 'lessons' filter. Um de: `daily`, `weekly`, `release`, `retro`, `incident`, `freeform`. |
| `auto_generated` | boolean |  | true = LLM-generated draft; false = human or agent-curated prose. Studio shows a small badge so readers know what they're reading. |
| `body` | string | yes | Markdown body of the narrative (lives in NARRATIVE.md). Free-form — paragraphs, bullets, links to Stories/Features/commits. Should read like a human update, not a log dump. |
| `covers_epics` | array |  | Epic names this narrative discusses. |
| `covers_features` | array |  | Feature names this narrative discusses. |
| `covers_session` | string |  | AgentSession name this narrative was auto-derived from (Karpathy 'context ephemeral, files durable' pattern). Set by `dna sdlc session capture` when the post-capture narrative hook runs. |
| `covers_stories` | array |  | Story names this narrative discusses. |
| `created_at` | string |  |  |
| `decisions` | array |  | Ratified decisions made during the period covered by this narrative. Each captures the WHY, not just the WHAT — the decision-extractor pattern. |
| `decisions[].reason` | string |  | Why — the tradeoff or driving constraint. |
| `decisions[].summary` | string | yes | What was decided (1 sentence). |
| `decisions[].trade_offs` | string |  | Optional: what we gave up to make this choice. |
| `journey_phase` | string |  | Universal journey phase (discover → specify → plan → build → reflect). Additive layer over Story/Feature/Epic status, Spec phase, etc. Lets the journey ledger pin this doc to one of five universal phases compatible with Superpowers / BMAD / Spec Kit / Kiro. Um de: `discover`, `specify`, `plan`, `build`, `verify`, `reflect`. |
| `open_items` | array |  | Work that started but didn't close in this period. Studio's 'still open' section reads from this when present (otherwise computes heuristically from event diff). |
| `open_items[].blocker` | string |  |  |
| `open_items[].owner` | string |  |  |
| `open_items[].title` | string | yes |  |
| `paragraphs` | array |  | Structured prose: list of past-tense paragraphs describing what shipped. Studio renders these as the hero block; falls back to `body` when empty. |
| `period_end` | string |  | End of the period (often the moment the narrative was written). |
| `period_start` | string |  | Start of the period this narrative covers (ISO-8601). |
| `summary` | string |  | Optional one-line tl;dr. When present, the Studio card shows this above the body for scanning. |
| `tags` | array |  | Free-form tags for filtering (daily, release, retro, ...). |
| `title` | string | yes | Headline for this narrative. Shown above the body. |
| `updated_at` | string |  |  |

## Organization

- **Alias:** `portfolio-org`
- **apiVersion:** `github.com/ruinosus/dna/portfolio/v1`
- **Plane:** record

An Organization is the tenant's own org profile — the enterprise-familiar top-level container (as in GitHub / Azure DevOps) whose portfolio of Projects the DNA Cloud console aggregates. It carries the org name, a URL-safe slug, an optional display name, and a plan_ref annotation naming a DNA Cloud Tier the org is on, as per-tenant declarative data. One Organization per tenant; it is distinct from the platform-level Tenant provisioning identity Kind (the editable org profile inside the tenant's own portfolio, not the GLOBAL identity row).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `created_at` | string \| null |  | ISO-8601 timestamp, stamped by the writer (not defaulted here). |
| `display_name` | string \| null |  | Human-facing name shown in the console. Falls back to name. |
| `name` | string | yes | The organization's canonical name. The doc name SHOULD equal this. |
| `plan_ref` | string \| null |  | The DNA Cloud Tier this org is on (a Tier tier_id). NOTE the SUBSCRIPTION is not read from here — billing is per BILLING ACCOUNT (AccountPlan, keyed on Workspace.account_id); this is a portfolio-level annotation only. Null falls back to Free. The billing→enforcement bridge reads it; the OSS SDK only stores it. |
| `slug` | string | yes | URL-safe identity for the org, e.g. acme-corp. Used in routes and as a stable handle for the tenant's portfolio. |

## Plan

- **Alias:** `sdlc-plan`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Plan is a pointer to an implementation plan document on disk. Usually descends from a Spec (`spec_ref`). Pattern-agnostic — DNA tracks pointer + metadata + refs, not the structure of the plan itself.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `authors` | array |  |  |
| `body` | string |  | Markdown body (stored in PLAN.md). |
| `date` | string | yes |  |
| `epic` | string |  |  |
| `journey_phase` | string |  | Universal journey phase. A Plan typically lives in `plan` (decomposition) and may transition to `build` once Stories start landing. Um de: `discover`, `specify`, `plan`, `build`, `verify`, `reflect`. |
| `methodology` | string |  | Which planning methodology produced this plan (superpowers \| bmad \| spec-kit \| ...). Opt-in; lets the journey show the plan's origin honestly. The SDLC stays methodology-agnostic — this only records it. Um de: `superpowers`, `bmad`, `spec-kit`, `kiro`, `rfc`, `adr`, `ad-hoc`, `custom`. |
| `origin` | string |  | Optional audit-only origin path. |
| `pattern` | string |  |  |
| `spec_ref` | string |  | Name of the Spec this plan implements. |
| `status` | string | yes | Um de: `draft`, `proposed`, `accepted`, `deprecated`, `superseded`. |
| `summary` | string |  |  |
| `tags` | array |  |  |
| `title` | string | yes |  |

## PlanBinding

- **Alias:** `cloud-plan-binding`
- **apiVersion:** `github.com/ruinosus/dna/cloud/v1`
- **Plane:** record

An AccountPlan maps one DNA Cloud BILLING ACCOUNT to its current Tier as GLOBAL declarative data, so enforcement follows billing state without a redeploy. The subscription is per ACCOUNT — one AccountPlan covers every Workspace whose `account_id` matches, so a second workspace is never a second charge. It replaces the retired per-workspace WorkspacePlan, which forced an unsafe fan-out. dna-cloud's Stripe webhook writes it on subscribe/cancel; the MCP server resolves workspace → account_id → AccountPlan via kernel.account_plan(account_id) when the token carries no explicit plan claim. A workspace with no resolvable account gets the Free floor (fail-closed) — never another account's tier.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `account_id` | string | yes | The BILLING ACCOUNT this assignment is for — the opaque id recorded on every Workspace the account owns (Workspace.account_id). One plan covers ALL of them. The doc name SHOULD equal it; kernel.account_plan() matches on this field. Opaque - matched, never parsed. |
| `notes` | string \| null |  | Free-form operator notes. |
| `source` | string |  | Where the assignment came from, e.g. stripe / manual / trial. |
| `status` | string |  | The billing status of the assignment, e.g. active / past_due / canceled. |
| `stripe_customer_id` | string |  | The Stripe customer id backing the assignment (dna-cloud writes it; the OSS SDK never calls Stripe). |
| `stripe_subscription_id` | string |  | The Stripe subscription id backing the assignment (dna-cloud writes it; the OSS SDK never calls Stripe). |
| `tier_id` | string | yes | The assigned PricingPlan's id, e.g. free, pro, enterprise. Resolved to caps via kernel.tier(tier_id) — never a literal in code. This IS a reference and it IS declared, as `to: PricingPlan, by: tier_id` (see `spec.relations`). The resolver matches `PricingPlan.spec.tier_id` first and `PricingPlan.spec.aliases[]` second, in the `_lib` scope, and NEVER the instance name — so this runtime does not FOLLOW the declaration, exactly as it does not follow `Project.workspace_id`. It is a keyed reference, the same shape as `Organization.plan_ref`. NOTE the Kind was called `Tier` until the metering rename (dna 0.29.0); this description named the dead Kind until 2026-08-06, and claimed the field was undeclarable until 2026-08-06 as well. |
| `updated_at` | string |  | When dna-cloud last wrote this assignment (ISO 8601). |

## Postmortem

- **Alias:** `sdlc-postmortem`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Postmortem captures a factual analysis of an incident that happened — timeline, root cause, contributing factors, action items, lessons learned. Google SRE convention: blameless. Distinct from Retrospective (recurring period summary).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `action_items` | array |  | Concrete follow-ups to prevent recurrence. |
| `action_items[].due` | string |  |  |
| `action_items[].owner` | string |  |  |
| `action_items[].status` | string |  | Um de: `todo`, `in-progress`, `done`. |
| `action_items[].story_ref` | string |  |  |
| `action_items[].title` | string | yes |  |
| `blameless` | boolean |  | Google SRE requirement — should always be true. |
| `body` | string |  |  |
| `contributing_factors` | array |  | Secondary factors that worsened the incident. |
| `created_at` | string |  |  |
| `impact` | string |  | Customer-facing impact in plain language (downtime, errors, etc.). |
| `incident_at` | string | yes | When incident started. |
| `lessons_learned` | array |  | Insights that generalize beyond this incident. |
| `related_features` | array |  |  |
| `related_stories` | array |  | Story slugs related to root cause or action items. |
| `resolved_at` | string |  | When incident was mitigated. |
| `root_cause` | string | yes | Primary cause (1-3 paragraphs). |
| `severity` | string | yes | Incident severity (sev1=full outage, sev5=cosmetic). Um de: `sev1`, `sev2`, `sev3`, `sev4`, `sev5`. |
| `tags` | array |  |  |
| `timeline` | array |  | Chronological event log. |
| `timeline[].actor` | string |  |  |
| `timeline[].at` | string | yes |  |
| `timeline[].event` | string | yes |  |
| `title` | string | yes | Short incident headline. |
| `updated_at` | string |  |  |
| `what_went_well` | array |  | Detection / response things that worked. |
| `what_went_wrong` | array |  | Detection / response things that didn't work. |

## PricingPlan

- **Alias:** `cloud-pricing-plan`
- **apiVersion:** `github.com/ruinosus/dna/cloud/v1`
- **Plane:** record

A Tier declares one DNA Cloud plan's hard caps (calls/day, rate, tenants) and which feature families it unlocks, as GLOBAL declarative data so changing a limit is a file edit, not a redeploy. Resolve it via kernel.tier(id_or_alias); the quota enforcer reads the caps from here and never hardcodes them.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `aliases` | array |  | Alternate ids that resolve to this tier (legacy plan names). kernel.tier() matches these on pass 2. |
| `calls_per_day` | integer \| null |  | Daily call quota. Null = unlimited (enterprise). THE value the quota enforcer reads — never hardcode it in code. |
| `definitions_mode` | string |  | Definitions access level granted by the tier — the read-vs-write refinement of the `definitions` feature family, sibling of memory_mode/sdlc_mode. Only the GENERIC instance tools consult it, and only on a WRITE — a plan that omits it grants none, so writing an Agent/Soul/Tool/ModelProfile through the generic tool is refused until the operator declares write here. Reads keep riding the coarse feature_families gate. Um de: `none`, `read`, `write`. |
| `display_name` | string | yes | Human-facing plan name, e.g. Free, Pro, Enterprise. |
| `emit_mode` | string |  | Emit access level granted by the tier — the same read-vs-write refinement for the `emit` feature family. Same rule as definitions_mode - consulted by the generic instance tools on a write, and omitting it grants none. Um de: `none`, `read`, `write`. |
| `feature_families` | array |  | Tool families this tier unlocks, e.g. [definitions, sdlc, memory, emit]. |
| `margin_breaker_calls_per_window` | integer \| null |  | ⚠️ COST-PROTECTION CUTOUT — NOT a sold limit, NOT a pricing axis, and it must never appear on a price page or in a plan comparison. The caps above are what the plan SELLS (a promise to the customer); this is a fuse the OPERATOR arms so that one account cannot cost more than the business can absorb while the right sold axis does not exist yet (i-134). Reached, the metered call is REFUSED with a message that says so in as many words. Null/absent = no fuse, which is the default and leaves every plan behaving exactly as before. Denominated in CALLS because that is the only quantity the gate can count exactly — the token count lives in turn telemetry, in another process, and telemetry that drops under pressure would be a fuse that never blows. The operator derives the NUMBER from dollars (worst-case cost per call x ceiling <= what an account may be allowed to cost); the unit is calls, the intent is margin. |
| `margin_breaker_window_days` | integer \| null |  | Rolling horizon of margin_breaker_calls_per_window, in days (default 30 when absent). ROLLING, not calendar: a calendar period resets at midnight on the 1st, so a runaway straddling the 31st and the 1st would get two full ceilings inside 48 hours. Meaningless on its own — with no ceiling declared there is no fuse to give a horizon to. |
| `max_tenants` | integer \| null |  | Number of tenants the plan allows. Null = unlimited. |
| `memory_mode` | string |  | Memory access level granted by the tier — none, read, or write. Um de: `none`, `read`, `write`. |
| `notes` | string \| null |  | Free-form operator notes. |
| `overage_per_1k_usd` | number \| null |  | USD charged per 1k calls above the daily quota. Null = no overage (hard cap). |
| `price_usd_month` | number |  | Flat monthly price in USD (0 for the free tier). |
| `rate_per_sec` | integer \| null |  | Per-second rate limit. Null = unmetered. |
| `sdlc_mode` | string |  | SDLC board access level granted by the tier — none, read, or write. Read = list/digest/ADR; write = create/transition/comment. Um de: `none`, `read`, `write`. |
| `sla` | boolean |  | True when the tier includes a support/uptime SLA (enterprise). |
| `tier_id` | string | yes | Canonical tier id, e.g. free, pro, enterprise. The doc name SHOULD equal the tier_id; kernel.tier() matches on this field first. |

## Project

- **Alias:** `portfolio-project`
- **apiVersion:** `github.com/ruinosus/dna/portfolio/v1`
- **Plane:** record

A Project is the multi-repo development-space container — the key Kind of the portfolio model. It owns a SDLC board scope (convention <slug>-development), one or more IntelSources the intelligence layer observes, and scoped memory, and it is the permission boundary. Repos are attached BY REFERENCE via repo_refs (an N—N edge kept on the Project side — a repo can belong to many projects without duplication; Repo carries no project back-ref). A Project has a visibility (private / shared), an org_ref to its Organization and an explicit workspace_id naming the Workspace that owns it (decision A1), as per-tenant declarative data.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `board_scope` | string \| null |  | The SDLC scope this project owns (convention <slug>-development). Where its Stories / Issues / Epics live. |
| `created_at` | string \| null |  | ISO-8601 timestamp, stamped by the writer (not defaulted here). |
| `intel_source_refs` | array |  | IntelSource names the intelligence layer observes for this project (the sources feeding its insight stream). DECLARED (i-040) — every item resolves by INSTANCE NAME, the same key `org_ref` and `repo_refs` above already use. |
| `name` | string | yes | The project's canonical name. The doc name SHOULD equal this. |
| `org_ref` | string \| null |  | The Organization (name) this project belongs to. Null while unassigned. |
| `repo_refs` | array |  | Repo names attached to this project (the N—N edge — a repo may appear on multiple projects). The edge lives on the Project side only. |
| `slug` | string | yes | URL-safe identity for the project, e.g. copiloto-medico. Used in routes and to derive the board_scope by convention. |
| `visibility` | string |  | Who can see the project — private (org-internal) or shared (visible across the portfolio). Um de: `private`, `shared`. |
| `workspace_id` | string \| null |  | The Workspace this project belongs to — the EXPLICIT owning edge (decision A1; a Project is created inside exactly one workspace and never moves). The physical `tenant` column carries the same value, so this field is the DECLARATIVE twin of the storage keying, readable without knowing how the kernel keys rows. Null only on a legacy pre-A1 doc, whose owning workspace is then its `tenant` column alone. The board_scope / scope a project resolves to is DERIVED from (workspace, slug) — presentation, never the project's identity. |

## PromptTemplate

- **Alias:** `sdlc-prompt-template`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A PromptTemplate is a versioned, overlayable user-prompt template owned by the kernel — the declarative answer to 'where does the user prompt live?'. Callers (typically Python helpers or HTTP endpoints) fetch the template by name and format() it with per-call variables. Tenants can override the template body without touching code. Templates can ship versioned with their consuming Kind (Narrative, StatusReport, etc.) so prompt-engineering changes are reviewable diffs, not commits to call sites.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string | yes | Template text with {var} placeholders. |
| `default_locale` | string |  |  |
| `description` | string |  |  |
| `tags` | array |  |  |
| `variables` | array |  | Names of placeholders body expects. |

## Reference

- **Alias:** `sdlc-reference`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `cited_by` | array |  | Auto-maintained by `dna sdlc cite`. Don't author by hand. |
| `content_path` | string |  | Optional path to rich-content sidecar (e.g. docs/superpowers/research/<slug>.md) |
| `created_at` | string |  |  |
| `fetched_at` | string |  |  |
| `key_quotes` | array |  |  |
| `kind_of` | string | yes | Um de: `web`, `paper`, `book`, `file`, `internal-doc`, `other`. |
| `owner` | string |  |  |
| `relevance` | string |  | Why this matters for THIS project. |
| `summary` | string | yes | 1-2 sentence what this source says. |
| `tags` | array |  |  |
| `title` | string | yes |  |
| `updated_at` | string |  |  |
| `url` | string |  |  |

## RemoteAgent

- **Alias:** `a2a-remote-agent`
- **apiVersion:** `github.com/ruinosus/dna/a2a/v1`
- **Plane:** record

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `capabilities` | object |  | A2A `capabilities` — flags booleanas, não operações nomeadas. |
| `capabilities.extended_agent_card` | boolean |  |  |
| `capabilities.push_notifications` | boolean |  |  |
| `capabilities.streaming` | boolean |  |  |
| `data_scope` | object | yes | O que este endpoint PODE receber. Obrigatório — ver o cabeçalho. |
| `data_scope.kinds` | array | yes | Nomes de Kind cujas instâncias podem ser delegados a este remoto. Lista vazia = nada pode, o que é um estado honesto (registrado, sem permissão) e não um erro. |
| `default_input_modes` | array |  |  |
| `default_output_modes` | array |  |  |
| `delegation_target_for` | object |  | O bloco COMPARTILHADO com `Agent` (kernel `DelegationTargetFor`). É o que o roster derivado lê para achar este alvo sem enumerar Kinds. |
| `delegation_target_for.agents` | array |  | Allowlist de delegadores; `["*"]` = qualquer. |
| `delegation_target_for.format` | string |  | Um de: `slug`, `json`, `text`. |
| `delegation_target_for.purpose` | string |  |  |
| `delegation_target_for.typical_seconds` | integer |  |  |
| `delegation_target_for.use_when` | string |  |  |
| `description` | string | yes | A2A `description`. Para que ele serve, nas palavras dele. |
| `documentation_url` | string |  |  |
| `icon_url` | string |  |  |
| `name` | string | yes | A2A `name`. O nome pelo qual o agente se anuncia. |
| `security_schemes` | object |  | A2A `securitySchemes` (forma do OpenAPI 3). Diz COMO autenticar. A credencial em si NUNCA vive aqui — o schema é fechado justamente para que um bearer não possa ser anexado à instância. Quem guarda a credencial é o deployment, por remoto, e ela nunca é o token do usuário. |
| `signature_state` | string |  | Tri-estado DE PROPÓSITO: uma instância que não foi verificado tem de ser legível como tal. `unsigned` = o Card não trouxe assinatura; `present_unverified` = trouxe e não checamos; `verified` = checamos (não alcançável nesta versão). Um booleano `signed` faria "não verificado" parecer "não assinado", que são coisas diferentes. Um de: `unsigned`, `present_unverified`, `verified`. |
| `signatures` | array |  | A2A `signatures`, preservadas como vieram. A VERIFICAÇÃO criptográfica está fora desta versão (exige decidir a cadeia de confiança, que é decisão de produto) — por isso `signature_state` existe e é tri-estado. |
| `skills` | array |  | A2A `skills[]` — o que ele sabe fazer, item a item. |
| `skills[].description` | string | yes |  |
| `skills[].examples` | array |  |  |
| `skills[].id` | string | yes |  |
| `skills[].name` | string | yes |  |
| `skills[].tags` | array |  |  |
| `supported_interfaces` | array | yes | A2A `supportedInterfaces` (1.0 — substituiu o `url` único das versões anteriores). Cada entrada nomeia um BINDING de protocolo e onde alcançá-lo. |
| `supported_interfaces[].protocol_binding` | string | yes | Um de: `JSONRPC`, `GRPC`, `HTTP+JSON`. |
| `supported_interfaces[].protocol_version` | string |  | A2A `protocolVersion` da interface (`"1.0"`). Opcional: a 1.0 permite omiti-lo, e o cliente oficial trata a ausência como "sem preferência" em vez de erro. |
| `supported_interfaces[].url` | string | yes | HTTPS obrigatório. Delegar dado de workspace por texto claro seria exfiltração com um passo a menos. |
| `version` | string |  | A2A `version` — a versão QUE O AGENTE declara de si. |

## Repo

- **Alias:** `portfolio-repo`
- **apiVersion:** `github.com/ruinosus/dna/portfolio/v1`
- **Plane:** record

A Repo is a code repository the portfolio references — its name, url, provider (github / gitlab / azure-devops / other) and default_branch, as per-tenant declarative data. It is attached to N Projects via Project.repo_refs (the N—N edge lives on the Project side); a Repo carries no project back-ref, so a repo shared across projects is never duplicated. "Which projects use this repo" is a query over Projects, not a stored reverse list.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `created_at` | string \| null |  | ISO-8601 timestamp, stamped by the writer (not defaulted here). |
| `default_branch` | string \| null |  | The repo's default branch, e.g. main. Null when unknown. |
| `name` | string | yes | The repo name, e.g. copiloto-medico. The doc name SHOULD equal this; Project.repo_refs point at it. |
| `provider` | string |  | Where the repo is hosted — github, gitlab, azure-devops, or other. Um de: `github`, `gitlab`, `azure-devops`, `other`. |
| `url` | string \| null |  | Clone / browse URL of the repository. Null when the name alone identifies it. |

## Retrospective

- **Alias:** `sdlc-retrospective`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Retrospective captures lessons + action items from a period of work. Schema follows Atlassian 4 Ls (Loved/Loathed/Longed for/Learned) — what_went_well, what_didnt, action_items. Adopt for sprint retros, release retros, incident retros. For one architectural decision, use ADR. For one incident factual analysis, use Postmortem (Phase 3 — TBD).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `action_items` | array |  | Concrete next-steps surfaced by the retro. |
| `action_items[].due` | string |  |  |
| `action_items[].owner` | string |  |  |
| `action_items[].story_ref` | string |  | Optional Story slug if turned into work. |
| `action_items[].title` | string | yes |  |
| `actor` | string |  | Who wrote this retro (Actor name, 'claude-code', 'human', ...). |
| `auto_generated` | boolean |  | true = LLM-generated draft; false = human-curated. |
| `body` | string |  | Optional full markdown body (RETROSPECTIVE.md). Falls back from structured fields when present. |
| `covers_epics` | array |  | Epic names this retro discusses. |
| `covers_features` | array |  | Feature names this retro discusses. |
| `covers_session` | string |  | AgentSession name (Karpathy pattern). |
| `covers_stories` | array |  | Story names this retro discusses. |
| `created_at` | string |  |  |
| `intent` | string |  | What kind of retro this is. Drives Studio grouping — daily stack on timeline, releases pin as marquee, incidents surface in alert filter. Um de: `daily`, `weekly`, `sprint`, `release`, `incident`, `freeform`. |
| `learned` | array |  | Learned — insights surfaced during the period. Atlassian 4 Ls bucket #4. Feeds future ADRs. |
| `longed_for` | array |  | Longed for — capabilities/conditions wished for but absent. Atlassian 4 Ls bucket #3. |
| `narrative_origin` | string |  | When extracted from a Narrative during Phase 2.2 migration, this points to the source Narrative slug for provenance. |
| `open_items` | array |  | Work that started but didn't close — carry-over to next period. |
| `open_items[].blocker` | string |  |  |
| `open_items[].owner` | string |  |  |
| `open_items[].title` | string | yes |  |
| `period_end` | string | yes | End of period covered. |
| `period_start` | string | yes | Start of period covered (ISO-8601). |
| `summary` | string |  | Optional one-line tl;dr (shown above body in Studio card). |
| `tags` | array |  | Free-form tags. |
| `title` | string | yes | Headline for this retrospective. |
| `updated_at` | string |  |  |
| `what_didnt` | array |  | Loathed / Lacked — things that didn't work or caused friction. Atlassian 4 Ls bucket #2. |
| `what_went_well` | array |  | Loved / Liked — things that worked in this period. Atlassian 4 Ls bucket #1. |

## RiskRegister

- **Alias:** `sdlc-risk-register`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

One risk entry per RiskRegister doc. PMBOK 7 + ISO 31000:2018 compliant schema: cause→event→consequence description, category, likelihood × impact scoring, mitigation actions, residual score, owner, status lifecycle. Studio aggregates all RiskRegister docs into a heatmap.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string |  |  |
| `category` | string | yes | PMBOK 7 categorization. Um de: `strategic`, `operational`, `financial`, `compliance`, `reputational`, `cyber`, `ESG`. |
| `created_at` | string |  |  |
| `description` | string | yes | Risk in cause→event→consequence format. ISO 31000 convention: 'If <cause>, then <event> may occur, resulting in <consequence>'. |
| `impact` | integer | yes | 1=negligible, 5=catastrophic. |
| `inherent_score` | integer |  | likelihood × impact (auto-derivable). |
| `last_reviewed` | string |  |  |
| `likelihood` | integer | yes | 1=rare, 5=almost certain. |
| `mitigation_actions` | array |  |  |
| `mitigation_actions[].action` | string | yes |  |
| `mitigation_actions[].due` | string |  |  |
| `mitigation_actions[].owner` | string |  |  |
| `mitigation_actions[].status` | string |  | Um de: `todo`, `in-progress`, `done`. |
| `mitigation_actions[].story_ref` | string |  |  |
| `next_review_due` | string |  |  |
| `owner` | string | yes | Actor name accountable for monitoring/mitigation. |
| `related_epics` | array |  |  |
| `related_features` | array |  |  |
| `residual_impact` | integer |  |  |
| `residual_likelihood` | integer |  | Likelihood after mitigation. |
| `residual_score` | integer |  |  |
| `response` | string |  | Strategy: avoid\|transfer\|mitigate\|accept. Um de: `avoid`, `transfer`, `mitigate`, `accept`. |
| `status` | string | yes | Lifecycle: identified → assessed → mitigated → (realized = risk happened) → closed. Um de: `identified`, `assessed`, `mitigated`, `realized`, `closed`. |
| `tags` | array |  |  |
| `title` | string |  | Short risk name (used as doc name typically). |
| `updated_at` | string |  |  |

## Roadmap

- **Alias:** `sdlc-roadmap`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Roadmap groups Epics across time horizons (e.g. Q1 2026, Q2 2026). Pure organizational doc — no status of its own; the rolled-up status comes from the Epics it lists.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `description` | string | yes |  |
| `horizons` | array | yes |  |
| `horizons[].end_date` | string |  |  |
| `horizons[].epics` | array | yes | Names of Epic docs in this horizon |
| `horizons[].label` | string | yes | e.g. 'Q1 2026' |
| `horizons[].start_date` | string |  |  |
| `journey_phase` | string |  | Universal journey phase. Roadmaps typically live in `discover` or `specify` — they're the north star, not the build. Um de: `discover`, `specify`, `plan`, `build`, `verify`, `reflect`. |
| `links` | array |  | External URLs (Confluence, Notion, etc.) |
| `owner_team` | string |  |  |

## Role

- **Alias:** `portfolio-role`
- **apiVersion:** `github.com/ruinosus/dna/portfolio/v1`
- **Plane:** record

A Role is one rung of the RBAC ladder expressed as data — its role_id, display_name, rank (higher = more access), the capabilities it grants, and a can_delete flag protecting built-in rungs. Modelling the ladder as data (not a hardcoded enum) makes it extensible — a tenant can add a custom role without a code change, and highest-role-wins simply compares rank. The four standard rungs (owner / admin / member / guest) ship as per-tenant seed docs; the org owner is a superuser above the ladder.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `can_delete` | boolean |  | False for the built-in ladder rungs that must not be removed (e.g. owner); true for custom roles a tenant adds. |
| `capabilities` | array |  | The grants this role unlocks (e.g. project.write, member.invite, billing.manage). The permission checker reads them from here. |
| `display_name` | string | yes | Human-facing role name, e.g. Owner, Admin, Member, Guest. |
| `rank` | integer | yes | Ladder rank — higher = more access. highest-role-wins compares this across a user's memberships. |
| `role_id` | string | yes | Canonical role id, e.g. owner / admin / member / guest. The doc name SHOULD equal this; Membership.role references it. |

## Solution

- **Alias:** `helix-solution`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** record

A Solution is the DECLARATION of a repo generated from Copier templates, plus the ANSWERS that generated it — never the code and never the template body. It is the second view of the `.copier-answers.<service>.yml` files a `dna solution new` writes, and the only one that OUTLIVES them: a `when:`-gated answer is erased from the file when its condition stops holding, and a record that survives the file is the only place such a value can survive (measured — see `docs/guides/solution-scaffolding.md`). `dna solution update --solution <name>` reads the answers back from here and re-passes them to Copier, which is what makes a version floor recorded here reach the generated tree instead of staying behind in silence. One entry in `services[]` per answers file — one template overlaid N times is the design, not one template of the whole repo. The per-service `answers` map is deliberately free-form (the vocabulary belongs to the TEMPLATE); `pode_dormir` is the one fact promoted out of it, because a cost commitment must be readable across the fleet without knowing which template asked. `apps` is a declared RELATION to `App` — the sellable unit this solution's code delivers, never one it creates. `services[].name` and `App.service_name` address the same axis, the CODE, and that is the join between the two — not a bijection: one layer here can be the code of N Apps (measured — dna-cloud runs 9 deployable services over 4 `apps/` directories). `services[].pode_dormir` is the DERIVED, per-layer half of the cost question; `App.can_sleep` is the AUTHORED, per-deployment half, and the bill is per deployment.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `apps` | array |  | Os `App`s que esta solução ENTREGA, por nome de instância — a unidade vendável, que continua sendo do `App` e do runtime que a serve. Referência validada na gravação (`spec.relations`). Vazio é o caso comum e não é uma lacuna - o próprio dna-cloud gera nove serviços e nenhum `App`. |
| `criado_em` | string \| null |  | Quando esta solução foi declarada (ISO-8601, relógio de quem gravou). Preservado nas gravações seguintes - um `update` que acrescenta uma camada não recria a solução. |
| `criado_por` | string \| null |  | A identidade verificada de quem criou esta solução, resolvida a partir da sessão - nunca digitada. Mesmo molde de `SourceArtifact.uploaded_by` e `CopilotBlueprint.criado_por`; não há Kind de pessoa para apontar, e por isso não é uma relação. Vazio é uma AFIRMAÇÃO - a solução é anterior ao registro existir, e ninguém sabe quem a criou. |
| `description` | string |  | Uma linha do que esta solução entrega. |
| `repo` | string |  | Onde a árvore gerada vive (URL do git ou caminho). É um ENDEREÇO, não um conteúdo — nada aqui guarda o que está lá dentro. Vazio quando a solução ainda não foi gerada em lugar nenhum. |
| `services` | array | yes | Uma entrada POR CAMADA — e uma camada é um answers file, que é um app. Nove serviços sobre quatro imagens são nove entradas aqui, quatro `template.src` distintos, e nove updates independentes. Nunca um template do repo inteiro (§4.4 regra 3). |
| `services[].answers` | object |  | As respostas desta camada, VERBATIM, no vocabulário do template. Mapa livre de propósito - o conjunto de perguntas é do template e muda com ele, e nenhuma chave é obrigatória porque uma resposta atrás de `when:` legitimamente desaparece (medido - exigir uma seria recusar a gravação exatamente do caso que este registro existe para socorrer). Copier já filtra o próprio bookkeeping (`_src_path`, `_commit`) para os campos `template` acima; ele não se repete aqui. |
| `services[].answers_file` | string | yes | O caminho do `.copier-answers.<name>.yml` RELATIVO à raiz da árvore gerada — o endereço da outra vista deste mesmo fato. Gravado verbatim, nunca derivado do `name` — a convenção do arquivo é declarada pelo template (`_answers_file`), e um Kind que a recalculasse estaria adivinhando a decisão de outro autor. |
| `services[].name` | string | yes | O nome desta camada — o que `dna solution update --service <name>` recebe. Endereça o CÓDIGO, e é o mesmo eixo que `App.service_name`, que é a junção entre este Kind e a unidade vendável. ⚠️ Não é uma bijeção com `App`: medido no dna-cloud em 07/08/2026, 9 serviços implantáveis rodam sobre 4 diretórios `apps/`, então uma camada daqui pode ser o código de N `App`s (`apps/mcp/` serve `mcp`, `mcp-entra` e `mcp-ws`). |
| `services[].pode_dormir` | boolean |  | Este app pode escalar a zero. É o ÚNICO fato promovido para fora de `answers`, e a razão é que ele não é um detalhe de render - é um COMPROMISSO DE CUSTO. Um app que não dorme custa uma réplica fixa, ~US$ 90/mês, para sempre (o portão de custo do CLAUDE.md do dna-cloud, que já custou essa conta uma vez). Promovido porque quem soma a frota precisa responder "quantos não dormem?" SEM saber que este template chamou a pergunta de `can_sleep` e o próximo vai chamar de outra coisa. Ausente significa que esta camada NUNCA respondeu a pergunta de custo - e isso é um achado reportado a cada execução, nunca um `false` presumido — presumir o lado barato esconderia justamente a réplica que ninguém decidiu. ⚠️ Não confundir com `App.can_sleep`, que NÃO é uma duplicata deste campo. Aqui a resposta é DERIVADA do Copier e vale por CAMADA (por diretório de código); lá ela é AUTORADA e vale por DEPLOYMENT. A fatura é por deployment, então a resposta que paga é a do `App` - `apps/mcp/` responde aqui uma vez e serve três portas que podem dormir diferente. |
| `services[].template` | object | yes | O PONTEIRO para o template, nunca o corpo dele. |
| `services[].template.ref` | string |  | A tag/commit em que esta camada está (o `_commit` do answers file) — o que o próximo `update` move. Vazio significa que a camada nunca foi renderizada a partir de um clone versionado, e portanto não pode ser atualizada; não significa "a mais recente". |
| `services[].template.src` | string | yes | O que o Copier aceita como origem — um caminho local, uma URL git, `gh:owner/repo`. É o `_src_path` do answers file. |
| `title` | string | yes | O nome que um humano usa para esta solução — o repo, o produto, a linha de montagem. O `metadata.name` é o slug. |

## SourceArtifact

- **Alias:** `artifact-source`
- **apiVersion:** `github.com/ruinosus/dna/artifact/v1`
- **Plane:** record

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `derived_refs` | array |  | The typed instances extracted from this artifact — the projection. The edge lives HERE, on the artifact, so one upload that yields twelve instances states that fact once, and so no derived Kind has to carry a field for it. Grows as more is extracted; an empty list means the file is stored and nothing has been read out of it yet, which is an honest state and not an error. |
| `derived_refs[].extracted_at` | string \| null |  | ISO-8601 timestamp of the extraction. |
| `derived_refs[].kind` | string | yes | The derived instance's Kind. |
| `derived_refs[].name` | string | yes | The derived instance's name within that Kind. |
| `derived_refs[].scope` | string \| null |  | The scope it was written to, when it differs from the artifact's own. |
| `detected_mime` | string \| null |  | What the bytes ACTUALLY are, read from their magic bytes (`dna.runtime.mime.detect_mime`). Kept BESIDE `mime`, never instead of it: the pair is the evidence. Overwriting the declared value would erase the fact that they ever disagreed, and that disagreement is the only thing either field is good for on its own. |
| `filename` | string \| null |  | The name the file arrived with, when one did. Display only — never a path to open, and never trusted as one. |
| `mime` | string \| null |  | The declared content type, e.g. application/pdf. What the uploader SAID it is; not proof of what it is. |
| `mime_mismatch` | boolean \| null |  | True when `detected_mime` and what the caller declared (or the filename implied) diverge in a way that matters. NOT an error and NOT a refusal — a `.pdf` that is really a ZIP may be an innocent mistake or an attempt, and a record that cannot tell you it happened cannot help you decide which. OOXML detected as its zip container and variation within text do NOT count; a signal that fires on half the uploads is a signal nobody reads. |
| `origin` | string \| null |  | Where the bytes came from. `uploaded` — a human attached the file; `generated` — an agent produced it (an image, a chart, a converted file). The distinction is not cosmetic: a generated artifact is REPRODUCIBLE and a retention policy may treat it very differently from an original nobody else holds a copy of. Um de: `uploaded`, `generated`, `None`. |
| `sha256` | string | yes | Lowercase hex SHA-256 of the ORIGINAL bytes. The content address: it is what lets anyone holding the file verify that this record and those bytes belong together, and what makes a re-upload of identical content the same artifact rather than a second one. |
| `size_bytes` | integer \| null |  | Size of the original in bytes, when known. |
| `uploaded_at` | string \| null |  | ISO-8601 timestamp of the upload. |
| `uploaded_by` | string \| null |  | The verified identity that uploaded it, resolved server-side from the request. Never a caller-supplied field. |
| `uri` | string | yes | Where the bytes live — an IDENTITY, never a credential. Never a signed URL or SAS token: an instance carrying one would BE the access to its own original, and would grant it to anyone the instance reaches. Reading goes through an authenticated route that checks membership. |

## Spec

- **Alias:** `sdlc-spec`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Spec is a top-level design artifact. Cross-cutting by default (may drive multiple Features). Pattern-agnostic — superpowers, BMAD, droid, RFC, ADR, Spec Kit all work. status is ADR-style, widened at both terminal ends (draft → proposed → accepted → executed | shelved | deprecated | superseded): `executed` means the design became code, `shelved` means 'not now' with the design still valid — neither of which `deprecated` (no longer applicable) may be stretched to mean. phase is the orthogonal SDLC view (brainstorm → spec → plan_ready → implementing → done). Linkage to work is via Story.spec_refs[] (M:N), NOT via Spec.feature — the axis flip preserves Jira/Confluence semantics.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `authors` | array |  |  |
| `body` | string |  | Markdown body of the spec (stored in SPEC.md). |
| `date` | string | yes |  |
| `deprecated_at` | string |  | When the design stopped applying (status=deprecated). |
| `deprecation_reason` | string |  | WHY the design no longer applies (`dna sdlc spec deprecate --reason`). |
| `epic` | string |  |  |
| `executed_at` | string |  | When the design became code (status=executed). |
| `execution_summary` | string |  | THE PROOF the design became code — PRs, commits, releases. Required by `dna sdlc spec executed`: a terminal state nobody can audit is a claim, not a record. |
| `journey_phase` | string |  | Universal journey phase. A Spec typically lives in `specify`, but draft Specs may be `discover` and finalized ones referenced by Plans drift to `plan`. Coexists with `phase` (SDLC-view) — `journey_phase` is the methodology-agnostic layer. Um de: `discover`, `specify`, `plan`, `build`, `verify`, `reflect`. |
| `origin` | string |  | Optional audit trail — repo-relative path the body was harvested from (e.g. docs/superpowers/specs/X.md). Not used at runtime. |
| `pattern` | string |  | Spec-driven pattern this artifact follows (superpowers \| bmad \| droid \| rfc \| adr \| spec-kit \| custom). |
| `phase` | string |  | Where in the SDLC this spec's work sits. Orthogonal to status. Um de: `brainstorm`, `spec`, `plan_ready`, `implementing`, `done`. |
| `shelve_reason` | string |  | The decision and WHY. Required by `dna sdlc spec shelve` — the design stays valid, so the next reader needs to know what would have to change for it to be 'now'. |
| `shelved_at` | string |  | When the direction was decided as 'not now' (status=shelved). |
| `status` | string | yes | Lifecycle: draft → proposed → accepted → executed\|shelved\|deprecated\|superseded. `executed` = the design became code (terminal, positive — carries `execution_summary` as the proof). `shelved` = decided as 'not now', design still valid (terminal, neutral, reversible — carries `shelve_reason`). `deprecated` = no longer applicable. `superseded` = replaced (link via `supersedes` on the replacement). Um de: `draft`, `proposed`, `accepted`, `deprecated`, `superseded`, `executed`, `shelved`. |
| `summary` | string |  | Short one-paragraph summary (auto-extracted). |
| `supersedes` | string |  | Name of the prior Spec this one replaces. |
| `tags` | array |  |  |
| `title` | string | yes |  |

## Spike

- **Alias:** `sdlc-spike`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Spike is a time-boxed technical investigation. ONE question + finite time budget + outcome handoff (findings → Story or ADR). Distinct from Story (work to ship) e ADR (decision já tomada).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `body` | string |  |  |
| `completed_at` | string |  |  |
| `created_at` | string |  |  |
| `feature` | string |  |  |
| `findings` | string |  |  |
| `follow_up_adr` | string |  |  |
| `follow_up_spec` | string |  |  |
| `follow_up_story` | string |  |  |
| `html_artifacts` | array |  | HtmlArtifact names attached to this Spike (rendered mockups, diagrams, design comparisons). |
| `labels` | array |  |  |
| `logged_hours` | number |  |  |
| `owner` | string |  |  |
| `produces` | array |  | Artifacts this work item produced — any Kind (hub). |
| `produces[].at` | string |  |  |
| `produces[].kind` | string | yes | Artifact Kind (any). |
| `produces[].name` | string | yes | Artifact doc name. |
| `produces[].role` | string |  | Optional role hint (e.g. visual-spec, plan, investigation). |
| `question_to_answer` | string | yes |  |
| `recommendation` | string |  |  |
| `references` | array |  | Free-form Reference names (papers, blog posts, library docs cited mid-spike). |
| `related_spikes` | array |  | Sibling Spikes investigating overlapping questions. |
| `research_refs` | array |  | Research names this Spike consulted (curated syntheses with N References). |
| `started_at` | string |  |  |
| `status` | string | yes | Um de: `proposed`, `in-progress`, `answered`, `abandoned`. |
| `time_box_hours` | number |  |  |
| `timeline` | array |  | Append-only activity log. Auto-stamped by the CLI on every status flip / groom / artifact write; populated by AgentSession capture for decision + artifact_produced events. Render in Studio as activity stream. |
| `timeline[].actor` | string | yes | Who triggered the event (Actor name or 'claude-code'). |
| `timeline[].at` | string | yes |  |
| `timeline[].commit_ref` | string |  | Git SHA associated with this event (when relevant). |
| `timeline[].excerpt` | string |  | decision: snippet from the source transcript. |
| `timeline[].fields` | object |  | groom: which fields changed and to what. |
| `timeline[].from` | string |  | status_change: previous status. |
| `timeline[].paths` | array |  | artifact_produced: file paths touched. |
| `timeline[].session_ref` | string |  | Back-link to a AgentSession that produced this event. |
| `timeline[].source` | string |  | Um de: `cli`, `studio`, `mcp`, `agent-session-extracted`, `system`. |
| `timeline[].summary` | string |  | comment/decision: short human-readable text. |
| `timeline[].to` | string |  | status_change: new status. |
| `timeline[].type` | string | yes | Event type. Recognized: status_change, groom, comment, decision, artifact_produced (open vocabulary — new types are additive, e.g. pr_opened). |
| `title` | string | yes |  |
| `updated_at` | string |  |  |

## Sprint

- **Alias:** `sdlc-sprint`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Sprint is the timebox that `Story.sprint_ref` and `Feature.sprint_ref` name — an identifier (`2026-Q2-S2`), optionally a display name, a start/end date and a state (planned/active/completed). The instance NAME is the key the two references resolve by. Membership is NOT stored here — it is the inverse of `sprint_ref` and is derived from the declared reference, so there is exactly one place a story's sprint is written. Goal, capacity and velocity are deliberately absent until a consumer exists for them.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `ends_on` | string | yes | Last day of the timebox (ISO 8601 date). REQUIRED, same reason as starts_on. |
| `name` | string \| null |  | Human display name, e.g. 'Sprint 2 — Q2 2026'. Editable; the identity is sprint_id / the doc name, never this. |
| `sprint_id` | string | yes | Canonical sprint identifier, e.g. '2026-Q2-S2'. THE DOC NAME MUST EQUAL IT — `Story.sprint_ref` / `Feature.sprint_ref` are declared references and resolve by instance name, so a doc whose name and sprint_id disagree is reachable under one of them only. Enforced on write by the sdlc write guards, not left to convention. |
| `starts_on` | string | yes | First day of the timebox (ISO 8601 date). REQUIRED — a sprint IS a timebox, and one that cannot say when it starts is a label with a Kind wrapped around it. |
| `state` | string |  | Where the timebox is in its life. Kept as data rather than derived from the dates because the dates are optional and because a sprint can be closed early — the same three-state vocabulary Jira (future/active/closed) and Azure DevOps iterations use. Um de: `planned`, `active`, `completed`. |

## StatusReport

- **Alias:** `sdlc-status-report`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `ascended_from` | string |  | If the previous verdict's confidence differs from this one, this is the previous level. Empty string when it's the first verdict. Um de: `certain`, `guess`, `insufficient`, ``. |
| `bumped_remembrances` | array |  | Phase 2B (squishy-jumping-nebula): audit trail written by oracle_cue_hook listing the LessonLearned slugs whose cue history was bumped because this report cited them. Bidirectional pairing with LessonLearned.cues_history. Empty when the run had nothing to bump (the field is omitted, not stored as []). |
| `confidence` | string | yes | How firm the verdict is. `insufficient` = the heuristic didn't have enough data — the LLM was NOT called and the verdict is a stock message. Um de: `certain`, `guess`, `insufficient`. |
| `evidence_refs` | array |  | Doc refs (Kind/name) cited as evidence for this verdict. Studio renders these as navigable links. |
| `generated_at` | string |  |  |
| `generated_by` | string |  | Model + actor (e.g. 'claude-sonnet-4-6'). |
| `heuristic_explanation` | string |  | Plain-text walkthrough of HOW the heuristic computed the metrics and decided the confidence. Transparency: a reader can audit the math. |
| `insight` | string | yes | Free-text marker for what produced this report. Was a slug reference to an Insight Kind; that Kind was deleted in censo-12-kinds (2026-07-20) because the oracle runner that resolved it never shipped. The only live producer, `dna sdlc digest --save`, already wrote the synthetic marker 'sdlc-digest' here rather than an Insight slug — so the field stays, as the free-text tag it actually is. |
| `metrics` | object |  | Deterministic numbers the heuristic computed (cycle counts, frequencies, averages). Free-form object — schema varies per oracle. |
| `owner` | string |  | Slug reference to a Agent. When set, this StatusReport is PRIVATE to that agent. When null, it is GENERAL. Phase: cognitive-reflection. |
| `question` | string |  | The question this report answers, written out. Was an echo of an Insight's question at run time; no runner ships, so the author writes it. |
| `rag_status` | string |  | PMO-standard RAG status (Red/Amber/Green) for executive dashboards. Red = action needed; Amber = watch; Green = healthy. Optional — heuristics that map metrics → RAG should populate this. Um de: `red`, `amber`, `green`. |
| `thresholds` | object |  | Self-describing thresholds the heuristic used (e.g. `to_certain: 'pattern_freq > 0.9 AND n>=5'`). Lets the reader know what would change the verdict. |
| `verdict` | string | yes | Human-readable answer (1-3 sentences pt-BR). Synthesized by the LLM from the heuristic numbers. |

## Story

- **Alias:** `sdlc-story`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Story is a granular task: one developer, one PR, one estimate. Lists acceptance criteria, dependencies (other Stories that must land first), and rolls up to a Feature.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `acceptance_criteria` | array |  | Acceptance criteria. Legacy: list[str]. New (s-ac-dod-checklist-state): list[{text, done?, done_at?, done_by?}] for per-item state tracking. |
| `as_a` | string |  | Role: 'As a <role>'. INVEST/user-story format slot. |
| `blocked_reason` | string |  |  |
| `business_value` | number |  | WSJF-style scalar for relative prioritization. |
| `closed_at` | string |  |  |
| `created_at` | string |  |  |
| `definition_of_done` | array |  | Per-Story DoD. Same union shape as acceptance_criteria — legacy list[str] OR list[{text, done?, done_at?, done_by?}]. |
| `dependencies` | array |  | Other Story names that must land first |
| `description` | string | yes |  |
| `estimate` | number |  | Fibonacci story points (1, 2, 3, 5, 8, 13, 21) |
| `feature` | string |  | Parent Feature name |
| `i_want` | string |  | Goal: 'I want <goal>'. INVEST/user-story format slot. |
| `journey_phase` | string |  | Universal journey phase (discover → specify → plan → build → reflect). Additive layer over Story/Feature/Epic status, Spec phase, etc. Lets the journey ledger pin this doc to one of five universal phases compatible with Superpowers / BMAD / Spec Kit / Kiro. Um de: `discover`, `specify`, `plan`, `build`, `verify`, `reflect`. |
| `labels` | array |  | Free-form tags for swim lanes / filters. |
| `mockups` | array |  | URLs/paths to design artifacts. |
| `owner` | string |  | Actor name |
| `priority` | string |  | Board priority. Jira-aligned. Um de: `highest`, `high`, `medium`, `low`, `lowest`. |
| `produces` | array |  | Artifacts this work item produced — any Kind (hub). |
| `produces[].at` | string |  |  |
| `produces[].kind` | string | yes | Artifact Kind (any). |
| `produces[].name` | string | yes | Artifact doc name. |
| `produces[].role` | string |  | Optional role hint (e.g. visual-spec, plan, investigation). |
| `release_target` | string |  | Epic name OR 'owner/pkg@semver' identifying the release this Story unblocks. |
| `reporter` | string |  | Actor who filed it (vs `owner` who works on it). |
| `so_that` | string |  | Benefit: 'so that <benefit>'. INVEST/user-story format slot. |
| `spec_refs` | array |  | Spec docs (kind=Spec) this Story implements. M:N linkage between the planning axis (Story) and the design axis (Spec) — Jira/Confluence-shaped. |
| `sprint_ref` | string |  | The Sprint this Story is committed to — the Sprint instance's NAME, which is also its sprint_id (e.g. '2026-Q2-S2'). DECLARED (i-040), so the write path resolves it instead of trusting a label. The value SHAPE did not change on 2026-08-06; a `Sprint` Kind simply started existing for the identifier to name. |
| `status` | string | yes | Um de: `needs-triage`, `todo`, `in-progress`, `review`, `done`, `blocked`, `deferred`, `cancelled`. |
| `time_tracking` | object |  |  |
| `time_tracking.logged_h` | number |  |  |
| `time_tracking.original_estimate_h` | number |  |  |
| `time_tracking.remaining_h` | number |  |  |
| `timeline` | array |  | Append-only activity log. Auto-stamped by the CLI on every status flip / groom / artifact write; populated by AgentSession capture for decision + artifact_produced events. Render in Studio as activity stream. |
| `timeline[].actor` | string | yes | Who triggered the event (Actor name or 'claude-code'). |
| `timeline[].at` | string | yes |  |
| `timeline[].commit_ref` | string |  | Git SHA associated with this event (when relevant). |
| `timeline[].excerpt` | string |  | decision: snippet from the source transcript. |
| `timeline[].fields` | object |  | groom: which fields changed and to what. |
| `timeline[].from` | string |  | status_change: previous status. |
| `timeline[].paths` | array |  | artifact_produced: file paths touched. |
| `timeline[].session_ref` | string |  | Back-link to a AgentSession that produced this event. |
| `timeline[].source` | string |  | Um de: `cli`, `studio`, `mcp`, `agent-session-extracted`, `system`. |
| `timeline[].summary` | string |  | comment/decision: short human-readable text. |
| `timeline[].to` | string |  | status_change: new status. |
| `timeline[].type` | string | yes | Event type. Recognized: status_change, groom, comment, decision, artifact_produced (open vocabulary — new types are additive, e.g. pr_opened). |
| `title` | string |  | Human-readable display name (Jira 'summary'). |
| `updated_at` | string |  |  |
| `watchers` | array |  | Actor names subscribed to changes. |

## Task

- **Alias:** `sdlc-task`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

A Task is a granular work item (horas-dias) typically as sub-item of a Story. For multi-day deliverables use Story.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `blocked_reason` | string |  |  |
| `body` | string |  |  |
| `closed_at` | string |  |  |
| `created_at` | string |  |  |
| `description` | string |  |  |
| `due` | string |  |  |
| `estimate_hours` | number |  |  |
| `labels` | array |  |  |
| `logged_hours` | number |  |  |
| `owner` | string |  |  |
| `priority` | string |  | Um de: `highest`, `high`, `medium`, `low`, `lowest`. |
| `produces` | array |  | Artifacts this work item produced — any Kind (hub). |
| `produces[].at` | string |  |  |
| `produces[].kind` | string | yes | Artifact Kind (any). |
| `produces[].name` | string | yes | Artifact doc name. |
| `produces[].role` | string |  | Optional role hint (e.g. visual-spec, plan, investigation). |
| `status` | string | yes | Um de: `todo`, `in-progress`, `done`, `blocked`, `cancelled`. |
| `story_ref` | string |  |  |
| `timeline` | array |  | Append-only activity log. Auto-stamped by the CLI on every status flip / groom / artifact write; populated by AgentSession capture for decision + artifact_produced events. Render in Studio as activity stream. |
| `timeline[].actor` | string | yes | Who triggered the event (Actor name or 'claude-code'). |
| `timeline[].at` | string | yes |  |
| `timeline[].commit_ref` | string |  | Git SHA associated with this event (when relevant). |
| `timeline[].excerpt` | string |  | decision: snippet from the source transcript. |
| `timeline[].fields` | object |  | groom: which fields changed and to what. |
| `timeline[].from` | string |  | status_change: previous status. |
| `timeline[].paths` | array |  | artifact_produced: file paths touched. |
| `timeline[].session_ref` | string |  | Back-link to a AgentSession that produced this event. |
| `timeline[].source` | string |  | Um de: `cli`, `studio`, `mcp`, `agent-session-extracted`, `system`. |
| `timeline[].summary` | string |  | comment/decision: short human-readable text. |
| `timeline[].to` | string |  | status_change: new status. |
| `timeline[].type` | string | yes | Event type. Recognized: status_change, groom, comment, decision, artifact_produced (open vocabulary — new types are additive, e.g. pr_opened). |
| `title` | string | yes |  |
| `updated_at` | string |  |  |

## Tool

- **Alias:** `helix-tool`
- **apiVersion:** `github.com/ruinosus/dna/v1`
- **Plane:** record

A Tool is a declarative, invocable capability an agent can call — an HTTP endpoint, an MCP server tool, a Python callable, a shell command, or a builtin. It bridges DNA with OpenAI/Anthropic tool-calling conventions. The agent-facing surface is its ``metadata.description`` (the text the model reads to decide to call it) and its ``spec.input_schema`` (the "parameters" JSON Schema of the arguments); ``dna.load_tools`` / ``loadTools`` serve exactly that surface, identically to Python and TypeScript consumers from this one source. It also declares an auth strategy and read_only / requires_confirmation flags the host honors at runtime. Agents reference Tools via ``dep_filters.tools``. Stored as ``tools/<name>.yaml`` — marketplace-shareable as standalone bundles.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `auth_env_var` | string |  | Environment variable holding the credential (e.g. GITHUB_TOKEN). |
| `auth_type` | string |  | Credential strategy for the invocation. Um de: `none`, `api_key`, `bearer`, `oauth2`. |
| `endpoint` | string |  | URL called when type=http. Supports {placeholder} templating. |
| `examples` | array |  | Usage examples ([{input, output}]). |
| `input_schema` | object |  | JSON Schema of the arguments the agent passes when invoking the tool — the "parameters" the model fills in. Surfaced as ``parameters`` by ``dna.load_tools`` / ``loadTools``. |
| `mcp_server` | string |  | MCP server name when type=mcp. |
| `mcp_tool` | string |  | Tool name on the MCP server when type=mcp. |
| `method` | string |  | HTTP method when type=http (default POST). |
| `output_schema` | object |  | JSON Schema describing the shape of the tool's response. |
| `python_callable` | string |  | Attribute on the module (function or class) when type=python. |
| `python_module` | string |  | Dotted import path when type=python. |
| `read_only` | boolean |  | False = the tool may mutate state (DB writes, file changes, external side effects). |
| `requires_confirmation` | boolean |  | Force user approval before each invocation. |
| `shell_command` | string |  | Command template when type=shell. Never executed without confirmation. |
| `tags` | array |  | Free-form labels for filtering and search. |
| `type` | string |  | How the tool is executed. builtin \| http \| mcp \| python \| shell. Um de: `http`, `mcp`, `python`, `shell`, `builtin`. |

## WorkflowEvent

- **Alias:** `sdlc-workflow-event`
- **apiVersion:** `github.com/ruinosus/dna/sdlc/v1`
- **Plane:** record

Append-only journey ledger. One entry per (artifact, phase) pair. Read together as a sequence, they form the trail from discover → reflect for a Roadmap/Epic/Feature. DNA's methodology-agnostic layer — Superpowers / BMAD / Spec Kit all map onto it via the `methodology` field.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `actor` | string |  | Who recorded the transition. |
| `artifact_kind` | string |  | Back-compat (deprecated): legacy Kind half of ``ref``. |
| `artifact_name` | string |  | Back-compat (deprecated): legacy name half of ``ref``. |
| `auto_emitted_by` | string |  | Back-compat (deprecated): legacy form of ``actor``. |
| `closes_cycle` | boolean |  | True on a `reflect` entry that has been closed by `journey close-cycle` — marks the boundary where the next discover starts cycle N+1. Set automatically; client may use as the explicit cycle delimiter. |
| `created_at` | string |  |  |
| `cycle_index` | integer |  | 1-based cycle number this entry belongs to. All entries within the same ouroboros loop share the same cycle_index. Incremented when `journey close-cycle` opens the next discover. Backend-explicit alternative to client-side heuristic cycle detection. |
| `decision_text` | string |  | Back-compat (deprecated): free-text decision on the entry. |
| `decisions` | string |  | Back-compat (deprecated): legacy decisions note on the entry. |
| `ended_at` | string |  | When the agent left this phase. Null while the phase is still active. |
| `epic_ref` | string |  | Back-compat (deprecated): legacy form of ``parent_ref`` (Epic). |
| `feature_ref` | string |  | Back-compat (deprecated): legacy form of ``parent_ref`` (Feature). |
| `methodology` | string |  | Which methodology the agent followed in this phase. ``ad-hoc`` is honest — Studio renders it with a 'no methodology' badge so we can spot where we cut corners. Um de: `superpowers`, `bmad`, `spec-kit`, `kiro`, `rfc`, `adr`, `ad-hoc`, `custom`. |
| `methodology_artifact` | string |  | Repo-relative path or URL to the methodology's external artifact, when applicable. E.g. ``docs/superpowers/plans/foo-plan.md`` for the Superpowers writing-plans output, ``.specify/foo/plan.md`` for Spec Kit, etc. |
| `owner` | string |  | Back-compat (deprecated): legacy owner of the entry. |
| `parent_ref` | string |  | Anchor doc grouping this entry with siblings. Typically ``Feature/<name>`` or ``Epic/<name>`` — everything in the journey of one Feature has the same parent_ref. |
| `phase` | string | yes | Which of the five universal phases this entry represents. Um de: `discover`, `specify`, `plan`, `build`, `verify`, `reflect`. |
| `rationale` | string |  | Back-compat (deprecated): free-text rationale on the entry. |
| `ref` | string |  | Doc this entry pins. Format: ``Kind/name`` (e.g. ``Spec/foo``, ``Plan/bar``, ``AgentSession/vs-baz``). |
| `seed_from` | string |  | Name of the prior cycle's `reflect` WorkflowEvent that seeded this entry. Set on `discover` entries created via `dna sdlc journey close-cycle` — the ouroboros bite, where reflect's lessons literally feed into the next discover. Distinct from `transitioned_from`: that's the immediate predecessor across phases; this is the cross-cycle inheritance link. |
| `skipped_phases` | array |  | Phases jumped over to get to this entry. E.g. discover → build means skipped ['specify', 'plan'] — Studio shows them in muted strikethrough so the trajectory stays honest. |
| `started_at` | string |  |  |
| `summary` | string |  | 1-2 sentence note about what happened in this phase. Optional — rendered as the entry's tooltip in Studio. |
| `tags` | array |  |  |
| `timestamp` | string |  | Back-compat (deprecated): legacy form of ``created_at``. |
| `transitioned_from` | string |  | Name of the previous WorkflowEvent in this trajectory (forms a linked list). Optional for the first entry of a trajectory. |

## Workspace

- **Alias:** `tenant-workspace`
- **apiVersion:** `github.com/ruinosus/dna/tenant/v1`
- **Plane:** record

A Workspace is the DNA tenancy root — a first-class, named, DNA-native space that authenticates identities from any Azure org via Entra and decides visibility through WorkspaceMembership (Model B, the GitHub/Slack shape). Its opaque, immutable workspace_id is the physical `tenant` column value on every row it owns, so renaming never rewrites data; the id is GENERATED by the server at creation and never derived from an Azure tid (decision D5). GLOBAL declarative data in `_lib`.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `account_id` | string \| null |  | The BILLING ACCOUNT that owns this workspace — an opaque id (like workspace_id it is matched WHOLE, never parsed), recorded AT CREATION from the caller's VERIFIED claims by dna.tenancy.account_id_from_claims. An account is an ORGANIZATION (the provider block's `tenant_claim` — Entra `tid`, WorkOS/Clerk/Auth0 `org_id`, Google Workspace `hd`) or, when the sign-in belongs to no organization, a PERSON (the identity's durable `sub` — the consumer lane). The id is NAMESPACED by provider and kind (`entra-org:<tid>`, `workos-org:<org_id>`, `workos-user:<sub>`, ...) so a `tid` and a `sub` sharing a literal value can never be one account, and so the kind is legible; the prefix is for uniqueness and reading, NEVER a parsing or authorization surface. THE SUBSCRIPTION IS PER ACCOUNT - one AccountPlan covers EVERY workspace sharing this id, so a second workspace is never a second charge and never needs a second write. Null = no resolvable account, which resolves to the Free floor (fail-closed) — never another account's tier, never a paid default. |
| `created_at` | string | yes | When the workspace was created (ISO 8601). |
| `created_by` | string | yes | Email of the identity that created the workspace (its first Owner). |
| `name` | string | yes | Human display name, e.g. "Barnabé Labs". Editable. |
| `slug` | string |  | URL-safe handle (e.g. for `/w/<slug>` links). Editable; distinct from the immutable workspace_id. |
| `workspace_id` | string | yes | Opaque, GENERATED, immutable id — the physical value of the `tenant` column on every row this workspace owns. Never changes (renaming edits name/slug, never this). The doc name SHOULD equal it. MINTED BY THE SERVER (decision D5); a client-supplied id is refused, which is what makes workspace takeover impossible by construction. Never derived from an Azure `tid`. |

## WorkspaceMembership

- **Alias:** `tenant-workspace-membership`
- **apiVersion:** `github.com/ruinosus/dna/tenant/v1`
- **Plane:** record

A WorkspaceMembership maps a verified identity (Entra oid + email + tid) to a workspace_id + role + status — the identity→workspace boundary of ADR Model B and the crown-jewel authorization check (an ACTIVE grant is required to touch a workspace; fail-closed otherwise). Invites are by email (the handle) and bind to the durable oid on first verified sign-in (two-phase), matching only on verified token claims. GLOBAL declarative data in `_lib`, distinct from the portfolio Membership (intra-workspace org/project RBAC).

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `accepted_at` | string \| null |  | ISO-8601 timestamp when the invite was accepted and oid bound. |
| `identity_email` | string | yes | Normalized (lowercased) email — the INVITE HANDLE. You invite by email before the person has ever signed in; matching is only ever on a verified token email claim, never a caller-supplied value. |
| `identity_oid` | string \| null |  | The stable Entra `oid`, BOUND on first accepted sign-in (null while pending). The durable key — post-bind re-auth keys on this, never the mutable email. |
| `identity_tid` | string \| null |  | The Azure org (tenant id) the accepting identity came from — PROVENANCE only (no longer the DNA tenant under Model B). Bound on accept. |
| `invited_at` | string \| null |  | ISO-8601 timestamp of the invite (stamped by the writer). |
| `invited_by` | string \| null |  | Email of the Owner/Admin who created the invite. |
| `role` | string | yes | Workspace-level role — the standard ladder (owner > admin > member > guest, highest-role-wins). References the Role Kind. Um de: `owner`, `admin`, `member`, `guest`. |
| `status` | string | yes | Invite lifecycle — pending (invited, oid not yet bound) → active (accepted, oid bound). No membership / non-active → no access. Um de: `pending`, `active`. |
| `workspace_id` | string | yes | The workspace this grant is in — the tenant key (matches a Workspace.workspace_id). |

## WorkspaceScopeGrant

- **Alias:** `tenant-workspace-scope-grant`
- **apiVersion:** `github.com/ruinosus/dna/tenant/v1`
- **Plane:** record

A WorkspaceScopeGrant records that one workspace may READ one scope that is not its own. It exists so a multi-scope reach is an auditable row rather than a process-wide env var or an inference - the binder validates against the rows and derives nothing, so a leak is always a wrong row somebody wrote. No wildcard - enumerate. GLOBAL declarative data in `_lib`, alongside Workspace and WorkspaceMembership.

**Spec fields**

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `access` | string |  | What the grant permits, and the binder ENFORCES it - a request carries a read/write axis and this value is what answers it, so the grant that opens a second scope for reading refuses a write to it. READ only, and the enum has one member so widening it is a deliberate schema change with a reviewer - a cross-workspace WRITE is a different decision than a cross-workspace read and must not arrive as a value nobody noticed. Um de: `read`. |
| `granted_at` | string \| null |  | ISO-8601 timestamp, stamped by the writer. |
| `granted_by` | string \| null |  | Identity (email / oid) of whoever created the grant. |
| `reason` | string \| null |  | Why this workspace may reach that scope. Free text, for the human reading the audit six months later. |
| `revoked_at` | string \| null |  | ISO-8601 timestamp when status flipped to `revoked`. |
| `scope` | string | yes | The single scope name this row grants. One scope per row on purpose - granting and revoking are then one instance each, so an audit reads as a list of facts rather than a diff inside a list. |
| `status` | string | yes | Only `active` grants anything. Revoking keeps the row (and its history) instead of deleting the evidence that access once existed. Um de: `active`, `revoked`. |
| `workspace_id` | string | yes | The workspace this grant is FOR — the caller's resolved workspace_id (matches a Workspace.workspace_id / the tenant key). |

