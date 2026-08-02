"""A trilha de aprovação — a forma do registro e a regra que fecha.

Puro: nada aqui grava. O que se exercita é a decisão sobre uma estrutura de
dados, que é justamente a parte que um teste contra o banco não alcança nos
casos difíceis.
"""
from __future__ import annotations

import json

from dna.runtime.audit import (
    DECISIONS,
    ApprovalRecord,
    records_from_request,
    settle,
)

PEDIDO = {
    "action_requests": [
        {"name": "remember", "args": {"text": "o contrato vence em março"}},
        {"name": "forget", "args": {"name": "engram-7"}},
    ]
}


def _pedidos(**kw):
    kw.setdefault("ids", ["a-1", "a-2"])
    kw.setdefault("requested_at", "2026-08-02T18:00:00+00:00")
    return records_from_request(PEDIDO, **kw)


# ── a forma ─────────────────────────────────────────────────────────────────


def test_uma_linha_por_ACAO_e_nao_por_interrupcao():
    """⚠️ O middleware pode gatear várias tools numa tacada, e a decisão é
    POSICIONAL. Uma linha só perderia qual argumento pertence a qual aprovação —
    e é exatamente isso que uma auditoria precisa saber."""
    assert [r.tool for r in _pedidos()] == ["remember", "forget"]


def test_os_argumentos_ficam_INTEGROS():
    """Sem truncar, ao contrário da telemetria. É o que foi autorizado: um corte
    tornaria a trilha incapaz de responder à única pergunta que ela existe para
    responder."""
    grande = {"texto": "x" * 50_000}
    [reg] = records_from_request(
        {"action_requests": [{"name": "remember", "args": grande}]},
        ids=["a-1"], requested_at="t",
    )
    assert json.loads(reg.arguments)["texto"] == grande["texto"]
    assert "truncado" not in reg.arguments


def test_o_EMAIL_vive_AO_LADO_do_oid_e_nao_no_lugar():
    """`oid` identifica a conta e não muda; e-mail identifica o humano e muda.
    Guardar só um dos dois perde uma das duas perguntas."""
    [reg, _] = _pedidos(oid="user_1", actor_email="barna@exemplo.com")
    assert (reg.oid, reg.actor_email) == ("user_1", "barna@exemplo.com")


def test_formato_inesperado_devolve_VAZIO_e_nao_uma_linha_fantasma():
    """Vazio é "nada a registrar"; uma linha inventada seria pior que o silêncio,
    porque entraria na trilha como fato."""
    assert records_from_request(None, ids=[], requested_at="t") == []
    assert records_from_request({"outra": "coisa"}, ids=[], requested_at="t") == []
    assert records_from_request({"action_requests": "nao-e-lista"}, ids=[], requested_at="t") == []


# ── o casamento com a decisão ───────────────────────────────────────────────


def test_a_decisao_casa_POSICIONALMENTE():
    """Casar por nome de tool pareceria mais seguro e seria PIOR: duas chamadas
    da mesma tool numa interrupção ficariam ambíguas — e a ambiguidade cairia
    justamente no caso em que a trilha mais importa."""
    fechados = settle(
        _pedidos(),
        [{"type": "approve"}, {"type": "reject", "message": "não quero"}],
        decided_at="2026-08-02T18:00:05+00:00",
    )
    assert [(r.tool, r.decision) for r in fechados] == [
        ("remember", "approve"), ("forget", "reject")
    ]
    assert fechados[1].reason == "não quero"


def test_a_RECUSA_tambem_entra_na_trilha():
    """Uma trilha que só registra o "sim" não responde "por que isto não foi
    feito?" — que é metade do que uma auditoria pergunta."""
    [reg, _] = settle(_pedidos(), [{"type": "reject"}, {"type": "reject"}],
                      decided_at="t")
    assert reg.decision == "reject"
    assert reg.decided_at == "t"


def test_uma_EDICAO_guarda_o_que_foi_editado():
    """Aprovar algo diferente do que foi pedido é o caso mais interessante da
    trilha, e o único em que o pedido original sozinho mente."""
    [reg, _] = settle(
        _pedidos(),
        [{"type": "edit", "edited_action": {"name": "remember", "args": {"text": "corrigido"}}},
         {"type": "approve"}],
        decided_at="t",
    )
    assert reg.decision == "edit"
    assert "corrigido" in reg.edited_args
    assert "março" in reg.arguments, "perdeu o pedido ORIGINAL"


def test_decisao_DESCONHECIDA_vira_recusa_com_o_motivo():
    """⚠️ O default FECHA. Um tipo que a trilha não sabe nomear tratado como
    aprovação registraria consentimento que ninguém deu."""
    [reg, _] = settle(_pedidos(), [{"type": "talvez"}, {"type": "approve"}],
                      decided_at="t")
    assert reg.decision == "reject"
    assert "talvez" in reg.reason


def test_decisao_AUSENTE_vira_recusa():
    """Menos decisões que pedidos: o que sobrou não foi aprovado."""
    [_, segundo] = settle(_pedidos(), [{"type": "approve"}], decided_at="t")
    assert segundo.decision == "reject"


def test_o_vocabulario_e_FECHADO():
    """Um nome livre transformaria a coluna num campo de texto qualquer, e
    "quantas aprovações houve?" viraria uma pergunta sem resposta."""
    assert DECISIONS == {"approve", "reject", "edit", "respond"}


def test_o_registro_e_IMUTAVEL():
    """Append-only: uma decisão não se edita, se sucede. A imutabilidade fecha o
    caminho de alguém "corrigir" a trilha em memória antes de gravar."""
    reg = ApprovalRecord(approval_id="a", tool="t", arguments="{}")
    try:
        reg.decision = "approve"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("o registro aceitou ser alterado")
