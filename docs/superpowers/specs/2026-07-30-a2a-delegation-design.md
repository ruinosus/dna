# Delegação de agentes + a face A2A — desenho

**Data:** 2026-07-30
**Repo:** `ruinosus/dna` (SDK) — a metade de kernel/runtime desta feature.
**Par:** `dna-cloud` tem a spec irmã (supervisor/conversor como documentos,
console, canvas do rascunho). Esta spec **não** contém nada de portal.
**Estado:** proposta, aguardando revisão do fundador.

---

## 1. Em uma frase

Fazer o DNA **executar** a delegação que ele já declara, e falar **A2A** nas duas
direções — para que um agente supervisor delegue a especialistas, sejam eles
agentes DNA no mesmo runtime ou agentes de terceiros em outra nuvem, sem que o
DNA invente protocolo nenhum.

## 2. O que já existe (medido, não suposto)

O modelo de delegação **já está no kernel**, com as duas pontas do aperto de mão:

| ponta | onde | o que declara |
|---|---|---|
| quem PODE delegar | `AgentSpec.team_members: list[str]` | os subagentes deste agente |
| quem ACEITA receber | `DelegationTargetFor` (bloco `delegation_target_for`) | `agents` (allowlist de delegadores, `"*"` = qualquer), `format` (`slug`\|`json`\|`text` — contrato de retorno), `typical_seconds`, `use_when`, `purpose` |

E o comentário de `AgentSpec.tool_groups` confirma a intenção:
*"subagents in team_members can declare disjoint groups for delegation."*

**O que NÃO existe:** o executor. `delegate_to` aparece **exclusivamente** em
`kernel/models.py` — nenhuma implementação em `packages/`, nenhum teste, nenhuma
tool. É o padrão "capacidade existe, porta não": o vocabulário está desenhado, e
não há caminho alcançável.

Também já existe, e esta spec reusa sem tocar:

- **`emit`** (`dna.emit.mcp_ui`, `dna.emit.frontend`): projetar um documento num
  artefato que um sistema externo consome. A face A2A de **saída** é um alvo de
  emit, não um mecanismo novo.
- **O funil de aprovação de Kind autorado**: proposta inerte até um humano
  aprovar. `RemoteAgent` entra por esse funil (§6.1) — não ganha exceção.
- **O registro de Kinds por descritor** (`extensions/<x>/kinds/*.kind.yaml` +
  entry point): como `RemoteAgent` nasce, igual ao `SourceArtifact`.

## 3. A pilha de padrões — o que é nosso e o que é do mercado

| fronteira | padrão | estado ao fim desta spec |
|---|---|---|
| agente → tools/contexto | **MCP** | já no ar |
| agente → UI | **AG-UI** | já no ar |
| supervisor → agente DNA (mesmo runtime) | **subagents-as-tools** (a recomendação da LangChain desde março/2026) | **§5 — o executor** |
| supervisor ↔ agente de terceiro | **A2A** (Linux Foundation, 150+ orgs) | **§6 — a face, duas direções** |

**Não criamos protocolo.** Implementamos o executor de um bloco que o kernel já
declara, e uma projeção de um documento que o kernel já tem.

## 4. `RemoteAgent` — o Agent Card como Kind

### 4.1 O protocolo não é um Kind; o Card é

Transformar "A2A" num Kind seria erro de categoria — protocolo é transporte. Mas
o **Agent Card** é um documento versionado, com schema, que descreve identidade e
capacidade: `name`, `description`, `version`, `skills[]`, `capabilities`,
`securitySchemes`, `supportedInterfaces`, `signatures`. Isso *é* um Kind.

### 4.2 Dois Kinds, porque os campos são disjuntos

| | declara | o DNA |
|---|---|---|
| **`Agent`** (existe) | `instruction`, `model`, `tools`, `mcp_servers`, `team_members` | **compõe e executa** — o documento DEFINE o comportamento |
| **`RemoteAgent`** (novo) | `supportedInterfaces`, `skills`, `capabilities`, `securitySchemes`, `data_scope` | **localiza e chama** — o documento DESCREVE e APONTA |

Um Kind só com os dois modos validaria absurdo (um agente local com
`securitySchemes`; um remoto com `instruction`), e `additionalProperties: false`
não sabe expressar "estes campos **ou** aqueles" — o schema teria de ser
permissivo, o oposto do que um schema fechado serve. O `SourceArtifact` é fechado
por essa mesma razão: para uma credencial não viajar de carona.

### 4.3 O que UNE os dois: um roster DERIVADO

O supervisor não recebe uma lista de agentes. Ele recebe *"todo documento que
declara `delegation_target_for` cuja allowlist me inclui"* — atravessando
`Agent` **e** `RemoteAgent`, resolvido no momento da chamada.

Isto é deliberado e é a lição do dna-cloud de 29/07 aplicada no desenho: **toda
lista mantida à mão ficou cega e verde.** Um terceiro tipo de alvo de delegação,
no futuro, entra sem uma linha de mudança no supervisor.

### 4.4 O descritor

`packages/sdk-py/dna/extensions/a2a/kinds/remote-agent.kind.yaml`,
`tenant_scope: tenanted`, `plane: record`, `additionalProperties: false`.

`required: [name, description, supported_interfaces, data_scope]`.

Campos: os do Agent Card (nomes em `snake_case`, a convenção do kernel, com o
mapeamento para o JSON do A2A documentado no descritor), mais
`delegation_target_for` (o bloco compartilhado) e mais **`data_scope`** (§6.2),
que é nosso e não do A2A — e o descritor diz por quê.

## 5. O executor de `delegate_to`

Uma tool de host, entregue ao agente que declara `team_members`, cujo alvo é
resolvido pelo roster derivado (§4.3). Por alvo:

- **`Agent` local** → executa no mesmo runtime (subagents-as-tools).
- **`RemoteAgent`** → uma chamada A2A (§6).

A declaração é a **mesma** nos dois casos; só o transporte difere, resolvido na
hora da chamada. É o padrão da resolução de Kind, e é o que faz a face A2A ser
**aditiva**: um alvo que era local pode passar a ser remoto sem o supervisor
saber.

O `format` declarado pelo alvo dirige o parse do retorno (`slug` cria documento e
devolve o slug; `json` valida; `text` é narrativa). `typical_seconds` vai para o
delegador narrar a espera. Uma delegação que estoura o tempo **volta com recusa
nomeada**, nunca com silêncio.

## 6. A face A2A — as duas direções

### 6.1 Entrada: um Card de terceiro vira `RemoteAgent`

Buscar `/.well-known/agent-card.json`, validar, e escrever um `RemoteAgent`
**inerte** — que só passa a ser delegável quando um humano aprova, pelo funil
que já existe. Registrar um agente passa a ser **escrever um documento**: sem
deploy, sem edição de código.

⚠️ **Um `RemoteAgent` é, por construção, um canal de exfiltração** — o DNA vai
mandar dado do workspace para uma URL que o tenant escolheu. Isso não é defeito
do A2A; é a natureza da coisa. Daí o funil ser obrigatório e o §6.2 existir.

### 6.2 As três regras de segurança que nascem com o desenho

**1. `data_scope` é obrigatório e explícito.** O supervisor pode ter lido
documentos antes de delegar. Então aprovar não é "essa URL é ok" — é **"este
endpoint pode receber ESTES dados"**. Campo obrigatório, porque resposta
implícita significa "tudo". O executor recusa quando o payload excede o escopo,
e a recusa é nomeada.

**2. Nunca repassar o token do usuário.** A credencial é uma que o *workspace*
configurou para aquele remoto — jamais o bearer de quem conversa. Repassá-lo
faria de cada agente remoto uma impersonação completa do usuário contra o nosso
próprio MCP. O `securitySchemes` do Card diz *como* autenticar; **de quem é a
credencial é decisão nossa, e é do workspace.** (A mesma decisão que o dna-cloud
tomou duas vezes em 29/07: identidade emprestada não atravessa fronteira.)

**3. A allowlist é dupla.** `team_members` (o delegador declara) **e**
`delegation_target_for.agents` (o alvo aceita). As duas, sempre — uma ponta só
seria autorização unilateral. O kernel já modela as duas; o executor as exige.

### 6.3 Saída: um `Agent` do DNA vira um Card

Projeção via **emit** — a tese que o DNA já tem. `name`/`description` do
documento; `skills[]` derivados das tools do agente; `capabilities.streaming:
true` porque o AG-UI já faz streaming. Servido no well-known pela face de
runtime.

Isto é o que faz *outro* sistema poder delegar **para** nós — o lado que
transforma DNA Cloud em plataforma, não em produto com dois agentes.

## 7. Fora desta spec

- **Push notifications do A2A** (`capabilities.pushNotifications`): a v1 é
  request/response + streaming. Webhook de volta é camada seguinte.
- **Verificação de `signatures`** — decisão aberta (§9).
- **Descoberta automática de agentes** (diretórios A2A): a v1 registra por
  documento, deliberadamente. Descoberta sem curadoria humana contradiz §6.1.
- **Delegação multi-salto** (um remoto que delega a outro): fora, e o executor
  deve **recusar** em vez de encaminhar em silêncio.

## 8. Riscos

- **O executor é a peça mais delicada.** Ele decide, por chamada, quem pode
  chamar quem com quais dados. Um erro aqui não é um bug de feature, é uma
  fronteira de autorização. Testes de recusa (allowlist unilateral, escopo
  excedido, token do usuário vazando) valem mais que testes de caminho felizo.
- **`RemoteAgent` pode virar um Kind sem consumidor** se o executor atrasar. Os
  dois entram juntos — a lição do `X-Tenant-OID` (meia-implementação silenciosa
  é pior que nenhuma).
- **O A2A 1.0 é recente.** `supportedInterfaces` substituiu o `url` único de
  versões anteriores. Nosso descritor deve mapear a versão que declaramos
  suportar, e dizer qual é.

## 9. Decisões abertas (do fundador)

1. **Assinaturas.** Verificamos `signatures` do Card? E um Card não assinado —
   recusa, ou aceita **marcado**? (O DNA já tem o vocabulário de "documento
   marcado", da revogação: inválido é lido com marca, nunca apagado.)
2. **Escopo do `data_scope`.** Por Kind (`pode receber SourceArtifact e
   Invoice`), por sensibilidade (um rótulo), ou os dois?
3. **Onde o Card de saída é servido** — na face MCP, na REST, ou numa face
   própria?

## 10. Como saberemos que funcionou

1. Um supervisor delega a um `Agent` local e recebe o retorno no `format`
   declarado.
2. Um supervisor delega a um `RemoteAgent` **aprovado** e o mesmo código de
   supervisor não sabe que o transporte mudou.
3. Uma allowlist unilateral (só `team_members`, ou só `delegation_target_for`)
   **recusa**, com razão nomeada.
4. Um payload fora do `data_scope` **recusa**, com razão nomeada.
5. O bearer do usuário **nunca** aparece numa chamada A2A de saída (asserido, não
   revisado a olho).
6. `GET /.well-known/agent-card.json` devolve um Card válido derivado de um
   documento `Agent` — validável por um validador A2A de terceiro.
