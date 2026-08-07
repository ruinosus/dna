"""O transporte A2A de saída — e as duas regras que o desenho exige.

Um `RemoteAgent` é, por construção, um canal de exfiltração: o DNA manda dado do
workspace para uma URL que o tenant escolheu. As duas regras abaixo são o que
separa isso de um vazamento, e são asseridas — não revisadas a olho.

O transporte em si passou a ser o `Client` do `a2a-sdk`. Por isso os testes que
espiavam um POST à mão saíram: eles asseriam a forma de um envelope que o SDK
agora monta, e o envelope que eles asseriam estava ERRADO — chamava
`message/send`, o nome da A2A 0.3. O que ficou é o que continua sendo nosso: a
ORDEM das recusas, a ausência de um caminho para o bearer do usuário, e a
escolha do último artifact.
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
    interfaces=(
        {
            "url": "https://vendor.example/a2a",
            "protocol_binding": "JSONRPC",
            "protocol_version": "1.0",
        },
    ),
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
    (Num alvo local `None` significa 'não se aplica'; quem chama aqui só passa
    remotos.)"""
    none_scope = DelegationTarget(name="x", kind="RemoteAgent", data_scope_kinds=None)
    assert scope_allows(none_scope, ["SourceArtifact"]) is False


# ── as recusas correm ANTES de o cliente existir ────────────────────────────
#
# A ordem é load-bearing, e é por isso que o dublê aqui EXPLODE em vez de
# gravar: a asserção "não chamou" fica sendo estrutural, e não uma lista vazia
# que alguém pode esquecer de conferir.


def _nunca_disca(monkeypatch):
    import dna.application.a2a_transport as transporte

    def _explode(*a, **kw):  # pragma: no cover — não deve ser alcançado
        raise AssertionError("o transporte foi acionado apesar da recusa")

    monkeypatch.setattr(transporte, "_client_para", _explode)


def test_a_payload_out_of_scope_REFUSES_BEFORE_the_call(monkeypatch):
    """A ordem importa: a checagem tem de ser ANTES do envio, senão o dado já
    saiu quando a recusa acontece."""
    _nunca_disca(monkeypatch)
    with pytest.raises(DelegationRefused, match="fora do data_scope"):
        asyncio.run(
            call_remote(
                _TARGET,
                "leia isto",
                credential_for=lambda _n: "ws-cred-123",
                payload_kinds=("WorkspaceMembership",),
            )
        )


def test_a_missing_credential_REFUSES_instead_of_calling_anonymously(monkeypatch):
    """Chamar sem credencial poderia ser aceito pelo remoto, e é decisão que
    ninguém tomou. Recusa nomeada."""
    _nunca_disca(monkeypatch)
    with pytest.raises(DelegationRefused, match="nenhuma credencial"):
        asyncio.run(
            call_remote(
                _TARGET,
                "leia isto",
                credential_for=lambda _n: None,
                payload_kinds=("SourceArtifact",),
            )
        )


def test_only_https_is_dialed(monkeypatch):
    """O descritor já exige `https://` no schema; o transporte não confia nisso
    e checa de novo — uma instância antigo, ou um schema afrouxado, não deve
    virar texto claro na rede."""
    _nunca_disca(monkeypatch)
    plain = DelegationTarget(
        name="x",
        kind="RemoteAgent",
        data_scope_kinds=("SourceArtifact",),
        interfaces=({"url": "http://vendor.example/a2a", "protocol_binding": "JSONRPC"},),
    )
    with pytest.raises(DelegationRefused):
        asyncio.run(
            call_remote(
                plain,
                "leia isto",
                credential_for=lambda _n: "ws-cred-123",
                payload_kinds=("SourceArtifact",),
            )
        )


# ── regra 2: a credencial nunca é a do usuário ──────────────────────────────


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


# ── o transporte é o Client OFICIAL ─────────────────────────────────────────

pytest.importorskip("a2a", reason="o transporte de saída fala pelo SDK oficial")


class _ClienteFalso:
    """A superfície do `Client` que `call_remote` usa, e nada além dela."""

    def __init__(self, eventos):
        self._eventos = eventos
        self.contexto = None
        self.pedido = None
        self.fechado = False

    async def send_message(self, pedido, *, context=None):
        self.pedido = pedido
        self.contexto = context
        for evento in self._eventos:
            yield evento

    async def close(self):
        self.fechado = True


def _com_cliente(monkeypatch, eventos):
    import dna.application.a2a_transport as transporte

    falso = _ClienteFalso(eventos)
    monkeypatch.setattr(transporte, "_client_para", lambda *a, **kw: falso)
    return falso


def _artifact(texto):
    from a2a.types import Artifact, Part, StreamResponse, TaskArtifactUpdateEvent

    return StreamResponse(
        artifact_update=TaskArtifactUpdateEvent(
            task_id="t1",
            context_id="c1",
            artifact=Artifact(artifact_id="a1", parts=[Part(text=texto)]),
        )
    )


def _progresso():
    from a2a.types import StreamResponse, Task

    return StreamResponse(task=Task(id="t1", context_id="c1"))


def _chamar(monkeypatch, eventos, **kw):
    falso = _com_cliente(monkeypatch, eventos)
    texto = asyncio.run(
        call_remote(
            _TARGET,
            "leia isto",
            credential_for=lambda _n: "ws-cred-123",
            payload_kinds=("SourceArtifact",),
            **kw,
        )
    )
    return texto, falso


def test_o_texto_final_vem_dos_ARTIFACTS_que_o_cliente_oficial_entrega(monkeypatch):
    """Nada de parse de SSE à mão: o `Client` agrega os eventos e entrega
    `StreamResponse`. O que é nosso é escolher o artifact certo."""
    texto, _ = _chamar(monkeypatch, [_progresso(), _artifact("pronto")])
    assert texto == "pronto"


def test_o_ULTIMO_artifact_vence(monkeypatch):
    """Um stream pode reemitir a task com o resultado crescendo; o primeiro
    seria parcial."""
    texto, _ = _chamar(monkeypatch, [_artifact("par"), _artifact("parcial e final")])
    assert texto == "parcial e final"


def test_um_evento_de_PROGRESSO_nao_e_confundido_com_resultado(monkeypatch):
    """Sem artifact algum o retorno é vazio — e não o texto de um evento de
    andamento, que faria "andou" parecer "terminou"."""
    texto, _ = _chamar(monkeypatch, [_progresso()])
    assert texto == ""


def test_on_event_ve_cada_evento_assim_que_chega(monkeypatch):
    """É o que transforma a espera em progresso: sem isso a chamada fica muda
    até o fim, e um alvo de vinte segundos é indistinguível de travado."""
    vistos = []
    _chamar(
        monkeypatch,
        [_progresso(), _artifact("pronto")],
        on_event=vistos.append,
    )
    assert len(vistos) == 2


def test_a_credencial_viaja_no_CONTEXTO_da_chamada_e_nao_num_cliente_compartilhado(
    monkeypatch,
):
    """`service_parameters` é a costura que o próprio SDK usa para credencial
    (`a2a.client.auth.AuthInterceptor` escreve no mesmo lugar). Gravá-la nos
    headers de um cliente HTTP do chamador a vazaria deste remoto para toda
    chamada seguinte feita com ele."""
    _, falso = _chamar(monkeypatch, [_artifact("pronto")])
    assert falso.contexto is not None
    assert falso.contexto.service_parameters == {
        "Authorization": "Bearer ws-cred-123"
    }


def test_o_pedido_sai_como_Message_de_texto_do_SDK(monkeypatch):
    """A `Part` da 1.0 é um `oneof` sem campo `kind` — a versão à mão emitia
    `{"kind": "text", …}`, que um servidor conforme não faz o parse."""
    _, falso = _chamar(monkeypatch, [_artifact("pronto")])
    partes = list(falso.pedido.message.parts)
    assert [p.WhichOneof("content") for p in partes] == ["text"]
    assert partes[0].text == "leia isto"


def test_um_cliente_HTTP_do_CHAMADOR_nao_e_fechado_por_nos(monkeypatch):
    """`Client.close()` fecha o httpx por baixo. Fechar o do chamador o
    quebraria para a chamada seguinte — `dna.runtime.builder` passa o seu."""
    import httpx

    async def _corpo():
        async with httpx.AsyncClient() as http:
            falso = _com_cliente(monkeypatch, [_artifact("pronto")])
            await call_remote(
                _TARGET,
                "leia isto",
                credential_for=lambda _n: "ws-cred-123",
                http=http,
                payload_kinds=("SourceArtifact",),
            )
            return falso.fechado

    assert asyncio.run(_corpo()) is False


def test_o_streaming_declarado_pelo_remoto_chega_ao_alvo():
    """`capabilities.streaming` do Card ingerido tem de sobreviver até o
    `DelegationTarget` — é ele que faz o cliente escolher entre
    `SendStreamingMessage` e `SendMessage`. Perdido no caminho, `on_event`
    continuaria existindo e nunca dispararia, que é a pior forma de quebrar:
    silenciosa."""
    from dna.application.delegation import targets_for

    docs = [
        {
            "kind": "Agent",
            "metadata": {"name": "supervisor"},
            "spec": {"team_members": ["stream-remoto", "mudo-remoto"]},
        },
        {
            "kind": "RemoteAgent",
            "metadata": {"name": "stream-remoto"},
            "spec": {
                "capabilities": {"streaming": True},
                "delegation_target_for": {"agents": ["supervisor"]},
            },
        },
        {
            "kind": "RemoteAgent",
            "metadata": {"name": "mudo-remoto"},
            "spec": {"delegation_target_for": {"agents": ["supervisor"]}},
        },
    ]
    alvos = {t.name: t for t in targets_for("supervisor", docs)}
    assert alvos["stream-remoto"].streaming is True
    # Não declarado é `None`, e não `False`: ausência de declaração não é uma
    # declaração de ausência.
    assert alvos["mudo-remoto"].streaming is None
