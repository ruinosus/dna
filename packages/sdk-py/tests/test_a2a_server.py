"""A face A2A que SERVE — o mount HTTP.

Fecha a metade que faltava: o SDK projetava o Card, ingeria o de terceiros e
tinha o cliente. Faltava a porta — e sem ela `capabilities.streaming: true` no
Card era promessa sem nada atrás.
"""
from __future__ import annotations

import json

import pytest

fastapi = pytest.importorskip("fastapi", reason="a face A2A servida precisa do extra `api`")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from dna.emit.agent_card import agent_card_for  # noqa: E402
from dna.extensions.a2a.rpc import (  # noqa: E402
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
)
from dna.extensions.a2a.server import TaskStore, attach_a2a  # noqa: E402

AGENTE = {"metadata": {"name": "converter-agent", "description": "converte"}, "spec": {}}
CARD = agent_card_for(AGENTE, tools=["review_kind"], base_url="https://x/a2a")


def _cliente(resposta="pronto", explode=False):
    app = FastAPI()

    async def run(texto: str) -> str:
        if explode:
            raise RuntimeError("o alvo caiu")
        return f"{resposta}:{texto}"

    loja = attach_a2a(app, "/a2a", run=run, card=CARD)
    return TestClient(app), loja


def _envia(c, metodo="message/send", texto="converta isto", **kw):
    corpo = {
        "jsonrpc": "2.0",
        "id": "r1",
        "method": metodo,
        "params": {"message": {"role": "user", "parts": [{"kind": "text", "text": texto}]}},
    }
    corpo["params"].update(kw)
    return c.post("/a2a", json=corpo)


# ── o Card ──────────────────────────────────────────────────────────────────


def test_o_card_e_servido_no_caminho_da_1_0():
    c, _ = _cliente()
    r = c.get("/.well-known/agent-card.json")
    assert r.status_code == 200
    assert r.json()["name"] == "converter-agent"


def test_o_card_servido_e_a_PROJECAO_verbatim():
    """Duplicar o Card aqui criaria uma segunda verdade sobre o mesmo agente."""
    c, _ = _cliente()
    assert c.get("/.well-known/agent-card.json").json() == CARD


def test_o_caminho_do_card_e_PARAMETRO():
    """A raiz do domínio não é do SDK — um host que monta sob prefixo precisa
    poder dizer onde. `dna.emit.agent_card` já declarava isso."""
    app = FastAPI()

    async def run(t):
        return t

    attach_a2a(app, "/a2a", run=run, card=CARD, card_path="/sob/prefixo/card.json")
    c = TestClient(app)
    assert c.get("/sob/prefixo/card.json").status_code == 200
    assert c.get("/.well-known/agent-card.json").status_code == 404


# ── message/send ────────────────────────────────────────────────────────────


def test_send_devolve_uma_Task_completa_com_o_resultado():
    c, _ = _cliente()
    corpo = _envia(c).json()
    assert corpo["jsonrpc"] == "2.0" and corpo["id"] == "r1"
    t = corpo["result"]
    assert t["status"]["state"] == "completed"
    assert t["artifacts"][0]["parts"][0]["text"] == "pronto:converta isto"


def test_uma_falha_do_agente_vira_Task_FAILED_e_nao_500():
    """Uma exceção que escapasse viraria um 500 sem `id`, e o cliente perderia
    tanto o resultado quanto a razão."""
    c, _ = _cliente(explode=True)
    r = _envia(c)
    assert r.status_code == 200
    t = r.json()["result"]
    assert t["status"]["state"] == "failed"
    assert "o alvo caiu" in t["status"]["message"]["parts"][0]["text"]


# ── message/stream ──────────────────────────────────────────────────────────


def test_stream_responde_event_stream_com_o_primeiro_evento_ANTES_do_trabalho():
    """O primeiro evento é o que transforma a espera em progresso — sem ele o
    cliente fica com uma conexão aberta e silenciosa, indistinguível de travada."""
    c, _ = _cliente()
    r = _envia(c, metodo="message/stream")
    assert r.headers["content-type"].startswith("text/event-stream")
    quadros = [q for q in r.text.split("\n\n") if q.strip()]
    assert len(quadros) == 2
    primeiro = json.loads(quadros[0][len("data: "):])
    assert primeiro["result"]["status"]["state"] == "working"
    ultimo = json.loads(quadros[1][len("data: "):])
    assert ultimo["result"]["status"]["state"] == "completed"


def test_o_stream_pede_para_NAO_ser_buferizado():
    """Sem isto um proxy pode entregar o stream inteiro no fim — continuaria
    "funcionando" no teste e deixaria de funcionar atrás do primeiro proxy."""
    c, _ = _cliente()
    r = _envia(c, metodo="message/stream")
    assert r.headers.get("x-accel-buffering") == "no"
    assert "no-cache" in r.headers.get("cache-control", "")


def test_cada_quadro_do_stream_carrega_o_MESMO_id_do_pedido():
    c, _ = _cliente()
    r = _envia(c, metodo="message/stream")
    for q in [x for x in r.text.split("\n\n") if x.strip()]:
        assert json.loads(q[len("data: "):])["id"] == "r1"


# ── tasks/get ───────────────────────────────────────────────────────────────


def test_uma_Task_concluida_e_recuperavel_por_tasks_get():
    """A rede de segurança do streaming: o cliente que perdeu a conexão volta e
    busca o resultado."""
    c, _ = _cliente()
    tid = _envia(c).json()["result"]["id"]
    r = c.post("/a2a", json={"jsonrpc": "2.0", "id": 9, "method": "tasks/get",
                             "params": {"id": tid}})
    assert r.json()["result"]["id"] == tid
    assert r.json()["result"]["status"]["state"] == "completed"


def test_uma_Task_desconhecida_recusa_com_o_id_do_pedido():
    c, _ = _cliente()
    corpo = c.post("/a2a", json={"jsonrpc": "2.0", "id": 9, "method": "tasks/get",
                                 "params": {"id": "nao-existe"}}).json()
    assert corpo["id"] == 9 and corpo["error"]["code"] == INVALID_PARAMS


def test_uma_falha_TAMBEM_fica_recuperavel():
    """Quem perdeu a conexão precisa saber que falhou — e por quê. Guardar só o
    sucesso faria a falha virar silêncio."""
    c, _ = _cliente(explode=True)
    tid = _envia(c).json()["result"]["id"]
    corpo = c.post("/a2a", json={"jsonrpc": "2.0", "id": 1, "method": "tasks/get",
                                 "params": {"id": tid}}).json()
    assert corpo["result"]["status"]["state"] == "failed"


def test_o_armazem_de_Tasks_e_LIMITADO():
    """Um dicionário sem teto num processo de vida longa é vazamento de memória
    com passos extras. Não é cache de resultado — é rede de segurança de segundos."""
    loja = TaskStore(limit=2)
    for i in range(5):
        loja.put({"id": f"t{i}"})
    assert loja.get("t0") is None and loja.get("t4") is not None


# ── as recusas de protocolo ─────────────────────────────────────────────────


def test_corpo_ilegivel_recusa_com_PARSE_ERROR_e_200():
    """200 com `error` no corpo, não 400: no JSON-RPC o transporte funcionou e o
    erro é da camada de cima. Um 400 faria um cliente conforme tratar como falha
    de rede e reenviar."""
    c, _ = _cliente()
    r = c.post("/a2a", content=b"{isto nao e json", headers={"content-type": "application/json"})
    assert r.status_code == 200 and r.json()["error"]["code"] == PARSE_ERROR


def test_metodo_desconhecido_recusa_pela_porta():
    c, _ = _cliente()
    corpo = c.post("/a2a", json={"jsonrpc": "2.0", "id": 3, "method": "message/telepathy"}).json()
    assert corpo["error"]["code"] == METHOD_NOT_FOUND and corpo["id"] == 3


def test_um_pedido_sem_texto_recusa_CARREGANDO_o_id():
    c, _ = _cliente()
    corpo = c.post("/a2a", json={"jsonrpc": "2.0", "id": 7, "method": "message/send",
                                 "params": {"message": {"parts": []}}}).json()
    assert corpo["error"]["code"] == INVALID_PARAMS and corpo["id"] == 7
