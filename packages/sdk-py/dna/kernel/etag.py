"""The optimistic-concurrency token — one definition, both layers.

``spec_etag`` was written for the generic write use-case
(:mod:`dna.application.documents`), where it guards a read-modify-write in
APPLICATION code. i-083 needed the same guarantee one layer down, on
``kernel.write_document``, so that the adapter — not a cache — decides whether
the document moved. Adapters may import ``dna.kernel.*`` and nothing above it,
so the function lives here and ``dna.application.documents`` re-exports it.

**ONE definition is the point, not tidiness.** The token
:func:`~dna.application.documents.get_document_impl` hands a caller is the token
``kernel.write_document`` checks; two hashes of the same bytes that disagreed by
a sort order or a separator would refuse every honest write while letting a
stale one through, and the failure would look like flakiness rather than a bug.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

__all__ = ["spec_etag", "check_if_match"]


def spec_etag(spec: Any) -> str:
    """A content fingerprint of a document ``spec`` — the optimistic-concurrency
    token ``get_document`` returns and ``write_document`` checks (``if_match``).

    Deliberately NOT the adapter's version id: ``kernel.write_document`` returns
    one, but nothing on the READ path exposes it (``get_document`` yields the raw
    document and nothing else), and version support is per-adapter — the
    filesystem source has none, and answers ``"1"`` to every write. A hash of the
    content the tool actually writes is available on every adapter, is derivable
    by the caller from the very read it already made, and answers the only
    question that matters here: *is the spec I based my update on still the
    stored spec?*

    That last property is what makes it usable at the ADAPTER too (i-083): an
    adapter can recompute this from the bytes it has stored, with no version
    column and no extra column to add. A version id would first have to be
    threaded onto the read path — and would still be unavailable on the
    filesystem store.

    Keyed on the ``spec`` alone because the ``spec`` is all a generic write can
    change — the envelope is rebuilt from the resolved Kind port every time. It
    also means the token is stable across the envelope churn a write path may
    legitimately introduce (an ``apiVersion`` alias resolving differently, a
    ``metadata`` key the writer normalises), so the guard fires on CONTENT
    divergence and not on incidental re-shaping. Sorted keys + ``default=str``
    make it stable across processes and tolerant of non-JSON scalars a Kind may
    store.
    """
    payload = json.dumps(spec or {}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def check_if_match(
    stored: Any, if_match: str, *, scope: str, kind: str, name: str,
    tenant: str | None = None,
) -> None:
    """Raise :class:`~dna.kernel.errors.StaleDocumentWrite` unless ``stored`` —
    the document AS THE STORE HOLDS IT — still hashes to ``if_match``.

    Shared by every adapter that declares the ``if_match`` write kwarg. One
    implementation because the two halves that would drift are the ones that
    matter: the *absent document* verdict (a delete between the read and the
    write is a stale write, not a create — see below), and the wording of the
    refusal, which is the only thing telling a caller that the remedy is to
    re-read rather than to retry the same bytes.

    ``stored is None`` is a REFUSAL, not a pass-through create. ``if_match``
    asserts "I am updating the document I read"; a document that vanished
    between the read and the write did not satisfy that assertion, and turning
    the update into a create would resurrect a document somebody deleted, with
    the deleter's change lost — the same lost update by a different route.
    """
    if stored is not None:
        spec = stored.get("spec") if isinstance(stored, dict) else None
        current = spec_etag(spec)
        if current == if_match:
            return
        detail = (
            f"changed since you read it (if_match={if_match!r}, "
            f"now {current!r})"
        )
    else:
        detail = (
            f"no longer exists (if_match={if_match!r}) — it was deleted between "
            f"your read and this write"
        )

    from dna.kernel.errors import StaleDocumentWrite

    where = f"scope {scope!r}" + (f" (tenant={tenant!r})" if tenant else "")
    raise StaleDocumentWrite(
        f"{kind} {name!r} in {where} {detail} — refusing so your update does "
        f"not overwrite somebody else's. Re-read the document and re-apply "
        f"your change to the fresh etag."
    )
