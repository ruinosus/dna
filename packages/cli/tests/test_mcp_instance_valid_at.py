"""``get_instance(valid_at=…)`` over MCP — the OTHER time axis, through the door.

The sibling of ``test_mcp_instance_as_of``, and it exists for the same reason
that one does: **a parameter that is accepted must CHANGE the answer or
REFUSE — never both silently.** That is the i-106 rule, and this file applies
it to a parameter that was added the day the column was, so it never gets the
chance to be accepted-and-ignored.

The two axes and why they are two parameters:

    ``as_of``      TRANSACTION time — *what did this store BELIEVE at T*
                   (``dna_versions.created_at``)
    ``valid_at``   WORLD time — *was the fact TRUE at T*
                   (``dna_instances.valid_at``, a ``tstzrange``)

A note written today about last year is valid last year and believed today.
One parameter serving both would make that distinction unstateable, which is
the classic bitemporal mistake.

⚠️ **What this suite can prove without a Postgres**, and it is deliberately the
half that matters most here: the world-time column exists on ONE dialect, so
every store this suite can reach — the filesystem, and SQLite — must REFUSE.
The refusal is the contract; the answer is the easy part, and it is proved
against a real Postgres in ``packages/sdk-py/tests/test_valid_time_axis.py``.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"


def _mcp(args, **build):
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, **build)

    async def go():
        async with Client(server) as client:
            return await client.call_tool("get_instance", args)

    return asyncio.run(go()).structured_content


def _mcp_refused(args, **build) -> str:
    with pytest.raises(Exception) as ei:  # noqa: PT011 — FastMCP ToolError
        _mcp(args, **build)
    return str(ei.value)


@pytest.fixture
def fs_dir(tmp_path, monkeypatch):
    """The filesystem store — no world-time column, and no table to put one in."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")
    return dst


def test_the_tool_ACCEPTS_valid_at_at_all(fs_dir):
    """Mutante: não repassar ``valid_at`` de ``get_instance`` para
    ``get_instance_impl``.

    É literalmente a i-106: o parâmetro fica no schema da tool, o cliente o
    manda, e a resposta é a instância VIVA sob um carimbo de tempo — 200 com
    nada no corpo que desminta. Aqui o sinal de que ele CHEGOU é a recusa; uma
    resposta de sucesso neste store prova que foi descartado."""
    msg = _mcp_refused({"kind": "Tool", "name": "ping",
                        "valid_at": "2026-01-01T00:00:00Z"})
    assert "ValidTimeUnsupported" in msg, (
        "o parâmetro foi aceito e ignorado — o defeito da i-106, na outra face"
    )


def test_the_refusal_arrives_NAMED_not_as_a_crash(fs_dir):
    """Mutante: tirar ``CapabilityRefusal`` das bases de
    ``ValidTimeUnsupported``.

    A face captura a FAMÍLIA, não o nome; sem a base, esta recusa documentada
    chegaria ao cliente como ``Error calling tool 'get_instance'`` — a mesma
    falha que criou a base (``recall(as_of=…)``). O teste pede o nome do tipo
    na mensagem porque sobre MCP não há status code: o nome É o 501."""
    msg = _mcp_refused({"kind": "Tool", "name": "ping",
                        "valid_at": "2026-01-01T00:00:00Z"})
    assert "ValidTimeUnsupported:" in msg
    assert "dna_instances.valid_at" in msg, (
        "a recusa tem de dizer o que falta no DEPLOY — o remédio é outro "
        "adapter, e uma mensagem sem isso manda o chamador procurar permissão"
    )


def test_a_typo_is_the_CALLERS_mistake_and_is_told_apart_from_the_refusal(fs_dir):
    """Mutante: consultar a capability ANTES de normalizar o instante.

    Um ``valid_at`` inválido passaria a ser relatado como "este deploy não sabe
    ler tempo de mundo" — e o chamador iria trocar de adapter para consertar um
    erro de digitação. A ORDEM é a asserção."""
    msg = _mcp_refused({"kind": "Tool", "name": "ping",
                        "valid_at": "ontem à tarde"})
    assert "ValueError" in msg
    assert "ValidTimeUnsupported" not in msg


def test_as_of_and_valid_at_TOGETHER_are_refused_as_the_faces_own_gap(fs_dir):
    """Mutante: aplicar um dos dois eixos e ignorar o outro.

    A interseção bitemporal de verdade — *o que a loja acreditava em T1 sobre o
    que era verdade em T2* — precisa da janela de validade nas linhas de
    VERSÃO, e ``dna_versions`` não a tem. Responder pelo eixo que calhou de ser
    checado primeiro devolve a resposta de uma pergunta que ninguém fez, na
    forma de uma que fizeram. E é ``ValueError`` e não ``ValidTimeUnsupported``
    de propósito: é uma afirmação sobre o que ESTA face implementa, não sobre o
    deploy — trocar de adapter não resolveria."""
    msg = _mcp_refused({"kind": "Tool", "name": "ping",
                        "as_of": "2026-01-01T00:00:00Z",
                        "valid_at": "2026-01-01T00:00:00Z"})
    assert "ValueError" in msg
    assert "DIFFERENT time axes" in msg


def test_without_valid_at_the_live_read_is_UNTOUCHED(fs_dir):
    """Mutante: rotear todo ``get_instance`` pelo caminho de tempo de mundo.

    O caminho vivo é o que 100% das chamadas de hoje usam; um eixo novo que o
    atravessasse cobraria a recusa de quem não pediu nada. A ausência do
    parâmetro tem de deixar a porta exatamente como estava."""
    out = _mcp({"kind": "Tool", "name": "ping"})
    assert out["instance"]["metadata"]["name"] == "ping"
    assert "valid_at" not in out, (
        "uma leitura VIVA não pode carregar o eco de um eixo que ninguém pediu"
    )
