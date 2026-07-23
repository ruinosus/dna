"""AutomationExtension — declarative background automation as data.

Registers 1 Kind, from a descriptor (F3 — record Kinds are data, not
classes):

  - Automation (``dna-automation``) — one doc declares WHEN background
    work fires (``on: {type: cron|hook|tool, ...}``) and WHAT runs
    (``runner: {kind: agent|tool, ref}`` + ``agent_directive`` /
    ``input`` / result templating / spoken copy / ``safety``). Tier A
    port from the internal SDK's automation extension
    (s-tier-a-automation) — upstream, this Kind unified an async-tool /
    bus-event / cron trio and killed hardcoded dispatch: adding or
    retargeting an automation is writing one YAML, zero deploy.

What travels vs what does not (honest evolution):

  - The DECLARATION travels: the Kind (descriptor), write-time validation
    (``write_guards``: 5-field cron parse + hook names against the
    kernel's typed ``KNOWN_HOOK_NAMES`` vocabulary) and the query helpers
    (``query.automations_for`` / ``query.trigger_key``) a host executor
    reads.
  - EXECUTION does not: the SDK has no scheduler, bus or worker. The host
    reads Automation docs via the query helpers and runs them — the same
    declare-here/execute-in-the-host pattern as the CLI's
    ``register_post_transition_hook``. The runner contract + a minimal
    example live in docs/concepts/builtin-kinds.md.

Inheritable ⇒ never TENANTED (s-inheritable-kinds-tenancy-invariant):
Automation is an inheritable ``_lib`` default (it is in
``DEFAULT_INHERITABLE_KINDS_V1``) → tenancy PERMISSIVE (no ``tenant_scope``
in the descriptor): base writable in ``_lib`` + per-tenant override via
overlay.
"""
from __future__ import annotations

from dna.extensions.automation.query import (
    TRIGGER_TYPES,
    automations_for,
    trigger_key,
)
from dna.extensions.automation.write_guards import (
    register_write_guards,
    validate_cron_expression,
)
from dna.kernel.source.descriptor_loader import load_descriptors
from dna.kernel.protocols import ExtensionHost


class AutomationExtension:
    """Registers the Automation Kind (descriptor-backed) + write guards."""

    name = "automation"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        # F3: Automation ships as kinds/automation.kind.yaml package data
        # (a declarative descriptor), registered through the SAME funnel
        # as per-scope KindDefinitions (plane lint + digest idempotency +
        # builtin conflict marker).
        for raw in load_descriptors("dna.extensions.automation"):
            kernel.kind_from_descriptor(raw)
        # Write-time semantic validation the JSON Schema cannot express:
        # cron expression parse + hook-name vocabulary (pre_save veto,
        # helix write_guards pattern).
        register_write_guards(kernel)


__all__ = [
    "AutomationExtension",
    "TRIGGER_TYPES",
    "automations_for",
    "trigger_key",
    "validate_cron_expression",
]
