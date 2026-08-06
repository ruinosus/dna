"""O executor de `delegate_to` — o caminho local, e as recusas.

`delegate_to` estava declarado no kernel desde antes desta feature e NUNCA teve
implementação: aparecia só em `models.py`. Capacidade existe, porta não. Isto é a
porta.

O que se pina aqui é sobretudo RECUSA. Um executor que despacha o caminho felizo
e falha aberto na autorização é pior que nenhum — e as recusas são o que a
política (Task 2) existe para decidir.
"""
from __future__ import annotations

import asyncio

import pytest

from dna.application.delegation_exec import (
    DelegationRefused,
    delegate,
    parse_result,
)


def _docs(team=("conv",), accepts=("supervisor",), fmt="text"):
    return [
        {
            "kind": "Agent",
            "metadata": {"name": "supervisor"},
            "spec": {"team_members": list(team)},
        },
        {
            "kind": "Agent",
            "metadata": {"name": "conv"},
            "spec": {
                "instruction": "…",
                "delegation_target_for": {"agents": list(accepts), "format": fmt},
            },
        },
    ]


def _run(**kw):
    async def _local(name, request):
        return f"feito por {name}: {request}"

    async def _remote(target, request):  # pragma: no cover — não usado aqui
        raise AssertionError("o caminho remoto não deve ser tocado por alvo local")

    kw.setdefault("run_local", _local)
    kw.setdefault("call_remote", _remote)
    return asyncio.run(delegate(**kw))


def test_a_local_delegation_runs_and_returns():
    out = _run(
        delegator="supervisor",
        target_name="conv",
        request="converta isto",
        instances=_docs(),
    )
    assert "feito por conv" in out["result"]
    assert out["target"] == "conv"


def test_an_unlisted_target_is_REFUSED_by_name():
    """A recusa carrega o motivo. Silêncio aqui seria a pior falha possível: o
    delegador narraria sucesso sobre trabalho que ninguém fez."""
    with pytest.raises(DelegationRefused) as exc:
        _run(
            delegator="supervisor",
            target_name="conv",
            request="x",
            instances=_docs(team=()),
        )
    assert "conv" in str(exc.value)


def test_a_target_that_does_not_accept_us_is_REFUSED():
    with pytest.raises(DelegationRefused):
        _run(
            delegator="supervisor",
            target_name="conv",
            request="x",
            instances=_docs(accepts=("jarvis",)),
        )


def test_an_unknown_target_is_REFUSED_not_silently_skipped():
    with pytest.raises(DelegationRefused):
        _run(
            delegator="supervisor",
            target_name="nao-existe",
            request="x",
            instances=_docs(),
        )


def test_the_local_path_never_calls_the_remote_transport():
    """Pinado porque o inverso — um alvo local vazando pela rede — seria
    exfiltração silenciosa. O dublê remoto do módulo levanta se tocado."""
    out = _run(
        delegator="supervisor", target_name="conv", request="x", instances=_docs()
    )
    assert out["transport"] == "local"


# ── o parse por `format` ────────────────────────────────────────────────────


def test_text_is_returned_as_is():
    assert parse_result("text", "narrativa livre") == "narrativa livre"


def test_json_is_parsed():
    assert parse_result("json", '{"a": 1}') == {"a": 1}


def test_malformed_json_is_REFUSED_not_returned_as_text():
    """Cair para texto esconderia um alvo que quebrou o contrato que ELE
    declarou. O delegador tem de saber."""
    with pytest.raises(DelegationRefused):
        parse_result("json", "isto nao e json")


def test_slug_takes_the_last_nonempty_line():
    assert parse_result("slug", "criando…\ns-nota-fiscal-001\n") == "s-nota-fiscal-001"


def test_an_unknown_format_is_REFUSED():
    with pytest.raises(DelegationRefused):
        parse_result("xml", "<a/>")
