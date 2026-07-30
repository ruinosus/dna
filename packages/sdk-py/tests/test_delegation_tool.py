"""`delegate_to` — a StructuredTool wrapping `dna.application.delegation_exec.delegate()`.

`delegate()` existe, é testado (`test_delegation_exec_local.py`), e está
publicado — e é INALCANÇÁVEL: não é tool de agente algum. Este arquivo prova
as sete propriedades da Peça A do plano
`docs/superpowers/plans/2026-07-30-close-the-two-doors-plan.md`, contra o
padrão de mercado citado ali (subagents da LangChain, recomendação vigente
desde março/2026): alvo por NOME, tarefa como HUMAN MESSAGE, retorno como
RESUMO (não transcript), isolamento de contexto (o sub-run não recebe o
histórico do delegador).

A política de autorização (`dna.application.delegation`) não é retestada
aqui — já tem `test_delegation_policy.py` e `test_delegation_exec_local.py`.
O que se prova aqui é que a TOOL não engole nem contorna nada disso.
"""
from __future__ import annotations

import asyncio

from dna.application.delegation_tool import TOOL_NAME, make_delegate_tool


def _docs(team=("conv",), accepts=("supervisor",), fmt="text", use_when="quando precisar converter"):
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
                "delegation_target_for": {
                    "agents": list(accepts),
                    "format": fmt,
                    "use_when": use_when,
                },
            },
        },
    ]


def _remote_doc(accepts=("supervisor",)):
    return {
        "kind": "RemoteAgent",
        "metadata": {"name": "far"},
        "spec": {"delegation_target_for": {"agents": list(accepts), "format": "text"}},
    }


async def _never_local(name, request):  # pragma: no cover — não deve ser tocado
    raise AssertionError("run_local não deve ser tocado por um alvo remoto")


async def _never_remote(target, request):  # pragma: no cover — não deve ser tocado
    raise AssertionError(
        "o dublê remoto levanta se tocado — um alvo local nunca toca a rede"
    )


def _run(tool, target, task):
    return asyncio.run(tool.ainvoke({"target": target, "task": task}))


# ── 1. nome + descrição lista alvos com use_when ────────────────────────────


def test_the_tool_is_named_delegate_to():
    tool = make_delegate_tool(
        delegator="supervisor",
        documents=_docs(),
        run_local=_never_local,
        call_remote=_never_remote,
    )
    assert tool.name == TOOL_NAME == "delegate_to"


def test_the_description_lists_available_targets_with_their_use_when():
    tool = make_delegate_tool(
        delegator="supervisor",
        documents=_docs(use_when="quando precisar converter algo"),
        run_local=_never_local,
        call_remote=_never_remote,
    )
    assert "conv" in tool.description
    assert "quando precisar converter algo" in tool.description


def test_a_target_missing_use_when_is_still_listed_not_dropped():
    tool = make_delegate_tool(
        delegator="supervisor",
        documents=_docs(use_when=None),
        run_local=_never_local,
        call_remote=_never_remote,
    )
    assert "conv" in tool.description


def test_a_delegator_with_no_targets_gets_a_description_that_says_so():
    tool = make_delegate_tool(
        delegator="supervisor",
        documents=_docs(team=()),
        run_local=_never_local,
        call_remote=_never_remote,
    )
    assert "no target" in tool.description.lower() or "nenhum" in tool.description.lower()


# ── 2. alvo fora do roster é recusado, com razão + lista de alvos válidos ──


def test_an_out_of_roster_target_is_refused_naming_the_reason_and_valid_targets():
    tool = make_delegate_tool(
        delegator="supervisor",
        documents=_docs(),
        run_local=_never_local,
        call_remote=_never_remote,
    )
    out = _run(tool, "nao-existe", "faça algo")
    assert "nao-existe" in out
    assert "conv" in out  # a lista de alvos válidos aparece na recusa


def test_the_refusal_is_a_returned_string_not_a_raised_exception():
    """O supervisor precisa RECEBER a recusa como tool result para poder
    narrá-la — uma exceção crua que derruba o turno seria pior que a recusa
    (o próprio ponto do padrão "recusa nomeada, nunca silêncio")."""
    tool = make_delegate_tool(
        delegator="supervisor",
        documents=_docs(),
        run_local=_never_local,
        call_remote=_never_remote,
    )
    out = _run(tool, "nao-existe", "x")
    assert isinstance(out, str)


# ── 3. a tarefa chega ao subagente como human message, não concatenada ────


def test_the_task_reaches_run_local_verbatim_as_the_request_arg():
    captured = {}

    async def _local(name, request):
        captured["name"] = name
        captured["request"] = request
        return "ok"

    tool = make_delegate_tool(
        delegator="supervisor", documents=_docs(), run_local=_local, call_remote=_never_remote,
    )
    _run(tool, "conv", "converta este documento")
    assert captured["name"] == "conv"
    assert captured["request"] == "converta este documento"


# ── 4. o retorno é o resumo, não o transcript ───────────────────────────────


def test_the_return_is_the_short_summary_run_local_reduced_to():
    """Um `run_local` bem-comportado já reduziu uma conversa de dez mensagens
    a uma string curta antes de devolver — o transcript inteiro que ele viu
    por dentro nunca deve aparecer na saída da tool."""
    transcript_lines = [f"mensagem intermediária número {i} do subagente" for i in range(9)]
    final_summary = "feito: documento convertido"

    async def _local(name, request):
        _ = transcript_lines  # nunca sai da função — simula o sub-run isolado
        return final_summary

    tool = make_delegate_tool(
        delegator="supervisor", documents=_docs(), run_local=_local, call_remote=_never_remote,
    )
    out = _run(tool, "conv", "converta isto")
    assert out == final_summary
    for line in transcript_lines:
        assert line not in out


# ── 5. isolamento de contexto: nada do histórico do pai atravessa ──────────


def test_run_local_receives_only_target_name_and_task_nothing_else():
    """Não há parâmetro em `make_delegate_tool` por onde uma mensagem do
    delegador entraria — provamos isso capturando TODOS os args que
    `run_local` recebe e confirmando que são exatamente (target_name, task)."""
    received = {}

    async def _local(*args, **kwargs):
        received["args"] = args
        received["kwargs"] = kwargs
        return "ok"

    tool = make_delegate_tool(
        delegator="supervisor", documents=_docs(), run_local=_local, call_remote=_never_remote,
    )
    _run(tool, "conv", "tarefa isolada")
    assert received["args"] == ("conv", "tarefa isolada")
    assert received["kwargs"] == {}


# ── 6. o transporte é escolhido pelo Kind do alvo ───────────────────────────


def test_a_local_agent_target_uses_run_local_and_never_touches_the_network():
    async def _local(name, request):
        return f"feito por {name}"

    tool = make_delegate_tool(
        delegator="supervisor", documents=_docs(), run_local=_local, call_remote=_never_remote,
    )
    out = _run(tool, "conv", "x")
    assert "feito por conv" in out


def test_a_remote_agent_target_uses_call_remote():
    async def _remote(target, request):
        assert target.name == "far"
        return "feito remotamente"

    docs = [_docs(team=("conv", "far"))[0], _remote_doc()]
    tool = make_delegate_tool(
        delegator="supervisor", documents=docs, run_local=_never_local, call_remote=_remote,
    )
    out = _run(tool, "far", "x")
    assert out == "feito remotamente"


def test_credential_for_completes_a_call_remote_that_still_expects_it():
    """`credential_for` é o param opcional do plano: quando `call_remote`
    ainda espera essa keyword (o formato de `a2a_transport.call_remote`
    depois de `http` já ligado), `make_delegate_tool` a injeta."""

    async def _remote(target, request, *, credential_for):
        return f"cred={credential_for(target.name)}"

    docs = [_docs(team=("conv", "far"))[0], _remote_doc()]
    tool = make_delegate_tool(
        delegator="supervisor",
        documents=docs,
        run_local=_never_local,
        call_remote=_remote,
        credential_for=lambda name: f"token-for-{name}",
    )
    out = _run(tool, "far", "x")
    assert out == "cred=token-for-far"


# ── 7. exceção do subagente vira recusa nomeada, nunca crua ─────────────────


def test_a_crashing_subagent_becomes_a_named_refusal_not_a_raw_exception():
    async def _local(name, request):
        raise RuntimeError("modelo indisponível")

    tool = make_delegate_tool(
        delegator="supervisor", documents=_docs(), run_local=_local, call_remote=_never_remote,
    )
    out = _run(tool, "conv", "x")
    assert isinstance(out, str)
    assert "modelo indisponível" in out
    assert "conv" in out
