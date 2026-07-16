"""DNA → **CopilotKit frontend console** scaffold (TS-only golden family).

Where the backend emitters materialize a servable AG-UI *backend* (agno / MS
Agent Framework), this module materializes the **frontend** that drives it: one
shared CopilotKit v2 console + a **tiny per-runtime resume-adapter**. It is the
concrete form of the design's §6.2 decision — *both reference consoles are ~95%
generic CopilotKit + `HttpAgent`; the only per-runtime seam is how a paused run
resumes* — so DNA emits ONE console and swaps just the resume-adapter file.

Shape of the emit (all artifacts tagged ``role="frontend"``):

    app/api/copilotkit/route.ts     the CopilotRuntime route — an `HttpAgent`
                                    bridge to the emitted `/agui` backend.
    components/copilot/console.tsx  the console — `CopilotChat` + a canvas of
                                    panels (from `frontend.panels`) + the HITL
                                    approval hook per gated write tool + the
                                    starter prompts (`frontend.suggested_prompts`).
    components/copilot/approval-card.tsx    the HITL card (generic).
    components/copilot/suggested-prompts.tsx  the starter-prompt chips (generic).
    lib/copilot/resume-adapter.ts   the ONE per-runtime file — agno resumes
                                    natively (identity `HttpAgent`); MS Agent
                                    Framework rewrites the resume payload.

Parameterization comes ENTIRELY from the neutral :class:`~dna.emit.EmitContext`
(filled by :func:`~dna.emit.build_copilot_context` from the ``Copilot`` doc's
``frontend`` + ``hitl`` blocks): the mounted agent's slug is the agent id, the
gated tools drive the HITL hooks, the ``hitl.approval_card`` config drives the
card copy, ``frontend.panels`` drive the canvas, ``frontend.suggested_prompts``
drive the chips, and ``tenant.propagate`` decides whether the console forwards
DNA's inbound tenant header (``X-DNA-Tenant``; ``X-Tenant-OID`` is server-derived).

**TS-only golden family (design §7).** The emitted files are TypeScript, so this
family has no Py↔TS *twin-diff* (there is no Python frontend to diff against);
it is governed by its own byte-stable golden render. The emitter itself has a
1:1 Py/TS twin (``frontend.py`` ↔ ``frontend.ts``) rendering byte-identical
templates, so both SDKs emit the same console.

This is NOT a registered :class:`~dna.emit.EmitterPort` — a console carries no
byte-equal instruction and is outside the ``build_prompt`` contract; it is a
standalone surface a consumer calls alongside the backend emit.
"""
from __future__ import annotations

import json
from typing import Any

from dna.emit import EmitArtifact, EmitContext, EmitError, EmitResult

__all__ = ["has_frontend", "emit_frontend_console", "available_frontend_runtimes"]

#: Target runtime → its resume-adapter template basename. The ONE per-runtime
#: file: agno resumes `external_execution` gates natively (identity HttpAgent);
#: MS Agent Framework rewrites the AG-UI `resume` array into `{interrupts:[…]}`.
_RESUME_ADAPTERS: dict[str, str] = {
    "agno": "resume-adapter.agno.ts.tmpl",
    "agent-framework": "resume-adapter.msaf.ts.tmpl",
}

#: The shared console files: (template basename, target-relative output path).
_SHARED: list[tuple[str, str]] = [
    ("route.ts.tmpl", "app/api/copilotkit/route.ts"),
    ("console.tsx.tmpl", "components/copilot/console.tsx"),
    ("approval-card.tsx.tmpl", "components/copilot/approval-card.tsx"),
    ("suggested-prompts.tsx.tmpl", "components/copilot/suggested-prompts.tsx"),
]

#: Where the emitted resume-adapter lands (its content is per-runtime).
_ADAPTER_PATH = "lib/copilot/resume-adapter.ts"


def available_frontend_runtimes() -> list[str]:
    """Sorted runtimes with a resume-adapter (``agno``, ``agent-framework``)."""
    return sorted(_RESUME_ADAPTERS)


def has_frontend(ctx: EmitContext) -> bool:
    """Whether ``ctx`` carries a ``Copilot.frontend`` block (a console to emit).

    Keyed on ``frontend_console`` — a copilot with no ``frontend`` declares no
    console and emits none (backend-only)."""
    return ctx.frontend_console is not None


def _read_template(name: str) -> str:
    """Read a CopilotKit frontend template from package data."""
    from importlib.resources import files

    res = files("dna.emit").joinpath("scaffolds", "copilotkit", name)
    if not res.is_file():
        raise EmitError(f"missing CopilotKit frontend template {name!r}")
    return res.read_text(encoding="utf-8")


def _ts_literal(value: str) -> str:
    """Render ``value`` as a TypeScript string literal (JSON string syntax is a
    valid TS literal). Emitted through triple-mustache so it is NOT HTML-escaped."""
    return json.dumps(value)


def _frontend_context(ctx: EmitContext) -> dict[str, Any]:
    """Template variables for the console, projected from the neutral ctx. Every
    list is sorted/ordered deterministically so the golden is byte-stable."""
    from dna.emit.scaffold import py_identifier

    gated = sorted(ctx.tools_requiring_confirmation)
    card = ctx.hitl_approval_card or {}
    return {
        "agent_id": ctx.name,
        "agent_id_literal": _ts_literal(ctx.name),
        # the emitted backend module name (`<module>_serve.py`) — matches the
        # Agno backend scaffold's `py_identifier(ctx.name)` module.
        "agent_module": py_identifier(ctx.name),
        "has_panels": bool(ctx.frontend_panels),
        "panels": [
            {"name": p, "name_literal": _ts_literal(p)} for p in ctx.frontend_panels
        ],
        "prompts": [
            {"text_literal": _ts_literal(p)} for p in ctx.frontend_suggested_prompts
        ],
        "gated_tools": [
            {"name": t, "name_literal": _ts_literal(t)} for t in gated
        ],
        "approval_title_literal": _ts_literal(str(card.get("title") or "Confirm write")),
        "details_from_literal": _ts_literal(str(card.get("details_from") or "")),
        "reason_from_literal": _ts_literal(str(card.get("reason_from") or "")),
        "tenant_propagate": bool(ctx.tenant_propagate),
    }


def _frontend_losses(ctx: EmitContext, runtime: str) -> list[str]:
    """The honest de-para for the frontend scaffold."""
    out = [
        "panel bodies — each `frontend.panels` entry renders the agent's shared "
        "state as JSON; wire the real per-panel UI to your domain (the panel "
        "names are hints, not components)",
        "inbound-tenant values — the console forwards `X-DNA-Tenant` from the app "
        "session and the `/agui` backend derives `X-Tenant-OID` server-side from "
        "the verified token; the scaffold marks WHERE, the auth store is per-app",
    ]
    if not ctx.tools_requiring_confirmation:
        out.append(
            "approval card — no gated write tool, so the console mounts no HITL "
            "hook; the card component ships anyway for a later gated tool"
        )
    return out


def emit_frontend_console(ctx: EmitContext, *, runtime: str = "agno") -> EmitResult:
    """Render the shared CopilotKit console + the ``runtime`` resume-adapter.

    ``ctx`` is an enriched copilot context (:func:`~dna.emit.build_copilot_context`)
    that carries a ``frontend`` block. ``runtime`` selects the ONE per-runtime file
    (``agno`` — native resume; ``agent-framework`` — the ``{interrupts:[…]}``
    bridge). Returns an :class:`~dna.emit.EmitResult` whose artifacts are all
    tagged ``role="frontend"``.
    """
    if not has_frontend(ctx):
        raise EmitError(
            f"copilot {ctx.name!r} declares no `frontend` block — nothing to emit "
            "(a pure-action/back-end-only copilot has no console)"
        )
    adapter_tmpl = _RESUME_ADAPTERS.get(runtime)
    if adapter_tmpl is None:
        raise EmitError(
            f"no frontend resume-adapter for runtime {runtime!r}; "
            f"available: {', '.join(available_frontend_runtimes())}"
        )
    try:
        import chevron
    except ModuleNotFoundError as exc:  # pragma: no cover - dev dep always present
        raise EmitError(
            "the frontend emit needs `chevron` (Mustache) — it ships with the SDK"
        ) from exc

    variables = _frontend_context(ctx)
    artifacts: list[EmitArtifact] = []
    for tmpl_name, out_path in _SHARED:
        content = chevron.render(_read_template(tmpl_name), variables)
        artifacts.append(EmitArtifact(path=out_path, content=content, role="frontend"))
    adapter_src = chevron.render(_read_template(adapter_tmpl), variables)
    artifacts.append(EmitArtifact(path=_ADAPTER_PATH, content=adapter_src, role="frontend"))

    return EmitResult(
        target=f"copilotkit-{runtime}",
        artifacts=artifacts,
        losses=_frontend_losses(ctx, runtime),
        mapping={
            "Copilot.frontend.console": "CopilotKit v2 console (CopilotChat + canvas)",
            "Copilot.frontend.panels[]": "components/copilot/console.tsx canvas panels",
            "Copilot.frontend.suggested_prompts[]": "SUGGESTED_PROMPTS (anti-blank-box chips)",
            "Copilot.hitl.approval_card": "components/copilot/approval-card.tsx (via useHumanInTheLoop)",
            "Tool.requires_confirmation": "useHumanInTheLoop({name}) HITL write-gate",
            "Copilot.tenant.propagate": "X-DNA-Tenant header forwarding (oid server-derived)",
            f"serving runtime = {runtime}": "lib/copilot/resume-adapter.ts",
        },
    )
