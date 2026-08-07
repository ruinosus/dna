"""Bi-temporal invalidation guard (i-046) — never resurrect a superseded memory."""
from __future__ import annotations

from dna.kernel.write.bitemporal_guard import preserve_bitemporal_invalidation


def test_preserves_valid_to_when_incoming_drops_it():
    incoming = {"summary": "x", "surface_count": 0}  # a maintenance re-write
    existing = {"summary": "x", "valid_to": "2026-06-02T00:00:00+00:00",
                "superseded_by_memory": "sem-x"}
    changed = preserve_bitemporal_invalidation(incoming, existing)
    assert changed is True
    assert incoming["valid_to"] == "2026-06-02T00:00:00+00:00"
    assert incoming["superseded_by_memory"] == "sem-x"


def test_noop_when_existing_not_invalidated():
    incoming = {"summary": "x"}
    existing = {"summary": "x"}  # no valid_to
    assert preserve_bitemporal_invalidation(incoming, existing) is False
    assert "valid_to" not in incoming


def test_respects_incoming_valid_to():
    # the consolidation close-out write carries its OWN valid_to — don't override
    incoming = {"valid_to": "2026-07-01T00:00:00+00:00", "superseded_by_memory": "sem-new"}
    existing = {"valid_to": "2026-06-02T00:00:00+00:00", "superseded_by_memory": "sem-old"}
    assert preserve_bitemporal_invalidation(incoming, existing) is False
    assert incoming["valid_to"] == "2026-07-01T00:00:00+00:00"
    assert incoming["superseded_by_memory"] == "sem-new"


def test_none_existing_is_safe():
    incoming = {"summary": "x"}
    assert preserve_bitemporal_invalidation(incoming, None) is False


# ── i-139: a exceção, e ela é DERIVADA do payload ───────────────────────────
#
# O guard existe para que uma invalidação nunca caia no chão. Um revive não a
# deixa cair: ele a ARQUIVA em `spec.revivals`, verbatim e para sempre. Então a
# exceção não é "confie neste chamador" — é "prove que arquivou", e a prova é o
# próprio payload citar o `valid_to` exato que está levantando.
#
# Sem isso o guard tornava a memória ETERNAMENTE irrevivível: a proteção contra
# perder a história virava proteção contra ter história nenhuma.

_VT = "2026-06-02T00:00:00+00:00"


def test_um_revive_que_ARQUIVOU_a_invalidacao_passa():
    incoming = {
        "summary": "x",
        "revivals": [{"valid_to": _VT, "revived_at": "2026-06-09T00:00:00+00:00"}],
    }
    existing = {"summary": "x", "valid_to": _VT, "superseded_by_memory": "sem-x"}
    assert preserve_bitemporal_invalidation(incoming, existing) is False
    assert "valid_to" not in incoming, "o guard ressuscitou a lápide de um revive legítimo"
    assert "superseded_by_memory" not in incoming, (
        "a memória voltaria ao vigor marcada como substituída — meia revivida"
    )


def test_uma_entrada_que_NAO_cita_esta_invalidacao_nao_libera_nada():
    """A asserção que separa "arquivou" de "tem uma lista".

    Um `revivals` com QUALQUER conteúdo liberaria toda memória se a checagem
    fosse pela existência da lista. Aqui a entrada fala de outro esquecimento —
    de um ciclo anterior, ou fabricada — e a invalidação corrente continua de pé.
    """
    incoming = {
        "summary": "x",
        "revivals": [{"valid_to": "2025-01-01T00:00:00+00:00", "revived_at": "x"}],
    }
    existing = {"summary": "x", "valid_to": _VT, "superseded_by_memory": "sem-x"}
    assert preserve_bitemporal_invalidation(incoming, existing) is True
    assert incoming["valid_to"] == _VT


def test_revivals_malformado_nao_e_uma_porta():
    """Fail-CLOSED nesta borda, e é o lado certo: um `revivals` que não é lista
    de dicts não provou nada, e não provar nada tem de resultar em preservar a
    invalidação — nunca em levantá-la porque a estrutura era estranha demais
    para verificar."""
    existing = {"valid_to": _VT}
    for lixo in ("nao-e-lista", 42, [], [None], ["texto"], [{"valid_to": None}], {}):
        incoming = {"summary": "x", "revivals": lixo}
        assert preserve_bitemporal_invalidation(incoming, existing) is True, lixo
        assert incoming["valid_to"] == _VT, lixo


def test_uma_manutencao_que_carrega_revivals_ANTIGO_continua_barrada():
    """O caso que faz a exceção ser segura, e o único que a torna não-trivial.

    Uma memória já revivida uma vez e esquecida DE NOVO carrega `revivals` do
    ciclo anterior. Uma escrita de manutenção sobre ela (decay/cue) traz esse
    histórico junto sem querer reviver nada — e não pode passar. Só passa se
    citar o esquecimento CORRENTE, que uma escrita de manutenção não tem motivo
    para conhecer nem para escrever.
    """
    incoming = {
        "summary": "x",
        "surface_count": 3,  # a marca de uma escrita de manutenção
        "revivals": [{"valid_to": "2026-01-01T00:00:00+00:00",
                      "revived_at": "2026-02-01T00:00:00+00:00"}],
    }
    existing = {
        "summary": "x",
        "valid_to": _VT,  # o esquecimento CORRENTE, posterior àquele ciclo
        "revivals": [{"valid_to": "2026-01-01T00:00:00+00:00",
                      "revived_at": "2026-02-01T00:00:00+00:00"}],
    }
    assert preserve_bitemporal_invalidation(incoming, existing) is True
    assert incoming["valid_to"] == _VT
