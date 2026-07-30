"""A pergunta de PRIVILÉGIO da delegação: o contexto do request sobrevive ao sub-run?

## Por que este arquivo existe

O sub-agente delegado recebe as tools MCP do alvo, e o provedor de credencial
(`mcp_auth`) lê o bearer do usuário de um **contextvar de request**. O host
(dna-cloud) resolve assim:

    return current_request_bearer() or os.environ.get("DNA_MCP_TOKEN", "")

Ou seja: **sem contexto de request, ele cai no token de SERVIÇO** — que existe
para a descoberta de tools no boot, e cujo alcance não é o do usuário.

Se o `graph.ainvoke()` do sub-run rodasse fora do contexto do request, as tools
do agente delegado sairiam com credencial de serviço. E o modo de falha é o pior
possível: **funcionaria**. Ninguém veria erro; o subagente simplesmente agiria com
mais alcance do que a pessoa que pediu.

"Contextvars são copiados para tasks filhas" é semântica de Python e é verdade —
mas a pergunta real é se o LangGraph faz algo que QUEBRE isso (um executor
próprio, um pool de threads sem cópia de contexto, um loop de fundo). Isso não se
responde por raciocínio; responde-se atravessando o `ainvoke` de verdade.

Este teste atravessa. Se ele algum dia falhar, a delegação passou a vazar
privilégio em silêncio.
"""
from __future__ import annotations

import asyncio
import contextvars

import pytest

pytest.importorskip("langchain", reason="a delegação precisa do extra [runtime]")

#: O contextvar que representa o bearer do request, no mesmo shape que o host usa.
_BEARER: contextvars.ContextVar[str] = contextvars.ContextVar("bearer", default="")

#: Onde a tool registra o que ENXERGOU quando foi chamada dentro do sub-run.
_SEEN: list[str] = []


def _tool_that_reads_the_context():
    """Uma tool que faz o que uma tool MCP faria: perguntar a credencial AGORA.

    O ponto é ela ler no momento da CHAMADA, dentro do sub-run — não receber o
    valor por parâmetro, que provaria outra coisa.
    """
    from langchain_core.tools import StructuredTool

    def _read(_ignored: str = "") -> str:
        _SEEN.append(_BEARER.get())
        return "ok"

    return StructuredTool.from_function(
        func=_read, name="read_the_bearer", description="lê o bearer do contexto"
    )


def _model_that_calls_the_tool_once():
    """Um modelo mínimo que chama a tool na primeira volta e encerra na segunda.

    Escrito à mão em vez de usar os fakes do `langchain_core`: eles não
    implementam `bind_tools`, que o `create_agent` chama — e um teste que não
    consegue nem montar o agente não mediria a propagação."""
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    class _CallsToolThenStops(BaseChatModel):
        turns: int = 0

        @property
        def _llm_type(self) -> str:
            return "fake-delegation-target"

        def bind_tools(self, tools, **kwargs):  # noqa: ANN001 — assinatura do framework
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self.turns += 1
            if self.turns == 1:
                msg = AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "read_the_bearer", "args": {"_ignored": ""}, "id": "call-1"}
                    ],
                )
            else:
                msg = AIMessage(content="pronto")
            return ChatResult(generations=[ChatGeneration(message=msg)])

    return _CallsToolThenStops()


async def _run_subagent_like_delegation_does() -> None:
    """O caminho do `run_local`: create_agent + ainvoke com UMA human message."""
    from langchain.agents import create_agent
    from langchain_core.messages import HumanMessage

    graph = create_agent(
        model=_model_that_calls_the_tool_once(),
        tools=[_tool_that_reads_the_context()],
        system_prompt="você é o alvo da delegação",
    )
    await graph.ainvoke({"messages": [HumanMessage(content="faça a coisa")]})


def test_the_request_bearer_SURVIVES_into_the_delegated_sub_run():
    """A medição. Se isto falhar, a delegação vaza privilégio em silêncio.

    Fixamos o contextvar ANTES (como o dependency do FastAPI faz no request), e
    exigimos que a tool, chamada lá dentro pelo `ainvoke` do sub-agente, enxergue
    exatamente o mesmo valor — nunca `""` (que no host viraria o token de
    serviço)."""
    _SEEN.clear()
    _BEARER.set("bearer-do-usuario-real")

    asyncio.run(_run_subagent_like_delegation_does())

    assert _SEEN, "a tool nunca foi chamada — o teste não mediu nada"
    assert _SEEN[0] == "bearer-do-usuario-real", (
        f"o contexto do request NÃO sobreviveu ao sub-run: a tool viu {_SEEN[0]!r}. "
        f"No host isso significa cair no DNA_MCP_TOKEN de serviço — o subagente "
        f"delegado agiria com MAIS alcance que o usuário, e sem erro nenhum."
    )


def test_the_measurement_would_NOTICE_a_lost_context():
    """A prova de que o teste acima mede algo.

    Rodamos o mesmo sub-run a partir de um contexto LIMPO (o que aconteceria se o
    LangGraph descartasse o contexto) e exigimos que a tool veja o default vazio.
    Se este teste falhar, o `_BEARER` está vazando por outro caminho e o teste de
    cima estaria verde por engano."""
    _SEEN.clear()

    def _in_a_fresh_context() -> None:
        asyncio.run(_run_subagent_like_delegation_does())

    ctx = contextvars.Context()
    ctx.run(_in_a_fresh_context)

    assert _SEEN, "a tool nunca foi chamada"
    assert _SEEN[0] == "", (
        f"esperava o default vazio num contexto limpo, vi {_SEEN[0]!r} — o teste "
        f"de propagação acima não estaria provando nada"
    )
