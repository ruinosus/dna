"""``delegate_to`` — the tool a delegator agent gets when it declares
``team_members``.

Peça A of ``docs/superpowers/plans/2026-07-30-close-the-two-doors-plan.md``.
``dna.application.delegation_exec.delegate()`` already existed, tested,
published — and was UNREACHABLE: it was not any agent's tool. This module is
the door: it wraps ``delegate()`` in a ``StructuredTool`` shaped after the
pattern LangChain's subagents documentation names (the recommendation current
since March/2026, above the legacy ``langgraph-supervisor``):

- the target is picked by NAME;
- the task reaches the subagent as a HUMAN MESSAGE, never concatenated onto
  the delegator's system prompt;
- the return is a concise SUMMARY — never the transcript;
- the stated reason for the pattern is CONTEXT ISOLATION: the sub-run gets
  its own state and never sees the delegator's history. This module
  guarantees that by construction — the only thing that crosses the boundary
  is ``(target: str, task: str)``; there is no parameter through which a
  parent message could enter.

The transports (``run_local``, ``call_remote``) are INJECTED — the actual
wiring (who builds ``run_local`` from the live runtime, who binds
``call_remote`` to the A2A transport) lives in ``dna.runtime.builder`` (A.1),
not here. This module never decides WHO may delegate to WHOM — that's
``dna.application.delegation``, consulted from inside ``delegate()``. This
module only shapes the tool around it.

Heavy framework deps (``langchain_core``, ``pydantic``) are imported INSIDE
``make_delegate_tool``, never at module top level — same discipline
``dna.runtime.port``'s docstring names for langchain/agent-framework, so
importing this module never requires the ``[runtime]`` extra to be
installed; only calling ``make_delegate_tool`` does.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Iterable, Mapping

from dna.application.delegation import DelegationTarget, targets_for
from dna.application.delegation_exec import DelegationRefused, delegate

#: The tool name the kernel already documents (``DelegationTargetFor``'s
#: docstring, ``AgentSpec.team_members``) — not invented here.
TOOL_NAME = "delegate_to"


def _roster(
    delegator: str, documents: Iterable[Mapping[str, Any]]
) -> list[DelegationTarget]:
    return targets_for(delegator, list(documents))


def _tool_description(targets: list[DelegationTarget]) -> str:
    """List the available targets with their ``use_when`` — the discovery
    path LangChain's docs name: the model picks a target from what the TOOL
    PROMPT says, not blindly. ``use_when`` exists in the kernel precisely to
    drive this choice (``DelegationTargetFor.use_when``)."""
    if not targets:
        return (
            "Delegate a task to a named subagent. No target currently accepts "
            "delegation from this agent — none has opted in via "
            "delegation_target_for.agents for this delegator."
        )
    lines = ["Delegate a task to a named subagent, selected by name. Available targets:"]
    for target in sorted(targets, key=lambda t: t.name):
        hint = target.use_when or target.purpose or "(no use_when declared)"
        lines.append(f"- {target.name}: {hint}")
    return "\n".join(lines)


def make_delegate_tool(
    *,
    delegator: str,
    documents: Iterable[Mapping[str, Any]],
    run_local: Callable[[str, str], Awaitable[str]],
    call_remote: Callable[..., Awaitable[str]],
    credential_for: Callable[[str], str | None] | None = None,
    enqueue: Callable[..., Awaitable[str]] | None = None,
) -> Any:
    """Build the ``delegate_to`` ``StructuredTool`` for ``delegator``.

    ``documents`` is the raw scope snapshot (mappings with ``kind`` /
    ``metadata`` / ``spec``) — the same shape
    ``dna.application.delegation.targets_for`` already reads. The roster is
    re-derived from it, never a hand-kept list of names: once here (for the
    tool's description) and again, independently, inside ``delegate()`` at
    call time (the source of truth for authorization stays
    ``dna.application.delegation`` — this module never shortcuts it).

    ``enqueue``, when given, is the THIRD transport: a target that declares
    ``typical_seconds`` above the threshold is recorded as work to do and the
    supervisor answers immediately with a run id, instead of holding the
    connection open for minutes. Absent, a long target simply runs in-process
    as before — a deployment without a worker keeps working, which is why this
    is optional rather than required.

    ``credential_for``, when given, completes a ``call_remote`` that still
    expects it as a keyword — e.g. a
    ``functools.partial(a2a_transport.call_remote, http=client)`` whose only
    remaining unbound piece is the per-target workspace credential. When
    ``call_remote`` already matches the plain ``(target, request) -> str``
    contract ``delegate()`` expects (every test double in this package's
    tests does), leave it ``None``.
    """
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    documents = list(documents)

    class _DelegateToArgs(BaseModel):
        target: str = Field(..., description="The name of the subagent to delegate to.")
        task: str = Field(
            ...,
            description=(
                "The task, in natural language — becomes the subagent's sole "
                "human message. The subagent never sees this conversation's "
                "history."
            ),
        )

    effective_call_remote = call_remote
    if credential_for is not None:

        async def effective_call_remote(target: DelegationTarget, request: str) -> str:
            return await call_remote(target, request, credential_for=credential_for)

    async def _delegate_to(target: str, task: str) -> str:
        try:
            outcome = await delegate(
                delegator=delegator,
                target_name=target,
                request=task,
                documents=documents,
                run_local=run_local,
                call_remote=effective_call_remote,
                enqueue=enqueue,
            )
        except DelegationRefused as exc:
            # Recusa nomeada, nunca silêncio: o supervisor recebe a razão
            # como TOOL RESULT (não uma exceção crua) para poder narrá-la em
            # vez de assumir sucesso.
            return f"delegate_to refused: {exc}"
        except Exception as exc:  # noqa: BLE001 — o subagente quebrou; ver acima
            return f"delegate_to to {target!r} failed: {exc}"
        if outcome.get("transport") == "queued":
            # Um Run enfileirado NÃO tem resultado — e a tool não pode fingir
            # que tem. O supervisor precisa saber que o trabalho foi ACEITO e
            # ainda não feito, para dizer "estou convertendo, aviso quando
            # terminar" em vez de narrar uma conclusão que não aconteceu.
            #
            # Narrar sucesso sobre trabalho pendente é o pior modo de falha
            # desta feature: o usuário vai embora acreditando que existe um
            # documento que ainda não existe.
            return (
                f"accepted: {outcome['target']} is working on this in the "
                f"background (run {outcome['run_id']}). Tell the user you have "
                f"started it and will report back — do NOT claim it is done."
            )
        return str(outcome["result"])

    description = _tool_description(_roster(delegator, documents))
    return StructuredTool.from_function(
        coroutine=_delegate_to,
        name=TOOL_NAME,
        description=description,
        args_schema=_DelegateToArgs,
    )
