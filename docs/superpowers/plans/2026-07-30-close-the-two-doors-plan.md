# As duas portas que faltam — plano de implementação (SDK)

> **Para quem executa:** use `superpowers:subagent-driven-development`. Passos com
> checkbox (`- [ ]`).

**Goal:** tornar alcançável o que o 0.38.0 publicou. Duas peças, ambas nos padrões
de mercado, ambas no SDK.

**Motivo (medido, não suposto):**

| o que existe | por que é inalcançável |
|---|---|
| `dna.application.delegation_exec.delegate()` | **não é tool de nenhum agente**, e `run_local` só existe como parâmetro — ninguém o fornece |
| `POST /v1/documents` | **não existe.** Só rotas por Kind (`/v1/memories`, `/v1/artifacts`, `/v1/kinds`, `/v1/projects`, …) |

As duas são *capacidade existe, porta não* — o mesmo defeito que esta feature
existe para consertar, reproduzido dentro dela. A causa foi minha: a spec do SDK
dizia *"uma tool de host, entregue ao agente que declara `team_members`"*, e o
plano derivado listou só `delegate()`/`parse_result()`. A tool sumiu entre a spec
e o plano.

## Global Constraints

- **Padrão de mercado antes de invenção.** As duas peças têm convenção
  estabelecida (§ abaixo). Divergir dela exige razão escrita.
- **Nada de portal.** 100% SDK.
- **Recusa nomeada, nunca silêncio** — o padrão que o executor já segue.
- **A allowlist dupla e o `data_scope` continuam sendo a política** (`dna.application.delegation`).
  Nenhuma peça aqui os contorna.
- O bearer do usuário **nunca** atravessa: `call_remote` segue sem parâmetro de
  identidade, e o teste contra a assinatura permanece.

---

## Peça A — `delegate_to` como tool

### A.0 O padrão de mercado que seguimos

Da documentação de **subagents da LangChain** (a recomendação vigente desde
março/2026, acima do `langgraph-supervisor` legado):

- agentes são **selecionados por nome**;
- a tarefa é passada ao subagente como **human message**;
- o resultado volta como **tool result**, e é um **resumo conciso** — não o
  transcript;
- o motivo declarado do padrão é **isolamento de contexto**: o subagente roda em
  janela própria para não inflar a conversa do principal.

O último ponto é load-bearing e não é detalhe de eficiência: é o que faz o
sub-run ter **state próprio**. (E é por isso que, no dna-cloud, o compositor de
memória não pode ser atendido por um supervisor delegante — o rascunho vive no
state do sub-run.)

**Files:**
- Create: `packages/sdk-py/dna/application/delegation_tool.py`
- Modify: `packages/sdk-py/dna/application/__init__.py` (export)
- Test: `packages/sdk-py/tests/test_delegation_tool.py`

**Interfaces:**
- Produces: `make_delegate_tool(*, delegator, documents, run_local, call_remote, credential_for=None) -> StructuredTool`
  - nome da tool: **`delegate_to`** (o nome que o kernel já documenta)
  - args (Pydantic, structured tool calling — o padrão 2026):
    `target: str` (nome do agente) · `task: str` (o pedido, em linguagem natural)
  - retorno: **string** — o resumo conciso do subagente

### As propriedades que o teste tem de provar

- [ ] **A tool se chama `delegate_to`** e sua `description` **lista os alvos
  disponíveis com o `use_when` de cada um.** Sem isso o modelo escolhe alvo às
  cegas — e `use_when` existe no kernel exatamente para dirigir essa escolha. A
  descoberta por prompt é a via que a LangChain nomeia.
- [ ] **Um alvo fora do roster é RECUSADO pela tool**, com a razão e a lista de
  alvos válidos. (O executor já recusa; a tool não pode engolir a recusa e
  devolver texto vago — o supervisor precisa saber para não narrar sucesso.)
- [ ] **A tarefa chega ao subagente como human message**, não concatenada ao
  system prompt. Asserir no que `run_local` recebe.
- [ ] **O retorno é o resumo, não o transcript.** Um `run_local` que devolve dez
  mensagens deve produzir uma string curta — e o teste fixa que o transcript
  inteiro NÃO aparece.
- [ ] **Isolamento de contexto:** `run_local` recebe a tarefa e **nada** do
  histórico do delegador. Asserir que nenhuma mensagem do pai chega.
- [ ] **O transporte é escolhido pelo Kind do alvo** — `Agent` → `run_local`,
  `RemoteAgent` → `call_remote`. Um alvo local **nunca** toca a rede (o dublê
  remoto levanta se chamado).
- [ ] **Uma exceção do subagente vira recusa nomeada**, não propaga crua: o
  supervisor deve poder dizer o que falhou.

- [ ] **Steps:** escreva o teste → rode e confirme FALHA → implemente → rode e
  confirme PASSA → commit.

Comando: `cd packages/sdk-py && uv run python -m pytest tests/test_delegation_tool.py -q`

### A.1 Quem fornece `run_local` — a fiação no runtime

**Files:**
- Modify: `packages/sdk-py/dna/runtime/builder.py` (ou o adapter LangChain — ver
  nota)
- Test: `packages/sdk-py/tests/test_delegation_wiring.py`

O `build_runtime` já lê a def do agente. Quando ela declara **`team_members`
não-vazio**, o runtime deve:

1. montar o roster (`targets_for`) a partir dos documentos do escopo;
2. construir `run_local` — dado o nome de um agente alvo, **compor e rodar aquele
   agente** com a tarefa como única human message, devolvendo o texto final;
3. ligar `call_remote` do `a2a_transport`;
4. entregar `make_delegate_tool(...)` ao agente, junto das tools dele.

- [ ] **A propriedade central do teste:** um agente **sem** `team_members` **não
  recebe** a tool (nem a vê na lista) — e um **com** recebe. Derivado da
  declaração, nunca de uma lista de nomes mantida à mão.
- [ ] **Nota para quem implementa:** decida entre `builder.py` e o adapter
  LangChain **lendo o código**, não pelo palpite deste plano. O critério: a tool
  precisa chegar junto das outras tools do agente, e `run_local` precisa poder
  construir outro agente no mesmo runtime. Se a escolha divergir do que este
  plano sugere, **relate** — o plano errou antes sobre mecanismo, várias vezes.

---

## Peça B — a rota genérica de documento, kubernetes-shaped

### B.0 O padrão de mercado que seguimos

O Kubernetes resolveu exatamente este problema, e **o DNA já tem a forma dele**
(`apiVersion` / `kind` / `metadata` / `spec`):

- aplicar um CRD **cria um endpoint** que serve aquele tipo;
- *"`kind` é uma string representando o recurso REST; **servidores podem inferi-lo
  do endpoint** ao qual o cliente submete"*;
- desde a 1.25 um CRD exige **schema OpenAPI v3 estrutural**, e **o API server
  valida todo create/update contra ele antes de gravar**;
- `spec` é o estado desejado escrito pelo usuário; `status` é escrito pelo
  controlador.

**Consequência que corrige uma decisão anterior:** a validação de schema pertence
ao **servidor**, não ao portal. Uma decisão minha anterior a colocou na rota do
portal por não existir rota no servidor — certo em tirá-la da tool do copiloto,
errado quanto ao lugar. Aqui ela vai para onde a verdade mora, e o portal passa a
só **relatar** a recusa.

**Files:**
- Modify: `packages/cli/dna_cli/_rest_api.py` (a rota)
- Modify: `packages/sdk-py/dna/application/documents.py` (o seam, se couber ali —
  **leia antes**)
- Test: `packages/cli/tests/test_rest_documents.py`

**Interfaces:**
- `POST /v1/kinds/{kind}/documents` — o endpoint carrega o Kind (convenção k8s),
  o corpo carrega `{metadata, spec}`.

### As propriedades que o teste tem de provar

- [ ] **O `kind` vem do PATH, não do corpo.** Se o corpo trouxer um `kind`
  divergente, **recusa** — não "o corpo vence" nem "o path vence" em silêncio.
  Duas fontes para o mesmo fato é o defeito que este projeto passou o dia
  consertando.
- [ ] **O servidor valida `spec` contra o schema registrado do Kind** antes de
  gravar, e a recusa **nomeia o campo** (desconhecido, ou obrigatório ausente).
  Como o API server do k8s.
- [ ] **Um Kind autorado e NÃO APROVADO recusa** — o portão que o DNA já tem, e
  que nenhuma rota pode contornar. (Específico do DNA, não do k8s: um CRD não
  tem funil de aprovação humana; o nosso tem, de propósito.)
- [ ] **Identidade e escopo NÃO são entrada do caller** — nem `claims` nem
  `scope` no corpo ou na query. Asserido contra o **schema publicado da rota**
  (o padrão que `test_tools_bind_their_scope.py` já usa para as tools MCP).
- [ ] **A proveniência é gravada como aresta:** quando o corpo cita um artefato
  de origem (`sha256`), o `derived_refs` do `SourceArtifact` ganha a referência —
  e uma re-escrita **preserva** as anteriores (o `register_artifact_impl` já tem
  essa propriedade; não a perca).
- [ ] **Um Kind inexistente → 404 com o nome**, nunca 500.

- [ ] **Steps:** teste → falha → implementação → passa → **as quatro guardas**
  (`gen_kinds_docs`, `data_model_guard --write`, `docs_coverage_guard`, e o
  **drift de OpenAPI + cobertura de método nomeado nos clients** — esta rota nova
  vai exigir `dump_openapi.py` e provavelmente método nos dois clients) → commit.

⚠️ **A guarda de OpenAPI/clients é a que morde nesta peça.** Uma rota nova no
`_rest_api.py` derruba a paridade dos clients gerados (`client-py`, `client-ts`)
até que os métodos nomeados existam. Rode `dump_openapi.py` e o `npm run gen` do
client TS, e **conte com isso no escopo** — não é surpresa, é o portão conhecido.

---

## Peça C — release

- [ ] Suíte inteira + as quatro guardas + `brand_guard` + `gitleaks`
- [ ] Versão em **CINCO** lugares (descoberto no release anterior, e o
  `CLAUDE.md` diz três): `packages/sdk-py`, `packages/cli`, o teto interno do CLI
  **+ o comentário que o repete**, `packages/client-py`, `packages/client-ts`.
  Feature nova = **minor** → 0.39.0, e o teto move.
- [ ] ⚠️ Se os clients ganharem métodos (Peça B), eles **entram no mesmo bump** —
  o workflow `release-client` exige que a tag case com a versão deles, e ele
  **falha em toda release** hoje justamente por essa divergência (0.26.0 vs a
  tag). Esta é a chance de consertar de verdade em vez de conviver com uma guarda
  permanentemente vermelha.
- [ ] Tag → esperar o **índice SIMPLE** (nunca a API JSON) **com folga** — o CI do
  dna-cloud falhou uma vez em 0.38.0 contra uma borda de CDN defasada cinco
  minutos depois da publicação.
- [ ] Lockstep no dna-cloud (as cinco linhas + a linha de floors do `CLAUDE.md`).

---

## Auto-revisão

**Cobertura:** os dois buracos medidos → Peças A e B. A fiação que faltava
(`run_local`) → A.1, que é a parte que o plano anterior perdeu.

**Placeholders:** as duas peças descrevem **propriedades** e apontam o **padrão de
mercado com citação**, em vez de trazer código completo. Deliberado: eu errei o
mecanismo cinco vezes hoje escrevendo código de cabeça (o envelope do descritor, o
comando de teste, `now=None`, `parents[2]`, e a tool que sumiu). Onde o padrão é
externo e verificável, a propriedade + a citação erram menos que o meu palpite.

**A aresta que fica visível:** A.1 não diz com certeza se a fiação mora em
`builder.py` ou no adapter LangChain, e manda o implementador decidir lendo o
código **e relatar**. Não é preguiça: é o reconhecimento de que este plano já
errou sobre mecanismo, e que uma prescrição errada custa mais que uma pergunta
honesta.
