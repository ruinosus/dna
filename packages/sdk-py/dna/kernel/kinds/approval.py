"""The approval state of a Kind — THREE states, read in exactly one place.

Registration is what confers schema validation and storage routing, so the
registry's gate is the whole mechanism: a Kind that never registers has no
effect, and there is no second gate to keep in sync. i-085 adds the third state
to that gate, and the reason it cannot be the absence of the second is a
measured one:

    **Revoking is not the inverse of approving.** Removing the approval returns
    the Kind to *unregistered*, and an unregistered Kind's documents are
    accepted with NO validation at all. So a revocation implemented as a plain
    un-approval LOOSENS instead of tightening — it switches the gate off rather
    than closing it.

    state            existing documents      new documents
    ---------------- ---------------------- ---------------------------
    never approved   —                       accepted WITHOUT validation
    approved         valid, routed           validated against the schema
    revoked          INVALID                 REFUSED

Clearing ``approved_by`` is therefore indistinguishable from never having
approved, and the revoked fact has to be PERSISTED. It is persisted the way the
two acts already on this document are — by naming the actor of its own act
(``revoked_by``/``revoked_at`` beside ``proposed_by``/``approved_by``), so a
reader who understands the audit already understands this.

**Why this is a function and not a field somebody reads.** The failure mode a
third state invites is a fourth reader that checks ``approved_by`` and not
``revoked_by``, and quietly treats a revoked Kind as approved. So the fields are
never read directly: :func:`approval_state` is the ONE reader, it returns a
state rather than a field, and the states are exhaustive — there is no way to
ask "is it approved?" that silently answers yes for a revoked Kind. Downstream
of the funnel nobody reads the document at all: the state becomes a fact ON THE
REGISTERED PORT (``__revoked__``), which is the surface every behaviour-
conferring path already consults.

**Mutual exclusion is maintained by the two ACTS, not by comparing timestamps.**
Approving clears the revocation; revoking stamps it and leaves ``approved_by``
standing (the audit must keep who conferred effect in the first place). Ordering
by ``approved_at`` vs ``revoked_at`` would make the current state depend on
caller-supplied strings from possibly-skewed clocks in possibly-different
formats — a state machine arbitrated by data nobody validates.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

__all__ = ["APPROVED", "REVOKED", "UNAPPROVED", "approval_state"]

#: Authored, never approved. Parsed, logged, NOT registered — and therefore
#: without effect: its documents are accepted unvalidated and unrouted.
UNAPPROVED: Final = "unapproved"

#: A human conferred effect. Registered: documents validate against the schema
#: and route to the declared storage.
APPROVED: Final = "approved"

#: The workspace changed its mind. Registered — deliberately, because being
#: KNOWN is what stops revocation from meaning "accepts anything" — but marked,
#: so new documents are refused and existing ones read back invalid.
REVOKED: Final = "revoked"


def _identity(spec: Any, field: str) -> str:
    """The stripped identity string at ``spec.<field>``, or ``""``.

    Accepts both shapes the two funnels hold: a raw ``dict`` (the store, the
    application doors, ``Module.spec.custom_kinds`` entries) and a
    :class:`~dna.kernel.models.KindDefinitionSpec` dataclass (the typed parse).
    A non-string is ``""`` — ``approved_by: true`` names no one, and the same
    must hold for a revoker."""
    value = (
        spec.get(field) if isinstance(spec, Mapping) else getattr(spec, field, None)
    )
    return value.strip() if isinstance(value, str) else ""


def approval_state(spec: Any) -> str:
    """The Kind's current state — :data:`UNAPPROVED`, :data:`APPROVED` or
    :data:`REVOKED`.

    Revocation wins over approval when both are recorded, and that is not a
    tie-break: revoking deliberately LEAVES ``approved_by`` in place so the
    audit keeps who conferred effect, and approving deliberately CLEARS the
    revocation. Both markers present is therefore exactly one situation — a Kind
    that was approved and then revoked.
    """
    if _identity(spec, "revoked_by"):
        return REVOKED
    if _identity(spec, "approved_by"):
        return APPROVED
    return UNAPPROVED
