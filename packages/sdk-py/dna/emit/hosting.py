"""DNA → **hosted-variant** deployment artifacts for a servable Copilot.

Where :mod:`dna.emit.agno` / :mod:`dna.emit.agent_framework` emit the *self-hosted*
AG-UI app (the per-user copilot backend) and :mod:`dna.emit.frontend` its console,
this module emits the **hosted** variant — a container image + a managed-runtime
manifest deployed to a managed service. It is the concrete form of the design's
§2 — *"`hosting.mode` is a variant selector over ONE agent def: the same agent
emits BOTH the per-user AG-UI app AND the single-identity hosted agent; the hosted
variant DEGRADES"*.

Gated on ``ctx.hosting.mode == "hosted"`` (:func:`has_hosting`): a copilot with no
``hosting`` block, or ``mode: self-hosted``, has NO hosted variant and keeps the
existing AG-UI emit UNCHANGED (back-compat). The emit routes on
``ctx.hosting.target``:

**``foundry`` — FIRST-CLASS (a true managed runtime).** Four artifacts, all
``role="hosting"``:

    Dockerfile        python:3.12-slim, ``EXPOSE 8088``, ``linux/amd64``, the
                      Responses-protocol container (built remotely by ACR).
    main.py           ``ResponsesHostServer(build_agent()).run()`` — the MS-AF
                      agent-build reused from the self-hosted agent_framework
                      copilot scaffold, but the DEGRADED single-identity variant
                      (per-user OBO / per-user memory / HITL stripped — see the
                      module docstring the template emits).
    requirements.txt  ``agent-framework`` + ``agent-framework-foundry-hosting``
                      (+ ``agent-framework-postgres`` when a pgvector knowledge
                      store survives as single-identity RAG grounding).
    azure.yaml        the ``host: azure.ai.agent`` service block — the
                      NON-deprecated Foundry hosted-agent manifest (NOT the
                      deprecated ``agent.yaml``). ``azd deploy`` builds the image
                      (``remoteBuild`` when ``image.remote_build``) and publishes a
                      new agent VERSION (a deploy step, not an ARM resource).

**``langgraph-platform`` — DOCUMENTED (a stateful server, not a Foundry-style
managed agent).** Emits ``langgraph.json`` (graphs + dependencies + env) + a
``HOSTING.md`` note that ``langgraph build`` produces the image and that the
abstraction leaks (LangGraph is a server, ``identity``/``protocol`` don't map).

**``agentos`` — DOCUMENTED (no managed runtime).** Emits the AgentOS ``main.py`` +
a thin ``compose.yaml`` (port 7777) + a ``HOSTING.md`` note that "hosted" ≈
self-host + control-plane registration.

This is NOT a registered :class:`~dna.emit.EmitterPort` — hosting artifacts carry
no byte-equal instruction and are outside the ``build_prompt`` contract; it is a
standalone surface a consumer calls alongside the backend emit (mirrors
:func:`~dna.emit.frontend.emit_frontend_console` / :func:`~dna.emit.infra.emit_infra`).
The emitter has a 1:1 Py/TS twin (``hosting.py`` ↔ ``hosting.ts``) rendering
byte-identical templates, so both SDKs emit the same hosted variant.
"""
from __future__ import annotations

from typing import Any

from dna.emit import EmitArtifact, EmitContext, EmitError, EmitResult

__all__ = ["has_hosting", "emit_hosting"]

#: Default serve port per hosting target (design §2: 8088 / 8123 / 7777).
_DEFAULT_PORT = {"foundry": 8088, "langgraph-platform": 8123, "agentos": 7777}


def has_hosting(ctx: EmitContext) -> bool:
    """Whether ``ctx`` declares a **hosted** variant to emit.

    True only when ``ctx.hosting`` is present AND ``hosting.mode == "hosted"``.
    A copilot with no ``hosting`` block, or ``mode: self-hosted``, keeps the
    existing self-hosted AG-UI emit UNCHANGED — there is no hosted variant to
    emit (back-compat; the variant selector of design §2)."""
    return ctx.hosting is not None and ctx.hosting.get("mode") == "hosted"


def _read_template(name: str) -> str:
    """Read a hosting template from package data (``scaffolds/hosting/<name>``)."""
    from importlib.resources import files

    res = files("dna.emit").joinpath("scaffolds", "hosting", name)
    if not res.is_file():
        raise EmitError(f"missing hosting template {name!r}")
    return res.read_text(encoding="utf-8")


def _render(name: str, variables: dict[str, Any]) -> str:
    try:
        import chevron
    except ModuleNotFoundError as exc:  # pragma: no cover - dev dep always present
        raise EmitError(
            "the hosting emit needs `chevron` (Mustache) — it ships with the SDK"
        ) from exc

    return chevron.render(_read_template(name), variables)


def _foundry_variables(ctx: EmitContext) -> dict[str, Any]:
    """Template variables for the Foundry hosted variant, projected from the
    neutral ctx. Reuses the SAME persistence/mcp facts the self-hosted MS-AF
    scaffold reads, so the hosted build_agent mirrors it — minus the degraded
    per-user concerns. Everything sorted for a byte-stable golden."""
    from dna.emit.scaffold import (
        persistence_facts,
        pg_url_expr,
        py_identifier,
        py_str_literal,
    )

    hosting = ctx.hosting or {}
    image = hosting.get("image") or {}
    resources = hosting.get("resources") or {}
    port = image.get("port") or _DEFAULT_PORT["foundry"]

    facts = persistence_facts(ctx)
    has_pgvector = facts["vector_pg"]

    # ── DEGRADED MCP mount: the SAME tools, but no approval_mode (HITL stripped)
    # and no header_provider (per-user OBO/tenant stripped) — a single service
    # identity. `allowed_tools` still bounds what the model may call.
    servers: list[dict[str, Any]] = []
    for s in ctx.mcp_servers:
        allowed_sorted = sorted(s.allowed_tools)
        servers.append(
            {
                "name_literal": py_str_literal(f"mcp_{s.ref}"),
                "url_literal": py_str_literal(s.url) if s.url else "None",
                "allowed_tools_literal": (
                    "[" + ", ".join(py_str_literal(t) for t in allowed_sorted) + "]"
                ),
            }
        )

    cpu = resources.get("cpu")
    memory = resources.get("memory")

    return {
        "name": ctx.name,
        "name_literal": py_str_literal(ctx.name),
        "instructions_literal": py_str_literal(ctx.instructions),
        "has_model": ctx.model is not None,
        "model_literal": py_str_literal(ctx.model) if ctx.model else "",
        "port": port,
        "has_mcp": bool(servers),
        "mcp_servers": servers,
        "needs_os": bool(has_pgvector),
        "has_pgvector": bool(has_pgvector),
        "vector_ref": facts["vector_ref"] or "",
        "vector_collection_literal": py_str_literal(
            py_identifier(ctx.knowledge[0]) if ctx.knowledge else "knowledge"
        ),
        "vector_db_url_expr": (
            pg_url_expr(facts["vector_ref"]) if has_pgvector and facts["vector_ref"] else ""
        ),
        "embed_model_literal": py_str_literal(
            facts["embed_model"] or "text-embedding-3-small"
        ),
        "embed_dims": facts["embed_dims"] if facts["embed_dims"] is not None else 1536,
        # azure.yaml service block
        "service_name": ctx.name,
        "remote_build": bool(image.get("remote_build")),
        "has_resources": bool(cpu or memory),
        "cpu_literal": _yaml_scalar(cpu),
        "memory_literal": _yaml_scalar(memory),
    }


def _yaml_scalar(value: Any) -> str:
    """Render a YAML scalar for the azure.yaml block. A string that looks numeric
    (``0.5``) is quoted so azd reads it as a string (matching the foundry
    reference's ``cpu: "0.5"``); a plain token (``1Gi``) is bare."""
    if value is None:
        return '""'
    s = str(value)
    # quote when it parses as a number (or is empty) — else emit bare.
    try:
        float(s)
        return f'"{s}"'
    except ValueError:
        return s


def _foundry_losses(ctx: EmitContext) -> list[str]:
    """The honest de-para for the Foundry hosted variant — what the DEGRADE drops
    and what stays a per-app wiring point."""
    out = [
        "per-user OBO — the hosted variant authenticates as the platform-injected "
        "AGENT identity (`DefaultAzureCredential`), NOT the signed-in user; the "
        "on-behalf-of flow lives only in the self-hosted AG-UI app (design §2)",
        "HITL approval gates — the single-turn hosted agent has no approval card / "
        "no workflow escalation; write tools run ungated under the agent identity "
        "(the AG-UI variant keeps the gate)",
        "per-user long-term memory — Foundry hosting manages conversation history; "
        "the cross-session per-user memory store is dropped in the hosted variant",
        "the agent VERSION is not built here — `azd deploy` builds the image "
        "(remoteBuild via ACR) and publishes a new agent version (a deploy step, "
        "not an artifact)",
    ]
    if ctx.mcp_servers:
        out.append(
            "MCP tool bodies — the hosted agent calls the DNA MCP server's tools over "
            "Streamable HTTP (mounted WITHOUT approval_mode / header_provider — the "
            "degrade); the tool implementations live on the remote MCP server"
        )
    from dna.emit.scaffold import persistence_facts

    if persistence_facts(ctx)["vector_pg"]:
        out.append(
            "pgvector RAG — the surviving single-identity knowledge grounding binds "
            "`PostgresVectorStore` (DSN from the infra ref via env var); wire it as "
            "`context_providers` + load the corpus CONTENT per-app"
        )
    if ctx.model is None:
        out.append(
            "model unbound in DNA and none supplied — emitted `FoundryChatClient(...)` "
            "has no `model=`; supply one at wire-up"
        )
    return out


def _emit_foundry(ctx: EmitContext) -> EmitResult:
    variables = _foundry_variables(ctx)
    artifacts = [
        EmitArtifact(
            path="Dockerfile",
            content=_render("foundry/Dockerfile.tmpl", variables),
            role="hosting",
        ),
        EmitArtifact(
            path="main.py",
            content=_render("foundry/main.py.tmpl", variables),
            role="hosting",
        ),
        EmitArtifact(
            path="requirements.txt",
            content=_render("foundry/requirements.txt.tmpl", variables),
            role="hosting",
        ),
        EmitArtifact(
            path="azure.yaml",
            content=_render("foundry/azure.yaml.tmpl", variables),
            role="hosting",
        ),
    ]
    return EmitResult(
        target="foundry-hosted",
        artifacts=artifacts,
        losses=_foundry_losses(ctx),
        mapping={
            "Copilot.hosting.target=foundry": "host: azure.ai.agent service block (azure.yaml)",
            "build_prompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (main.py, byte-equal)",
            "Copilot.hosting.image.port": "EXPOSE <port> (Dockerfile) — default 8088",
            "Copilot.hosting.image.remote_build": "docker.remoteBuild (azure.yaml)",
            "Copilot.hosting.resources": "config.container.resources (azure.yaml)",
            "Copilot.hosting.mode=hosted": "the DEGRADED single-identity variant (no OBO/memory/HITL)",
        },
    )


def _langgraph_variables(ctx: EmitContext) -> dict[str, Any]:
    from dna.emit.scaffold import py_identifier

    hosting = ctx.hosting or {}
    image = hosting.get("image") or {}
    port = image.get("port") or _DEFAULT_PORT["langgraph-platform"]
    module = py_identifier(ctx.name)
    return {
        "name": ctx.name,
        "module": module,
        "graph_id": module,
        "port": port,
    }


def _emit_langgraph(ctx: EmitContext) -> EmitResult:
    variables = _langgraph_variables(ctx)
    artifacts = [
        EmitArtifact(
            path="langgraph.json",
            content=_render("langgraph/langgraph.json.tmpl", variables),
            role="hosting",
        ),
        EmitArtifact(
            path="HOSTING.md",
            content=_render("langgraph/HOSTING.md.tmpl", variables),
            role="hosting",
        ),
    ]
    return EmitResult(
        target="langgraph-platform",
        artifacts=artifacts,
        losses=[
            "LangGraph Platform is a stateful SERVER, not a Foundry-style managed "
            "hosted agent — the hosting abstraction leaks (design §2/§6): `identity` "
            "and `protocol` don't map, and `langgraph build` (not this emit) produces "
            "the image from langgraph.json. Emitted DOCUMENTED, lower v1 priority.",
            "graph body — `langgraph.json` points at `./{}:graph`; the compiled "
            "StateGraph is a per-app body (the self-hosted LangGraph scaffold emits "
            "it), not part of the hosting manifest.".format(variables["module"]),
        ],
        mapping={
            "Copilot.hosting.target=langgraph-platform": "langgraph.json (graphs + dependencies + env)",
            "`langgraph build`": "the container image (NOT this emit)",
        },
    )


def _agentos_variables(ctx: EmitContext) -> dict[str, Any]:
    from dna.emit.scaffold import py_identifier, py_str_literal

    hosting = ctx.hosting or {}
    image = hosting.get("image") or {}
    port = image.get("port") or _DEFAULT_PORT["agentos"]
    module = py_identifier(ctx.name)
    return {
        "name": ctx.name,
        "name_literal": py_str_literal(ctx.name),
        "instructions_literal": py_str_literal(ctx.instructions),
        "has_model": ctx.model is not None,
        "model_literal": py_str_literal(ctx.model) if ctx.model else "",
        "module": module,
        "port": port,
    }


def _emit_agentos(ctx: EmitContext) -> EmitResult:
    variables = _agentos_variables(ctx)
    artifacts = [
        EmitArtifact(
            path="main.py",
            content=_render("agentos/main.py.tmpl", variables),
            role="hosting",
        ),
        EmitArtifact(
            path="compose.yaml",
            content=_render("agentos/compose.yaml.tmpl", variables),
            role="hosting",
        ),
        EmitArtifact(
            path="HOSTING.md",
            content=_render("agentos/HOSTING.md.tmpl", variables),
            role="hosting",
        ),
    ]
    return EmitResult(
        target="agentos",
        artifacts=artifacts,
        losses=[
            "Agno AgentOS has NO managed runtime — `mode: hosted` for agentos ≈ "
            "self-host (the emitted `AgentOS(...)` app + compose.yaml) + an optional "
            "control-plane REGISTRATION step; there is no Foundry-style hosted agent "
            "(design §2/§6). Emitted DOCUMENTED, lower v1 priority.",
            "the compose.yaml is a THIN single-service scaffold (port {}); wire the "
            "managed Postgres/Redis + JWT secrets + ingress via "
            "f-copilot-infra-binding, not this file.".format(variables["port"]),
        ],
        mapping={
            "Copilot.hosting.target=agentos": "AgentOS(...) main.py + thin compose.yaml",
            "build_prompt (Soul+guardrails+instruction)": "INSTRUCTIONS constant (main.py, byte-equal)",
            "Copilot.hosting.mode=hosted": "self-host + control-plane registration (no managed runtime)",
        },
    )


_TARGETS = {
    "foundry": _emit_foundry,
    "langgraph-platform": _emit_langgraph,
    "agentos": _emit_agentos,
}


def emit_hosting(ctx: EmitContext) -> EmitResult:
    """Render the **hosted** variant deployment artifacts for a Copilot.

    ``ctx`` is an enriched copilot context (:func:`~dna.emit.build_copilot_context`)
    carrying a ``hosting`` block with ``mode: hosted``. Routes on ``hosting.target``
    (``foundry`` first-class; ``langgraph-platform`` / ``agentos`` documented) and
    returns an :class:`~dna.emit.EmitResult` whose artifacts are all tagged
    ``role="hosting"``. Raises :class:`~dna.emit.EmitError` when the copilot has no
    hosted variant (``has_hosting`` is False) or names an unknown target.
    """
    if not has_hosting(ctx):
        raise EmitError(
            f"copilot {ctx.name!r} declares no HOSTED variant "
            "(`hosting.mode` is not 'hosted') — the self-hosted AG-UI emit is "
            "unchanged; there is nothing to emit here (design §2 variant selector)"
        )
    target = (ctx.hosting or {}).get("target")
    emit = _TARGETS.get(target)
    if emit is None:
        raise EmitError(
            f"hosting target {target!r} has no emitter (design §2 covers "
            f"foundry, langgraph-platform, agentos)"
        )
    return emit(ctx)
