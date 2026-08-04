"""E2 do épico das nove seções — decay e paleta ALCANÇAM o scoring.

O que se prende: os resolvers puros (campo a campo com fallback), e a
paridade — sem doc, o comportamento é byte-igual ao de antes (o risco nomeado
na spec)."""
from __future__ import annotations

from dna.memory.decay import affect_factor
from dna.memory.policy import (
    DecayPolicy,
    resolve_affect_palette,
    resolve_decay_policy,
)


def test_decay_resolve_campo_a_campo_com_fallback():
    p = resolve_decay_policy({
        "decay": {"stability_tiers": {"faint": 2.0, "firm": "lixo"},
                   "max_stability_days": 90}
    })
    base = DecayPolicy()
    assert p.tier_faint == 2.0
    assert p.tier_firm == base.tier_firm          # lixo → default
    assert p.tier_burning == base.tier_burning    # ausente → default
    assert p.max_stability_days == 90.0


def test_paridade_sem_doc():
    assert resolve_decay_policy(None) == DecayPolicy()
    assert resolve_decay_policy({}) == DecayPolicy()
    assert resolve_affect_palette(None) is None
    assert resolve_affect_palette({"affect": {"palette": []}}) is None


def test_paleta_do_tenant_vence_os_builtins():
    palette = resolve_affect_palette({
        "affect": {"palette": [{"id": "urgent", "affect_weight": 1.7}]}
    })
    assert palette is not None
    # O tom PRÓPRIO do workspace resiste ao esquecimento com o peso dele —
    # antes de E2, a paleta era literalmente inalcançável (verbs sem o arg).
    assert affect_factor("urgent", palette) == 1.7
    # Tom desconhecido continua neutro, nunca derrubado.
    assert affect_factor("inexistente", palette) == 1.0
