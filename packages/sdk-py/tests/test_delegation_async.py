"""O terceiro transporte: enfileirar em vez de rodar, quando o alvo é longo.

## Por que isto existe

Hoje uma delegação roda **dentro do request**. Uma conversão de PDF segura a
conexão inteira — e, se a aba fechar, o disconnect do cliente aborta o stream e o
**trabalho é descartado**, não apenas invisível.

O executor já despacha por transporte injetado (`run_local` para alvo local,
`call_remote` para `RemoteAgent`). O assíncrono é o **terceiro**: `enqueue`.

## O gatilho não é uma lista

Quem decide é o próprio alvo, pelo `typical_seconds` que ele **já declara** no
bloco `delegation_target_for` do kernel. Não existe lista de "jobs longos" para
alguém manter — toda lista mantida à mão neste projeto ficou cega e verde.

## As duas degradações, que são decisões e não descuidos

1. **Alvo sem `typical_seconds` → síncrono.** Ausência de declaração não vira
   "provavelmente longo". Na dúvida, o caminho conhecido.
2. **Sem `enqueue` + alvo longo → síncrono.** Um deployment que não tem worker
   continua funcionando exatamente como hoje. Degradação, nunca quebra.
"""
from __future__ import annotations

import asyncio

import pytest

from dna.application.delegation_exec import DelegationRefused, delegate

_THRESHOLD = 30


def _docs(typical_seconds=None, accepts=("sup",)):
    """Um supervisor e um alvo local que declara (ou não) `typical_seconds`."""
    block: dict = {"agents": list(accepts), "format": "text"}
    if typical_seconds is not None:
        block["typical_seconds"] = typical_seconds
    return [
        {"kind": "Agent", "metadata": {"name": "sup"}, "spec": {"team_members": ["conv"]}},
        {
            "kind": "Agent",
            "metadata": {"name": "conv"},
            "spec": {"instruction": "…", "delegation_target_for": block},
        },
    ]


def _run(docs, *, with_enqueue=True, target_name="conv"):
    """Executa a delegação com dublês que REGISTRAM qual transporte foi tocado."""
    touched: list[str] = []

    async def run_local(name, request):
        touched.append("local")
        return "rodou in-process"

    async def call_remote(target, request):  # pragma: no cover — alvo local
        touched.append("a2a")
        raise AssertionError("o transporte remoto não deve ser tocado por alvo local")

    async def enqueue(target, request):
        touched.append("queued")
        return "run-abc123"

    kw = dict(
        delegator="sup",
        target_name=target_name,
        request="converta isto",
        instances=docs,
        run_local=run_local,
        call_remote=call_remote,
    )
    if with_enqueue:
        kw["enqueue"] = enqueue
    out = asyncio.run(delegate(**kw))
    return out, touched


# ── o gatilho ───────────────────────────────────────────────────────────────


def test_a_long_target_is_QUEUED_and_never_runs_in_process():
    """A propriedade central. Acima do limiar, o job sai do request.

    Se `run_local` for tocado aqui, a conversão voltou a segurar a conexão — e o
    trabalho volta a morrer com a aba."""
    out, touched = _run(_docs(typical_seconds=120))
    assert touched == ["queued"]
    assert out["transport"] == "queued"
    assert out["run_id"] == "run-abc123"


def test_a_short_target_still_runs_in_process():
    """Abaixo do limiar nada muda. O chat segue síncrono — decisão travada."""
    out, touched = _run(_docs(typical_seconds=5))
    assert touched == ["local"]
    assert out["transport"] == "local"


def test_a_target_that_declares_NOTHING_stays_synchronous():
    """Ausência de declaração não vira 'provavelmente longo'.

    Inverter isto (tratar `None` como longo) mandaria para a fila todo alvo que
    simplesmente não se descreveu — inclusive os rápidos, que passariam a exigir
    um worker para responder."""
    out, touched = _run(_docs(typical_seconds=None))
    assert touched == ["local"]
    assert out["transport"] == "local"


def test_the_threshold_boundary_is_not_long():
    """Exatamente no limiar é síncrono — `>` e não `>=`.

    Pinado porque o limite é arbitrário e um dia alguém vai mexer nele; que mexa
    sabendo de que lado a borda cai."""
    out, touched = _run(_docs(typical_seconds=_THRESHOLD))
    assert touched == ["local"]


# ── as degradações ──────────────────────────────────────────────────────────


def test_without_an_enqueue_a_long_target_runs_SYNCHRONOUSLY_instead_of_refusing():
    """Um deployment sem worker continua funcionando como hoje.

    Recusar aqui seria transformar 'não temos fila ainda' em 'a feature quebrou'
    — degradação é a resposta certa quando o caminho antigo ainda existe e
    funciona."""
    out, touched = _run(_docs(typical_seconds=120), with_enqueue=False)
    assert touched == ["local"]
    assert out["transport"] == "local"


# ── o que NÃO muda ──────────────────────────────────────────────────────────


def test_an_unauthorized_target_is_REFUSED_BEFORE_any_transport():
    """A política decide antes de qualquer transporte, o assíncrono inclusive.

    Enfileirar sem autorização seria pior que rodar sem autorização: fica
    GRAVADO, e roda depois, quando ninguém está olhando."""
    docs = _docs(typical_seconds=120, accepts=("outro-delegador",))
    with pytest.raises(DelegationRefused):
        _run(docs)


def test_an_unknown_target_is_refused_even_when_a_queue_exists():
    with pytest.raises(DelegationRefused):
        _run(_docs(typical_seconds=120), target_name="nao-existe")


def test_the_queued_answer_does_NOT_pretend_to_have_a_result():
    """Não há resultado ainda — então não há o que parsear.

    Passar o `run_id` por `parse_result` com `format=json` levantaria; com
    `format=slug` devolveria o id disfarçado de resultado. As duas seriam mentira
    sobre um trabalho que nem começou."""
    docs = [
        {"kind": "Agent", "metadata": {"name": "sup"}, "spec": {"team_members": ["conv"]}},
        {
            "kind": "Agent",
            "metadata": {"name": "conv"},
            "spec": {
                "delegation_target_for": {
                    "agents": ["sup"],
                    "format": "json",  # exigiria JSON válido se fosse parseado
                    "typical_seconds": 120,
                }
            },
        },
    ]
    out, touched = _run(docs)
    assert touched == ["queued"]
    assert "result" not in out, "um Run enfileirado não tem resultado para relatar"
    assert out["run_id"] == "run-abc123"


# ── a costura de ponta a ponta ──────────────────────────────────────────────
#
# Estes dois testes existem porque o buraco EXISTIU: o `delegate()` aceitava
# `enqueue` desde o release 0.40.0, e nem `make_delegate_tool` nem o `builder` o
# repassavam — o host não tinha por onde injetar. Parâmetro sem caminho até ele é
# o mesmo padrão que esta feature inteira nasceu para consertar, e ele reapareceu
# DENTRO dela pela terceira vez.
#
# O que faltava não era código: era um teste que atravessasse a costura em vez de
# verificar cada ponta isoladamente.


def test_make_delegate_tool_PASSES_the_enqueue_through():
    """Da fábrica da tool até o `delegate()`. Sem isto, o host injeta e nada usa."""
    from dna.application.delegation_tool import make_delegate_tool

    tocado: list[str] = []

    async def run_local(name, request):
        tocado.append("local")
        return "in-process"

    async def call_remote(target, request):  # pragma: no cover
        raise AssertionError("alvo local não deve tocar a rede")

    async def enqueue(target, request):
        tocado.append("queued")
        return "run-do-host"

    tool = make_delegate_tool(
        delegator="sup",
        instances=_docs(typical_seconds=120),
        run_local=run_local,
        call_remote=call_remote,
        enqueue=enqueue,
    )
    out = asyncio.run(tool.coroutine(target="conv", task="converta"))
    assert tocado == ["queued"], f"o enqueue não chegou ao delegate() — tocou {tocado}"
    assert "run-do-host" in str(out)


def test_the_builder_reads_the_enqueue_from_the_host_extension():
    """O nome da extensão é contrato entre SDK e host — se ele mudar de um lado
    só, a fila para de ser alimentada e NADA dá erro: o alvo longo volta a rodar
    in-process, que é exatamente a degradação silenciosa."""
    import inspect

    from dna.runtime import builder

    fonte = inspect.getsource(builder)
    assert "delegation_enqueue" in fonte, (
        "o builder não lê a extensão `delegation_enqueue` — o host não tem por "
        "onde fornecer a fila"
    )
    assert "enqueue=" in fonte, "o builder não repassa o enqueue à tool"
