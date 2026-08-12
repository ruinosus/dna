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

* where a store **does** expose a watermark, this module reads it — one cheap
  call, and the number is the store's own;
* where it does **not**, the watermark is **computed**: a digest over the
  ``(name, spec-etag)`` pairs of the slice being listed.

⭐ **The fallback is a cost, deliberately paid, and not a lie.** Three answers
were on the table and two of them were dishonest:

``null``
    says *"I cannot tell you which moment this is"*, which is true — but §6.2
    requires a revision, §8's client rule 2 requires clients to treat it as
    opaque, and a ``null`` invites a client to read it as *absent* instead. It
    also makes rule 3 (constant across pages) vacuous: two pages both reporting
    ``null`` agree about nothing.

a minted token (a uuid, a timestamp)
    is opaque and constant and **means nothing**. A client comparing two such
    tokens would draw conclusions from a number the server invented. That is
    §7's rule — *an empty result and an unanswerable question are different
    values* — applied to a scalar, and it is the worse of the two failures
    because it looks like an answer.

a content digest
    is a TRUE statement: *these rows came from this state*. Opaque, constant
    across the pages of one listing, and it changes when anything in the slice
    changes. It costs one extra pass over the slice's ``(name, etag)`` pairs.

The digest is what ships. ⚠️ **It is a fallback, not a design**: it is O(n) per
listing, and a store that exposes a sequence supersedes it at O(1).
``initialize`` reports which of the two a connection is getting, so a client
can tell an O(1) watermark from an O(n) one rather than discovering the cost in
a latency graph.

The probe is **duck-typed on the method**, mirroring
:func:`dna.memory.as_of.store_supports_as_of` — the established precedent in
this repo for a source capability that not every adapter has and that no
Protocol declares.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

__all__ = [
    "CHANNEL_REVISION_METHOD",
    "channel_revision",
    "digest_revision",
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

    ``None`` means *"this store exposes no sequence"* — the caller then computes
    :func:`digest_revision` instead. A failure to *read* an available watermark
    is **not** turned into ``None``: it propagates, because a store that has the
    capability and could not use it is the unanswerable case, and collapsing it
    into the "no capability" answer is the §7 sin one layer down.
    """
    src = _source_of(kernel)
    fn = getattr(src, CHANNEL_REVISION_METHOD, None)
    if not callable(fn):
        return None
    value = await fn(scope, tenant=tenant)
    return None if value is None else str(value)


def digest_revision(pairs: Iterable[tuple[str, str]]) -> str:
    """A watermark computed from content — the honest fallback.

    ``pairs`` is ``(name, etag)`` for every instance in the slice. Sorted before
    hashing, so the digest is a property of the SET and not of the order the
    store happened to yield it in; a store whose iteration order changed would
    otherwise report a moved channel and expire every cursor for nothing.

    The empty slice gets a digest too, and a stable one. *"Nothing of this Kind
    exists here"* is a state like any other, and a listing of it belongs to a
    snapshot exactly as much as a full one does.
    """
    hasher = hashlib.sha256()
    for name, etag in sorted(pairs):
        hasher.update(name.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(etag.encode("utf-8"))
        hasher.update(b"\x00")
    return hasher.hexdigest()[:32]
