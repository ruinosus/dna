"""Helix-owned write-path guards (s-write-path-despecialize).

These rules used to live inline in ``Kernel._write_document_inner`` as
``kind == "Agent"`` special-cases — extension domain knowledge leaked
into the microkernel. They are now ``pre_save`` VETO hooks registered by
``HelixExtension.register`` (the extension that owns Agent):

- platform-agent fork guard  (priority 10) — no per-tenant overlay of a
  ``_lib`` Agent (JARVIS 16384 outage, 2026-05-29).
- prompt-budget enforcement  (priority 20) — an Agent whose instruction
  exceeds its model's ``instruction_token_cap`` (read from the ModelProfile
  registry — never hardcode token caps) is blocked when the model is
  strict (voice persona / ``realtime: true`` profile) and warned when it
  is a chat model (fail-open on unknown model / missing cap /
  instruction_file).
- Kind-Writer contract       (priority 30) — a Agent declaring
  ``writes_kind`` must satisfy the slot↔schema contract at write time.

A raise from a guard vetoes the write (nothing is persisted). The hooks fire
for EVERY ``kernel.write_document`` regardless of ``skip_hooks`` — they are
integrity gates, not notifications.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dna.kernel.hooks import PreSaveContext

from dna.kernel.protocols import DEFAULT_BASE_SCOPE, TenantNotAllowed

logger = logging.getLogger(__name__)

_KIND = "Agent"

# Ordered ahead of other extensions' guards (SDLC bitemporal = 40).
PRIORITY_FORK_GUARD = 10
PRIORITY_PROMPT_BUDGET = 20
PRIORITY_KIND_WRITER = 30


def platform_agent_fork_guard(ctx: PreSaveContext) -> None:
    """Block per-tenant overlays of ``_lib`` Agents.

    The `_lib` scope is the shared baseline (jarvis + the 12 transversais);
    its Agents are edited in git + ``dna doc apply --scope _lib``
    (base only). A per-tenant overlay silently FORKS the persona and shadows
    the base for that tenant's reads — the root cause of the JARVIS 16384
    outage (2026-05-29) and the stale-persona bug (2026-06-14,
    DNA_TENANT=acme pollution forked jarvis/insights-oracle/
    briefing-conductor). Veto it loudly so the anti-pattern surfaces
    instead of corrupting reads.
    """
    if ctx.scope == DEFAULT_BASE_SCOPE and ctx.kind == _KIND and ctx.tenant:
        raise TenantNotAllowed(
            f"refusing a per-tenant overlay of the _lib agent {ctx.name!r} "
            f"(tenant={ctx.tenant!r}). _lib agents are base-only — "
            f"edit in git + `dna doc apply --scope _lib`. A tenant fork "
            f"shadows the base persona for that tenant (JARVIS 16384 outage)."
        )


async def prompt_budget_guard(ctx: PreSaveContext) -> None:
    """Enforce the Agent instruction budget against the ModelProfile registry.

    CONTRACT — never hardcode token caps: the cap ALWAYS comes from the
    ModelProfile registry (``kernel.model_profile(id_or_alias)`` → the
    ``modelreg-model-profile`` Kind in ``_lib``), never from a literal in
    code. Forcing function for a real outage: an over-cap voice persona
    silently degraded the realtime session because the cap lived in
    nobody's code.

    Three paths (s-tier-a-modelprofile):

    - **VETO** — the write targets a STRICT model (the Agent has a
      ``voice_persona``, or the resolved profile declares
      ``realtime: true``) and the instruction estimate exceeds the
      profile's ``instruction_token_cap``. The raise aborts the write with
      a didactic error.
    - **WARN** — a chat Agent (``spec.model`` declared, non-realtime
      profile) exceeds the cap: over-budget is tolerated (chat models
      truncate gracefully) but logged loud.
    - **PASS** — no model declared, no ModelProfile found, no cap on the
      profile, or instruction within budget. Enforcement is opt-in by
      DATA: writing a profile with a cap arms the guard.

    Token estimate: conservative chars/3.5 heuristic
    (``dna.kernel.prompt_budget``) — over-counts on purpose so the guard
    never under-blocks. Fail-open on uncounted text (instruction_file /
    non-string body): warn + proceed, never block on text we didn't count.
    ``DNA_PROMPT_BUDGET_ENFORCE=0`` downgrades the veto to a warn
    (ops kill-switch).
    """
    if ctx.kind != _KIND or not isinstance(ctx.raw, dict):
        return
    spec = ctx.raw.get("spec") or {}
    if not isinstance(spec, dict):
        return
    vp = spec.get("voice_persona")
    is_voice = vp is not None
    if is_voice:
        model_id = (
            (vp.get("model") if isinstance(vp, dict) else None)
            # s-realtime-model-single-default — the kernel property reads
            # DNA_VOICE_REALTIME_MODEL at access-time so the cap and the
            # minted voice session can't drift to different realtime models.
            or ctx.kernel._DEFAULT_REALTIME_MODEL
        )
    else:
        model_id = spec.get("model")
        if not model_id or not isinstance(model_id, str):
            return  # PASS — no model declared, nothing to enforce against.
    from dna.kernel.prompt_budget import (  # noqa: PLC0415
        evaluate_instruction_budget, PromptBudgetExceededError,
    )
    profile = await ctx.kernel.model_profile(model_id)
    instruction = spec.get("instruction") or ""
    if not isinstance(instruction, str):
        instruction = ""  # non-string body → uncounted → fail-open (warn below)
    # v1 limitation: no cheap kernel helper resolves instruction_file here;
    # if the body lives in a file, warn + fail-open (don't block on
    # uncounted text).
    if not instruction and spec.get("instruction_file"):
        logger.warning(
            "[prompt-budget] agent '%s' uses instruction_file; "
            "token budget NOT checked (v1 limitation)", ctx.name,
        )
    cap = ((profile or {}).get("spec") or {}).get("instruction_token_cap")
    if profile is None or cap is None or not instruction:
        # PASS — enforcement is opt-in: no profile / no cap / uncounted
        # text never blocks. Voice stays LOUD (the outage class this guard
        # exists for); a chat model without a profile is the common case
        # and stays quiet.
        if is_voice:
            logger.warning(
                "[prompt-budget] no ModelProfile/cap for model '%s' "
                "(agent '%s'); cap not enforced", model_id, ctx.name,
            )
        return
    verdict = evaluate_instruction_budget(instruction, cap=cap)
    if not verdict.exceeded:
        return  # PASS — within budget.
    strict = is_voice or bool((profile.get("spec") or {}).get("realtime"))
    if strict and os.environ.get("DNA_PROMPT_BUDGET_ENFORCE") != "0":
        raise PromptBudgetExceededError(
            model_id=model_id,
            estimated_tokens=verdict.estimated_tokens,
            cap=cap, agent_name=ctx.name,
        )
    # WARN — chat model over budget, or strict veto downgraded by the
    # kill-switch. Loud either way: the cap came from the ModelProfile
    # registry, the fix is trimming the instruction (or updating the
    # profile if the model's real cap changed — never a hardcoded number).
    logger.warning(
        "[prompt-budget] agent '%s' instruction is ~%d tokens, over the "
        "%d-token instruction_token_cap of model '%s' (ModelProfile "
        "registry)%s. Trim the instruction or move detail to "
        "tool-discoverable docs.",
        ctx.name, verdict.estimated_tokens, cap, model_id,
        " — VETO downgraded to WARN (DNA_PROMPT_BUDGET_ENFORCE=0)"
        if strict else "",
    )


def kind_writer_contract_guard(ctx: PreSaveContext) -> None:
    """Validate a Kind-Writer Agent's slot↔schema contract.

    A Agent that declares ``writes_kind`` is a Kind-Writer: it emits
    a structured document of the target Kind. Validate the contract at
    write time (fail early), not at runtime (feat/kind-writer-pilot, Task 2).
    """
    if ctx.kind != _KIND or not isinstance(ctx.raw, dict):
        return
    spec = ctx.raw.get("spec") or {}
    if isinstance(spec, dict) and (
        spec.get("writes_kind") or spec.get("writes_kinds")
    ):
        from dna.kernel.models import AgentSpec  # noqa: PLC0415
        ctx.kernel._validate_kind_writer(AgentSpec.from_raw(spec))


def register_write_guards(kernel: Any) -> None:
    """Wire the Helix write guards as ``pre_save`` veto hooks.

    Keys make the registration idempotent (re-loading the extension onto a
    shared HookRegistry replaces instead of stacking duplicates).
    """
    kernel.hooks.on_veto(
        "pre_save", platform_agent_fork_guard,
        priority=PRIORITY_FORK_GUARD, key="helix.platform-agent-fork-guard",
    )
    kernel.hooks.on_veto(
        "pre_save", prompt_budget_guard,
        priority=PRIORITY_PROMPT_BUDGET, key="helix.prompt-budget",
    )
    kernel.hooks.on_veto(
        "pre_save", kind_writer_contract_guard,
        priority=PRIORITY_KIND_WRITER, key="helix.kind-writer-contract",
    )
