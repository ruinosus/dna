"""Guardrail-owned write-path guard: the **live spec-kit constitution**.

Layer 3 of the Spec Kit adoption (ADR ``ADR-spec-kit-adoption`` §5) makes the
constitution a *live* Guardrail — enforced at ``write_document`` time,
overridable per scope/tenant with **no redeploy**. ``dna specify
install-templates`` (and ``dna specify import``) map ``constitution.md`` to a
``Guardrail`` named ``speckit-constitution`` carrying a ``severity``. This guard
turns that Guardrail into an enforced write-time gate, exactly like Helix's
prompt-budget guard turns a ModelProfile into one.

The rule (machine-checkable, reads only existing fields — zero schema change):

    A ``speckit-constitution`` Guardrail with ``severity: hard`` active in the
    (tenant-resolved) scope REQUIRES every governed spec-kit work item to trace
    back to a Spec:
      - a spec-kit **Story** must carry a non-empty ``spec.spec_refs``;
      - a spec-kit **Plan** must set ``spec.spec_ref`` (or ``spec.spec_refs``).
    ``hard`` → VETO the write; any other severity (``error``/``warn``) → WARN
    and proceed; no constitution (or a non-spec-kit one) → PASS.

This is the concrete no-deploy governance loop: flip the constitution's
``severity`` (``warn`` ⇄ ``hard``) and the very next write is enforced
differently — no restart, no deploy. Overlay the constitution per tenant and the
governance changes for that workspace alone.

The guard is tenant-aware (it reads the constitution through the write's own
tenant-bound ``ctx.kernel``, so an overlay wins) and fail-open (a read error
never blocks a write — governance must not become an outage).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dna.kernel.hooks import PreSaveContext

logger = logging.getLogger(__name__)

#: Ordered AFTER Helix's guards (fork=10, budget=20, kind-writer=30) and the
#: SDLC bitemporal guard (40).
PRIORITY_CONSTITUTION = 50

#: The canonical name `dna specify` writes the constitution Guardrail under.
_CONSTITUTION_NAME = "speckit-constitution"
_METHODOLOGY = "spec-kit"
_GOVERNED_KINDS = {"Story", "Plan"}


class ConstitutionViolationError(Exception):
    """Raised (→ veto) when a hard spec-kit constitution rejects a write."""


def _is_spec_kit(kind: str, spec: dict[str, Any]) -> bool:
    if spec.get("pattern") == _METHODOLOGY or spec.get("methodology") == _METHODOLOGY:
        return True
    labels = spec.get("labels")
    return isinstance(labels, list) and _METHODOLOGY in labels


def _traces_to_spec(kind: str, spec: dict[str, Any]) -> bool:
    refs = spec.get("spec_refs")
    if isinstance(refs, list) and any(refs):
        return True
    if kind == "Plan":
        return bool(spec.get("spec_ref"))
    return False


async def spec_kit_constitution_guard(ctx: "PreSaveContext") -> None:
    """Enforce a hard spec-kit constitution's traceability rule at write time.

    VETO when: the write is a spec-kit ``Story``/``Plan`` that does NOT trace to
    a Spec, AND an active ``speckit-constitution`` Guardrail in the
    (tenant-resolved) scope declares ``severity: hard``. Otherwise warn (softer
    severities) or pass (no constitution / not spec-kit / already traceable).
    """
    if ctx.kind not in _GOVERNED_KINDS or not isinstance(ctx.raw, dict):
        return
    spec = ctx.raw.get("spec")
    if not isinstance(spec, dict) or not _is_spec_kit(ctx.kind, spec):
        return
    if _traces_to_spec(ctx.kind, spec):
        return  # already compliant — nothing to enforce.

    # Resolve the live constitution through the write's own (tenant-bound)
    # kernel so a per-tenant overlay of the constitution wins. Fail-open.
    kernel = ctx.kernel
    if kernel is None:
        return
    try:
        con = await kernel.get_document(
            ctx.scope, "Guardrail", _CONSTITUTION_NAME, tenant=ctx.tenant
        )
    except Exception as exc:  # noqa: BLE001 — governance must never be an outage.
        logger.debug("constitution guard: read failed, failing open: %s", exc)
        return
    if not isinstance(con, dict):
        return
    con_spec = con.get("spec") or {}
    if not isinstance(con_spec, dict) or con_spec.get("pattern") != _METHODOLOGY:
        return  # not a spec-kit constitution — do not govern.
    severity = str(con_spec.get("severity") or "warn").lower()

    detail = (
        f"the spec-kit constitution in scope {ctx.scope!r} requires every "
        f"governed {ctx.kind} to trace to a Spec "
        f"({'spec.spec_refs' if ctx.kind == 'Story' else 'spec.spec_ref'} is "
        f"missing on {ctx.name!r})."
    )
    if severity == "hard":
        raise ConstitutionViolationError(
            f"refusing to write {ctx.kind}/{ctx.name}: {detail} "
            f"Add the Spec link, or relax the constitution's severity "
            f"(no redeploy: `dna doc apply` a Guardrail with severity=warn)."
        )
    # error / warn → tolerate but surface loudly (the governance is advisory).
    logger.warning("constitution guard (severity=%s, advisory): %s", severity, detail)


def register_constitution_guard(kernel: Any) -> None:
    """Wire the spec-kit constitution guard as a ``pre_save`` veto hook.

    The key makes registration idempotent (re-loading the extension onto a
    shared HookRegistry replaces instead of stacking duplicates)."""
    kernel.hooks.on_veto(
        "pre_save", spec_kit_constitution_guard,
        priority=PRIORITY_CONSTITUTION, key="guardrails.spec-kit-constitution",
    )
