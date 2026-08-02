"""DNA `Agent` → **A2A Agent Card** (JSON, camelCase) — the outbound projection.

A standalone emit surface, alongside ``dna.emit.mcp_ui`` and
``dna.emit.frontend`` — like those it is NOT a registered :class:`EmitterPort`:
it carries no byte-equal ``build_prompt`` instruction and is governed by its
own tests rather than the emit contract's golden-render machinery. Everything
here is a pure function of its inputs.

This is the OUT direction of A2A: the Agent Card is what lets *another* system
delegate work *to* us. (The IN direction — fetching a third party's Card into
a ``RemoteAgent`` document — is ``dna.application.a2a_ingest``.) The module
only PROJECTS the Card; who serves it and at which path is a deployment
decision (``/.well-known/`` is a domain-root convention, and the root isn't
the SDK's to own — see the plan's premise §9.3).

── The shape ──────────────────────────────────────────────────────────────

The A2A Card is camelCase JSON — the opposite convention from the DNA Kind
(snake_case), because the Kind IS a DNA document and the Card IS an A2A wire
artifact. Translating field names at the boundary, not before, keeps each side
speaking its own idiom.

``skills`` is DERIVED from the caller-supplied ``tools``, never a parallel
list kept on the ``Agent`` document — a hand-maintained list goes stale in
silence, the failure mode this project has already paid for more than once.
The tool NAMES are the only input; there is no tool registry lookup here (the
caller resolves ``spec.tools`` → real Tool docs upstream and passes the
resolved names in, the same shape ``EmitContext.tools`` already carries
elsewhere in this package).

``description`` prefers ``delegation_target_for.purpose`` — the field that
already exists so a delegator can choose a target — and falls back to
``metadata.description``. Both are exactly what a Card needs to communicate.

No credential is ever projected. There is no field here for one: the Card
carries identity and capability, never a secret. (``RemoteAgent``, the INBOUND
twin of this shape, makes the same point structurally — its schema is closed
with ``additionalProperties: false`` for the same reason.)
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

__all__ = ["agent_card_for"]

#: A2A `version` this SDK stamps on a Card it projects — the DNA `Agent` Kind
#: carries no version-of-self field (it is versioned as a DOCUMENT, not as an
#: API), so there is nothing truthful to read here yet. Fixed until the Kind
#: grows one.
_CARD_VERSION = "0.1.0"

#: Every DNA agent talks plain text over the wire today (no multimodal
#: input/output contract in `AgentSpec` yet).
_DEFAULT_MODES = ["text/plain"]


def _spec(agent_doc: Mapping[str, Any]) -> Mapping[str, Any]:
    return agent_doc.get("spec") or {}


def _metadata(agent_doc: Mapping[str, Any]) -> Mapping[str, Any]:
    return agent_doc.get("metadata") or {}


def _capabilities(
    streaming: bool, data_scope_kinds: Iterable[str] | None
) -> dict[str, Any]:
    """``capabilities`` — e a extensão de escopo, quando o deployment a serve.

    ``data_scope_kinds=None`` significa "este deployment não pede escopo", e a
    chave ``extensions`` nem aparece. Uma lista VAZIA é diferente e também
    legítima: anuncia a extensão dizendo *"existe, e o vocabulário não está
    publicado aqui"* — o caso de um deployment cujos Kinds são do tenant e não
    do Card público.

    A distinção entre ``None`` e ``[]`` é carregada de propósito. Colapsá-las
    faria um deployment sem vocabulário publicado parecer um que não suporta a
    extensão, e aí o terceiro nunca pediria nada — que é exatamente o estado que
    esta extensão existe para sair.
    """
    caps: dict[str, Any] = {"streaming": bool(streaming)}
    if data_scope_kinds is None:
        return caps

    # Import DENTRO, como o resto deste módulo: mantém o extra `a2a` opcional.
    from dna.extensions.a2a.data_scope import extension_declaration

    caps["extensions"] = [extension_declaration(available_kinds=data_scope_kinds)]
    return caps


def _description(agent_doc: Mapping[str, Any]) -> str:
    """``delegation_target_for.purpose`` first — it exists so a delegator can
    choose a target, which is exactly what a Card communicates. Falls back to
    ``metadata.description`` when the agent declares no delegation block (or
    the block omits ``purpose``)."""
    delegation = _spec(agent_doc).get("delegation_target_for") or {}
    purpose = delegation.get("purpose")
    if purpose:
        return str(purpose)
    return str(_metadata(agent_doc).get("description") or "")


def _skills(tools: Iterable[str]) -> list[dict[str, str]]:
    """DERIVED from ``tools``, never a hand-kept list — see the module
    docstring. Sorted so the projection is deterministic."""
    return [
        {
            "id": name,
            "name": name,
            "description": f"Invokes the {name!r} tool.",
        }
        for name in sorted(set(tools))
    ]


def agent_card_for(
    agent_doc: Mapping[str, Any],
    *,
    tools: Iterable[str] = (),
    base_url: str,
    streaming: bool = False,
    data_scope_kinds: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Project a DNA ``Agent`` document into an A2A 1.0 Agent Card (dict, JSON-ready).

    ``tools`` is the resolved list of tool names the agent exposes (the
    caller's job — this function does not look anything up); ``skills`` is
    derived from it. ``base_url`` is where the caller intends to serve this
    agent's A2A endpoint; ``supportedInterfaces`` is built from it.

    ``streaming`` — o que o EXECUTOR daquele deployment implementa, não uma
    constante. Fixo em ``True``, ``capabilities.streaming`` era uma promessa sem
    nada atrás; quem monta a face sabe se há streaming e é quem responde por
    isso (``dna.extensions.a2a.serve.attach_a2a`` deriva do executor montado).

    O binding e a versão do protocolo vêm de ``a2a.utils.constants``, nunca de
    literais daqui. O campo chamava-se ``transport`` numa leitura nossa da spec
    e NÃO EXISTE: a 1.0 o chama ``protocolBinding``, com o valor em maiúsculas.
    Enquanto divergia, o ``ClientFactory`` oficial encontrava zero interfaces
    neste Card — ou seja, nenhum cliente conforme conseguia nos chamar, com
    todos os testes verdes, porque eles herdavam a mesma leitura errada.

    No field here can carry a credential — the Card is safe to publish as-is.
    """
    # Import DENTRO da função, deliberadamente: é o que mantém o extra `a2a`
    # opcional (guarda: tests/test_a2a_import_isolation.py). Um import no topo
    # faria este módulo — importado por quem só quer PROJETAR — exigir a árvore
    # inteira do protobuf.
    from a2a.utils.constants import PROTOCOL_VERSION_1_0, TransportProtocol

    metadata = _metadata(agent_doc)
    name = str(metadata.get("name") or "")
    url = str(base_url).rstrip("/")

    return {
        "name": name,
        "description": _description(agent_doc),
        "version": _CARD_VERSION,
        "supportedInterfaces": [
            {
                "url": url,
                "protocolBinding": TransportProtocol.JSONRPC.value,
                "protocolVersion": PROTOCOL_VERSION_1_0,
            }
        ],
        "capabilities": _capabilities(streaming, data_scope_kinds),
        "defaultInputModes": list(_DEFAULT_MODES),
        "defaultOutputModes": list(_DEFAULT_MODES),
        "skills": _skills(tools),
    }
