"""O cliente A2A aprende `message/stream` — Fase 3.

`call_remote` abre a conexão e fica MUDA até o fim. Para um alvo de 20 segundos
isso é indistinguível de travado — a queixa que originou este épico. Aqui cada
evento passa por `on_event` assim que chega.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from dna.application.a2a_transport import (
    parse_sse_events,
    stream_remote,
    task_text,
)
from dna.application.delegation import DelegationTarget
from dna.application.delegation_exec import DelegationRefused


def _alvo(**kw):
    base = dict(
        name="converter-agent",
        kind="RemoteAgent",
        format="text",
        typical_seconds=20,
        use_when="",
        purpose="",
        interfaces=({"transport": "jsonrpc", "url": "https://alvo/a2a"},),
        data_scope_kinds=("SourceArtifact",),
    )
    base.update(kw)
    campos = {f: base[f] for f in base if f in DelegationTarget.__dataclass_fields__}
    return DelegationTarget(**campos)


class _Resposta:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


class _Http:
    def __init__(self, resposta):
        self._resposta = resposta
        self.chamadas = []

    async def post(self, url, **kw):
        self.chamadas.append((url, kw))
        return self._resposta


def _sse(*objs):
    return "".join(f"data: {json.dumps(o)}\n\n" for o in objs)


def _task(estado, texto=None):
    t = {"id": "t1", "kind": "task", "status": {"state": estado}}
    if texto:
        t["artifacts"] = [{"artifactId": "a", "parts": [{"kind": "text", "text": texto}]}]
    return {"jsonrpc": "2.0", "id": "1", "result": t}


# ── o parse do SSE ──────────────────────────────────────────────────────────


def test_cada_data_vira_um_objeto():
    evs = parse_sse_events(_sse(_task("working"), _task("completed", "pronto")))
    assert [e["result"]["status"]["state"] for e in evs] == ["working", "completed"]


def test_um_quadro_ILEGIVEL_e_pulado_e_nao_derruba_o_stream():
    """Um stream longo não pode morrer inteiro por um evento malformado no meio —
    o cliente ainda tem os que vieram antes e os que virão depois."""
    corpo = _sse(_task("working")) + "data: {isto nao e json\n\n" + _sse(_task("completed", "ok"))
    evs = parse_sse_events(corpo)
    assert len(evs) == 2 and evs[-1]["result"]["artifacts"]


def test_um_corpo_sem_SSE_devolve_lista_vazia():
    assert parse_sse_events('{"jsonrpc":"2.0"}') == []
    assert parse_sse_events("") == []


# ── o texto do artifact ─────────────────────────────────────────────────────


def test_o_texto_vem_do_ARTIFACT():
    assert task_text(_task("completed", "o documento")) == "o documento"


def test_um_evento_de_PROGRESSO_nao_tem_texto():
    """É isso que deixa quem consome distinguir "andou" de "terminou" sem olhar o
    estado por fora."""
    assert task_text(_task("working")) is None
    assert task_text({"jsonrpc": "2.0"}) is None


# ── o stream ────────────────────────────────────────────────────────────────


def _chama(resposta, **kw):
    http = _Http(resposta)
    saida = asyncio.run(
        stream_remote(_alvo(), "converta", credential_for=lambda _n: "tok", http=http, **kw)
    )
    return saida, http


def test_devolve_o_texto_FINAL_e_chama_o_metodo_de_stream():
    saida, http = _chama(_Resposta(_sse(_task("working"), _task("completed", "pronto"))))
    assert saida == "pronto"
    assert http.chamadas[0][1]["json"]["method"] == "message/stream"


def test_cada_evento_passa_por_on_event_ASSIM_QUE_CHEGA():
    """O ganho inteiro da fase: progresso em vez de silêncio."""
    vistos = []
    _chama(
        _Resposta(_sse(_task("working"), _task("completed", "pronto"))),
        on_event=vistos.append,
    )
    assert [e["result"]["status"]["state"] for e in vistos] == ["working", "completed"]


def test_o_ULTIMO_artifact_vence():
    """Um stream pode reemitir a task com o resultado crescendo; o primeiro seria
    parcial."""
    saida, _ = _chama(_Resposta(_sse(_task("working", "par"), _task("completed", "parcial+fim"))))
    assert saida == "parcial+fim"


def test_um_corpo_que_NAO_e_stream_degrada_para_o_corpo_cru():
    """Um servidor que não faz streaming responde JSON. Devolver vazio faria
    parecer que o alvo não respondeu."""
    saida, _ = _chama(_Resposta('{"jsonrpc":"2.0","result":{}}'))
    assert saida == '{"jsonrpc":"2.0","result":{}}'


def test_pede_text_event_stream_no_accept():
    _, http = _chama(_Resposta(_sse(_task("completed", "x"))))
    assert http.chamadas[0][1]["headers"]["accept"] == "text/event-stream"


# ── as recusas, IDÊNTICAS às de call_remote ─────────────────────────────────


def test_SEM_credencial_recusa_antes_de_qualquer_byte():
    """Um caminho novo com portões mais frouxos que o antigo é a forma mais
    silenciosa de perder uma garantia."""
    http = _Http(_Resposta(""))
    with pytest.raises(DelegationRefused, match="anonimamente"):
        asyncio.run(
            stream_remote(_alvo(), "x", credential_for=lambda _n: None, http=http)
        )
    assert http.chamadas == [], "nao pode ter tocado a rede"


def test_um_payload_fora_do_data_scope_recusa():
    alvo = _alvo(data_scope_kinds=("Engram",))
    http = _Http(_Resposta(""))
    with pytest.raises(DelegationRefused, match="data_scope"):
        asyncio.run(
            stream_remote(
                alvo, "x", credential_for=lambda _n: "tok", http=http,
                payload_kinds=("Project",),
            )
        )
    assert http.chamadas == []


def test_um_status_de_erro_do_remoto_recusa():
    http = _Http(_Resposta("", status_code=503))
    with pytest.raises(DelegationRefused, match="503"):
        asyncio.run(stream_remote(_alvo(), "x", credential_for=lambda _n: "t", http=http))
