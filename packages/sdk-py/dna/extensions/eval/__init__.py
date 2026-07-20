"""EvalExtension — evaluation authoring as data + a LOCAL runner.

Registers 4 Kinds, all from descriptors (F3 — record Kinds are data, not
classes):

  - EvalCase     (``eval-eval-case``)     — one scenario: target + checks
  - EvalSuite    (``eval-eval-suite``)    — groups cases + run config
  - EvalRun      (``eval-eval-run``)      — persisted execution result
  - EvalBaseline (``eval-eval-baseline``) — pinned "known good" run

Tier B port from the internal SDK's eval extension (s-dna-eval-kit).
What travels vs what does not (honest evolution):

  - The AUTHORING VOCABULARY travels: a case declares WHAT to evaluate
    (``target``) and HOW to judge it (deterministic ``checks``); a suite
    groups cases; a run is the persisted ledger; a baseline is the pinned
    reference future runs are compared against.
  - The upstream RUNNER does not: it was a Temporal worker driving live
    agents through LLM judges (trajectory matching, HITL policies,
    deepeval engines, red-team orchestration). A notation SDK ships none
    of that. Instead the local runner (:mod:`dna.extensions.eval.runner`)
    is a pure, synchronous library over the kernel: the DEFAULT target is
    the kernel itself — ``target: {type: prompt, agent: X}`` composes
    ``build_prompt(agent=X)`` and applies the checks to the composed
    prompt. Deterministic, offline, and a real evaluation of declarative
    config ("does my agent compose what I expect?" is the thesis).
  - LLM / live-system targets are an EXTENSION POINT the host registers
    (:class:`~dna.extensions.eval.runner.EvalTargetPort` — the same
    declare-here/execute-in-the-host split as Automation runners and the
    CLI's post-transition hooks). Example in
    docs/guides/evaluating-agents.md.

tenant_scope intentionally NOT declared on any of the four (permissive:
base + per-tenant overlay) — the Evidence/Automation precedent.
"""
from __future__ import annotations

from dna.extensions.eval.runner import (
    CHECK_TYPES,
    EvalTargetPort,
    PromptCompositionTarget,
    apply_checks,
    compare,
    run_suite,
)
from dna.kernel.descriptor_loader import load_descriptors
from dna.kernel.protocols import ExtensionHost


class EvalExtension:
    """Registers the four Eval Kinds (descriptor-backed)."""

    name = "eval"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        # F3: the Kinds ship as kinds/*.kind.yaml package data
        # (declarative descriptors), registered through the SAME
        # funnel as per-scope KindDefinitions (plane lint + digest
        # idempotency + builtin conflict marker).
        for raw in load_descriptors("dna.extensions.eval"):
            kernel.kind_from_descriptor(raw)


__all__ = [
    "CHECK_TYPES",
    "EvalExtension",
    "EvalTargetPort",
    "PromptCompositionTarget",
    "apply_checks",
    "compare",
    "run_suite",
]
