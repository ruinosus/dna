"""E3 — pagination liga o fio (o leitor que o schema citava e nunca existiu)."""
from __future__ import annotations

from dna.memory.policy import PaginationPolicy, resolve_pagination


def test_paridade_sem_doc():
    assert resolve_pagination(None) == PaginationPolicy()
    assert resolve_pagination({}) == PaginationPolicy()


def test_politica_vale_e_a_sanidade_segura():
    p = resolve_pagination({"pagination": {"default_limit": 100, "max_limit": 1000}})
    assert p.default_limit == 100 and p.max_limit == 1000
    # default acima do max é puxado para o max; max acima do teto duro, cortado
    q = resolve_pagination({"pagination": {"default_limit": 900, "max_limit": 200}})
    assert q.default_limit == 200 and q.max_limit == 200
    r = resolve_pagination({"pagination": {"max_limit": 999999}})
    assert r.max_limit == 5000
    # lixo campo a campo cai no default
    s = resolve_pagination({"pagination": {"default_limit": "muitos", "max_limit": 0}})
    assert s == PaginationPolicy()
