# A face A2A sobre o SDK oficial — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Servir e consumir A2A pela implementação oficial (`a2a-sdk` 1.1.2), com o
DNA fornecendo só a cola — a projeção do Card, as recusas de política e a ligação
com o kernel.

**Architecture:** Um `DnaAgentExecutor` adapta um agente DNA (`run(text) -> str`) à
interface `AgentExecutor` do SDK; `attach_a2a` monta as rotas JSON-RPC + Card do SDK
num `FastAPI` que o host já tem; `call_remote` passa a falar pelo `Client` do SDK,
preservando as recusas de `data_scope`/credencial que rodam ANTES de qualquer byte.
Nada do protocolo é escrito à mão.

**Tech Stack:** Python 3.12+ · `a2a-sdk[fastapi]` 1.1.2 (protobuf/proto-plus) ·
FastAPI · httpx · pytest · jsonschema

---

## Global Constraints

- **Branch base: `origin/main`.** Medido em 31/07: `rpc.py`, `server.py`,
  `test_a2a_rpc.py`, `test_a2a_server.py`, `test_a2a_stream_client.py` e
  `stream_remote`/`parse_sse_events`/`task_text` existem SOMENTE em
  `feat/a2a-server-face` (PR `dna#292`, fechado). O passo 1 da spec ("remover a
  implementação à mão") custa **zero linha**: basta ramificar de `main`, onde ela
  nunca esteve. Não fazer merge nem cherry-pick de `feat/a2a-server-face`.
  `main` já contém o fix `prefab-ui` (`dna#291`) — nada dela é necessário.
- **Repositório: `~/projects/dna`** (o SDK OSS), NÃO `dna-cloud`. A spec mora em
  dna-cloud; o código todo mora aqui.
- **Versão do SDK: `a2a-sdk>=1.1.2,<2`**, extra `fastapi`. Resolução verificada com
  `uv pip install --dry-run` contra `dna-cli[mcp,api,dev]` e contra
  `dna-sdk[dev,runtime]`: **94 pacotes, sem conflito**. Entram 8 pacotes
  (`protobuf 6.33.6`, `google-api-core`, `googleapis-common-protos`, `proto-plus`,
  `google-auth`, `pyasn1`, `pyasn1-modules`, `json-rpc`). O `protobuf` desce de
  7.35.1 → 6.33.6 no ambiente local do sdk-py (o teto `protobuf<7` do a2a-sdk);
  quem trouxe o 7 foi `onnxruntime` via o extra `embed-onnx`, e a resolução aceita
  o 6.33.6 — medido, não presumido.
- **Nomes do protocolo vêm do SDK, nunca de literal nosso.** `TransportProtocol.JSONRPC`
  (`"JSONRPC"`), `PROTOCOL_VERSION_1_0` (`"1.0"`), `AGENT_CARD_WELL_KNOWN_PATH`
  (`"/.well-known/agent-card.json"`) — todos de `a2a.utils.constants`. Um literal
  à mão é a mesma falha que este plano existe para consertar.
- **O Kind `RemoteAgent` renomeia sem compatibilidade** (decisão do fundador,
  31/07): `transport` → `protocol_binding`, mais `protocol_version`. Nenhum
  `oneOf` de transição, nenhuma normalização de legado.
- **A borda de identidade continua fora.** Nenhum módulo deste plano lê um bearer
  de entrada; a verificação é da porta (ADR `adr-identity-doors-verify-different-sets`).
- **Docstrings em português**, no registro dos módulos vizinhos (`a2a_transport.py`,
  `a2a_ingest.py`): dizer POR QUE, não o que.
- **Comandos de teste** (de `packages/sdk-py/`):
  `uv run --no-project pytest tests/<arquivo> -q --timeout=120 -p no:cacheprovider`

---

## Os três defeitos que este plano conserta (medidos em 31/07)

A versão à mão tinha 49 testes verdes e mutação verde. Nenhum deles pegou isto,
porque foram escritos pela mesma leitura da spec que o código:

| # | onde | a versão à mão | a A2A 1.0 real |
|---|---|---|---|
| 1 | `emit/agent_card.py` | `{"transport": "jsonrpc"}` | `{"protocolBinding": "JSONRPC", "protocolVersion": "1.0"}` |
| 2 | `remote-agent.kind.yaml` | `required: [transport, url]`, fechado | idem #1 |
| 3 | as `parts` | `{"kind": "text", "text": …}` | `{"text": …}` — `Part` é um `oneof`, sem `kind` |

Consequência medida de #1: `ClientFactory._find_best_interface` filtra por
`i.protocol_binding in ["JSONRPC"]` — contra o nosso Card acha **zero** candidatos,
e um cliente conforme não consegue nos chamar.

Consequência medida de #2: `card_to_spec` + validação de um Card conforme →
`Additional properties are not allowed ('protocolBinding', 'protocolVersion' were
unexpected)` **e** `'transport' is a required property`. Nenhum agente A2A 1.0 real
podia ser ingerido.

---

## File Structure

| arquivo | responsabilidade |
|---|---|
| `packages/cli/pyproject.toml` | **MOD** — o extra `a2a` |
| `packages/sdk-py/pyproject.toml` | **MOD** — `a2a-sdk[fastapi]` no extra `dev` (os testes moram aqui) |
| `.github/workflows/python.yml` | **MOD** — o job `sdk-py` instala o extra |
| `packages/sdk-py/dna/emit/agent_card.py` | **MOD** — a projeção, conforme e com `streaming` derivado |
| `packages/sdk-py/dna/extensions/a2a/kinds/remote-agent.kind.yaml` | **MOD** — `protocol_binding` |
| `packages/sdk-py/dna/application/a2a_ingest.py` | **MOD** — o mapa de campos da interface |
| `packages/sdk-py/dna/extensions/a2a/executor.py` | **NOVO** — `DnaAgentExecutor` (a única peça nova; é cola) |
| `packages/sdk-py/dna/extensions/a2a/serve.py` | **NOVO** — `attach_a2a`, sobre as rotas do SDK |
| `packages/sdk-py/dna/application/a2a_transport.py` | **MOD** — `call_remote` sobre o `Client` do SDK |
| `packages/cli/dna_cli/serving.py` | **MOD** — re-exporta `attach_a2a` (o seam público do host) |
| `packages/sdk-py/tests/test_agent_card_emit.py` | **MOD** — a asserção de conformidade |
| `packages/sdk-py/tests/test_a2a_ingest.py` | **MOD** — Card conforme entra |
| `packages/sdk-py/tests/test_a2a_transport.py` | **MOD** — recusas preservadas sobre o novo transporte |
| `packages/sdk-py/tests/test_a2a_executor.py` | **NOVO** |
| `packages/sdk-py/tests/test_a2a_serve.py` | **NOVO** |
| `packages/sdk-py/tests/test_a2a_conformance.py` | **NOVO** — cliente oficial × servidor nosso |

---

### Task 1: O extra `a2a`, e a garantia de que ele é opcional

**Files:**
- Modify: `packages/cli/pyproject.toml` (bloco `[project.optional-dependencies]`, junto de `mcp`/`api`)
- Modify: `packages/sdk-py/pyproject.toml` (lista `dev`)
- Modify: `.github/workflows/python.yml` (passo `Install` do job `sdk-py`)
- Test: `packages/sdk-py/tests/test_a2a_import_isolation.py` (criar)

**Interfaces:**
- Consumes: nada.
- Produces: o extra `dna-cli[a2a]`; `a2a-sdk` disponível nos testes do sdk-py.

- [ ] **Step 1: Escrever o teste que falha — o import base nunca puxa `a2a`**

Espelha `tests/test_embedding_import_isolation.py`, o padrão do repo. Criar
`packages/sdk-py/tests/test_a2a_import_isolation.py`:

```python
"""O extra `a2a` é OPCIONAL — e a garantia é estrutural, não documental.

`a2a-sdk` traz oito dependências base (protobuf, google-api-core,
googleapis-common-protos e a árvore de auth do Google), herança do transporte
gRPC que nem usamos. Quem não serve A2A não pode pagar por elas. Um import
solto no topo de um módulo do kernel converteria "extra opcional" em
"dependência de todo mundo" sem que ninguém percebesse — este teste é o que
percebe.
"""
from __future__ import annotations

import subprocess
import sys


def test_o_import_base_do_dna_nunca_puxa_a2a():
    codigo = (
        "import dna, dna.application.a2a_transport, dna.application.a2a_ingest, "
        "dna.emit.agent_card, dna.extensions.a2a; "
        "import sys; "
        "vazados = sorted(m for m in sys.modules if m == 'a2a' or m.startswith('a2a.')); "
        "print(','.join(vazados))"
    )
    saida = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, text=True, check=True
    )
    vazados = [m for m in saida.stdout.strip().split(",") if m]
    assert not vazados, (
        f"importar o DNA puxou {vazados} — o extra `a2a` deixou de ser opcional"
    )
```

- [ ] **Step 2: Rodar e ver falhar/passar por engano**

```bash
cd packages/sdk-py
uv run --no-project pytest tests/test_a2a_import_isolation.py -q --timeout=120 -p no:cacheprovider
```

Esperado agora: **PASS** — não há import de `a2a` ainda. O teste é a rede de
segurança das Tasks 4–6, não um teste vermelho-primeiro. Confirme que ele passa e
siga; ele volta a importar quando o executor existir.

- [ ] **Step 3: Declarar o extra no `dna-cli`**

Em `packages/cli/pyproject.toml`, logo depois da linha `api = [...]`:

```toml
# A face A2A (Agent2Agent, governado pela Linux Foundation) — servir e consumir
# pelo SDK OFICIAL, `a2a-sdk`. Extra próprio, ao lado de `mcp` e `api`, por uma
# razão medida: a árvore BASE do a2a-sdk traz protobuf, google-api-core e
# googleapis-common-protos mesmo para quem só usa JSON-RPC (herança do
# transporte gRPC). São oito dependências, três pesadas. Quem não serve A2A não
# paga; quem serve paga o protobuf sem usar, e esse é o custo da conformidade —
# que é o produto.
#
# `[fastapi]` porque é o que traz `a2a.server.routes.fastapi_routes`
# (`add_a2a_routes_to_fastapi`) + sse-starlette, e a face servida monta num
# FastAPI que o host já tem. Sem gRPC: `dna` fala JSON-RPC, e o extra `grpc`
# arrastaria grpcio/grpcio-tools por um transporte que não servimos.
#
# Teto `<2`: o 1.x já foi uma quebra grande (os tipos viraram protobuf, e
# `AgentInterface.transport` virou `protocolBinding`). Subir de major é decisão,
# não efeito colateral de um `pip install`.
a2a = ["a2a-sdk[fastapi]>=1.1.2,<2"]
```

- [ ] **Step 4: Tornar o SDK disponível aos testes do sdk-py**

O código mora em `dna/extensions/a2a/` (sdk-py) mas o extra é do `dna-cli` — o
mesmo arranjo que `fastapi`/extra `api` já tem com `extensions/a2a/serve.py`. Para
os testes rodarem, `a2a-sdk` entra em `dev`. Em `packages/sdk-py/pyproject.toml`,
dentro da lista `dev = [...]`, antes do `]` final:

```toml
    # A face A2A é servida/consumida pelo SDK OFICIAL. O extra de PRODUÇÃO é
    # `dna-cli[a2a]` (o código serve HTTP, e o dna-cli é quem declara faces);
    # aqui ele entra em `dev` porque os testes moram neste pacote. Os testes que
    # o exigem fazem `importorskip("a2a")`, então um ambiente sem ele coleta
    # limpo — e `tests/test_a2a_import_isolation.py` garante que o import base
    # do DNA continua sem tocá-lo.
    "a2a-sdk[fastapi]>=1.1.2,<2",
```

- [ ] **Step 5: Instalar e confirmar a resolução**

```bash
cd packages/sdk-py
uv pip install -e ".[dev,runtime]" fastapi
uv run --no-project python -c "import a2a, importlib.metadata as m; print(m.version('a2a-sdk'))"
```

Esperado: `1.1.2` (ou maior dentro de `<2`).

- [ ] **Step 6: Ensinar o CI**

Em `.github/workflows/python.yml`, job `sdk-py`, passo `Install`: a linha
`uv pip install -e ".[dev,runtime]" fastapi "ag-ui-langgraph==0.0.42"` já cobre o
novo extra, porque `a2a-sdk` entrou em `dev` no Step 4. **Nenhuma edição é
necessária** — verifique lendo o arquivo e confirme; se `dev` não estiver na
linha de instalação, adicione `a2a-sdk[fastapi]` explicitamente.

- [ ] **Step 7: Rodar a suíte inteira e confirmar que nada quebrou**

```bash
cd packages/sdk-py
uv run --no-project pytest tests -q --timeout=120 -p no:cacheprovider 2>&1 | tail -20
```

Esperado: mesmo número de passes de antes, zero falhas.

- [ ] **Step 8: Commit**

```bash
git add packages/cli/pyproject.toml packages/sdk-py/pyproject.toml \
        packages/sdk-py/tests/test_a2a_import_isolation.py
git commit -m "chore(a2a): o extra oficial — a2a-sdk[fastapi], e a guarda de que ele é opcional"
```

---

### Task 2: A projeção do Card — conforme, e provada contra o parser oficial

**Files:**
- Modify: `packages/sdk-py/dna/emit/agent_card.py`
- Test: `packages/sdk-py/tests/test_agent_card_emit.py`

**Interfaces:**
- Consumes: o extra da Task 1.
- Produces: `agent_card_for(agent_doc, *, tools=(), base_url, streaming=False) -> dict`
  — **assinatura mudou**: `streaming` é novo, keyword-only, default `False`.
  `supportedInterfaces[i]` passa a ser
  `{"url": str, "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}`.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao fim de `packages/sdk-py/tests/test_agent_card_emit.py`:

```python
# ── conformidade: o Card é lido pelo PARSER OFICIAL ─────────────────────────
#
# O teste que a versão à mão não tinha. Um Card que nós mesmos validamos contra a
# nossa leitura da spec é uma tautologia; um Card que o `a2a-sdk` faz o parse é um
# fato. Foi exatamente aqui que a versão à mão falhou: ela emitia
# `{"transport": "jsonrpc"}` e a 1.0 pede `protocolBinding: "JSONRPC"`, então o
# `ClientFactory` oficial achava ZERO interfaces e não conseguia nos chamar.

import pytest

a2a = pytest.importorskip("a2a", reason="a conformidade se mede contra o SDK oficial")


def test_o_card_projetado_e_lido_pelo_parser_oficial_sem_perda():
    from google.protobuf import json_format
    from a2a.types import AgentCard

    card = agent_card_for(
        {"metadata": {"name": "analista", "description": "analisa"}, "spec": {}},
        tools=["review_kind", "list_stories"],
        base_url="https://exemplo/a2a",
    )

    # ParseDict é ESTRITO: um campo desconhecido levanta. É essa severidade que
    # transforma o teste numa medição de conformidade em vez de um smoke test.
    proto = json_format.ParseDict(card, AgentCard())

    assert proto.name == "analista"
    assert [s.id for s in proto.skills] == ["list_stories", "review_kind"]


def test_a_interface_declara_o_binding_que_o_cliente_oficial_procura():
    """O `ClientFactory` filtra por `protocol_binding`; um Card com o nome
    errado do campo produz zero candidatos e um cliente que não nos alcança."""
    from google.protobuf import json_format
    from a2a.client.client_factory import ClientFactory
    from a2a.types import AgentCard
    from a2a.utils.constants import PROTOCOL_VERSION_1_0, TransportProtocol

    card = agent_card_for(
        {"metadata": {"name": "analista", "description": "analisa"}, "spec": {}},
        base_url="https://exemplo/a2a",
    )
    proto = json_format.ParseDict(card, AgentCard())

    escolhida = ClientFactory._find_best_interface(
        list(proto.supported_interfaces),
        protocol_bindings=[TransportProtocol.JSONRPC],
    )
    assert escolhida is not None, "o cliente oficial não achou interface alguma"
    assert escolhida.url == "https://exemplo/a2a"
    assert escolhida.protocol_version == PROTOCOL_VERSION_1_0


def test_streaming_e_DERIVADO_do_que_o_executor_faz():
    """Fixo em `True`, `capabilities.streaming` era promessa sem nada atrás — o
    Card anunciava uma capacidade que ninguém tinha implementado."""
    agente = {"metadata": {"name": "a", "description": "d"}, "spec": {}}
    assert agent_card_for(agente, base_url="https://x/a")["capabilities"] == {
        "streaming": False
    }
    assert agent_card_for(agente, base_url="https://x/a", streaming=True)[
        "capabilities"
    ] == {"streaming": True}
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd packages/sdk-py
uv run --no-project pytest tests/test_agent_card_emit.py -q --timeout=120 -p no:cacheprovider
```

Esperado: FAIL — `ParseError: ... has no field named "transport"` e o
`capabilities` fixo em `True`.

- [ ] **Step 3: Corrigir a projeção**

Em `packages/sdk-py/dna/emit/agent_card.py`, substituir o bloco de constantes:

```python
#: A2A `version` this SDK stamps on a Card it projects — the DNA `Agent` Kind
#: carries no version-of-self field (it is versioned as a DOCUMENT, not as an
#: API), so there is nothing truthful to read here yet. Fixed until the Kind
#: grows one.
_CARD_VERSION = "0.1.0"

#: Every DNA agent talks plain text over the wire today (no multimodal
#: input/output contract in `AgentSpec` yet).
_DEFAULT_MODES = ["text/plain"]
```

(ou seja: some `_CAPABILITIES`). E trocar o `return` de `agent_card_for`:

```python
def agent_card_for(
    agent_doc: Mapping[str, Any],
    *,
    tools: Iterable[str] = (),
    base_url: str,
    streaming: bool = False,
) -> dict[str, Any]:
    """Project a DNA ``Agent`` document into an A2A 1.0 Agent Card (dict, JSON-ready).

    ``tools`` is the resolved list of tool names the agent exposes (the
    caller's job — this function does not look anything up); ``skills`` is
    derived from it. ``base_url`` is where the caller intends to serve this
    agent's A2A endpoint; ``supportedInterfaces`` is built from it.

    ``streaming`` — o que o EXECUTOR daquele deployment implementa, não uma
    constante. Fixo em ``True``, ``capabilities.streaming`` era uma promessa sem
    nada atrás; quem monta a face sabe se há streaming e é quem responde por
    isso (``dna.extensions.a2a.serve.attach_a2a`` deriva do executor montado).

    O binding e a versão do protocolo vêm de ``a2a.utils.constants``, não de
    literais daqui: um Card cujo ``protocolBinding`` diverge por uma letra é
    invisível para o ``ClientFactory`` oficial, e essa é exatamente a classe de
    erro que escrever o protocolo à mão produz.

    No field here can carry a credential — the Card is safe to publish as-is.
    """
    from a2a.utils.constants import PROTOCOL_VERSION_1_0, TransportProtocol

    metadata = _metadata(agent_doc)
    name = str(metadata.get("name") or "")
    url = str(base_url).rstrip("/")

    return {
        "name": name,
        "description": _description(agent_doc),
        "version": _CARD_VERSION,
        "supportedInterfaces": [
            {
                "url": url,
                "protocolBinding": TransportProtocol.JSONRPC.value,
                "protocolVersion": PROTOCOL_VERSION_1_0,
            }
        ],
        "capabilities": {"streaming": bool(streaming)},
        "defaultInputModes": list(_DEFAULT_MODES),
        "defaultOutputModes": list(_DEFAULT_MODES),
        "skills": _skills(tools),
    }
```

⚠️ O `from a2a.utils.constants import …` é DENTRO da função, deliberadamente: é o
que mantém `tests/test_a2a_import_isolation.py` verde. Um import no topo faria
`dna.emit.agent_card` — importado por quem só quer projetar — exigir o extra.

- [ ] **Step 4: Rodar e ver passar**

```bash
cd packages/sdk-py
uv run --no-project pytest tests/test_agent_card_emit.py tests/test_a2a_import_isolation.py -q --timeout=120 -p no:cacheprovider
```

Esperado: PASS em ambos.

- [ ] **Step 5: Consertar os testes antigos que assumiam a forma errada**

Os testes pré-existentes de `test_agent_card_emit.py` que afirmam
`{"transport": "jsonrpc"}` ou `capabilities == {"streaming": True}` vão falhar.
Eles estavam **certos sobre a intenção e errados sobre a spec** — atualize a forma
esperada, não a intenção. Rode a suíte e conserte um por um:

```bash
uv run --no-project pytest tests -q --timeout=120 -p no:cacheprovider 2>&1 | tail -30
```

- [ ] **Step 6: Commit**

```bash
git add packages/sdk-py/dna/emit/agent_card.py packages/sdk-py/tests/test_agent_card_emit.py
git commit -m "fix(a2a): o Card falava 'transport'; a 1.0 pede 'protocolBinding' — e agora o parser oficial julga"
```

---

### Task 3: A entrada — ingerir um Agent Card 1.0 de verdade

**Files:**
- Modify: `packages/sdk-py/dna/extensions/a2a/kinds/remote-agent.kind.yaml:63-83`
- Modify: `packages/sdk-py/dna/application/a2a_ingest.py:41-64`
- Test: `packages/sdk-py/tests/test_a2a_ingest.py`

**Interfaces:**
- Consumes: nada da Task 2 (direção oposta).
- Produces: `card_to_spec` emite `supported_interfaces: [{url, protocol_binding, protocol_version}]`.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao fim de `packages/sdk-py/tests/test_a2a_ingest.py`:

```python
# ── o Card REAL, medido do a2a-sdk 1.1.2 ────────────────────────────────────
#
# Não é uma fixture inventada: é a serialização que um servidor A2A 1.0 conforme
# publica em /.well-known/agent-card.json, capturada do SDK oficial. Contra ela,
# `card_to_spec` + o schema do Kind recusavam DUAS vezes — `protocolBinding` era
# propriedade desconhecida num schema fechado, e `transport` estava faltando.
# Ou seja: nenhum agente A2A real podia ser registrado.
CARD_CONFORME = {
    "name": "eco",
    "description": "devolve o que recebe",
    "version": "0.1.0",
    "supportedInterfaces": [
        {
            "url": "https://exemplo/a2a",
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0",
        }
    ],
    "capabilities": {"streaming": True},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [{"id": "eco", "name": "eco", "description": "ecoa"}],
}


def _validador_do_kind():
    from pathlib import Path

    import yaml
    from jsonschema import Draft202012Validator

    import dna.extensions.a2a as pacote

    caminho = Path(pacote.__file__).parent / "kinds" / "remote-agent.kind.yaml"
    schema = yaml.safe_load(caminho.read_text())["spec"]["schema"]
    return Draft202012Validator(schema)


def test_um_card_conforme_vira_RemoteAgent_valido():
    spec = card_to_spec(CARD_CONFORME, data_scope_kinds=["Story"])
    erros = [
        f"{list(e.path)}: {e.message}"
        for e in _validador_do_kind().iter_errors(spec)
    ]
    assert not erros, "o Kind recusou um Agent Card A2A 1.0 conforme: " + "; ".join(erros)


def test_a_interface_preserva_binding_e_versao_do_protocolo():
    spec = card_to_spec(CARD_CONFORME, data_scope_kinds=[])
    assert spec["supported_interfaces"] == [
        {
            "url": "https://exemplo/a2a",
            "protocol_binding": "JSONRPC",
            "protocol_version": "1.0",
        }
    ]


def test_o_campo_transport_da_versao_a_mao_nao_e_mais_aceito():
    """Sem compatibilidade, por decisão: duas leituras do mesmo campo
    convivendo é o débito que este épico existe para não criar."""
    antigo = dict(
        CARD_CONFORME,
        supportedInterfaces=[{"transport": "jsonrpc", "url": "https://exemplo/a2a"}],
    )
    spec = card_to_spec(antigo, data_scope_kinds=[])
    assert list(_validador_do_kind().iter_errors(spec)), (
        "a forma antiga passou — o schema ainda aceita as duas leituras"
    )
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd packages/sdk-py
uv run --no-project pytest tests/test_a2a_ingest.py -q --timeout=120 -p no:cacheprovider
```

Esperado: FAIL nos dois primeiros
(`Additional properties are not allowed ('protocolBinding', 'protocolVersion' were unexpected)`
e `'transport' is a required property`).

- [ ] **Step 3: Corrigir o schema do Kind**

Em `packages/sdk-py/dna/extensions/a2a/kinds/remote-agent.kind.yaml`, substituir o
bloco `supported_interfaces` inteiro (linhas 63–83) por:

```yaml
      supported_interfaces:
        type: array
        description: >
          A2A `supportedInterfaces` (1.0 — substituiu o `url` único das versões
          anteriores). Cada entrada nomeia um BINDING de protocolo e onde
          alcançá-lo.

          O campo chamava-se `transport` numa leitura nossa da spec, e não
          existe: a 1.0 o chama `protocolBinding`, com os valores em MAIÚSCULAS,
          e o cliente oficial filtra por ele. Enquanto o nome divergia, nenhum
          Agent Card conforme podia ser ingerido — e todos os testes passavam,
          porque as fixtures herdavam o mesmo erro de leitura.
        minItems: 1
        items:
          type: object
          additionalProperties: false
          required: [protocol_binding, url]
          properties:
            protocol_binding:
              type: string
              # Os valores de `a2a.utils.constants.TransportProtocol`, verbatim.
              enum: [JSONRPC, GRPC, HTTP+JSON]
            protocol_version:
              type: string
              description: >
                A2A `protocolVersion` da interface (`"1.0"`). Opcional: a 1.0
                permite omiti-lo, e o cliente oficial trata a ausência como
                "sem preferência" em vez de erro.
            url:
              type: string
              pattern: '^https://'
              description: >
                HTTPS obrigatório. Delegar dado de workspace por texto claro
                seria exfiltração com um passo a menos.
```

- [ ] **Step 4: Corrigir o mapa de campos do ingest**

Em `packages/sdk-py/dna/application/a2a_ingest.py`, acrescentar depois de
`_CAPABILITY_FIELD_MAP`:

```python
#: O mesmo, mas DENTRO de cada `supportedInterfaces[]`. Separado do mapa raiz
#: porque o kernel só converte o nível que declara: um dicionário aninhado que
#: chega camelCase atravessa a tradução intocado e vira documento inválido —
#: silenciosamente, porque `additionalProperties: false` acusa o sintoma
#: (propriedade desconhecida) e não a causa (ninguém traduziu este nível).
_INTERFACE_FIELD_MAP = {
    "protocolBinding": "protocol_binding",
    "protocolVersion": "protocol_version",
}
```

e substituir a linha `spec["supported_interfaces"] = card["supportedInterfaces"]` por:

```python
    spec["supported_interfaces"] = [
        {
            _INTERFACE_FIELD_MAP.get(chave, chave): valor
            for chave, valor in (iface or {}).items()
        }
        for iface in card["supportedInterfaces"]
    ]
```

- [ ] **Step 5: Rodar e ver passar**

```bash
cd packages/sdk-py
uv run --no-project pytest tests/test_a2a_ingest.py -q --timeout=120 -p no:cacheprovider
```

Esperado: PASS. Se testes antigos do arquivo usavam `{"transport": …}` nas
fixtures, atualize-os para a forma conforme — eles documentavam o erro.

- [ ] **Step 6: Confirmar que o transporte de saída não regrediu**

`a2a_transport._endpoint` lê só `url` de cada interface, então é indiferente ao
rename. Confirme, não presuma:

```bash
uv run --no-project pytest tests/test_a2a_transport.py -q --timeout=120 -p no:cacheprovider
```

Esperado: PASS.

- [ ] **Step 7: Commit**

```bash
git add packages/sdk-py/dna/extensions/a2a/kinds/remote-agent.kind.yaml \
        packages/sdk-py/dna/application/a2a_ingest.py \
        packages/sdk-py/tests/test_a2a_ingest.py
git commit -m "fix(a2a): o Kind RemoteAgent recusava todo Agent Card 1.0 real — 'transport' nao existe na spec"
```

---

### Task 4: `DnaAgentExecutor` — a única peça nova, e é cola

**Files:**
- Create: `packages/sdk-py/dna/extensions/a2a/executor.py`
- Test: `packages/sdk-py/tests/test_a2a_executor.py`

**Interfaces:**
- Consumes: o extra da Task 1.
- Produces: `DnaAgentExecutor(run: Callable[[str], Awaitable[str]])`, subclasse de
  `a2a.server.agent_execution.AgentExecutor`. Atributo de classe
  `streaming: bool = True`. A Task 5 lê `executor.streaming` para derivar
  `capabilities.streaming`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `packages/sdk-py/tests/test_a2a_executor.py`:

```python
"""`DnaAgentExecutor` — o agente do DNA visto pela interface do SDK oficial.

É cola, não protocolo: quem decide o que sai na fila de eventos, em que ordem, e
o que vira Task é o `a2a-sdk`. O que é nosso é `run(text) -> str` — e a decisão
de que uma exceção do agente vira uma Task `failed` com a razão dentro, em vez
de escapar como erro de transporte.
"""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("a2a", reason="o executor adapta o SDK oficial")

from a2a.server.agent_execution import RequestContext  # noqa: E402
from a2a.server.events import EventQueue  # noqa: E402
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState  # noqa: E402

from dna.extensions.a2a.executor import DnaAgentExecutor  # noqa: E402


def _contexto(texto: str) -> RequestContext:
    from a2a.server.context import ServerCallContext

    return RequestContext(
        call_context=ServerCallContext(),
        request=SendMessageRequest(
            message=Message(
                message_id="m1", role=Role.ROLE_USER, parts=[Part(text=texto)]
            )
        ),
        task_id="t1",
        context_id="c1",
    )


async def _drenar(executor, texto: str) -> list:
    fila = EventQueue()
    ctx = _contexto(texto)
    await executor.execute(ctx, fila)
    await fila.close()
    eventos = []
    consumidor = fila.tap()
    try:
        async for evento in consumidor:
            eventos.append(evento)
    except Exception:  # a fila fechada encerra o laço
        pass
    return eventos


def test_o_texto_do_agente_sai_como_ARTIFACT_e_a_task_completa():
    async def run(texto: str) -> str:
        return f"eco:{texto}"

    eventos = asyncio.run(_drenar(DnaAgentExecutor(run=run), "ola"))
    tipos = [type(e).__name__ for e in eventos]
    assert "Task" in tipos, f"nenhuma Task foi enfileirada primeiro: {tipos}"
    assert any("Artifact" in t for t in tipos), f"o resultado não virou artifact: {tipos}"
    estados = [
        e.status.state for e in eventos if type(e).__name__ == "TaskStatusUpdateEvent"
    ]
    assert TaskState.TASK_STATE_COMPLETED in estados, estados


def test_uma_excecao_do_agente_vira_task_FAILED_com_a_razao_dentro():
    """Deixar escapar produziria um erro de transporte sem `id` — o cliente
    perderia o resultado E a razão. A chamada funcionou; foi a tarefa que
    falhou, e a 1.0 distingue as duas coisas."""

    async def run(_texto: str) -> str:
        raise RuntimeError("o alvo caiu")

    eventos = asyncio.run(_drenar(DnaAgentExecutor(run=run), "ola"))
    estados = [
        e.status.state for e in eventos if type(e).__name__ == "TaskStatusUpdateEvent"
    ]
    assert TaskState.TASK_STATE_FAILED in estados, estados
    razoes = [
        p.text
        for e in eventos
        if type(e).__name__ == "TaskStatusUpdateEvent" and e.status.HasField("message")
        for p in e.status.message.parts
    ]
    assert any("o alvo caiu" in r for r in razoes), razoes


def test_um_pedido_sem_texto_algum_falha_em_vez_de_completar_vazio():
    """Uma Task que completa sem ter feito nada é o pior resultado possível,
    porque parece sucesso."""
    chamado = []

    async def run(texto: str) -> str:  # pragma: no cover — não deve ser chamado
        chamado.append(texto)
        return "nunca"

    eventos = asyncio.run(_drenar(DnaAgentExecutor(run=run), ""))
    estados = [
        e.status.state for e in eventos if type(e).__name__ == "TaskStatusUpdateEvent"
    ]
    assert TaskState.TASK_STATE_FAILED in estados, estados
    assert not chamado, "o agente rodou com pedido vazio"


def test_o_executor_declara_que_faz_streaming():
    """`attach_a2a` DERIVA `capabilities.streaming` disto — o Card deixa de
    prometer o que ninguém implementou."""
    assert DnaAgentExecutor.streaming is True
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd packages/sdk-py
uv run --no-project pytest tests/test_a2a_executor.py -q --timeout=120 -p no:cacheprovider
```

Esperado: FAIL com `ModuleNotFoundError: No module named 'dna.extensions.a2a.executor'`.

⚠️ Se `EventQueue.tap()` não existir nesta versão, ajuste `_drenar` para a API
real (descubra com `python -c "from a2a.server.events import EventQueue; print([m for m in dir(EventQueue) if not m.startswith('_')])"`).
Meça, não adivinhe — é a regra deste plano inteiro.

- [ ] **Step 3: Escrever o executor**

Criar `packages/sdk-py/dna/extensions/a2a/executor.py`:

```python
"""Um agente do DNA, visto pela interface `AgentExecutor` do `a2a-sdk`.

É a ÚNICA peça nova desta face, e é cola — não protocolo. Quem decide a ordem
dos eventos, o que vira Task, como o SSE é enquadrado e o que a `tasks/get`
devolve é o SDK oficial. O que é nosso é `run(text) -> str`, o mesmo formato
que `delegation_exec` já injeta nos outros transportes.

## Por que não escrevemos isto à mão (de novo)

A versão anterior desta face era artesanal e tinha 49 testes verdes. Mesmo
assim errava três coisas do protocolo — o nome do campo do binding, o valor
dele, e a forma de uma `Part` — porque os testes foram escritos pela mesma
leitura da spec que o código. Conformidade não se testa contra a própria
leitura; se mede contra a implementação de referência.

## O que este módulo DECIDE, e é nosso

1. **Uma exceção do agente vira Task `failed` com a razão dentro do status.**
   Deixá-la escapar produziria um erro de TRANSPORTE, e o cliente perderia
   tanto o resultado quanto o motivo. A chamada funcionou; foi a tarefa que
   falhou, e a 1.0 distingue as duas coisas de propósito.
2. **Um pedido sem texto algum FALHA em vez de completar vazio.** Uma Task que
   completa sem ter feito nada é o pior desfecho possível, porque parece
   sucesso.
3. **`streaming` é declarado aqui**, e o Card o deriva — em vez de uma
   constante `True` que prometia o que ninguém tinha implementado.

## O que ele NÃO faz

**Não autentica.** A verificação é da PORTA, antes de chegar aqui, como as
portas MCP fazem — uma autoridade por porta (ADR
`adr-identity-doors-verify-different-sets`). Este módulo nunca vê um bearer.

**Não decide o alcance do agente.** Quem executa é o `run` injetado; o que o
agente pode fazer é do host que o construiu.
"""
from __future__ import annotations

from typing import Awaitable, Callable

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, Task, TaskState, TaskStatus

__all__ = ["DnaAgentExecutor"]


def _texto_do_pedido(context: RequestContext) -> str:
    """O texto da mensagem, concatenado das partes de texto.

    Partes que não são texto são IGNORADAS, não recusadas: um cliente que anexa
    uma imagem a um pedido cujo texto basta deve ser atendido, e recusar o
    pedido inteiro por uma parte que não sabemos ler trocaria uma degradação
    por uma falha.

    `Part` na 1.0 é um `oneof` (`text` | `raw` | `url` | `data`) — não há campo
    `kind` discriminador, e supor que havia foi um dos erros da versão à mão.
    """
    mensagem = getattr(context, "message", None)
    if mensagem is None:
        return ""
    pedacos = [
        parte.text
        for parte in mensagem.parts
        if parte.WhichOneof("content") == "text" and parte.text.strip()
    ]
    return "\n".join(pedacos)


class DnaAgentExecutor(AgentExecutor):
    """Adapta `run(text) -> str` à interface do `a2a-sdk`."""

    #: O que esta implementação REALMENTE faz — lido por
    #: `dna.extensions.a2a.serve.attach_a2a` para derivar
    #: `capabilities.streaming` do Card. `True` porque os eventos saem pela
    #: `EventQueue` conforme acontecem, e o SDK os transmite.
    streaming: bool = True

    def __init__(self, *, run: Callable[[str], Awaitable[str]]) -> None:
        self._run = run

    async def execute(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        # A Task PRIMEIRO. O SDK recusa com
        # `InvalidAgentResponseError: Agent should enqueue Task before
        # TaskStatusUpdateEvent` se um status vier antes — regra da 1.0 que
        # só a implementação de referência conhece, e que a versão à mão não
        # tinha como saber.
        if context.current_task is None:
            await event_queue.enqueue_event(
                Task(
                    id=context.task_id,
                    context_id=context.context_id,
                    status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
                )
            )

        texto = _texto_do_pedido(context)
        if not texto:
            await updater.failed(
                updater.new_agent_message(
                    [Part(text="a mensagem não carrega texto algum; não há o que fazer")]
                )
            )
            return

        await updater.start_work()
        try:
            resultado = await self._run(texto)
        except Exception as exc:  # noqa: BLE001 — a mensagem É o resultado
            await updater.failed(
                updater.new_agent_message(
                    [Part(text=f"{type(exc).__name__}: {exc}")]
                )
            )
            return

        await updater.add_artifact([Part(text=resultado)], name="resultado")
        await updater.complete()

    async def cancel(
        self, context: RequestContext, event_queue: EventQueue
    ) -> None:
        """Não suportado — e dizê-lo alto é a resposta honesta.

        Cancelar de verdade exige que `run` seja interrompível, e o `run` que
        recebemos é uma corrotina opaca do host. Um `cancel` que devolve
        "cancelado" sem cancelar nada é pior que um que recusa: o cliente para
        de esperar enquanto o trabalho continua rodando.
        """
        raise NotImplementedError(
            "este executor não suporta cancelamento: `run` é opaco e não é interrompível"
        )
```

- [ ] **Step 4: Rodar e ver passar**

```bash
cd packages/sdk-py
uv run --no-project pytest tests/test_a2a_executor.py -q --timeout=120 -p no:cacheprovider
```

Esperado: PASS nos quatro testes.

- [ ] **Step 5: Confirmar que o import base continua limpo**

```bash
uv run --no-project pytest tests/test_a2a_import_isolation.py -q --timeout=120 -p no:cacheprovider
```

Esperado: PASS — `executor.py` importa `a2a` no topo, mas ninguém o importa a
partir de `dna/extensions/a2a/__init__.py`. Se falhar, o `__init__.py` ganhou um
import que não devia.

- [ ] **Step 6: Commit**

```bash
git add packages/sdk-py/dna/extensions/a2a/executor.py packages/sdk-py/tests/test_a2a_executor.py
git commit -m "feat(a2a): DnaAgentExecutor — a cola entre um agente DNA e o SDK oficial"
```

---

### Task 5: `attach_a2a` — montar as rotas do SDK, servindo o NOSSO Card

**Files:**
- Create: `packages/sdk-py/dna/extensions/a2a/serve.py`
- Modify: `packages/cli/dna_cli/serving.py`
- Test: `packages/sdk-py/tests/test_a2a_serve.py`

**Interfaces:**
- Consumes: `DnaAgentExecutor` (Task 4), `agent_card_for` (Task 2).
- Produces:
  `attach_a2a(app, path, *, executor, card, card_path=AGENT_CARD_WELL_KNOWN_PATH, task_store=None) -> DefaultRequestHandler`
  — `card` é o dict de `agent_card_for`; `capabilities.streaming` é
  **sobrescrito** a partir de `getattr(executor, "streaming", False)`.
  Re-exportado como `dna_cli.serving.attach_a2a`.

- [ ] **Step 1: Escrever o teste que falha**

Criar `packages/sdk-py/tests/test_a2a_serve.py`:

```python
"""A face A2A SERVIDA — as rotas do SDK oficial montadas num FastAPI do host.

O que é nosso aqui é o Card (a projeção de `dna.emit.agent_card`) e a derivação
de `capabilities.streaming`. As rotas, o dispatch JSON-RPC, o enquadramento SSE
e a `tasks/get` são do `a2a-sdk` — e é por isso que este arquivo tem poucos
testes: não há protocolo nosso para testar.
"""
from __future__ import annotations

import pytest

pytest.importorskip("a2a", reason="a face servida monta as rotas do SDK oficial")
fastapi = pytest.importorskip("fastapi", reason="a face servida precisa do extra `api`")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from dna.emit.agent_card import agent_card_for  # noqa: E402
from dna.extensions.a2a.executor import DnaAgentExecutor  # noqa: E402
from dna.extensions.a2a.serve import attach_a2a  # noqa: E402

AGENTE = {"metadata": {"name": "eco", "description": "ecoa"}, "spec": {}}


def _app(run=None, executor=None):
    async def _eco(texto: str) -> str:
        return f"eco:{texto}"

    app = FastAPI()
    attach_a2a(
        app,
        "/a2a",
        executor=executor or DnaAgentExecutor(run=run or _eco),
        card=agent_card_for(AGENTE, tools=["review_kind"], base_url="https://x/a2a"),
    )
    return TestClient(app)


def test_o_card_e_servido_no_caminho_convencional():
    corpo = _app().get("/.well-known/agent-card.json").json()
    assert corpo["name"] == "eco"
    assert corpo["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"


def test_streaming_do_card_e_DERIVADO_do_executor_montado():
    """O Card é a nossa verdade sobre o agente — mas `capabilities.streaming`
    é fato sobre o EXECUTOR, e quem monta é quem sabe."""

    class SemStreaming(DnaAgentExecutor):
        streaming = False

    async def _eco(t: str) -> str:
        return t

    com = _app().get("/.well-known/agent-card.json").json()
    sem = _app(executor=SemStreaming(run=_eco)).get(
        "/.well-known/agent-card.json"
    ).json()

    assert com["capabilities"]["streaming"] is True
    assert sem.get("capabilities", {}).get("streaming", False) is False


def test_message_send_devolve_a_task_completa_com_o_artifact():
    resposta = _app().post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": "m1",
                    "role": "ROLE_USER",
                    "parts": [{"text": "ola"}],
                }
            },
        },
    )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert "error" not in corpo, corpo
    texto = str(corpo["result"])
    assert "eco:ola" in texto, corpo


def test_um_metodo_desconhecido_e_recusado_pelo_SDK_com_o_codigo_do_protocolo():
    """Não testamos o CÓDIGO (-32601 é do SDK, não nosso) — testamos que a
    recusa existe e é de protocolo, não um 500."""
    resposta = _app().post(
        "/a2a",
        json={"jsonrpc": "2.0", "id": "1", "method": "nao/existe", "params": {}},
    )
    assert resposta.status_code < 500, resposta.text
    assert "error" in resposta.json(), resposta.json()
```

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd packages/sdk-py
uv run --no-project pytest tests/test_a2a_serve.py -q --timeout=120 -p no:cacheprovider
```

Esperado: FAIL com `ModuleNotFoundError: No module named 'dna.extensions.a2a.serve'`.

- [ ] **Step 3: Escrever o mount**

Criar `packages/sdk-py/dna/extensions/a2a/serve.py`:

```python
"""A face A2A que SERVE — as rotas do SDK OFICIAL montadas num app do host.

Este módulo tem uma responsabilidade e ela cabe numa frase: pegar o Card que
`dna.emit.agent_card` projeta, entregá-lo ao `a2a-sdk` junto com um executor, e
montar as rotas que o SDK produz. Não há protocolo escrito aqui — nem envelope
JSON-RPC, nem enquadramento SSE, nem armazém de Tasks. Tudo isso é do SDK, e
essa é a decisão inteira desta face.

## O que continua NOSSO

- **A projeção do Card.** O Card é a nossa verdade sobre o agente
  (`dna.emit.agent_card.agent_card_for`); o SDK só o serve. Duplicar a projeção
  aqui criaria uma segunda verdade sobre o mesmo agente.
- **A derivação de `capabilities.streaming`.** O Card diz o que o EXECUTOR
  montado faz, não uma constante. Fixo em `True`, era promessa sem nada atrás.

## O que ele NÃO faz, e é deliberado

**Não autentica.** A verificação acontece na BORDA, antes de chegar aqui, como
as portas MCP fazem — uma autoridade por porta (ADR
`adr-identity-doors-verify-different-sets`). Meter verificação aqui criaria uma
segunda implementação da regra de identidade, que é exatamente o débito que
aquele ADR registrou.

## O caminho do Card

Default `AGENT_CARD_WELL_KNOWN_PATH` (`/.well-known/agent-card.json`), do SDK —
não um literal nosso. Continua PARÂMETRO porque a raiz do domínio não é do SDK:
um host que monta sob prefixo precisa poder dizer onde.
"""
from __future__ import annotations

from typing import Any, Mapping

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH

__all__ = ["attach_a2a", "card_to_proto"]


def card_to_proto(card: Mapping[str, Any]) -> AgentCard:
    """O Card (dict camelCase da nossa projeção) como `AgentCard` do SDK.

    `ParseDict` é ESTRITO — um campo desconhecido levanta em vez de ser
    ignorado. É de propósito que a conversão passe por ele: é o ponto onde uma
    divergência entre a nossa projeção e a 1.0 vira erro AQUI, na montagem, em
    vez de virar um Card que ninguém consegue ler lá fora.
    """
    from google.protobuf import json_format

    return json_format.ParseDict(dict(card), AgentCard())


def attach_a2a(
    app: Any,
    path: str,
    *,
    executor: Any,
    card: Mapping[str, Any],
    card_path: str = AGENT_CARD_WELL_KNOWN_PATH,
    task_store: Any = None,
) -> DefaultRequestHandler:
    """Montar a face A2A de `executor` em `app`, e devolver o handler do SDK.

    `card` é o dict de `dna.emit.agent_card.agent_card_for`. `capabilities.
    streaming` é SOBRESCRITO a partir de `executor.streaming`: quem monta é quem
    sabe o que o executor faz, e o Card não deve prometer o que ninguém
    implementou.

    `task_store` default é o `InMemoryTaskStore` do SDK. O antecessor à mão
    tinha um armazém próprio com teto de 256 inventado; o SDK traz este e um
    `DatabaseTaskStore` nos extras, para quem precisar de durabilidade.
    """
    corpo = dict(card)
    capacidades = dict(corpo.get("capabilities") or {})
    capacidades["streaming"] = bool(getattr(executor, "streaming", False))
    corpo["capabilities"] = capacidades

    proto = card_to_proto(corpo)
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store or InMemoryTaskStore(),
        agent_card=proto,
    )
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(proto, card_url=card_path),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url=path),
    )
    return handler
```

- [ ] **Step 4: Rodar e ver passar**

```bash
cd packages/sdk-py
uv run --no-project pytest tests/test_a2a_serve.py -q --timeout=120 -p no:cacheprovider
```

Esperado: PASS nos quatro testes.

- [ ] **Step 5: Expor pelo seam público do host**

Em `packages/cli/dna_cli/serving.py`, depois do bloco que importa
`build_rest_app`, acrescentar:

```python
# A face A2A servida. Um HOST a compõe sobre o app que ele já tem — o mesmo
# arranjo do MCP e do REST, e a razão pela qual ela NÃO é uma flag de
# `dna api serve`: este módulo diz, na primeira linha, que os comandos `serve`
# são conveniência de dev e estão depreciados para produção. Quem serve A2A a
# sério (dna-cloud) monta no seu próprio app, com a sua própria porta de
# identidade.
#
# Exige o extra `dna-cli[a2a]` (+ `api`, pelo FastAPI). O import é PREGUIÇOSO
# pela mesma razão de sempre: importar `dna_cli.serving` não pode exigir todo
# extra que ele exporta.
def attach_a2a(*args, **kwargs):
    """Montar a face A2A num app FastAPI do host — ver
    `dna.extensions.a2a.serve.attach_a2a`."""
    from dna.extensions.a2a.serve import attach_a2a as _attach

    return _attach(*args, **kwargs)
```

- [ ] **Step 6: Confirmar o seam e o isolamento de import**

```bash
cd packages/cli
uv run --no-project python -c "from dna_cli.serving import attach_a2a; print(attach_a2a)"
cd ../sdk-py
uv run --no-project pytest tests/test_a2a_import_isolation.py -q --timeout=120 -p no:cacheprovider
```

Esperado: o `print` mostra a função; o teste passa.

- [ ] **Step 7: Commit**

```bash
git add packages/sdk-py/dna/extensions/a2a/serve.py \
        packages/sdk-py/tests/test_a2a_serve.py \
        packages/cli/dna_cli/serving.py
git commit -m "feat(a2a): a porta — rotas do SDK oficial montadas no app do host, servindo o nosso Card"
```

---

### Task 6: A saída — `call_remote` sobre o `Client` do SDK, com as recusas intactas

**Files:**
- Modify: `packages/sdk-py/dna/application/a2a_transport.py`
- Test: `packages/sdk-py/tests/test_a2a_transport.py`

**Interfaces:**
- Consumes: o extra da Task 1.
- Produces: `call_remote(target, request, *, credential_for, http=None, payload_kinds=(), timeout_s=DEFAULT_TIMEOUT_S) -> str`
  — **`http` passa a ser opcional** (o `Client` do SDK constrói o seu se não vier
  um `httpx.AsyncClient`). `scope_allows` e `_endpoint` não mudam.
  **Nenhum parâmetro novo aceita identidade de caller** — a asserção contra a
  assinatura continua valendo.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar ao fim de `packages/sdk-py/tests/test_a2a_transport.py`:

```python
# ── o transporte agora é o Client OFICIAL, e as recusas continuam ANTES ──────
#
# A ordem é load-bearing e é o motivo destes testes: `data_scope` e credencial
# são checados antes de qualquer byte sair. Um caminho novo com portões mais
# frouxos que o antigo é a forma mais silenciosa de perder uma garantia — então
# eles são exercitados de novo, contra o transporte novo.


def test_o_escopo_recusa_ANTES_de_o_cliente_do_SDK_existir(monkeypatch):
    import dna.application.a2a_transport as transporte

    def _explode(*a, **kw):  # pragma: no cover — não deve ser alcançado
        raise AssertionError("o SDK foi acionado apesar do escopo fechado")

    monkeypatch.setattr(transporte, "_client_para", _explode)
    alvo = _alvo(data_scope_kinds=["Story"])
    with pytest.raises(DelegationRefused, match="fora do data_scope"):
        asyncio.run(
            transporte.call_remote(
                alvo, "x", credential_for=lambda _n: "tok", payload_kinds=["Secret"]
            )
        )


def test_a_ausencia_de_credencial_recusa_ANTES_de_o_cliente_do_SDK_existir(monkeypatch):
    import dna.application.a2a_transport as transporte

    def _explode(*a, **kw):  # pragma: no cover
        raise AssertionError("o SDK foi acionado sem credencial")

    monkeypatch.setattr(transporte, "_client_para", _explode)
    with pytest.raises(DelegationRefused, match="nenhuma credencial"):
        asyncio.run(
            transporte.call_remote(_alvo(), "x", credential_for=lambda _n: None)
        )


def test_NENHUM_parametro_deixa_o_bearer_do_usuario_atravessar():
    """A garantia estrutural: a credencial é do WORKSPACE, nunca do usuário.
    Repassar o bearer de quem conversa faria de cada remoto uma impersonação
    completa dele contra o nosso próprio MCP."""
    import inspect

    from dna.application.a2a_transport import call_remote

    params = set(inspect.signature(call_remote).parameters)
    proibidos = {"token", "bearer", "caller", "identity", "user", "authorization"}
    assert not (params & proibidos), (
        f"call_remote expõe {params & proibidos!r} — um caminho para o token do usuário"
    )
```

E o teste que prova que o transporte é mesmo o oficial:

```python
def test_o_texto_final_vem_dos_artifacts_que_o_cliente_oficial_entrega(monkeypatch):
    """Nada de parse de SSE à mão: o `Client` do SDK agrega os eventos e
    entrega `StreamResponse`. O que é nosso é escolher o último artifact."""
    pytest.importorskip("a2a")
    import dna.application.a2a_transport as transporte
    from a2a.types import Artifact, Part, Task, TaskArtifactUpdateEvent, StreamResponse

    class _ClienteFalso:
        async def send_message(self, req, **kw):
            yield StreamResponse(task=Task(id="t1", context_id="c1"))
            yield StreamResponse(
                artifact_update=TaskArtifactUpdateEvent(
                    task_id="t1",
                    context_id="c1",
                    artifact=Artifact(artifact_id="a1", parts=[Part(text="pronto")]),
                )
            )

        async def close(self):
            pass

    monkeypatch.setattr(
        transporte, "_client_para", lambda *a, **kw: _ClienteFalso()
    )
    texto = asyncio.run(
        transporte.call_remote(_alvo(), "x", credential_for=lambda _n: "tok")
    )
    assert texto == "pronto"
```

⚠️ `_alvo(...)` já existe no arquivo. Se a fábrica atual não aceitar
`data_scope_kinds=`, use a forma que o arquivo já usa — leia antes de escrever.

- [ ] **Step 2: Rodar e ver falhar**

```bash
cd packages/sdk-py
uv run --no-project pytest tests/test_a2a_transport.py -q --timeout=120 -p no:cacheprovider
```

Esperado: FAIL — `_client_para` não existe.

- [ ] **Step 3: Trocar o transporte, preservando as recusas**

Em `packages/sdk-py/dna/application/a2a_transport.py`: manter `scope_allows`,
`_endpoint` e o cabeçalho do módulo (as duas regras continuam sendo o assunto),
acrescentando ao cabeçalho, antes de `── As duas regras`:

```
**O transporte é o `Client` do `a2a-sdk`**, nunca um POST à mão. A versão
anterior montava o envelope JSON-RPC e fazia o parse do SSE aqui — e errava a
forma de uma `Part`, com testes verdes, porque testes escritos junto com a
implementação herdam a mesma leitura da spec. O que continua NOSSO são as duas
regras abaixo, e elas correm ANTES de o cliente sequer ser construído.
```

Substituir `call_remote` (e remover o corpo antigo que montava o `body` e fazia
`http.post`) por:

```python
def _client_para(target: DelegationTarget, url: str, credential: str, http: Any):
    """O `Client` oficial, apontado a `url` e já carregando a credencial.

    Um Card MÍNIMO — só a interface que vamos usar — em vez de buscar o Card
    remoto: o `RemoteAgent` documento JÁ é o Card ingerido e aprovado por um
    humano (`a2a_ingest`), e ir buscá-lo de novo na hora da chamada trocaria a
    verdade aprovada pela verdade corrente do terceiro, sem que ninguém
    aprovasse a troca.
    """
    import httpx
    from a2a.client import ClientConfig, ClientFactory
    from a2a.types import AgentCard, AgentInterface
    from a2a.utils.constants import PROTOCOL_VERSION_1_0, TransportProtocol

    cliente_http = http or httpx.AsyncClient()
    cliente_http.headers["authorization"] = f"Bearer {credential}"

    card = AgentCard(
        name=target.name,
        supported_interfaces=[
            AgentInterface(
                url=url,
                protocol_binding=TransportProtocol.JSONRPC.value,
                protocol_version=PROTOCOL_VERSION_1_0,
            )
        ],
    )
    fabrica = ClientFactory(ClientConfig(httpx_client=cliente_http, streaming=True))
    return fabrica.create(card)


async def call_remote(
    target: DelegationTarget,
    request: str,
    *,
    credential_for: Callable[[str], str | None],
    http: Any = None,
    payload_kinds: Iterable[str] = (),
    timeout_s: int = DEFAULT_TIMEOUT_S,
    on_event: Callable[[Any], None] | None = None,
) -> str:
    """Chamar `target` por A2A e devolver o texto cru (o parse é do executor).

    Nenhum parâmetro aceita identidade de caller — ver a regra 2 no cabeçalho.

    `on_event`, quando dado, recebe cada evento assim que chega: é o que
    transforma a espera em progresso. Sem ele a chamada é silenciosa até o fim,
    e para um alvo de 20 segundos isso é indistinguível de travado.

    O retorno continua sendo TEXTO: o executor (`delegation_exec`) faz o parse
    conforme o `format` que o alvo declara, e devolver uma estrutura obrigaria
    o chamador a conhecer A2A — o ponto de `delegation_exec` é que ele não
    conhece transporte nenhum.
    """
    # As duas recusas, ANTES de qualquer byte E antes de o cliente existir.
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

    from a2a.types import Message, Part, Role, SendMessageRequest

    cliente = _client_para(target, url, credential, http)
    pedido = SendMessageRequest(
        message=Message(
            message_id=str(uuid.uuid4()),
            role=Role.ROLE_USER,
            parts=[Part(text=request)],
        )
    )

    ultimo_texto: str | None = None
    try:
        async for evento in cliente.send_message(pedido):
            if on_event is not None:
                on_event(evento)
            texto = _texto_do_evento(evento)
            if texto is not None:
                # O ÚLTIMO artifact vence: um stream pode reemitir o resultado
                # crescendo, e o primeiro seria parcial.
                ultimo_texto = texto
    finally:
        if http is None:
            await cliente.close()

    _LOGGER.info("a2a call ok", extra={"target": target.name})
    return ultimo_texto or ""


def _texto_do_evento(evento: Any) -> str | None:
    """O texto de um `StreamResponse`, ou `None` se ele não carrega resultado.

    Lê os `artifacts` — o lugar que a 1.0 define para a SAÍDA de uma task. Um
    evento de progresso não tem artifact e devolve `None`, e é isso que deixa
    quem consome distinguir "andou" de "terminou" sem olhar o estado por fora.
    """
    qual = evento.WhichOneof("payload") if hasattr(evento, "WhichOneof") else None
    if qual == "artifact_update":
        partes = evento.artifact_update.artifact.parts
    elif qual == "task" and evento.task.artifacts:
        partes = [p for art in evento.task.artifacts for p in art.parts]
    else:
        return None
    pedacos = [p.text for p in partes if p.WhichOneof("content") == "text"]
    return "\n".join(pedacos) if pedacos else None
```

Acrescentar `import uuid` ao topo do módulo.

⚠️ `timeout_s` deixa de ser passado ao POST porque o `Client` gerencia o seu.
Mantenha o parâmetro na assinatura (chamadores existentes o passam) e configure-o
no `httpx.AsyncClient` que `_client_para` constrói:
`httpx.AsyncClient(timeout=timeout_s)`. Ajuste `_client_para` para receber
`timeout_s`.

- [ ] **Step 4: Rodar e ver passar**

```bash
cd packages/sdk-py
uv run --no-project pytest tests/test_a2a_transport.py -q --timeout=120 -p no:cacheprovider
```

Esperado: PASS. Testes antigos que injetavam um `http` dublê com `.post()` vão
falhar — eles testavam o POST à mão, que deixou de existir. Substitua-os pelos
novos (as recusas + o dublê de `Client`); NÃO adapte o dublê de `.post()`.

- [ ] **Step 5: Confirmar que o resto da delegação não regrediu**

```bash
uv run --no-project pytest tests/test_delegation_tool.py tests/test_delegation_exec_local.py \
    tests/test_delegation_async.py tests/runtime -q --timeout=120 -p no:cacheprovider
```

Esperado: PASS. `dna/runtime/builder.py:_make_call_remote` passa `http=client`
explicitamente, então continua válido com o `http` agora opcional.

- [ ] **Step 6: Commit**

```bash
git add packages/sdk-py/dna/application/a2a_transport.py packages/sdk-py/tests/test_a2a_transport.py
git commit -m "feat(a2a): a chamada de saida fala pelo Client oficial — e as recusas continuam antes do primeiro byte"
```

---

### Task 7: A prova — um cliente A2A de terceiro conversa com o nosso servidor

**Files:**
- Create: `packages/sdk-py/tests/test_a2a_conformance.py`

**Interfaces:**
- Consumes: tudo das Tasks 2, 4 e 5.
- Produces: nada — é a medição que a spec chama de "como saber que funcionou".

- [ ] **Step 1: Escrever o teste**

Este é o teste que a versão à mão nunca teve, e é a razão desta spec existir.
Criar `packages/sdk-py/tests/test_a2a_conformance.py`:

```python
"""Conformidade MEDIDA: o cliente do `a2a-sdk` contra o nosso servidor.

Todo outro teste desta face é escrito por quem escreveu o código, e por isso não
consegue pegar um erro de LEITURA da spec — foi assim que a versão à mão chegou
a 49 testes verdes emitindo `{"transport": "jsonrpc"}` num protocolo que o
chama `protocolBinding`.

Este teste é diferente: o julgamento é da implementação de REFERÊNCIA. Ele sobe
o nosso servidor de verdade (uvicorn, porta real) e faz o cliente oficial
descobrir o Card, escolher o transporte e falar `message/stream`. Se a nossa
projeção divergir da 1.0 em qualquer ponto que importe, o cliente não chega até
os eventos — que é exatamente o que aconteceria com um cliente de terceiro em
produção, no pior momento possível.
"""
from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest

pytest.importorskip("a2a", reason="a conformidade se mede contra o SDK oficial")
pytest.importorskip("fastapi")
uvicorn = pytest.importorskip("uvicorn")

from fastapi import FastAPI  # noqa: E402

from dna.emit.agent_card import agent_card_for  # noqa: E402
from dna.extensions.a2a.executor import DnaAgentExecutor  # noqa: E402
from dna.extensions.a2a.serve import attach_a2a  # noqa: E402


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def servidor():
    porta = _porta_livre()
    base = f"http://127.0.0.1:{porta}"

    async def run(texto: str) -> str:
        return f"eco:{texto}"

    app = FastAPI()
    attach_a2a(
        app,
        "/a2a",
        executor=DnaAgentExecutor(run=run),
        card=agent_card_for(
            {"metadata": {"name": "eco", "description": "ecoa"}, "spec": {}},
            tools=["review_kind"],
            base_url=f"{base}/a2a",
        ),
    )
    servidor = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="error")
    )
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    for _ in range(100):
        if servidor.started:
            break
        time.sleep(0.1)
    assert servidor.started, "o servidor não subiu"
    try:
        yield base
    finally:
        servidor.should_exit = True
        thread.join(timeout=5)


def test_um_cliente_A2A_de_terceiro_descobre_o_card_e_recebe_os_eventos(servidor):
    import httpx
    from a2a.client import ClientConfig, ClientFactory
    from a2a.types import Message, Part, Role, SendMessageRequest, TaskState

    async def conversar():
        async with httpx.AsyncClient() as http:
            fabrica = ClientFactory(ClientConfig(httpx_client=http, streaming=True))
            # `create_from_url` faz a descoberta INTEIRA: busca
            # /.well-known/agent-card.json, lê `supportedInterfaces`, escolhe o
            # binding e monta o transporte. Se o nosso Card divergir, ele falha
            # AQUI — antes de qualquer evento.
            cliente = await fabrica.create_from_url(servidor)
            pedido = SendMessageRequest(
                message=Message(
                    message_id="m1", role=Role.ROLE_USER, parts=[Part(text="ola")]
                )
            )
            return [evento async for evento in cliente.send_message(pedido)]

    eventos = asyncio.run(conversar())

    assert eventos, "o cliente oficial não recebeu evento algum"
    tipos = [e.WhichOneof("payload") for e in eventos]
    assert "task" in tipos, f"nenhuma Task veio primeiro: {tipos}"
    assert "artifact_update" in tipos, f"o resultado não chegou como artifact: {tipos}"

    textos = [
        p.text
        for e in eventos
        if e.WhichOneof("payload") == "artifact_update"
        for p in e.artifact_update.artifact.parts
        if p.WhichOneof("content") == "text"
    ]
    assert "eco:ola" in textos, textos

    estados = [
        e.status_update.status.state
        for e in eventos
        if e.WhichOneof("payload") == "status_update"
    ]
    assert TaskState.TASK_STATE_COMPLETED in estados, estados
```

- [ ] **Step 2: Rodar**

```bash
cd packages/sdk-py
uv run --no-project pytest tests/test_a2a_conformance.py -q --timeout=120 -p no:cacheprovider -s
```

Esperado: PASS. Se falhar em `create_from_url`, o defeito é na projeção do Card
(Task 2) — leia a exceção antes de mexer no teste; é o cliente oficial dizendo
onde divergimos, que é o valor inteiro deste arquivo.

⚠️ `uvicorn` pode não estar no ambiente de teste do sdk-py. Se o
`importorskip` pular, instale-o no extra `dev` (`"uvicorn>=0.30"`) — um teste de
conformidade que pula em silêncio é pior que nenhum, porque parece cobertura.
Confirme que ele RODA, não que ele passa.

- [ ] **Step 3: Rodar a suíte inteira**

```bash
uv run --no-project pytest tests -q --timeout=180 -p no:cacheprovider 2>&1 | tail -20
```

Esperado: zero falhas.

- [ ] **Step 4: Commit**

```bash
git add packages/sdk-py/tests/test_a2a_conformance.py packages/sdk-py/pyproject.toml
git commit -m "test(a2a): a prova que a versao a mao nunca teve — o cliente oficial julga o nosso servidor"
```

---

### Task 8: Documentar a regra, e o que ela custou descobrir

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/superpowers/specs/2026-07-30-a2a-delegation-design.md` (nota de fechamento)

**Interfaces:**
- Consumes: os resultados das Tasks 2, 3 e 7.
- Produces: nada de código.

- [ ] **Step 1: Entrada no CHANGELOG**

No topo da seção não lançada de `CHANGELOG.md`:

```markdown
### A face A2A passa a ser o SDK oficial (`a2a-sdk`)

Servir e consumir A2A deixa de ser código nosso. `dna.extensions.a2a.serve`
monta as rotas do `a2a-sdk`; `DnaAgentExecutor` adapta um agente DNA à interface
`AgentExecutor`; `call_remote` fala pelo `Client` oficial. Novo extra:
`dna-cli[a2a]`.

**Quebra:** o Kind `RemoteAgent` renomeia `supported_interfaces[].transport`
para `protocol_binding` (valores em MAIÚSCULAS: `JSONRPC`, `GRPC`, `HTTP+JSON`)
e ganha `protocol_version`. Documentos `RemoteAgent` escritos antes precisam ser
reescritos.

**Por quê:** a implementação anterior, escrita a partir da especificação, tinha
49 testes verdes e divergia da A2A 1.0 em três pontos — o nome do campo do
binding, o valor dele, e a forma de uma `Part`. Consequência medida: nenhum
Agent Card A2A real podia ser ingerido, e nenhum cliente conforme conseguia nos
chamar. Os testes não pegaram porque foram escritos pela mesma leitura da spec
que o código. Conformidade agora é medida contra a implementação de referência
(`tests/test_a2a_conformance.py`), não contra a nossa leitura dela.
```

- [ ] **Step 2: Rodar as guardas do repo**

```bash
cd packages/sdk-py
uv run --no-project pytest tests -q --timeout=180 -p no:cacheprovider 2>&1 | tail -5
cd ../cli
uv run --no-project pytest tests -q --timeout=180 -p no:cacheprovider 2>&1 | tail -5
```

Esperado: zero falhas nos dois pacotes.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(a2a): a troca pelo SDK oficial, e os tres defeitos que ela revelou"
```

---

## Self-Review — cobertura da spec

| passo da spec | onde |
|---|---|
| 1. Remover a implementação à mão | **Global Constraints** — ramificar de `origin/main`, onde ela nunca esteve. Custo zero. |
| 2. `a2a` vira extra do `dna-cli` | Task 1 |
| 3. `DnaAgentExecutor` | Task 4 |
| 4. Montar as rotas do SDK no FastAPI | Task 5 (seam público `dna_cli.serving.attach_a2a`; a flag em `dna api serve` foi excluída por decisão do fundador, 31/07 — `serving.py` declara os comandos `serve` depreciados para produção) |
| 5. Trocar `call_remote`/`stream_remote` pelo `Client`, preservando as recusas | Task 6 (`stream_remote` não existe em `main`; `call_remote` ganha `on_event` e absorve o papel) |
| 6. `capabilities.streaming` derivado | Tasks 2 e 5 |
| "Como saber que funcionou" | Task 7 |
| A projeção do Card continua nossa | Task 2 |
| As recusas de política continuam nossas | Task 6 |
| A ligação com `delegation_exec` | Task 6, Step 5 |
| A borda de identidade fica fora | Tasks 4 e 5 (docstrings + ausência de leitura de bearer) |

**Fora do escopo da spec, e incluído porque a medição obrigou:** Task 3 (a
entrada). A spec não previa mexer no Kind `RemoteAgent` — mas o mesmo erro de
leitura que quebrava a saída quebrava a entrada, e deixar metade consertada
manteria o produto sem conseguir registrar um agente A2A real.
