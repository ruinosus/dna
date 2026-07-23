"""ModelRegExtension — per-model capability/limit registry.

Registers 1 Kind, from a descriptor (F3 — record Kinds are data, not
classes):

  - ModelProfile (``modelreg-model-profile``) — hard limits
    (``instruction_token_cap``, ``context_window``, ``tools_cap``) +
    modalities + cost of one LLM model, as a first-class GLOBAL Kind so
    limits are project data, not implicit knowledge. Ported from the
    internal SDK's model registry, motivated by a real outage: a
    17269-token voice persona silently exceeded the realtime model's
    16384-token session-instructions cap because the cap lived in
    nobody's code.

CONTRACT — never hardcode token caps. The single source of truth for a
model's limits is its ModelProfile doc (``_lib`` scope,
``model-profiles/<model_id>.yaml``), resolved via
``kernel.model_profile(id_or_alias)``. The prompt-budget write guard
(``dna.extensions.helix.write_guards.prompt_budget_guard`` + TS twin)
reads the cap from there — a token-cap literal in code is a bug.

The Kind is GLOBAL (herdável ⇒ nunca TENANTED does not even apply: the
registry is base-only shared data with no per-tenant override) and NOT
inheritable — ``kernel.model_profile`` queries ``_lib`` directly
regardless of the caller's scope.
"""
from __future__ import annotations

from dna.kernel.source.descriptor_loader import load_descriptors
from dna.kernel.protocols import ExtensionHost


class ModelRegExtension:
    """Registers the ModelProfile Kind (descriptor-backed)."""

    name = "modelreg"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        # F3: ModelProfile ships as kinds/model-profile.kind.yaml package
        # data, registered through the SAME
        # funnel as per-scope KindDefinitions (plane lint + digest
        # idempotency + builtin conflict marker).
        for raw in load_descriptors("dna.extensions.modelreg"):
            kernel.kind_from_descriptor(raw)
