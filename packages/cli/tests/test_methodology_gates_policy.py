"""#37 — os gates de metodologia leem a `CognitivePolicy.methodology`.

O leitor atravessa a PORTA do kernel da sessão (`get_doc`) — adapter-agnóstico
(FS/sqlite/Postgres por DNA_SOURCE_URL). Este teste mora na suíte do CLI
porque importa `dna_cli`; na suíte do sdk-py ele quebrou o CI (o job de lá
não instala o CLI — medido em 04/08).
"""

from __future__ import annotations

from dna_cli.sdlc.journey import _gates_da_politica


class _Sessao:
    def __init__(self, doc):
        self._doc = doc

    def get_doc(self, kind, name, **kw):
        assert (kind, name) == ("CognitivePolicy", "cognitive-policy")
        if isinstance(self._doc, Exception):
            raise self._doc
        return self._doc


def test_o_doc_vence():
    ok = _Sessao({"spec": {"methodology": {"auditor_window": 7, "auditor_threshold": 4}}})
    assert _gates_da_politica(ok) == (7, 4)


def test_lixo_e_ausencia_degradam_campo_a_campo():
    parcial = _Sessao({"spec": {"methodology": {"auditor_window": 99}}})
    assert _gates_da_politica(parcial) == (5, 3)
    assert _gates_da_politica(_Sessao(None)) == (5, 3)
    assert _gates_da_politica(_Sessao(RuntimeError("sem kernel"))) == (5, 3)
