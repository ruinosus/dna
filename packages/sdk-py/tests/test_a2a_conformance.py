"""Conformidade MEDIDA: o cliente do `a2a-sdk` contra o nosso servidor.

Todo outro teste desta face é escrito por quem escreveu o código, e por isso não
consegue pegar um erro de LEITURA da especificação — foi assim que a face A2A
anterior chegou a 49 testes verdes servindo A2A 0.3 sob o nome de 1.0.

Este arquivo é diferente: o julgamento é da implementação de REFERÊNCIA. Ele
sobe o nosso servidor de verdade (uvicorn, porta real) e faz o cliente oficial
descobrir o Card, escolher o binding, montar o transporte e falar. Se a nossa
projeção divergir da 1.0 em qualquer ponto que importe, o cliente não chega até
os eventos — que é exatamente o que aconteceria com um cliente de terceiro em
produção, no pior momento possível.

Se este teste PULAR, o valor dele é zero: um teste de conformidade ausente
parece cobertura e não é. Por isso `a2a-sdk` e `uvicorn` estão no extra `dev`.
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
        return int(s.getsockname()[1])


@pytest.fixture
def servidor():
    """O nosso servidor A2A, no ar, numa porta real."""
    porta = _porta_livre()
    base = f"http://127.0.0.1:{porta}"

    async def run(texto: str) -> str:
        if texto == "exploda":
            raise RuntimeError("o alvo caiu")
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


async def _conversar(base: str, texto: str) -> list:
    import httpx
    from a2a.client import ClientConfig, ClientFactory
    from a2a.types import Message, Part, Role, SendMessageRequest

    async with httpx.AsyncClient() as http:
        fabrica = ClientFactory(ClientConfig(httpx_client=http, streaming=True))
        # `create_from_url` faz a descoberta INTEIRA: busca
        # /.well-known/agent-card.json, lê `supportedInterfaces`, escolhe o
        # binding e monta o transporte. Se o nosso Card divergir, ele falha
        # AQUI — antes de qualquer evento.
        cliente = await fabrica.create_from_url(base)
        pedido = SendMessageRequest(
            message=Message(
                message_id="m1", role=Role.ROLE_USER, parts=[Part(text=texto)]
            )
        )
        return [evento async for evento in cliente.send_message(pedido)]


def test_um_cliente_A2A_de_terceiro_descobre_o_card_e_recebe_os_eventos(servidor):
    from a2a.types import TaskState

    eventos = asyncio.run(_conversar(servidor, "ola"))

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


def test_uma_falha_do_agente_chega_ao_terceiro_como_task_FAILED(servidor):
    """A recusa também precisa ser legível por quem não é nós: uma exceção que
    virasse erro de transporte deixaria o cliente sem resultado E sem razão."""
    from a2a.types import TaskState

    eventos = asyncio.run(_conversar(servidor, "exploda"))
    estados = [
        e.status_update.status.state
        for e in eventos
        if e.WhichOneof("payload") == "status_update"
    ]
    assert TaskState.TASK_STATE_FAILED in estados, estados

    razoes = [
        p.text
        for e in eventos
        if e.WhichOneof("payload") == "status_update"
        and e.status_update.status.HasField("message")
        for p in e.status_update.status.message.parts
    ]
    assert any("o alvo caiu" in r for r in razoes), razoes


def test_o_nosso_call_remote_conversa_com_a_nossa_propria_face_servida(
    servidor, monkeypatch
):
    """As duas pontas, fechando o círculo.

    Prova que as nossas duas metades falam a MESMA versão do protocolo — e é
    uma prova que só vale porque cada metade fala pelo SDK oficial. A versão à
    mão tinha as DUAS erradas do mesmo jeito (`message/send`, da 0.3), então
    elas conversavam perfeitamente entre si e com mais ninguém: um teste como
    este passaria e não significaria nada.

    `_endpoint` é substituído porque ele exige `https://` e o servidor de teste
    é `http://`. Isso é POLÍTICA de URL, não protocolo, e tem teste próprio em
    `test_a2a_transport.py::test_only_https_is_dialed` — aqui o assunto é a
    conversa.
    """
    import dna.application.a2a_transport as transporte
    from dna.application.delegation import DelegationTarget

    alvo = DelegationTarget(
        name="eco",
        kind="RemoteAgent",
        format="text",
        data_scope_kinds=("SourceArtifact",),
        interfaces=(
            {
                "url": f"{servidor}/a2a",
                "protocol_binding": "JSONRPC",
                "protocol_version": "1.0",
            },
        ),
        # O Card do remoto anuncia streaming, e é isso que faz o cliente pedir
        # `SendStreamingMessage`. Sem carregar este fato, a chamada cairia no
        # caminho não-streaming e `on_event` veria UM evento agregado — o
        # progresso morreria em silêncio.
        streaming=True,
    )
    monkeypatch.setattr(transporte, "_endpoint", lambda _alvo: f"{servidor}/a2a")

    vistos: list = []
    texto = asyncio.run(
        transporte.call_remote(
            alvo,
            "ola",
            credential_for=lambda _n: "tok",
            payload_kinds=("SourceArtifact",),
            on_event=vistos.append,
        )
    )

    assert texto == "eco:ola", texto
    assert len(vistos) >= 2, f"o progresso não chegou: {len(vistos)} evento(s)"
