"""Spike 0A experiment — does Agno `external_execution` fire on an MCPTools tool?

Two scenarios, both driven by a DETERMINISTIC stub model (no LLM/gateway needed —
the stub emits an OpenAI-style tool_call for `remember`, then a final text on resume):

  SCENARIO A (YES hypothesis): gate the REMOTE MCP tool directly via
      MCPTools(..., external_execution_required_tools=["remember"]).
      Prove: run pauses, tools_awaiting_external_execution == ["remember"], and
      acontinue_run resumes + the underlying MCP write runs (remembered.log grows).

  SCENARIO B (NO fallback): a LOCAL @tool(external_execution=True) remember_wrapper
      whose body calls the MCP remember. Prove the wrapper pauses + resumes.

Both use the aap-kb reference accessor: agent.get_last_run_output(session_id=...).
"""
from __future__ import annotations

import asyncio
import json
import pathlib
from typing import Any, Optional
from uuid import uuid4

from agno.agent import Agent
from agno.db.in_memory import InMemoryDb
from agno.models.base import Model
from agno.models.message import Message
from agno.models.response import ModelResponse
from agno.run.base import RunStatus
from agno.tools.mcp.mcp import MCPTools

MCP_URL = "http://127.0.0.1:8199/mcp"
LOG = pathlib.Path(__file__).parent / "remembered.log"


class StubModel(Model):
    """Deterministic model: 1st assistant turn calls `tool_name`, then returns final text.

    Overrides the 4 abstract provider hooks + parse. The agent's run loop consumes
    `_parse_provider_response(...)` -> ModelResponse; on the first call we emit a
    tool_call, on later calls plain content. This isolates the HITL mechanism from
    any real LLM.
    """

    def __init__(self, tool_name: str, tool_args: dict[str, Any]):
        super().__init__(id="stub-model", provider="stub")
        self._call_name = tool_name
        self._call_args = tool_args
        self._calls = 0

    # --- abstract provider hooks (unused: we override _aprocess_model_response) ---
    def invoke(self, *a, **k):
        return {}

    async def ainvoke(self, *a, **k):
        return {}

    def invoke_stream(self, *a, **k):
        yield {}

    async def ainvoke_stream(self, *a, **k):
        yield {}

    def _parse_provider_response(self, response: Any, **kwargs) -> ModelResponse:
        return ModelResponse(role="assistant")

    def _parse_provider_response_delta(self, response: Any) -> ModelResponse:
        return ModelResponse(role="assistant", content="")

    # --- the real seam: populate assistant_message directly, leave aresponse's
    #     pause logic (the code under test) untouched ---
    async def _aprocess_model_response(
        self, messages, assistant_message, model_response, **kwargs
    ) -> None:
        self._calls += 1
        if self._calls == 1:
            tcs = [
                {
                    "id": f"call_{uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": self._call_name,
                        "arguments": json.dumps(self._call_args),
                    },
                }
            ]
            assistant_message.tool_calls = tcs
            model_response.tool_calls = tcs
        else:
            assistant_message.content = "Done — memory recorded."
            if model_response.content is None:
                model_response.content = assistant_message.content
            else:
                model_response.content += assistant_message.content


def _line(c="-"):
    print(c * 72)


async def scenario_a_gate_remote() -> Optional[bool]:
    """YES hypothesis: external_execution on the MCPTools-provided `remember`."""
    _line("=")
    print("SCENARIO A — gate the REMOTE MCP tool directly")
    _line("=")
    before = LOG.read_text().count("\n") if LOG.exists() else 0
    session_id = f"sess-a-{uuid4().hex[:6]}"

    async with MCPTools(
        url=MCP_URL,
        transport="streamable-http",
        external_execution_required_tools=["remember"],  # <-- the whole question
    ) as mcp_tools:
        # confirm the built Function actually carries the flag
        fn = mcp_tools.functions.get("remember")
        print(f"  built Function 'remember' present : {fn is not None}")
        print(f"  Function.external_execution flag  : {getattr(fn, 'external_execution', None)}")

        agent = Agent(
            name="memory-agent",
            model=StubModel("remember", {"text": "buy milk"}),
            tools=[mcp_tools],
            db=InMemoryDb(),
        )
        out = await agent.arun("please remember to buy milk", session_id=session_id)
        print(f"  run status after first turn        : {out.status}")

        paused = agent.get_last_run_output(session_id=session_id)
        pend = paused.tools_awaiting_external_execution if paused else []
        print(f"  status via get_last_run_output      : {getattr(paused,'status',None)}")
        print(f"  tools_awaiting_external_execution   : {[t.tool_name for t in pend]}")

        if not pend or getattr(paused, "status", None) != RunStatus.paused:
            print("  >>> DID NOT PAUSE on the remote MCP tool")
            return False

        # Resume: set the external tool result, then continue — the MCP write must run.
        for t in pend:
            # emulate approval: actually execute the remote write on resume
            t.result = None  # let acontinue_run drive execution? test both below
        # Per aap-kb: set .result to the tool's produced value; here we ask acontinue_run
        # to execute. Agno external_execution means the CALLER supplies the result.
        # We emulate the approved path: call the remote tool ourselves via the Function.
        for t in pend:
            call_fn = mcp_tools.functions["remember"]
            res = call_fn.entrypoint(**(t.tool_args or {}))
            if asyncio.iscoroutine(res):
                res = await res
            t.result = str(res)
            print(f"  external result supplied            : {t.result!r}")

        resumed = await agent.acontinue_run(
            run_id=paused.run_id,
            session_id=session_id,
            updated_tools=pend,
        )
        print(f"  run status after acontinue_run      : {resumed.status}")

    after = LOG.read_text().count("\n") if LOG.exists() else 0
    wrote = after - before
    print(f"  remembered.log lines delta          : {wrote}")
    ok = wrote >= 1
    print(f"  >>> SCENARIO A verdict               : {'PAUSED+RESUMED+WROTE' if ok else 'INCOMPLETE'}")
    return ok


async def scenario_b_local_wrapper() -> bool:
    """NO fallback: local @tool(external_execution=True) wrapping the MCP write."""
    _line("=")
    print("SCENARIO B — local wrapper tool carrying external_execution")
    _line("=")
    from agno.tools.decorator import tool

    before = LOG.read_text().count("\n") if LOG.exists() else 0
    session_id = f"sess-b-{uuid4().hex[:6]}"

    async with MCPTools(url=MCP_URL, transport="streamable-http") as mcp_tools:
        remote = mcp_tools.functions["remember"]

        @tool(external_execution=True)
        async def remember_wrapper(text: str) -> str:
            """Local HITL wrapper that calls the remote MCP remember on approval."""
            res = remote.entrypoint(text=text)
            if asyncio.iscoroutine(res):
                res = await res
            return str(res)

        agent = Agent(
            name="memory-agent-wrap",
            model=StubModel("remember_wrapper", {"text": "call the dentist"}),
            tools=[remember_wrapper],
            db=InMemoryDb(),
        )
        out = await agent.arun("remember to call the dentist", session_id=session_id)
        paused = agent.get_last_run_output(session_id=session_id)
        pend = paused.tools_awaiting_external_execution if paused else []
        print(f"  status                              : {getattr(paused,'status',None)}")
        print(f"  tools_awaiting_external_execution   : {[t.tool_name for t in pend]}")
        if not pend:
            print("  >>> wrapper did NOT pause")
            return False
        for t in pend:
            res = await remember_wrapper.entrypoint(**(t.tool_args or {}))
            t.result = str(res)
        resumed = await agent.acontinue_run(
            run_id=paused.run_id, session_id=session_id, updated_tools=pend
        )
        print(f"  run status after acontinue_run      : {resumed.status}")

    after = LOG.read_text().count("\n") if LOG.exists() else 0
    print(f"  remembered.log lines delta          : {after - before}")
    ok = (after - before) >= 1
    print(f"  >>> SCENARIO B verdict               : {'PAUSED+RESUMED+WROTE' if ok else 'INCOMPLETE'}")
    return ok


async def main():
    a = None
    try:
        a = await scenario_a_gate_remote()
    except Exception as exc:
        import traceback
        print("SCENARIO A raised:", exc)
        traceback.print_exc()
        a = False
    b = None
    if not a:
        try:
            b = await scenario_b_local_wrapper()
        except Exception as exc:
            import traceback
            print("SCENARIO B raised:", exc)
            traceback.print_exc()
            b = False
    _line("=")
    print("FINAL")
    print(f"  Scenario A (gate remote MCP tool)  : {a}")
    print(f"  Scenario B (local wrapper fallback): {b}")
    if a:
        print("  VERDICT: YES — gate-remote-directly")
    elif b:
        print("  VERDICT: NO — local-wrapper-tool (fallback proven)")
    else:
        print("  VERDICT: INCONCLUSIVE")
    _line("=")


if __name__ == "__main__":
    asyncio.run(main())
