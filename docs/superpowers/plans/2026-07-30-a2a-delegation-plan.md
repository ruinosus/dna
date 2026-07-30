# Delegação de agentes + face A2A — plano de implementação (SDK)

> **Para quem executa:** use `superpowers:subagent-driven-development` (recomendado)
> ou `superpowers:executing-plans` para implementar tarefa por tarefa. Os passos
> usam checkbox (`- [ ]`) para acompanhamento.

**Goal:** fazer o DNA executar a delegação que já declara, e falar A2A nas duas
direções, sem inventar protocolo.

**Architecture:** um Kind novo (`RemoteAgent` = o Agent Card do A2A), um roster
**derivado** de alvos de delegação que atravessa `Agent` e `RemoteAgent`, e um
executor cujo transporte (local ou A2A) é resolvido por alvo na hora da chamada.
A projeção de saída é um alvo de `emit`.

**Tech Stack:** Python 3.12+, `dna.kernel` (Kinds por descritor), `httpx`
(transporte A2A), pytest.

**Spec:** `docs/superpowers/specs/2026-07-30-a2a-delegation-design.md`

## Premissas declaradas (as três decisões abertas do SDK)

O fundador não decidiu; nenhuma bloqueia, e as três são reversíveis. Ficam
explícitas aqui para serem contestadas em revisão, não descobertas em produção:

1. **Assinaturas** (spec §9.1): um Card **sem** `signatures` é aceito e o
   documento nasce **marcado** (`signature_state: unsigned`) — o vocabulário que
   a revogação já usa (inválido é lido *com marca*, nunca apagado). Um Card
   **com** assinatura tem o campo preservado; a **verificação criptográfica fica
   FORA desta v1** e o estado é `present_unverified`. Motivo: verificar exige
   decidir a cadeia de confiança (quais emissores?), que é decisão de produto, e
   um campo tri-estado torna a ausência de verificação **legível** em vez de
   implícita.
2. **`data_scope`** (spec §9.2): **por Kind** — uma lista de nomes de Kind que
   aquele endpoint pode receber. Checável mecanicamente e alinhado ao modelo do
   DNA. Um eixo de sensibilidade entra depois como campo **opcional**, aditivo.
3. **Onde o Card de saída é servido** (spec §9.3): **em lugar nenhum, nesta
   spec.** O SDK entrega a **projeção** (`agent_card_for`, Task 6); *qual face
   serve em qual path* é decisão de deployment — `/.well-known/` é convenção de
   raiz de domínio, e no dna-cloud a raiz é do portal, não do MCP. Separar a
   projeção do serviço dissolve a pergunta em vez de respondê-la errado.

## Global Constraints

- **Sem lógica de portal.** Este plano é 100% SDK. Nada de Next.js, nada de
  Prisma, nada de Azure.
- **Kind por descritor.** `RemoteAgent` nasce como `SourceArtifact` nasceu:
  `kinds/*.kind.yaml` + classe `*Extension` + entry point no `pyproject.toml`.
  Nunca um Kind em código imperativo.
- **`additionalProperties: false`** em todo schema novo. É o que impede uma
  credencial de viajar de carona (a razão pela qual o `SourceArtifact` é fechado).
- **Allowlist DUPLA, sempre.** `team_members` (o delegador declara) **E**
  `delegation_target_for.agents` (o alvo aceita). Uma ponta só é autorização
  unilateral e deve **recusar**.
- **O bearer do usuário NUNCA sai numa chamada A2A.** A credencial é do
  workspace. Isto é asserido por teste (Task 4), não revisado a olho.
- **Recusa nomeada, nunca silêncio.** Toda recusa carrega o motivo
  (`type(exc).__name__` + mensagem), o padrão que as tools de portfólio adotaram
  depois de uma enumeração de exceções ficar cega.
- **Derivar, nunca enumerar.** O roster é uma consulta sobre documentos, não uma
  lista mantida à mão.
- **`delegate_to` e `RemoteAgent` entram JUNTOS** (spec §8): um Kind sem executor
  é capacidade sem porta — o defeito que esta feature existe para corrigir.

---

## Estrutura de arquivos

| arquivo | responsabilidade |
|---|---|
| `dna/extensions/a2a/kinds/remote-agent.kind.yaml` | o descritor do Kind (o Agent Card) |
| `dna/extensions/a2a/__init__.py` | `A2AExtension` — registra o descritor |
| `dna/application/delegation.py` | **política pura**: o roster derivado + a decisão da allowlist dupla |
| `dna/application/delegation_exec.py` | o executor: resolve alvo, despacha por transporte, parseia por `format` |
| `dna/application/a2a_transport.py` | a chamada A2A de saída (httpx) + a credencial do workspace |
| `dna/application/a2a_ingest.py` | buscar um Card de terceiro → documento `RemoteAgent` inerte |
| `dna/emit/agent_card.py` | a projeção `Agent` → Agent Card (saída) |
| `pyproject.toml` | o entry point `a2a` |

Testes espelham em `packages/sdk-py/tests/`.

**Por que `delegation.py` e `delegation_exec.py` separados:** a política é pura e
é a fronteira de autorização — ela merece ser lida, testada e revisada sem que o
transporte, o parse e o timeout estejam no mesmo arquivo. A lição de 29/07 no
dna-cloud foi que **a política pura estava certa nos 13 defeitos; o erro estava
sempre na montagem em volta.** Separar mantém a parte correta pequena.

---

## Task 1: O Kind `RemoteAgent`

**Files:**
- Create: `packages/sdk-py/dna/extensions/a2a/kinds/remote-agent.kind.yaml`
- Create: `packages/sdk-py/dna/extensions/a2a/__init__.py`
- Modify: `packages/sdk-py/pyproject.toml` (entry point, junto de `artifact`)
- Test: `packages/sdk-py/tests/test_remote_agent_kind.py`

**Interfaces:**
- Produces: o Kind `RemoteAgent`, apiVersion `github.com/ruinosus/dna/a2a/v1`,
  com os campos abaixo. As Tasks 2–5 dependem destes nomes.

- [ ] **Step 1: Escrever o teste que falha**

`packages/sdk-py/tests/test_remote_agent_kind.py`:

```python
"""``RemoteAgent`` — o Agent Card do A2A como documento.

O protocolo A2A não é um Kind (transporte não é documento). O Agent CARD é: um
descritor versionado de identidade e capacidade. Este Kind é ele.

Quatro propriedades carregam o desenho, e cada uma é pinada porque cada uma é
fácil de perder num edit que parece inofensivo:

1. **``data_scope`` é OBRIGATÓRIO.** Um RemoteAgent é, por construção, um canal
   de exfiltração — o DNA manda dado do workspace para uma URL que o tenant
   escolheu. Um escopo implícito significa "tudo".
2. **O schema é FECHADO.** ``additionalProperties: false`` impede que uma
   credencial (um bearer, um api_key) seja anexada ao documento. O
   ``securitySchemes`` diz COMO autenticar; a credencial em si nunca é documento.
3. **``delegation_target_for`` é o campo COMPARTILHADO com ``Agent``** — é o que
   permite ao roster (Task 2) atravessar os dois Kinds sem enumerá-los.
4. **``signature_state`` é tri-estado.** Ausência de verificação fica LEGÍVEL
   em vez de implícita (ver as premissas do plano).
"""
from __future__ import annotations

import pytest

from dna.kernel.kinds.registry import KindRegistry
from dna.kernel.source.descriptor_loader import load_descriptors

_API = "github.com/ruinosus/dna/a2a/v1"
_KIND = "RemoteAgent"


@pytest.fixture
def port():
    """O port registrado, pelo mesmo funil que o kernel usa."""
    registry = KindRegistry()
    registered = [
        registry.register_from_descriptor(raw)
        for raw in load_descriptors("dna.extensions.a2a")
    ]
    assert len(registered) == 1, f"esperava um descritor, veio {len(registered)}"
    return registered[0]


def _spec(**overrides):
    base = {
        "name": "invoice-reader",
        "description": "Reads invoices and returns structured fields",
        "supported_interfaces": [
            {"transport": "jsonrpc", "url": "https://vendor.example/a2a"}
        ],
        "data_scope": {"kinds": ["SourceArtifact"]},
    }
    base.update(overrides)
    return base


def _validate(port, spec):
    """Valida pelo seam do PRÓPRIO port — o mesmo ``parse()`` que o caminho de
    escrita alcança. Asserir contra um validador substituto testaria a ideia que
    o teste tem do schema, não a que o kernel aplica."""
    raw = {
        "apiVersion": _API,
        "kind": _KIND,
        "metadata": {"name": "remote-under-test"},
        "spec": spec,
    }
    try:
        port.parse(raw)
    except Exception as exc:  # noqa: BLE001 — a recusa É o resultado
        return exc
    return None


def test_the_kind_registers_under_its_own_namespace(port):
    assert port.kind == _KIND
    assert port.api_version == _API


def test_a_valid_card_parses(port):
    assert _validate(port, _spec()) is None


def test_data_scope_is_required(port):
    """Tire ``data_scope`` do ``required`` e isto morre.

    Sem escopo declarado, aprovar um RemoteAgent seria aprovar "este endpoint
    pode receber qualquer coisa" — e ninguém aprova isso sabendo."""
    bad = _spec()
    del bad["data_scope"]
    assert _validate(port, bad) is not None


@pytest.mark.parametrize("missing", ["name", "description", "supported_interfaces"])
def test_the_a2a_required_fields_are_required(port, missing):
    """O A2A 1.0 exige name/description/supportedInterfaces. Um Card sem eles não
    é um Card."""
    bad = _spec()
    del bad[missing]
    assert _validate(port, bad) is not None


@pytest.mark.parametrize(
    "smuggled", ["bearer", "api_key", "token", "credential", "password"]
)
def test_no_credential_can_be_smuggled_into_the_document(port, smuggled):
    """``securitySchemes`` diz COMO autenticar; a credencial nunca é documento.

    Ponha ``additionalProperties: true`` e isto morre — e o documento passaria a
    carregar o próprio acesso, então quem alcançasse o documento alcançaria o
    endpoint com ele. O mesmo motivo pelo qual o ``SourceArtifact`` é fechado."""
    assert _validate(port, _spec(**{smuggled: "sk-live-abc123"})) is not None


def test_the_delegation_block_is_accepted(port):
    """O campo COMPARTILHADO com ``Agent``. É o que faz o roster (Task 2)
    atravessar os dois Kinds sem enumerá-los — tire-o e o RemoteAgent fica
    inalcançável por delegação."""
    assert (
        _validate(
            port,
            _spec(
                delegation_target_for={
                    "agents": ["supervisor-agent"],
                    "format": "json",
                    "use_when": "the user attached an invoice",
                    "typical_seconds": 12,
                }
            ),
        )
        is None
    )


def test_signature_state_is_tri_state(port):
    """Ausência de verificação tem de ser LEGÍVEL, não implícita."""
    for state in ("unsigned", "present_unverified", "verified"):
        assert _validate(port, _spec(signature_state=state)) is None
    assert _validate(port, _spec(signature_state="probably-fine")) is not None
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd packages/sdk-py && python -m pytest tests/test_remote_agent_kind.py -q`
Expected: FAIL na fixture — `load_descriptors("dna.extensions.a2a")` não resolve
(módulo inexistente).

- [ ] **Step 3: Escrever o descritor**

`packages/sdk-py/dna/extensions/a2a/kinds/remote-agent.kind.yaml`:

```yaml
# RemoteAgent — o Agent Card do A2A, como documento.
#
# O protocolo A2A não é um Kind: transporte não é documento. O Agent Card é —
# um descritor versionado de identidade e capacidade, publicado pelo servidor
# A2A em `/.well-known/agent-card.json`. Isto é ele, com os nomes em snake_case
# (a convenção do kernel) e o mapeamento para o JSON do A2A anotado campo a
# campo.
#
# ── Por que este Kind é SEPARADO de `Agent` ──────────────────────────────────
# Os campos são disjuntos. `Agent` declara COMPORTAMENTO (instruction, model,
# tools) e o DNA compõe e executa. `RemoteAgent` DESCREVE e APONTA
# (supported_interfaces, skills, security_schemes) e o DNA localiza e chama. Um
# Kind só com os dois modos validaria absurdo — um agente local com
# `security_schemes`, um remoto com `instruction` — e `additionalProperties:
# false` não sabe expressar "estes campos OU aqueles".
#
# O que UNE os dois é `delegation_target_for`, e é de propósito: o roster de
# alvos é DERIVADO ("todo documento que declara o bloco e cuja allowlist me
# inclui"), atravessando os dois Kinds. Um terceiro tipo de alvo, depois, entra
# sem tocar em quem delega.
#
# ── data_scope: o campo que é NOSSO e não do A2A ─────────────────────────────
# Um RemoteAgent é, por construção, um canal de exfiltração: o DNA manda dado do
# workspace para uma URL que o tenant escolheu. O A2A não tem opinião sobre
# isso — é protocolo de transporte. Então o escopo é nosso, é OBRIGATÓRIO, e é
# explícito: aprovar um remoto não é "essa URL é ok", é "este endpoint pode
# receber ESTES dados". Escopo implícito significa "tudo", e ninguém aprova isso
# sabendo.
apiVersion: github.com/ruinosus/dna/a2a/v1
kind: RemoteAgent
tenant_scope: tenanted
plane: record
container: remote-agents
schema:
  type: object
  additionalProperties: false
  required: [name, description, supported_interfaces, data_scope]
  properties:
    # ── o Card do A2A ────────────────────────────────────────────────────────
    name:
      type: string
      description: A2A `name`. O nome pelo qual o agente se anuncia.
      minLength: 1
      maxLength: 200
    description:
      type: string
      description: A2A `description`. Para que ele serve, nas palavras dele.
      minLength: 1
    version:
      type: string
      description: A2A `version` — a versão QUE O AGENTE declara de si.
    supported_interfaces:
      type: array
      description: >
        A2A `supportedInterfaces` (1.0 — substituiu o `url` único das versões
        anteriores). Cada entrada nomeia um transporte e onde alcançá-lo.
      minItems: 1
      items:
        type: object
        additionalProperties: false
        required: [transport, url]
        properties:
          transport:
            type: string
            enum: [jsonrpc, grpc, http+json]
          url:
            type: string
            pattern: '^https://'
            description: >
              HTTPS obrigatório. Delegar dado de workspace por texto claro seria
              exfiltração com um passo a menos.
    capabilities:
      type: object
      additionalProperties: false
      description: A2A `capabilities` — flags booleanas, não operações nomeadas.
      properties:
        streaming: {type: boolean}
        push_notifications: {type: boolean}
        extended_agent_card: {type: boolean}
    skills:
      type: array
      description: A2A `skills[]` — o que ele sabe fazer, item a item.
      items:
        type: object
        additionalProperties: false
        required: [id, name, description]
        properties:
          id: {type: string, minLength: 1}
          name: {type: string, minLength: 1}
          description: {type: string, minLength: 1}
          tags: {type: array, items: {type: string}}
          examples: {type: array, items: {type: string}}
    security_schemes:
      type: object
      description: >
        A2A `securitySchemes` (forma do OpenAPI 3). Diz COMO autenticar. A
        credencial em si NUNCA vive aqui — o schema é fechado justamente para
        que um bearer não possa ser anexado ao documento. Quem guarda a
        credencial é o deployment, por remoto, e ela nunca é o token do usuário.
      additionalProperties: true
    default_input_modes:
      type: array
      items: {type: string}
    default_output_modes:
      type: array
      items: {type: string}
    documentation_url: {type: string}
    icon_url: {type: string}
    signatures:
      type: array
      description: >
        A2A `signatures`, preservadas como vieram. A VERIFICAÇÃO criptográfica
        está fora desta versão (exige decidir a cadeia de confiança, que é
        decisão de produto) — por isso `signature_state` existe e é tri-estado.
      items: {type: object, additionalProperties: true}
    signature_state:
      type: string
      enum: [unsigned, present_unverified, verified]
      description: >
        Tri-estado DE PROPÓSITO: um documento que não foi verificado tem de ser
        legível como tal. `unsigned` = o Card não trouxe assinatura;
        `present_unverified` = trouxe e não checamos; `verified` = checamos (não
        alcançável nesta versão). Um booleano `signed` faria "não verificado"
        parecer "não assinado", que são coisas diferentes.

    # ── o que é nosso ────────────────────────────────────────────────────────
    data_scope:
      type: object
      additionalProperties: false
      required: [kinds]
      description: >
        O que este endpoint PODE receber. Obrigatório — ver o cabeçalho.
      properties:
        kinds:
          type: array
          description: >
            Nomes de Kind cujos documentos podem ser delegados a este remoto.
            Lista vazia = nada pode, o que é um estado honesto (registrado, sem
            permissão) e não um erro.
          items: {type: string}
    delegation_target_for:
      type: object
      additionalProperties: false
      description: >
        O bloco COMPARTILHADO com `Agent` (kernel `DelegationTargetFor`). É o
        que o roster derivado lê para achar este alvo sem enumerar Kinds.
      properties:
        agents:
          type: array
          items: {type: string}
          description: Allowlist de delegadores; `["*"]` = qualquer.
        format:
          type: string
          enum: [slug, json, text]
        typical_seconds: {type: integer, minimum: 0}
        use_when: {type: string}
        purpose: {type: string}
presentation:
  fields: [name, description, supported_interfaces, skills, data_scope, signature_state]
```

`packages/sdk-py/dna/extensions/a2a/__init__.py`:

```python
"""A2AExtension — o Agent Card do A2A como documento.

Registra um Kind de record, ``RemoteAgent``, a partir de um descritor.

O A2A (Agent2Agent, governado pela Linux Foundation) padronizou exatamente a
coisa que o DNA já trata como documento: um descritor auto-descritivo de
capacidade. Então falar A2A não pede modelo novo — pede um Kind para o Card que
chega, e uma projeção para o Card que sai (``dna.emit.agent_card``).

Vendor-neutro de propósito: "existe um agente ali, ele sabe estas coisas, e pode
receber estes dados" é fato sobre capacidade e permissão, não sobre hospedagem.
O Kind mora aqui, no SDK OSS; qual face serve o Card de saída, e onde a
credencial de cada remoto é guardada, são decisões do deployment.
"""
from __future__ import annotations

from dna.kernel.source.descriptor_loader import load_descriptors
from dna.kernel.protocols import ExtensionHost


class A2AExtension:
    """Registra ``RemoteAgent`` (descriptor-backed)."""

    name = "a2a"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        for raw in load_descriptors("dna.extensions.a2a"):
            kernel.kind_from_descriptor(raw)
```

Em `packages/sdk-py/pyproject.toml`, ao lado de `artifact`:

```toml
a2a = "dna.extensions.a2a:A2AExtension"
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `cd packages/sdk-py && python -m pytest tests/test_remote_agent_kind.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Rodar as guardas derivadas de docs**

Run: `cd /Users/jefferson.barnabe/projects/dna && python scripts/gen_kinds_docs.py && python scripts/data_model_guard.py --write && python scripts/docs_coverage_guard.py`
Expected: os dois primeiros regeneram (o Kind novo aparece na referência e no
MER); o terceiro passa ou nomeia a prosa que falta — se nomear, escrever a prosa
antes de commitar. **Um Kind novo sem prosa quebra o CI.**

- [ ] **Step 6: Commit**

```bash
git add packages/sdk-py/dna/extensions/a2a packages/sdk-py/tests/test_remote_agent_kind.py packages/sdk-py/pyproject.toml docs/
git commit -m "feat(a2a): RemoteAgent — o Agent Card do A2A como Kind

O protocolo nao e um Kind (transporte nao e documento); o CARD e. Campos do A2A
1.0 em snake_case com o mapeamento anotado, mais data_scope — que e NOSSO e
obrigatorio, porque um RemoteAgent e por construcao um canal de exfiltracao e
escopo implicito significa 'tudo'.

Schema FECHADO: securitySchemes diz COMO autenticar, e a credencial nunca e
documento. signature_state e tri-estado de proposito — 'nao verificado' e
diferente de 'nao assinado', e a ausencia de verificacao tem de ser legivel."
```

---

## Task 2: O roster derivado + a decisão da allowlist dupla (pura)

**Files:**
- Create: `packages/sdk-py/dna/application/delegation.py`
- Test: `packages/sdk-py/tests/test_delegation_policy.py`

**Interfaces:**
- Consumes: o campo `delegation_target_for` (Task 1 no `RemoteAgent`; já
  existente em `AgentSpec` via kernel `DelegationTargetFor`).
- Produces:
  - `DelegationTarget` — dataclass: `name: str`, `kind: str`,
    `format: str`, `typical_seconds: int | None`, `use_when: str | None`,
    `data_scope_kinds: tuple[str, ...] | None`, `interfaces: tuple[dict, ...]`.
  - `may_delegate(delegator_team_members, target_accepts_from, target_name) -> bool`
  - `targets_for(delegator, documents) -> list[DelegationTarget]`

  As Tasks 3–4 dependem destes nomes.

- [ ] **Step 1: Escrever o teste que falha**

`packages/sdk-py/tests/test_delegation_policy.py`:

```python
"""A política de delegação — pura, e é a fronteira de autorização.

Ela decide, por chamada, quem pode pedir trabalho a quem. Um erro aqui não é bug
de feature: é fronteira de autorização. Por isso a política mora sozinha, sem
transporte, sem parse e sem timeout no mesmo arquivo — a lição de 29/07 no
dna-cloud foi que a política pura estava CERTA nos treze defeitos e o erro estava
sempre na montagem em volta. Manter a parte correta pequena é o ponto.

As propriedades pinadas:

1. **A allowlist é DUPLA.** O delegador declara (`team_members`) E o alvo aceita
   (`delegation_target_for.agents`). Uma ponta só é autorização unilateral.
2. **O roster é DERIVADO, não enumerado** — atravessa `Agent` e `RemoteAgent`
   por quem DECLARA o bloco, nunca por uma lista de Kinds.
3. **`"*"` aceita qualquer delegador**, mas ainda exige a outra ponta.
"""
from __future__ import annotations

from dna.application.delegation import DelegationTarget, may_delegate, targets_for


# ── 1. a allowlist dupla ────────────────────────────────────────────────────


def test_both_ends_must_agree():
    # o caso feliz: o delegador lista o alvo E o alvo aceita o delegador
    assert may_delegate(["converter"], ["supervisor"], "converter") is True


def test_the_delegator_alone_is_not_enough():
    """Só `team_members` é autorização unilateral — o alvo nunca consentiu.

    Remova a checagem do lado do alvo e isto morre: qualquer agente poderia
    puxar trabalho de qualquer outro só por listá-lo."""
    assert may_delegate(["converter"], [], "converter") is False


def test_the_target_alone_is_not_enough():
    """Só `delegation_target_for` também não basta — o delegador não o declarou.

    Um alvo que aceita `"*"` não vira alvo de quem não o listou."""
    assert may_delegate([], ["*"], "converter") is False


def test_a_wildcard_target_still_needs_the_delegator_to_list_it():
    assert may_delegate(["converter"], ["*"], "converter") is True
    assert may_delegate(["outro"], ["*"], "converter") is False


def test_a_target_that_accepts_someone_else_refuses_us():
    assert may_delegate(["converter"], ["jarvis"], "converter") is False


# ── 2. o roster derivado ────────────────────────────────────────────────────


def _agent_doc(name, accepts, **extra):
    """Um documento `Agent` que declara o bloco de delegação."""
    spec = {"instruction": "…", "delegation_target_for": {"agents": accepts, **extra}}
    return {"kind": "Agent", "metadata": {"name": name}, "spec": spec}


def _remote_doc(name, accepts, scope_kinds=("SourceArtifact",), **extra):
    spec = {
        "name": name,
        "description": "…",
        "supported_interfaces": [{"transport": "jsonrpc", "url": "https://x/a2a"}],
        "data_scope": {"kinds": list(scope_kinds)},
        "delegation_target_for": {"agents": accepts, **extra},
    }
    return {"kind": "RemoteAgent", "metadata": {"name": name}, "spec": spec}


def _supervisor(team):
    return {
        "kind": "Agent",
        "metadata": {"name": "supervisor"},
        "spec": {"team_members": list(team)},
    }


def test_the_roster_spans_BOTH_kinds():
    """A propriedade central. O roster é 'quem declara o bloco e me aceita' —
    não 'os Agents, e também os RemoteAgents'.

    Faça-o filtrar por Kind e isto morre, junto com a capacidade de um terceiro
    tipo de alvo entrar sem tocar em quem delega."""
    docs = [
        _supervisor(["local-conv", "remote-conv"]),
        _agent_doc("local-conv", ["supervisor"], format="json"),
        _remote_doc("remote-conv", ["supervisor"], format="json"),
    ]
    targets = targets_for("supervisor", docs)
    assert {t.name for t in targets} == {"local-conv", "remote-conv"}
    assert {t.kind for t in targets} == {"Agent", "RemoteAgent"}


def test_a_document_without_the_block_is_not_a_target():
    docs = [
        _supervisor(["plain"]),
        {"kind": "Agent", "metadata": {"name": "plain"}, "spec": {"instruction": "…"}},
    ]
    assert targets_for("supervisor", docs) == []


def test_a_target_the_supervisor_did_not_list_is_absent():
    docs = [_supervisor([]), _agent_doc("lonely", ["*"])]
    assert targets_for("supervisor", docs) == []


def test_the_target_carries_what_the_delegator_needs_to_narrate_and_parse():
    """`format` dirige o parse do retorno; `typical_seconds` e `use_when` dirigem
    a narração e a escolha do alvo. Sem eles o delegador adivinha."""
    docs = [
        _supervisor(["conv"]),
        _agent_doc(
            "conv", ["supervisor"], format="slug", typical_seconds=9, use_when="quando X"
        ),
    ]
    (t,) = targets_for("supervisor", docs)
    assert (t.format, t.typical_seconds, t.use_when) == ("slug", 9, "quando X")


def test_a_remote_target_carries_its_data_scope_and_interfaces():
    """O executor (Task 4) precisa dos dois para recusar fora de escopo e para
    saber onde chamar."""
    docs = [_supervisor(["r"]), _remote_doc("r", ["supervisor"], scope_kinds=["Invoice"])]
    (t,) = targets_for("supervisor", docs)
    assert t.data_scope_kinds == ("Invoice",)
    assert t.interfaces[0]["url"] == "https://x/a2a"


def test_a_local_target_has_no_data_scope():
    """Um Agent local não atravessa fronteira — `data_scope` é do remoto.
    `None` (e não uma tupla vazia) diz 'não se aplica', não 'nada permitido'."""
    docs = [_supervisor(["c"]), _agent_doc("c", ["supervisor"])]
    (t,) = targets_for("supervisor", docs)
    assert t.data_scope_kinds is None


def test_the_default_format_is_text():
    """O kernel documenta `format` default `text`. O roster não inventa outro."""
    docs = [_supervisor(["c"]), _agent_doc("c", ["supervisor"])]
    (t,) = targets_for("supervisor", docs)
    assert t.format == "text"
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd packages/sdk-py && python -m pytest tests/test_delegation_policy.py -q`
Expected: FAIL — `ModuleNotFoundError: dna.application.delegation`.

- [ ] **Step 3: Implementar a política**

`packages/sdk-py/dna/application/delegation.py`:

```python
"""A política de delegação — quem pode pedir trabalho a quem, e com quais dados.

PURA de propósito: nenhum transporte, nenhum parse, nenhum timeout. Esta é a
fronteira de autorização da feature, e ela merece ser lida e revisada sozinha.
(Em 29/07 o dna-cloud teve treze defeitos de identidade; em TODOS a política pura
estava certa e o erro estava na montagem em volta. Manter a parte correta pequena
é o que torna isso possível.)

── As duas regras ───────────────────────────────────────────────────────────

1. **A allowlist é DUPLA.** O delegador declara o alvo (`AgentSpec.team_members`)
   E o alvo aceita o delegador (`delegation_target_for.agents`). As duas, sempre.
   Uma ponta só seria autorização unilateral: com só a primeira, qualquer agente
   puxaria trabalho de qualquer outro por listá-lo; com só a segunda, um alvo que
   aceita `"*"` seria alvo de quem nunca o quis.

2. **O roster é DERIVADO.** "Todo documento que declara `delegation_target_for` e
   cuja allowlist me inclui" — não uma lista de Kinds. `Agent` e `RemoteAgent`
   entram pelo mesmo caminho porque declaram o mesmo bloco, e um terceiro tipo de
   alvo, depois, entra sem uma linha de mudança aqui. Toda lista mantida à mão
   neste projeto ficou cega e verde; esta consulta não pode ficar.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

#: O default que o kernel documenta para `format` ("free-form narrative").
DEFAULT_FORMAT = "text"


@dataclass(frozen=True)
class DelegationTarget:
    """Um alvo de delegação, já autorizado pelas duas pontas.

    `data_scope_kinds` é `None` para um alvo LOCAL — "não se aplica", que é
    diferente de "nada permitido" (uma tupla vazia). O executor usa essa
    distinção para saber se há fronteira a policiar.
    """

    name: str
    kind: str
    format: str = DEFAULT_FORMAT
    typical_seconds: int | None = None
    use_when: str | None = None
    purpose: str | None = None
    data_scope_kinds: tuple[str, ...] | None = None
    interfaces: tuple[Mapping[str, Any], ...] = ()


def may_delegate(
    delegator_team_members: Iterable[str],
    target_accepts_from: Iterable[str],
    target_name: str,
) -> bool:
    """As DUAS pontas concordam? Ver a regra 1 no cabeçalho do módulo."""
    listed = target_name in set(delegator_team_members or ())
    accepts = set(target_accepts_from or ())
    accepted = "*" in accepts or _delegator_in(accepts)
    return listed and accepted


# `may_delegate` recebe o nome do ALVO e a allowlist do alvo; o nome do
# DELEGADOR é fechado pelo chamador (`targets_for`), que é quem o conhece. Manter
# a assinatura assim deixa a função testável com três argumentos simples.
def _delegator_in(accepts: set[str]) -> bool:  # pragma: no cover - ver nota
    raise NotImplementedError


def _spec(doc: Mapping[str, Any]) -> Mapping[str, Any]:
    return doc.get("spec") or {}


def _name(doc: Mapping[str, Any]) -> str:
    return str((doc.get("metadata") or {}).get("name") or "")


def targets_for(
    delegator: str, documents: Iterable[Mapping[str, Any]]
) -> list[DelegationTarget]:
    """Os alvos que `delegator` pode alcançar, derivados dos documentos.

    Ver a regra 2: a consulta é por QUEM DECLARA o bloco, nunca por Kind.
    """
    docs = list(documents)
    team: set[str] = set()
    for doc in docs:
        if _name(doc) == delegator:
            team = set(_spec(doc).get("team_members") or ())
            break

    out: list[DelegationTarget] = []
    for doc in docs:
        block = _spec(doc).get("delegation_target_for")
        if not isinstance(block, Mapping):
            continue
        name = _name(doc) or str(_spec(doc).get("name") or "")
        if name == delegator:
            continue
        accepts = set(block.get("agents") or ())
        if name not in team:
            continue
        if "*" not in accepts and delegator not in accepts:
            continue
        scope = _spec(doc).get("data_scope")
        out.append(
            DelegationTarget(
                name=name,
                kind=str(doc.get("kind") or ""),
                format=str(block.get("format") or DEFAULT_FORMAT),
                typical_seconds=block.get("typical_seconds"),
                use_when=block.get("use_when"),
                purpose=block.get("purpose"),
                data_scope_kinds=(
                    tuple(scope.get("kinds") or ())
                    if isinstance(scope, Mapping)
                    else None
                ),
                interfaces=tuple(_spec(doc).get("supported_interfaces") or ()),
            )
        )
    return out
```

⚠️ **Nota para quem implementa:** o esboço acima deixa `may_delegate` com um
`_delegator_in` não implementado de propósito — a assinatura de três argumentos
do teste (`delegator_team_members, target_accepts_from, target_name`) não carrega
o nome do delegador, então "o alvo me aceita" não é decidível dentro dela.
**Resolva assim:** troque a assinatura para
`may_delegate(delegator, delegator_team_members, target_accepts_from, target_name)`
e ajuste os testes do Step 1 para passar `"supervisor"` como primeiro argumento.
A lógica de `targets_for` (que já decide corretamente, inline) é a referência.
Deixei o defeito visível em vez de escondê-lo porque descobri-lo ao escrever o
plano é mais barato que descobri-lo em revisão — e porque um plano que finge não
ter arestas ensina a confiar nele sem ler.

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `cd packages/sdk-py && python -m pytest tests/test_delegation_policy.py -q`
Expected: PASS (todos), depois do ajuste de assinatura da nota.

- [ ] **Step 5: Matar os mutantes da fronteira de autorização**

Aplique um por vez, confirme que **mata** um teste, e reverta:

| mutante | tem de matar |
|---|---|
| tirar `if name not in team: continue` | `test_the_delegator_alone_is_not_enough` / `..._did_not_list_it` |
| tirar a checagem de `accepts` | `test_the_target_alone_is_not_enough` |
| filtrar por `doc["kind"] == "Agent"` | `test_the_roster_spans_BOTH_kinds` |
| `data_scope_kinds=()` quando ausente | `test_a_local_target_has_no_data_scope` |

Nenhum sobrevivente. Um mutante que sobrevive é um teste que não prova nada — o
padrão que custou caro em 29/07.

- [ ] **Step 6: Commit**

```bash
git add packages/sdk-py/dna/application/delegation.py packages/sdk-py/tests/test_delegation_policy.py
git commit -m "feat(delegation): a politica pura — allowlist dupla e roster derivado

Duas regras. (1) A allowlist e DUPLA: o delegador declara (team_members) E o alvo
aceita (delegation_target_for.agents). Uma ponta so e autorizacao unilateral.
(2) O roster e DERIVADO — 'todo documento que declara o bloco e cuja allowlist me
inclui' — atravessando Agent e RemoteAgent pelo mesmo caminho, porque declaram o
mesmo bloco. Um terceiro tipo de alvo entra sem tocar aqui.

Pura de proposito, sem transporte/parse/timeout: esta e a fronteira de
autorizacao, e em 29/07 a licao foi que a politica pura estava certa nos treze
defeitos e o erro estava sempre na montagem em volta. Quatro mutantes morrem."
```

---

## Task 3: O executor — transporte local

**Files:**
- Create: `packages/sdk-py/dna/application/delegation_exec.py`
- Test: `packages/sdk-py/tests/test_delegation_exec_local.py`

**Interfaces:**
- Consumes: `targets_for` / `DelegationTarget` (Task 2).
- Produces:
  - `class DelegationRefused(Exception)` — recusa nomeada.
  - `async def delegate(delegator, target_name, request, *, documents, run_local, call_remote, now=None) -> dict`
    onde `run_local(target_name, request) -> str` e
    `call_remote(target, request) -> str` são **injetados** (o transporte real é
    a Task 4; aqui o remoto é dublê).
  - `parse_result(format, raw) -> Any`

- [ ] **Step 1: Escrever o teste que falha**

`packages/sdk-py/tests/test_delegation_exec_local.py`:

```python
"""O executor de `delegate_to` — o caminho local, e as recusas.

`delegate_to` estava declarado no kernel desde antes desta feature e NUNCA teve
implementação: aparecia só em `models.py`. Capacidade existe, porta não. Isto é a
porta.

O que se pina aqui é sobretudo RECUSA. Um executor que despacha o caminho felizo
e falha aberto na autorização é pior que nenhum — e as recusas são o que a
política (Task 2) existe para decidir.
"""
from __future__ import annotations

import asyncio

import pytest

from dna.application.delegation_exec import (
    DelegationRefused,
    delegate,
    parse_result,
)


def _docs(team=("conv",), accepts=("supervisor",), fmt="text"):
    return [
        {
            "kind": "Agent",
            "metadata": {"name": "supervisor"},
            "spec": {"team_members": list(team)},
        },
        {
            "kind": "Agent",
            "metadata": {"name": "conv"},
            "spec": {
                "instruction": "…",
                "delegation_target_for": {"agents": list(accepts), "format": fmt},
            },
        },
    ]


def _run(**kw):
    async def _local(name, request):
        return f"feito por {name}: {request}"

    async def _remote(target, request):  # pragma: no cover — não usado aqui
        raise AssertionError("o caminho remoto não deve ser tocado por alvo local")

    kw.setdefault("run_local", _local)
    kw.setdefault("call_remote", _remote)
    return asyncio.run(delegate(**kw))


def test_a_local_delegation_runs_and_returns():
    out = _run(
        delegator="supervisor",
        target_name="conv",
        request="converta isto",
        documents=_docs(),
    )
    assert "feito por conv" in out["result"]
    assert out["target"] == "conv"


def test_an_unlisted_target_is_REFUSED_by_name():
    """A recusa carrega o motivo. Silêncio aqui seria a pior falha possível: o
    delegador narraria sucesso sobre trabalho que ninguém fez."""
    with pytest.raises(DelegationRefused) as exc:
        _run(
            delegator="supervisor",
            target_name="conv",
            request="x",
            documents=_docs(team=()),
        )
    assert "conv" in str(exc.value)


def test_a_target_that_does_not_accept_us_is_REFUSED():
    with pytest.raises(DelegationRefused):
        _run(
            delegator="supervisor",
            target_name="conv",
            request="x",
            documents=_docs(accepts=("jarvis",)),
        )


def test_an_unknown_target_is_REFUSED_not_silently_skipped():
    with pytest.raises(DelegationRefused):
        _run(
            delegator="supervisor",
            target_name="nao-existe",
            request="x",
            documents=_docs(),
        )


def test_the_local_path_never_calls_the_remote_transport():
    """Pinado porque o inverso — um alvo local vazando pela rede — seria
    exfiltração silenciosa. O dublê remoto do módulo levanta se tocado."""
    out = _run(
        delegator="supervisor", target_name="conv", request="x", documents=_docs()
    )
    assert out["transport"] == "local"


# ── o parse por `format` ────────────────────────────────────────────────────


def test_text_is_returned_as_is():
    assert parse_result("text", "narrativa livre") == "narrativa livre"


def test_json_is_parsed():
    assert parse_result("json", '{"a": 1}') == {"a": 1}


def test_malformed_json_is_REFUSED_not_returned_as_text():
    """Cair para texto esconderia um alvo que quebrou o contrato que ELE
    declarou. O delegador tem de saber."""
    with pytest.raises(DelegationRefused):
        parse_result("json", "isto nao e json")


def test_slug_takes_the_last_nonempty_line():
    assert parse_result("slug", "criando…\ns-nota-fiscal-001\n") == "s-nota-fiscal-001"


def test_an_unknown_format_is_REFUSED():
    with pytest.raises(DelegationRefused):
        parse_result("xml", "<a/>")
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd packages/sdk-py && python -m pytest tests/test_delegation_exec_local.py -q`
Expected: FAIL — `ModuleNotFoundError: dna.application.delegation_exec`.

- [ ] **Step 3: Implementar o executor (caminho local + parse)**

`packages/sdk-py/dna/application/delegation_exec.py`:

```python
"""O executor de `delegate_to` — a porta que faltava.

`delegate_to` vivia no kernel apenas como VOCABULÁRIO: o bloco
`delegation_target_for` e o campo `team_members` estavam modelados, documentados
e sem uma linha de implementação em nenhum pacote. Capacidade existe, porta não —
o padrão que este projeto já viu três vezes. Isto é a porta.

── A forma ──────────────────────────────────────────────────────────────────

A política (`dna.application.delegation`) decide QUEM pode chamar QUEM. Este
módulo decide COMO: resolve o alvo pelo roster, escolhe o transporte pelo Kind do
alvo, e parseia o retorno pelo `format` que o ALVO declarou.

Os transportes são INJETADOS (`run_local`, `call_remote`). Não é adorno de
testabilidade: é o que faz a face A2A ser aditiva. Um alvo que era local passa a
remoto trocando o documento, e nem o supervisor nem este módulo mudam.

── Recusa nomeada, nunca silêncio ───────────────────────────────────────────

Toda recusa levanta `DelegationRefused` com o motivo. O pior modo de falha desta
feature não é um erro: é um delegador narrando "convertido!" sobre trabalho que
ninguém fez. Silêncio produz exatamente isso.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, Iterable, Mapping

from dna.application.delegation import DelegationTarget, targets_for

_LOGGER = logging.getLogger("dna.delegation")

#: Os formatos de retorno que o kernel declara.
FORMATS = ("slug", "json", "text")


class DelegationRefused(Exception):
    """Uma delegação recusada, com o motivo no texto.

    Exceção própria (e não `PermissionError`) porque o chamador precisa
    distinguir "não pode" de qualquer outra falha — e porque uma enumeração de
    exceções alheias já ficou cega neste projeto."""


def parse_result(fmt: str, raw: str) -> Any:
    """Interpretar o retorno do alvo pelo `format` que ele declarou.

    Um `json` malformado é RECUSADO, não devolvido como texto: cair para texto
    esconderia um alvo que quebrou o próprio contrato, e o delegador seguiria
    adiante achando que entendeu.
    """
    if fmt not in FORMATS:
        raise DelegationRefused(
            f"formato de retorno desconhecido {fmt!r} — o kernel declara {FORMATS}"
        )
    if fmt == "text":
        return raw
    if fmt == "json":
        try:
            return json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise DelegationRefused(
                f"o alvo declarou format=json e devolveu algo que não é json: {exc}"
            ) from exc
    lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
    if not lines:
        raise DelegationRefused("o alvo declarou format=slug e não devolveu slug algum")
    return lines[-1]


async def delegate(
    *,
    delegator: str,
    target_name: str,
    request: str,
    documents: Iterable[Mapping[str, Any]],
    run_local: Callable[[str, str], Awaitable[str]],
    call_remote: Callable[[DelegationTarget, str], Awaitable[str]],
) -> dict:
    """Delegar `request` a `target_name`, em nome de `delegator`.

    Recusa (nunca devolve silenciosamente) quando o alvo não está no roster —
    o que cobre, pela política, tanto "o delegador não o listou" quanto "o alvo
    não aceita este delegador".
    """
    roster = {t.name: t for t in targets_for(delegator, documents)}
    target = roster.get(target_name)
    if target is None:
        raise DelegationRefused(
            f"{delegator!r} não pode delegar a {target_name!r}: o alvo não está no "
            f"roster (ou o delegador não o declarou em team_members, ou o alvo não "
            f"aceita este delegador em delegation_target_for.agents). "
            f"Alvos disponíveis: {sorted(roster) or 'nenhum'}"
        )

    if target.kind == "RemoteAgent":
        raw = await call_remote(target, request)
        transport = "a2a"
    else:
        raw = await run_local(target.name, request)
        transport = "local"

    _LOGGER.info(
        "delegated", extra={"delegator": delegator, "target": target_name, "transport": transport}
    )
    return {
        "target": target.name,
        "transport": transport,
        "format": target.format,
        "result": parse_result(target.format, raw),
    }
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `cd packages/sdk-py && python -m pytest tests/test_delegation_exec_local.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add packages/sdk-py/dna/application/delegation_exec.py packages/sdk-py/tests/test_delegation_exec_local.py
git commit -m "feat(delegation): o executor — a porta que faltava, e as recusas

delegate_to vivia no kernel apenas como VOCABULARIO: o bloco
delegation_target_for e o campo team_members modelados, documentados, e sem uma
linha de implementacao em nenhum pacote. Capacidade existe, porta nao. Isto e a
porta.

Transportes INJETADOS, e nao por testabilidade: e o que faz a face A2A ser
aditiva — um alvo que era local passa a remoto trocando o DOCUMENTO, sem o
supervisor nem este modulo mudarem.

Recusa nomeada em todo caminho. O pior modo de falha aqui nao e um erro, e um
delegador narrando 'convertido!' sobre trabalho que ninguem fez — silencio
produz exatamente isso. Um json malformado tambem recusa, em vez de cair para
texto e esconder um alvo que quebrou o proprio contrato."
```

---

## Task 4: O transporte A2A — e as duas regras de segurança

**Files:**
- Create: `packages/sdk-py/dna/application/a2a_transport.py`
- Test: `packages/sdk-py/tests/test_a2a_transport.py`

**Interfaces:**
- Consumes: `DelegationTarget` (Task 2), `DelegationRefused` (Task 3).
- Produces:
  - `def scope_allows(target, payload_kinds) -> bool`
  - `async def call_remote(target, request, *, credential_for, http) -> str`
    — `credential_for(target_name) -> str | None` é injetado (a credencial é do
    **deployment**, por remoto) e `http` é um cliente httpx injetado.

- [ ] **Step 1: Escrever o teste que falha**

`packages/sdk-py/tests/test_a2a_transport.py`:

```python
"""O transporte A2A de saída — e as duas regras que o desenho exige.

Um `RemoteAgent` é, por construção, um canal de exfiltração: o DNA manda dado do
workspace para uma URL que o tenant escolheu. As duas regras abaixo são o que
separa isso de um vazamento, e são asseridas — não revisadas a olho.
"""
from __future__ import annotations

import asyncio

import pytest

from dna.application.delegation import DelegationTarget
from dna.application.delegation_exec import DelegationRefused
from dna.application.a2a_transport import call_remote, scope_allows

_TARGET = DelegationTarget(
    name="invoice-reader",
    kind="RemoteAgent",
    format="json",
    data_scope_kinds=("SourceArtifact",),
    interfaces=({"transport": "jsonrpc", "url": "https://vendor.example/a2a"},),
)


# ── regra 1: o escopo de dados ──────────────────────────────────────────────


def test_a_payload_inside_the_scope_is_allowed():
    assert scope_allows(_TARGET, ["SourceArtifact"]) is True


def test_a_payload_OUTSIDE_the_scope_is_refused():
    """O ponto do `data_scope`. Aprovar um remoto não é 'essa URL é ok', é 'este
    endpoint pode receber ESTES dados'."""
    assert scope_allows(_TARGET, ["SourceArtifact", "WorkspaceMembership"]) is False


def test_an_empty_scope_allows_nothing():
    """Estado honesto: registrado, sem permissão. Não é erro, e não é 'tudo'."""
    empty = DelegationTarget(name="x", kind="RemoteAgent", data_scope_kinds=())
    assert scope_allows(empty, ["SourceArtifact"]) is False


def test_a_target_with_no_scope_declared_allows_nothing():
    """`None` num alvo REMOTO é ausência de declaração, e deve falhar fechado.
    (Num alvo local `None` significa 'não se aplica' — quem chama aqui só passa
    remotos.)"""
    none_scope = DelegationTarget(name="x", kind="RemoteAgent", data_scope_kinds=None)
    assert scope_allows(none_scope, ["SourceArtifact"]) is False


# ── regra 2: a credencial nunca é a do usuário ──────────────────────────────


class _FakeHttp:
    """Registra exatamente o que foi enviado — headers inclusive."""

    def __init__(self, reply='{"ok": true}'):
        self.reply = reply
        self.sent = []

    async def post(self, url, *, json=None, headers=None, timeout=None):
        self.sent.append({"url": url, "json": json, "headers": dict(headers or {})})

        class _R:
            status_code = 200

            def __init__(self, text):
                self.text = text

            def json(self_inner):
                import json as _j

                return _j.loads(self_inner.text)

        return _R(self.reply)


def _call(target=_TARGET, credential="ws-cred-123", payload_kinds=("SourceArtifact",), http=None):
    http = http or _FakeHttp()
    out = asyncio.run(
        call_remote(
            target,
            "leia isto",
            credential_for=lambda name: credential,
            http=http,
            payload_kinds=payload_kinds,
        )
    )
    return out, http


def test_the_workspace_credential_is_sent():
    _, http = _call()
    assert "ws-cred-123" in http.sent[0]["headers"].get("authorization", "")


def test_NO_user_bearer_can_reach_the_remote():
    """A regra mais importante do módulo.

    `call_remote` não tem parâmetro por onde um token de usuário entre — a
    credencial vem de `credential_for`, que é do DEPLOYMENT, por remoto.
    Repassar o bearer do usuário faria de cada remoto uma impersonação completa
    dele contra o nosso próprio MCP.

    Asserido pela ASSINATURA, que é o que um chamador pode alcançar: nenhum
    parâmetro aceita identidade de caller."""
    import inspect

    params = set(inspect.signature(call_remote).parameters)
    for forbidden in ("token", "bearer", "claims", "identity", "user", "authorization"):
        assert forbidden not in params, (
            f"call_remote expõe {forbidden!r} — um caminho para o token do usuário "
            f"atravessar a fronteira"
        )


def test_a_missing_credential_REFUSES_instead_of_calling_anonymously():
    """Chamar sem credencial poderia ser aceito pelo remoto e é decisão que
    ninguém tomou. Recusa nomeada."""
    http = _FakeHttp()
    with pytest.raises(DelegationRefused):
        _call(credential=None, http=http)
    assert http.sent == [], "recusou e ainda assim chamou"


def test_a_payload_out_of_scope_REFUSES_BEFORE_the_call():
    """A ordem importa: a checagem tem de ser ANTES do envio, senão o dado já
    saiu quando a recusa acontece."""
    http = _FakeHttp()
    with pytest.raises(DelegationRefused):
        _call(payload_kinds=("WorkspaceMembership",), http=http)
    assert http.sent == [], "o dado saiu antes da recusa"


def test_only_https_is_dialed():
    """O descritor já exige `https://` no schema; o transporte não confia nisso
    e checa de novo — um documento antigo, ou um schema afrouxado, não deve
    virar texto claro na rede."""
    plain = DelegationTarget(
        name="x",
        kind="RemoteAgent",
        data_scope_kinds=("SourceArtifact",),
        interfaces=({"transport": "jsonrpc", "url": "http://vendor.example/a2a"},),
    )
    with pytest.raises(DelegationRefused):
        _call(target=plain)
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd packages/sdk-py && python -m pytest tests/test_a2a_transport.py -q`
Expected: FAIL — `ModuleNotFoundError: dna.application.a2a_transport`.

- [ ] **Step 3: Implementar o transporte**

`packages/sdk-py/dna/application/a2a_transport.py`:

```python
"""A chamada A2A de saída — e as duas regras que a tornam segura.

Um `RemoteAgent` é, por construção, um canal de exfiltração: o DNA manda dado do
workspace para uma URL que o tenant escolheu. Isso não é defeito do A2A (que é
protocolo de transporte e não tem opinião sobre o assunto) — é a natureza da
coisa. As duas regras abaixo são o que separa isso de um vazamento.

**1. O escopo é checado ANTES do envio.** `data_scope.kinds` diz o que aquele
endpoint pode receber. A ordem é load-bearing: checar depois de postar é
auditoria, não controle.

**2. A credencial é do WORKSPACE, nunca do usuário.** O `security_schemes` do
Card diz COMO autenticar; de quem é a credencial é decisão nossa. Repassar o
bearer de quem está conversando faria de cada agente remoto uma impersonação
completa dele contra o nosso próprio MCP. Por isso `call_remote` não tem
parâmetro algum por onde uma identidade de caller entre — a ausência é asserida
por teste, contra a assinatura.

Ausência de credencial RECUSA, em vez de chamar anonimamente: um remoto pode
aceitar anônimo, e essa não é decisão que alguém tomou.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, Mapping

from dna.application.delegation import DelegationTarget
from dna.application.delegation_exec import DelegationRefused

_LOGGER = logging.getLogger("dna.a2a")

#: Timeout de uma chamada A2A. Generoso (um especialista pode pensar) mas finito:
#: uma delegação pendurada vira um supervisor mudo, que é indistinguível de um
#: supervisor que esqueceu.
DEFAULT_TIMEOUT_S = 120


def scope_allows(target: DelegationTarget, payload_kinds: Iterable[str]) -> bool:
    """O payload cabe no `data_scope` declarado do alvo?

    Fecha em três casos, e todos de propósito: escopo ausente (`None` — num
    remoto isso é falta de declaração), escopo vazio (registrado, sem permissão)
    e qualquer Kind fora da lista.
    """
    allowed = target.data_scope_kinds
    if not allowed:
        return False
    return set(payload_kinds or ()) <= set(allowed)


def _endpoint(target: DelegationTarget) -> str:
    for iface in target.interfaces or ():
        url = str((iface or {}).get("url") or "")
        if url.startswith("https://"):
            return url
        if url:
            raise DelegationRefused(
                f"o remoto {target.name!r} anuncia {url!r}: delegar dado de "
                f"workspace por texto claro não é permitido"
            )
    raise DelegationRefused(
        f"o remoto {target.name!r} não anuncia interface alcançável (https)"
    )


async def call_remote(
    target: DelegationTarget,
    request: str,
    *,
    credential_for: Callable[[str], str | None],
    http: Any,
    payload_kinds: Iterable[str] = (),
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> str:
    """Chamar `target` por A2A e devolver o texto cru (o parse é do executor).

    Nenhum parâmetro aceita identidade de caller — ver a regra 2 no cabeçalho.
    """
    if not scope_allows(target, payload_kinds):
        raise DelegationRefused(
            f"payload fora do data_scope de {target.name!r}: permitido "
            f"{sorted(target.data_scope_kinds or ())}, pedido "
            f"{sorted(set(payload_kinds or ()))}"
        )
    url = _endpoint(target)
    credential = credential_for(target.name)
    if not credential:
        raise DelegationRefused(
            f"nenhuma credencial de workspace configurada para o remoto "
            f"{target.name!r} — chamar anonimamente não é decisão que este "
            f"código pode tomar"
        )

    body = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/send",
        "params": {"message": {"role": "user", "parts": [{"kind": "text", "text": request}]}},
    }
    res = await http.post(
        url,
        json=body,
        headers={"authorization": f"Bearer {credential}", "content-type": "application/json"},
        timeout=timeout_s,
    )
    if getattr(res, "status_code", 500) >= 400:
        raise DelegationRefused(
            f"o remoto {target.name!r} respondeu {res.status_code}"
        )
    _LOGGER.info("a2a call ok", extra={"target": target.name})
    return res.text
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `cd packages/sdk-py && python -m pytest tests/test_a2a_transport.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Matar os mutantes de segurança**

| mutante | tem de matar |
|---|---|
| `scope_allows` devolver `True` com `allowed` vazio/`None` | dois testes de escopo |
| mover a checagem de escopo para DEPOIS do `http.post` | `..._REFUSES_BEFORE_the_call` |
| aceitar `http://` em `_endpoint` | `test_only_https_is_dialed` |
| chamar com `authorization` vazio quando não há credencial | `..._instead_of_calling_anonymously` |
| adicionar um parâmetro `token=` a `call_remote` | `test_NO_user_bearer_can_reach_the_remote` |

- [ ] **Step 6: Commit**

```bash
git add packages/sdk-py/dna/application/a2a_transport.py packages/sdk-py/tests/test_a2a_transport.py
git commit -m "feat(a2a): o transporte de saida — escopo antes do envio, credencial do workspace

Um RemoteAgent e por construcao um canal de exfiltracao. Duas regras separam
isso de um vazamento, e as duas sao ASSERIDAS:

1. O data_scope e checado ANTES do post. A ordem e load-bearing: checar depois
   de enviar e auditoria, nao controle.
2. A credencial e do WORKSPACE, nunca do usuario. call_remote nao tem parametro
   algum por onde uma identidade de caller entre — e a ausencia e asserida
   contra a ASSINATURA, nao revisada a olho. Repassar o bearer de quem conversa
   faria de cada remoto uma impersonacao completa dele contra o nosso MCP.

Sem credencial, RECUSA em vez de chamar anonimo (um remoto pode aceitar anonimo,
e essa nao e decisao que este codigo pode tomar). Cinco mutantes morrem."
```

---

## Task 5: Entrada — um Card de terceiro vira `RemoteAgent` inerte

**Files:**
- Create: `packages/sdk-py/dna/application/a2a_ingest.py`
- Test: `packages/sdk-py/tests/test_a2a_ingest.py`

**Interfaces:**
- Produces:
  - `def card_to_spec(card: Mapping, *, data_scope_kinds: list[str]) -> dict`
    — a tradução pura Card(JSON camelCase) → spec(snake_case), incluindo o
    `signature_state` derivado.
  - `async def ingest_card(url, *, http, data_scope_kinds, write) -> str`

- [ ] **Step 1: Escrever o teste que falha**

`packages/sdk-py/tests/test_a2a_ingest.py`:

```python
"""Entrada: um Agent Card de terceiro vira um `RemoteAgent` INERTE.

Registrar um agente passa a ser escrever um documento — sem deploy, sem edição
de código. E inerte é a palavra que carrega o desenho: um remoto só é delegável
depois que um humano aprova, pelo mesmo funil dos Kinds autorados. Sem isso,
"buscar um Card" seria "conceder acesso a dado do workspace" numa chamada HTTP.
"""
from __future__ import annotations

import asyncio

import pytest

from dna.application.a2a_ingest import card_to_spec, ingest_card

_CARD = {
    "name": "invoice-reader",
    "description": "Reads invoices",
    "version": "2.1.0",
    "supportedInterfaces": [{"transport": "jsonrpc", "url": "https://vendor.example/a2a"}],
    "capabilities": {"streaming": True, "pushNotifications": False},
    "skills": [
        {"id": "read", "name": "Read invoice", "description": "…", "tags": ["ocr"]}
    ],
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["application/json"],
}


def test_the_card_translates_to_the_kind_shape():
    spec = card_to_spec(_CARD, data_scope_kinds=["SourceArtifact"])
    assert spec["name"] == "invoice-reader"
    assert spec["supported_interfaces"][0]["url"] == "https://vendor.example/a2a"
    assert spec["capabilities"]["push_notifications"] is False
    assert spec["default_output_modes"] == ["application/json"]


def test_the_data_scope_comes_from_the_CALLER_not_the_card():
    """O `data_scope` é nosso: um Card de terceiro não declara — e não poderia
    declarar — o que ele tem permissão de receber do nosso workspace."""
    spec = card_to_spec(_CARD, data_scope_kinds=["Invoice"])
    assert spec["data_scope"] == {"kinds": ["Invoice"]}


def test_a_card_without_signatures_is_marked_unsigned():
    spec = card_to_spec(_CARD, data_scope_kinds=[])
    assert spec["signature_state"] == "unsigned"


def test_a_signed_card_is_marked_present_unverified():
    """A verificação criptográfica está fora desta versão. O estado diz isso em
    voz alta, em vez de deixar a ausência de verificação implícita."""
    signed = dict(_CARD, signatures=[{"protected": "…", "signature": "…"}])
    spec = card_to_spec(signed, data_scope_kinds=[])
    assert spec["signature_state"] == "present_unverified"
    assert spec["signatures"] == signed["signatures"]


@pytest.mark.parametrize("missing", ["name", "description", "supportedInterfaces"])
def test_a_card_missing_a_required_field_is_REFUSED(missing):
    bad = {k: v for k, v in _CARD.items() if k != missing}
    with pytest.raises(ValueError):
        card_to_spec(bad, data_scope_kinds=[])


def test_ingest_writes_an_INERT_document():
    """A propriedade central. `write` recebe `approved=False` — buscar um Card
    nunca concede acesso."""
    seen = {}

    class _Http:
        async def get(self, url, *, timeout=None):
            class _R:
                status_code = 200

                def json(self):
                    return _CARD

            return _R()

    async def _write(*, spec, approved):
        seen["spec"] = spec
        seen["approved"] = approved
        return "remote-invoice-reader"

    name = asyncio.run(
        ingest_card(
            "https://vendor.example/.well-known/agent-card.json",
            http=_Http(),
            data_scope_kinds=["SourceArtifact"],
            write=_write,
        )
    )
    assert name == "remote-invoice-reader"
    assert seen["approved"] is False, "um Card buscado NÃO pode nascer aprovado"
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd packages/sdk-py && python -m pytest tests/test_a2a_ingest.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar a entrada**

`packages/sdk-py/dna/application/a2a_ingest.py` — a tradução
Card→spec (camelCase→snake_case, os campos do §4.4 do descritor), o
`signature_state` derivado da presença de `signatures`, a recusa por campo
obrigatório ausente, e `ingest_card` chamando `write(spec=…, approved=False)`.

**O `data_scope` vem do CALLER**, nunca do Card: um terceiro não declara o que
tem permissão de receber do nosso workspace.

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `cd packages/sdk-py && python -m pytest tests/test_a2a_ingest.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/sdk-py/dna/application/a2a_ingest.py packages/sdk-py/tests/test_a2a_ingest.py
git commit -m "feat(a2a): entrada — um Card de terceiro vira RemoteAgent INERTE

Registrar um agente passa a ser escrever um documento: sem deploy, sem edicao de
codigo. E INERTE e a palavra que carrega o desenho — um remoto so e delegavel
depois que um humano aprova, pelo mesmo funil dos Kinds autorados. Sem isso,
'buscar um Card' seria 'conceder acesso a dado do workspace' numa chamada HTTP.

O data_scope vem do CALLER, nunca do Card: um terceiro nao declara — e nao
poderia — o que ele tem permissao de receber do nosso workspace. E
signature_state sai da presenca de signatures, deixando a ausencia de
verificacao dita em voz alta."
```

---

## Task 6: Saída — projetar um `Agent` num Agent Card

**Files:**
- Create: `packages/sdk-py/dna/emit/agent_card.py`
- Test: `packages/sdk-py/tests/test_agent_card_emit.py`

**Interfaces:**
- Produces: `def agent_card_for(agent_doc, *, tools=(), base_url) -> dict` — o
  Card em JSON do A2A (camelCase), pronto para ser servido por qualquer face.

- [ ] **Step 1: Escrever o teste que falha**

`packages/sdk-py/tests/test_agent_card_emit.py`:

```python
"""Saída: um documento `Agent` projetado num Agent Card do A2A.

É `emit` — a tese que o DNA já tem: projetar um documento num artefato que um
sistema externo consome (`dna.emit.mcp_ui`, `dna.emit.frontend`). Um Agent Card é
mais um alvo, não um mecanismo novo. É o lado que permite OUTRO sistema delegar
PARA nós.

O módulo devolve o Card; QUEM o serve e em qual path é decisão de deployment
(`/.well-known/` é convenção de raiz de domínio, e a raiz não é do SDK).
"""
from __future__ import annotations

from dna.emit.agent_card import agent_card_for

_AGENT = {
    "kind": "Agent",
    "metadata": {"name": "converter-agent", "description": "Converte arquivos"},
    "spec": {
        "instruction": "…",
        "model": "gpt-5-mini",
        "delegation_target_for": {
            "agents": ["supervisor-agent"],
            "use_when": "o usuário anexou um arquivo",
            "purpose": "Registra um arquivo como documento tipado",
        },
    },
}


def test_the_required_a2a_fields_are_present():
    card = agent_card_for(_AGENT, base_url="https://dna.example")
    for field in (
        "name",
        "description",
        "supportedInterfaces",
        "version",
        "capabilities",
        "defaultInputModes",
        "defaultOutputModes",
        "skills",
    ):
        assert field in card, f"Card sem {field} não é um Card válido do A2A 1.0"


def test_streaming_is_advertised_because_AG_UI_already_streams():
    card = agent_card_for(_AGENT, base_url="https://dna.example")
    assert card["capabilities"]["streaming"] is True


def test_the_skills_derive_from_the_agents_tools():
    """Derivar, não enumerar: o Card não mantém uma lista paralela do que o
    agente sabe fazer. Troque para uma lista à mão e ela ficará velha em
    silêncio — o modo de falha que este projeto já viu várias vezes."""
    card = agent_card_for(_AGENT, tools=("author_kind", "list_kinds"), base_url="https://x")
    assert {s["id"] for s in card["skills"]} == {"author_kind", "list_kinds"}


def test_the_purpose_becomes_the_description_when_present():
    """`purpose`/`use_when` do bloco de delegação existem para um delegador
    escolher alvo. É exatamente o que um Card comunica."""
    card = agent_card_for(_AGENT, base_url="https://x")
    assert "Registra um arquivo" in card["description"]


def test_no_credential_is_ever_projected():
    """O Card sai; segredo não sai com ele."""
    card = agent_card_for(_AGENT, base_url="https://x")
    flat = repr(card).lower()
    for leak in ("bearer ", "sk-", "api_key", "password", "secret"):
        assert leak not in flat
```

- [ ] **Step 2–5: falhar, implementar, passar, commitar**

Run (falha): `cd packages/sdk-py && python -m pytest tests/test_agent_card_emit.py -q`
Implementar `dna/emit/agent_card.py`: `skills` derivados de `tools`;
`description` preferindo `delegation_target_for.purpose` e caindo para
`metadata.description`; `capabilities.streaming: True`;
`supportedInterfaces` a partir de `base_url`; nenhum campo de credencial.
Run (passa): o mesmo comando.

```bash
git add packages/sdk-py/dna/emit/agent_card.py packages/sdk-py/tests/test_agent_card_emit.py
git commit -m "feat(emit): projetar um Agent num Agent Card do A2A

E emit — a tese que o DNA ja tem: projetar um documento num artefato que um
sistema externo consome. Um Agent Card e mais um alvo, nao mecanismo novo. E o
lado que permite OUTRO sistema delegar PARA nos.

skills DERIVADOS das tools do agente, nunca uma lista paralela (que ficaria
velha em silencio). O modulo devolve o Card; quem serve e em qual path e decisao
de deployment — /.well-known/ e convencao de raiz de dominio, e a raiz nao e do
SDK."
```

---

## Task 7: Fechar o release (a cadeia que o dna exige)

- [ ] **Step 1: Suíte inteira + as quatro guardas derivadas**

```bash
cd /Users/jefferson.barnabe/projects/dna
python -m pytest -q                                  # a suíte
python scripts/gen_kinds_docs.py                     # referência de Kinds
python scripts/data_model_guard.py --write           # o MER
python scripts/docs_coverage_guard.py                # cobertura de prosa
```

Expected: suíte verde; as guardas regeneram ou nomeiam o que falta. **Qualquer
uma delas vermelha bloqueia o release** — as quatro já dispararam antes por Kind
novo sem documentação.

- [ ] **Step 2: Subir a versão nos TRÊS lugares**

`packages/sdk-py/pyproject.toml`, `packages/cli/pyproject.toml`, e o teto
`dna-sdk>=X,<Y` interno do CLI (+ o comentário que o repete). Feature nova =
**minor**, então o teto move.

- [ ] **Step 3: Tag e publicar**

```bash
git tag vX.Y.0 && git push origin vX.Y.0
```

- [ ] **Step 4: Esperar o índice SIMPLE do PyPI (nunca a API JSON)**

```bash
curl -s -H "Accept: application/vnd.pypi.simple.v1+json" https://pypi.org/simple/dna-sdk/ | grep -c "X.Y.0"
```

- [ ] **Step 5: O lockstep no dna-cloud**

Cinco linhas — floor **e** teto em `apps/{mcp,api,copilot}/pyproject.toml` — mais
`uv lock` e a linha de floors no `CLAUDE.md`. Então o plano irmão do dna-cloud
fica desbloqueado.

---

## Auto-revisão deste plano

**Cobertura da spec:** §4 (o Kind) → Task 1. §4.3 (roster derivado) → Task 2.
§5 (executor) → Task 3. §6.1–6.2 (entrada + as três regras) → Tasks 4–5.
§6.3 (saída) → Task 6. §7 (fora de escopo) → nenhuma task, de propósito.

**Placeholders:** um consciente — a Task 5 Step 3 e a Task 6 Step 2 descrevem a
implementação em prosa em vez de dar o código inteiro, porque as duas são
tradução mecânica de campos que o teste já fixa campo a campo. Todas as demais
trazem o código.

**Consistência de tipos:** `DelegationTarget` (Task 2) é consumida com os mesmos
nomes de campo nas Tasks 3, 4 e 6. `DelegationRefused` nasce na Task 3 e é
importada na 4.

**Uma aresta deixada VISÍVEL:** a nota do Task 2 Step 3 — a assinatura de
`may_delegate` no teste não carrega o nome do delegador, então a função como
esboçada não decide. A correção está escrita ali. Deixei o defeito à vista em vez
de silenciosamente reescrever o teste porque um plano que finge não ter arestas
ensina a confiar nele sem ler.
