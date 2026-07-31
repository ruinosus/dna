"""O núcleo puro da face A2A de ENTRADA.

A face de saída (o Agent Card) já era pura e testada sem servidor. Esta é a
metade que faltava: interpretar o pedido, recusar o malformado com o código que a
especificação manda, e dar forma à Task.

São exatamente os casos que um cliente A2A de terceiro exercita primeiro — e
triviais aqui, caros por HTTP.
"""
from __future__ import annotations

import json

import pytest

from dna.extensions.a2a.rpc import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    METHODS,
    RpcError,
    parse_request,
    result,
    sse_frame,
    task,
    text_from_message,
)


def _pedido(**kw):
    base = {"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {}}
    base.update(kw)
    return base


# ── o envelope ──────────────────────────────────────────────────────────────


def test_um_pedido_valido_atravessa():
    r = parse_request(_pedido(params={"message": {"parts": []}}))
    assert (r.id, r.method) == (1, "message/send")


@pytest.mark.parametrize("metodo", METHODS)
def test_os_tres_metodos_da_1_0_sao_aceitos(metodo):
    assert parse_request(_pedido(method=metodo)).method == metodo


def test_um_metodo_desconhecido_recusa_NOMEANDO_os_que_existem():
    """Um cliente que errou o método está descobrindo a superfície. Mandá-lo de
    volta sem a lista o obriga a adivinhar — e o Agent Card e esta mensagem são
    as duas únicas fontes que ele tem."""
    with pytest.raises(RpcError) as e:
        parse_request(_pedido(method="message/telepathy"))
    assert e.value.code == METHOD_NOT_FOUND
    for m in METHODS:
        assert m in e.value.message


def test_a_versao_do_jsonrpc_e_exigida_exatamente():
    for ruim in ("1.0", 2.0, None, "2"):
        with pytest.raises(RpcError) as e:
            parse_request(_pedido(jsonrpc=ruim))
        assert e.value.code == INVALID_REQUEST


def test_o_ID_viaja_em_TODA_recusa():
    """Um erro sem `id` é um erro que o cliente não consegue casar com o pedido
    que o causou — e a especificação o exige de volta por isso. O `id` é extraído
    ANTES de qualquer outra checagem."""
    for pedido in (
        _pedido(jsonrpc="1.0", id="abc"),
        _pedido(method="nao/existe", id="abc"),
        _pedido(params=[], id="abc"),
    ):
        with pytest.raises(RpcError) as e:
            parse_request(pedido)
        assert e.value.id == "abc"
        assert e.value.envelope()["id"] == "abc"


def test_um_corpo_que_nao_e_objeto_recusa():
    for ruim in ([], "texto", 7, None):
        with pytest.raises(RpcError) as e:
            parse_request(ruim)
        assert e.value.code == INVALID_REQUEST


def test_params_ausente_vira_dicionario_vazio():
    """`params` é opcional no JSON-RPC. Recusar por ausência quebraria um
    `tasks/get` que o cliente monte sem ele."""
    assert parse_request({"jsonrpc": "2.0", "id": 1, "method": "tasks/get"}).params == {}
    assert parse_request(_pedido(params=None)).params == {}


def test_params_que_nao_e_objeto_recusa_com_INVALID_PARAMS():
    with pytest.raises(RpcError) as e:
        parse_request(_pedido(params=["a"]))
    assert e.value.code == INVALID_PARAMS


def test_o_envelope_de_erro_tem_a_forma_do_jsonrpc():
    env = RpcError(INVALID_PARAMS, "porque sim", "x").envelope()
    assert env == {
        "jsonrpc": "2.0",
        "id": "x",
        "error": {"code": INVALID_PARAMS, "message": "porque sim"},
    }


# ── a mensagem ──────────────────────────────────────────────────────────────


def test_o_texto_vem_das_partes_concatenadas():
    t = text_from_message(
        {"message": {"role": "user", "parts": [{"kind": "text", "text": "a"},
                                               {"kind": "text", "text": "b"}]}}
    )
    assert t == "a\nb"


def test_uma_parte_que_NAO_e_texto_e_ignorada_e_nao_recusada():
    """Um cliente que anexa uma imagem a um pedido cujo texto basta deve ser
    atendido. Recusar o pedido inteiro por uma parte que não sabemos ler trocaria
    uma degradação por uma falha."""
    t = text_from_message(
        {"message": {"parts": [{"kind": "file", "uri": "x"}, {"kind": "text", "text": "ok"}]}}
    )
    assert t == "ok"


def test_uma_parte_SEM_kind_e_tratada_como_texto():
    """A 1.0 traz `kind`, versões anteriores não. Exigi-lo recusaria clientes
    corretos de ontem por uma chave que não muda o significado."""
    assert text_from_message({"message": {"parts": [{"text": "ok"}]}}) == "ok"


def test_um_pedido_SEM_texto_nenhum_e_RECUSADO():
    """Não há tarefa a executar. Inventar uma vazia produziria uma Task que
    completa sem ter feito nada — o pior resultado, porque parece sucesso."""
    for params in (
        {"message": {"parts": []}},
        {"message": {"parts": [{"kind": "text", "text": "   "}]}},
        {"message": {"parts": [{"kind": "file"}]}},
    ):
        with pytest.raises(RpcError) as e:
            text_from_message(params)
        assert e.value.code == INVALID_PARAMS


def test_message_ausente_ou_malformada_recusa():
    for params in ({}, {"message": "texto"}, {"message": {"parts": "nao e lista"}}):
        with pytest.raises(RpcError) as e:
            text_from_message(params)
        assert e.value.code == INVALID_PARAMS


# ── a Task ──────────────────────────────────────────────────────────────────


def test_o_resultado_do_agente_vira_ARTIFACT_e_nao_mensagem():
    """Artifact é o que a 1.0 define como SAÍDA de uma task, e é o que um cliente
    coletor lê. Devolver como mensagem faria o resultado parecer conversa."""
    t = task("t1", "c1", "completed", text="o documento")
    assert t["artifacts"][0]["parts"][0]["text"] == "o documento"
    assert t["status"] == {"state": "completed"}
    assert t["kind"] == "task"


def test_uma_falha_viaja_DENTRO_do_status_nao_como_erro_de_protocolo():
    """A chamada funcionou; foi a tarefa que falhou. Confundir os dois faria um
    cliente tratar falha de negócio como protocolo quebrado e reenviar."""
    t = task("t1", "c1", "failed", error="o alvo recusou")
    assert t["status"]["state"] == "failed"
    assert t["status"]["message"]["parts"][0]["text"] == "o alvo recusou"
    assert "artifacts" not in t


def test_uma_task_em_curso_nao_carrega_artifact():
    t = task("t1", "c1", "working")
    assert t["status"]["state"] == "working" and "artifacts" not in t


# ── o SSE ───────────────────────────────────────────────────────────────────


def test_cada_evento_SSE_carrega_uma_Response_JSON_RPC_COMPLETA():
    """A parte que mais se erra: mandar só o objeto Task, sem envelope, faz o
    stream falar um protocolo diferente do da chamada síncrona — e um cliente
    conforme não o interpreta."""
    quadro = sse_frame(result("id-1", task("t1", "c1", "working")))
    assert quadro.startswith("data: ") and quadro.endswith("\n\n")
    corpo = json.loads(quadro[len("data: "):].strip())
    assert corpo["jsonrpc"] == "2.0" and corpo["id"] == "id-1"
    assert corpo["result"]["kind"] == "task"


def test_o_SSE_nao_escapa_acentos():
    """`ensure_ascii` ligado transformaria "conversão" em escapes — legível para
    a máquina e ilegível no `curl` de quem está depurando o stream."""
    assert "conversão" in sse_frame(result(1, task("t", "c", "completed", text="conversão")))
