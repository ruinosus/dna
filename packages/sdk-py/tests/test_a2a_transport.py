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
    (Num alvo local `None` significa 'não se aplica'; quem chama aqui só passa
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
