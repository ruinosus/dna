"""``revision`` — and the honest answer when the store cannot supply one.

DNAP has two revisions and they answer two questions:

``metadata.revision`` (spec §5)
    *"is the instance I based my edit on still the stored instance?"* — served
    by :func:`dna.kernel.etag.spec_etag`, the SDK's own optimistic-concurrency
    token, which is exactly what ``ifMatch`` / ``ifNoneMatch`` compare. It is a
    **content fingerprint**, not a counter.

the listing ``revision`` (spec §6.2 rule 3)
    *"which snapshot do these pages belong to?"* — a **channel watermark**, and
    the SDK has no port that exposes one.

⚠️ **The gap, stated rather than papered over.** Spec §5 calls
``metadata.revision`` "opaque, monotonic per channel". The reference store has
a per-``(scope, tenant)`` monotonic checkpoint — ``dna_versions_seq.last_id``,
upserted atomically with every write — but it is **Postgres-only** and private
to :class:`~dna.adapters.postgres.eventbus.PostgresEventBus`; no
``SourcePort``/``WritableSourcePort`` member exposes it, the SQLite schema sets
it to ``None``, and the filesystem source has nothing like it. So:

* where a store **does** expose a watermark, this module reads it, the cursor
  pins it, and a watermark that moved mid-listing answers ``-32005
  CURSOR_EXPIRED`` — the client restarts rather than assembling "a quilt of
  moments and calling it a state";
* where it does **not**, the listing reports ``revision: null`` and
  ``initialize`` advertises ``revisions.channelWatermark: false``.

The second bullet is the whole point. Minting a plausible token would claim a
snapshot isolation the read does not have, and a client comparing two such
tokens would draw conclusions from a number the server invented — the §7 rule
(*an empty result and an unanswerable question are different values*) applied
to a scalar. ``null`` says "I cannot tell you which moment this is", which is
true, and the capability flag says it once at connect time so no client has to
discover it per call.

The probe is **duck-typed on the method**, mirroring
:func:`dna.memory.as_of.store_supports_as_of` — the established precedent in
this repo for a source capability that not every adapter has and that no
Protocol declares.
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "CHANNEL_REVISION_METHOD",
    "channel_revision",
    "store_supports_channel_revision",
]

#: The duck-typed member a source implements to serve a channel watermark::
#:
#:     async def channel_revision(self, scope: str, *, tenant: str | None) -> str
#:
#: It must return an OPAQUE token that changes when anything in
#: ``(scope, tenant)`` changes, and must not change otherwise. No adapter in
#: this repo implements it yet — see the module docstring.
CHANNEL_REVISION_METHOD = "channel_revision"


def _source_of(kernel: Any) -> Any | None:
    return getattr(kernel, "_source", None)


def store_supports_channel_revision(kernel: Any) -> bool:
    """Can this kernel's store say which moment a listing belongs to?"""
    return callable(
        getattr(_source_of(kernel), CHANNEL_REVISION_METHOD, None)
    )


async def channel_revision(
    kernel: Any, scope: str, *, tenant: str | None = None,
) -> str | None:
    """The channel's watermark, or ``None`` when the store has none.

    ``None`` is an ANSWER — "this store cannot date a snapshot" — and it is the
    only value that may stand in for a watermark. A failure to *read* an
    available watermark is not turned into ``None``: it propagates, because a
    store that has the capability and could not use it is the unanswerable case,
    and collapsing it into the "no capability" answer is the §7 sin one layer
    down.
    """
    src = _source_of(kernel)
    fn = getattr(src, CHANNEL_REVISION_METHOD, None)
    if not callable(fn):
        return None
    value = await fn(scope, tenant=tenant)
    return None if value is None else str(value)
