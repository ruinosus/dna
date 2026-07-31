"""A face A2A SERVIDA — as rotas do SDK oficial montadas num FastAPI do host.

O que é nosso aqui é o Card (a projeção de `dna.emit.agent_card`) e a derivação
de `capabilities.streaming`. As rotas, o dispatch JSON-RPC, o enquadramento SSE
e a `tasks/get` são do `a2a-sdk` — e é por isso que este arquivo tem poucos
testes: não há protocolo nosso para testar. A conformidade de verdade é medida
em `test_a2a_conformance.py`, contra o cliente oficial.
"""
from __future__ import annotations

import pytest

pytest.importorskip("a2a", reason="a face servida monta as rotas do SDK oficial")
pytest.importorskip("fastapi", reason="a face servida precisa do extra `api`")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from a2a.utils.constants import PROTOCOL_VERSION_CURRENT, VERSION_HEADER  # noqa: E402

from dna.emit.agent_card import agent_card_for  # noqa: E402
from dna.extensions.a2a.executor import DnaAgentExecutor  # noqa: E402
from dna.extensions.a2a.serve import attach_a2a  # noqa: E402

#: O cabeçalho de versão do protocolo. A 1.0 o EXIGE: sem ele o handler assume
#: 0.3 e recusa com `-32009 VERSION_NOT_SUPPORTED`. O cliente oficial o manda
#: sozinho (`ClientFactory` faz `headers.setdefault`); um teste que fala HTTP
#: cru precisa mandá-lo à mão — e o valor vem do SDK, não de um literal nosso.
_VERSAO = {VERSION_HEADER: PROTOCOL_VERSION_CURRENT}

AGENTE = {"metadata": {"name": "eco", "description": "ecoa"}, "spec": {}}


async def _eco(texto: str) -> str:
    return f"eco:{texto}"


def _cliente(executor=None) -> TestClient:
    app = FastAPI()
    attach_a2a(
        app,
        "/a2a",
        executor=executor or DnaAgentExecutor(run=_eco),
        card=agent_card_for(AGENTE, tools=["review_kind"], base_url="https://x/a2a"),
    )
    return TestClient(app)


def test_o_card_e_servido_no_caminho_convencional():
    corpo = _cliente().get("/.well-known/agent-card.json").json()
    assert corpo["name"] == "eco"
    assert corpo["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"


def test_streaming_do_card_e_DERIVADO_do_executor_montado():
    """O Card é a nossa verdade sobre o agente — mas `capabilities.streaming` é
    fato sobre o EXECUTOR, e quem monta é quem sabe."""

    class SemStreaming(DnaAgentExecutor):
        streaming = False

    com = _cliente().get("/.well-known/agent-card.json").json()
    sem = (
        _cliente(executor=SemStreaming(run=_eco))
        .get("/.well-known/agent-card.json")
        .json()
    )

    assert com["capabilities"]["streaming"] is True
    # Um `false` em protobuf é o default do campo, e a serialização JSON o
    # OMITE. Ausente e `false` são a mesma afirmação aqui — o que importa é que
    # o Card não promete streaming.
    assert sem.get("capabilities", {}).get("streaming", False) is False


def test_SendMessage_devolve_a_task_completa_com_o_artifact():
    """O método é `SendMessage`, não `message/send`.

    Os nomes com barra (`message/send`, `message/stream`, `tasks/get`) são da
    A2A **0.3** — a versão à mão servia exatamente esses três e se anunciava
    como 1.0. O SDK oficial tem um flag `enable_v0_3_compat` justamente porque
    são protocolos diferentes; sem ele, `message/send` responde
    `-32601 Method not found`.
    """
    resposta = _cliente().post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": "m1",
                    "role": "ROLE_USER",
                    "parts": [{"text": "ola"}],
                }
            },
        },
        headers=_VERSAO,
    )
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert "error" not in corpo, corpo
    assert "eco:ola" in str(corpo["result"]), corpo


def test_o_nome_de_metodo_da_versao_a_mao_era_da_0_3_e_e_recusado():
    """Guarda contra a regressão mais silenciosa possível: alguém "consertar" o
    servidor para aceitar `message/send` de novo e voltar a servir 0.3 sob o
    nome de 1.0. Se um dia quisermos falar 0.3, é `enable_v0_3_compat=True` no
    SDK — uma decisão explícita, não um apelido."""
    corpo = (
        _cliente()
        .post(
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
            headers=_VERSAO,
        )
        .json()
    )
    assert corpo.get("error", {}).get("code") == -32601, corpo


def test_um_metodo_desconhecido_e_recusado_como_erro_de_PROTOCOLO():
    """Não asseriamos o código (-32601 é do SDK, não nosso) — asseriamos que a
    recusa é de protocolo e não um 500."""
    resposta = _cliente().post(
        "/a2a",
        json={"jsonrpc": "2.0", "id": "1", "method": "nao/existe", "params": {}},
        headers=_VERSAO,
    )
    assert resposta.status_code < 500, resposta.text
    assert "error" in resposta.json(), resposta.json()


def test_um_card_que_diverge_da_1_0_falha_na_MONTAGEM_e_nao_no_ar():
    """`ParseDict` é estrito de propósito: uma divergência entre a nossa
    projeção e a especificação vira erro AQUI, ao montar, em vez de virar um
    Card que ninguém lá fora consegue ler."""
    app = FastAPI()
    with pytest.raises(Exception, match="transport"):
        attach_a2a(
            app,
            "/a2a",
            executor=DnaAgentExecutor(run=_eco),
            card={
                "name": "eco",
                "description": "ecoa",
                # A forma da versão à mão. O campo não existe na 1.0.
                "supportedInterfaces": [
                    {"transport": "jsonrpc", "url": "https://x/a2a"}
                ],
            },
        )


def test_o_host_pode_injetar_o_seu_ServerCallContextBuilder():
    """A lacuna que só aparece quando um host REAL monta a face.

    A porta não autentica (a borda autentica), mas o executor precisa saber
    QUEM chamou para ligar o workspace e cobrar do plano certo. O SDK tem a
    costura para isso — `ServerCallContextBuilder`, que lê o `request` e popula
    o contexto que o executor recebe — e `attach_a2a` não a repassava.

    O caminho alternativo (copiar a identidade para um contextvar num
    middleware) está QUEBRADO para streaming: um `BaseHTTPMiddleware` reseta o
    contextvar quando o handler devolve a `StreamingResponse`, ou seja ANTES de
    o corpo streamar — o dna-cloud já pagou por essa lição
    (`mcp/request_ctx.py`). Para `SendStreamingMessage` a identidade sumiria no
    meio do caminho, e só ali.
    """
    from a2a.server.context import ServerCallContext
    from a2a.server.routes.common import ServerCallContextBuilder

    vistos: list = []

    class _Builder(ServerCallContextBuilder):
        def build(self, request):
            vistos.append(request.url.path)
            return ServerCallContext(state={"quem": "a-acme"})

    app = FastAPI()
    attach_a2a(
        app,
        "/a2a",
        executor=DnaAgentExecutor(run=_eco),
        card=agent_card_for(AGENTE, base_url="https://x/a2a"),
        context_builder=_Builder(),
    )
    TestClient(app).post("/a2a", json={
        "jsonrpc": "2.0", "id": "1", "method": "SendMessage",
        "params": {"message": {"messageId": "m1", "role": "ROLE_USER",
                               "parts": [{"text": "ola"}]}},
    }, headers=_VERSAO)

    assert vistos == ["/a2a"], f"o builder do host não foi consultado: {vistos}"
