"""``status`` — the DERIVED half of a document, and where "invalid" is said.

i-085 needed a place to say *this document is invalid because its Kind was
revoked*, and the search for one is worth recording, because the obvious answers
are wrong in instructive ways.

**There is no single read envelope to extend.** The kernel has three read
shapes, not one: ``get_document``/``query`` hand back RAW DICTS (what every
hosted face consumes), the sync wrappers and a ``ManifestInstance`` hand back
:class:`~dna.kernel.document.Document`, and ``resolve_document`` hands back a
:class:`~dna.kernel.query.resolver.ResolvedDocument` — the only real envelope,
and the one nothing on the read path of a face actually uses. So a new envelope
would have been a fourth shape that only the code written to look for it would
ever see, and the mark has to ride IN the document.

**But it must not become a STAMP on the document.** Validity follows the Kind's
CURRENT state — that is what makes revocation reversible in one act — so a
marker persisted into the store would be a lie the moment the Kind is approved
again. Two things keep it derived: it is computed at READ time from the
registry, and :func:`strip_derived_status` removes it on every write, so the
read-modify-write pattern that is everywhere in the application layer
(``{**raw, "spec": spec}``) cannot round-trip it back into the store.

**Why the key is ``status``.** DNA's own one-line description of itself is
"Kubernetes CRDs for agentic behavior", and a Kubernetes object is exactly this
split: ``spec`` is what an author declared, ``status`` is what the system
observed. DNA had only ever used the first half. Nothing needed inventing — the
shape was already implied by the notation, and a reader who knows CRDs needs no
explanation of which half is authoritative.

**Absent means nothing to report, not "valid".** ``status`` is written only when
there IS something derived to say, which today is exactly one thing. Stamping
``valid: true`` on every row of every query would cost a dict copy per row on
the hot path to carry no information, and would still not mean "verified" —
only "the kernel had nothing against it", which is what absence already says.
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "KIND_REVOKED",
    "STATUS_KEY",
    "invalid_status",
    "is_marked_invalid",
    "mark_invalid",
    "strip_derived_status",
]

#: The reserved top-level key. Reserved by the write path, not by convention:
#: :func:`strip_derived_status` drops it from every write, so a stored document
#: can never carry a forged or stale one.
STATUS_KEY = "status"

#: The one reason there is. A machine-readable token beside the prose, because a
#: surface deciding how to RENDER an invalid document must not have to match on
#: an English sentence.
KIND_REVOKED = "kind_revoked"


def invalid_status(*, reason: str, message: str) -> dict[str, Any]:
    """The derived status block for an invalid document."""
    return {"valid": False, "reason": reason, "message": message}


def revoked_kind_status(kind: str, api_version: str | None = None) -> dict[str, Any]:
    """The status block for a document whose Kind was revoked.

    The message says what happened AND that the document is intact, because the
    first question a person reading this has is whether their data survived."""
    which = f"{api_version}/{kind}" if api_version else kind
    return invalid_status(
        reason=KIND_REVOKED,
        message=(
            f"the Kind {which} has been revoked, so this document is no longer "
            f"valid. It is unchanged and still readable — nothing was deleted. "
            f"Approving the Kind again restores its validity."
        ),
    )


def mark_invalid(raw: Any, status: dict[str, Any]) -> Any:
    """``raw`` with ``status`` attached — a SHALLOW COPY, never a mutation.

    Mutating would be the cheaper thing and the wrong one: ``get_document``
    serves out of a bounded TTL cache, so stamping the cached object would leave
    the mark behind after the Kind is approved again — the exact
    stamp-on-the-document failure this module exists to avoid. The copy is
    shallow because only the top level changes."""
    if not isinstance(raw, dict):
        return raw
    return {**raw, STATUS_KEY: status}


def is_marked_invalid(raw: Any) -> bool:
    """Whether ``raw`` carries a derived status that says it is not valid."""
    if not isinstance(raw, dict):
        return False
    status = raw.get(STATUS_KEY)
    return isinstance(status, dict) and status.get("valid") is False


def strip_derived_status(raw: Any) -> Any:
    """``raw`` without its derived ``status`` — what the write path persists.

    Dropped silently rather than refused, deliberately: a caller that read a
    marked document and wrote it back (the application layer does this
    constantly — ``{**raw, "spec": spec}``) is doing nothing wrong, and failing
    its write would turn a derived annotation into a trap. What must not happen
    is the annotation reaching the STORE, where a later read would replay it as
    fact after the Kind was approved again.

    Returns ``raw`` itself when there is nothing to strip, so the ordinary write
    pays no copy."""
    if not isinstance(raw, dict) or STATUS_KEY not in raw:
        return raw
    return {k: v for k, v in raw.items() if k != STATUS_KEY}
