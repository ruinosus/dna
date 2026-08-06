"""Transaction time — reading what the system BELIEVED at a past instant.

DNA has had **world time** since the Engram Kind existed: ``valid_from`` and
``valid_to`` say *when a fact was true*. What it did not have is **transaction
time** — *when this system came to believe it*. The two are independent, and
only the second answers the question this module exists for:

    "What did the system believe at T-1?"

They come apart the moment a memory is recorded late or corrected. A note
written today about last year is **valid** last year and **believed** today; a
world-time read at last year finds it, a transaction-time read at last year must
not. That asymmetry is the whole reason ``recall(now=...)`` was never an answer
to this question: ``now=`` shifts the world-time filter and still hands back
*today's* spec for every hit.

**No new column.** ``dna_versions.created_at`` has been the transaction stamp
since schema revision 0001, and ``content`` holds the FULL envelope per write —
not a diff, not a pointer. The belief state was already on disk; nothing read it.
So this is a read, a parameter and a refusal, and no migration.

Three honesty rules, each of which the alternative would quietly violate:

1. **A store that cannot answer must refuse, not approximate.** The filesystem
   adapter declares ``versions=True`` and keeps no history at all
   (``list_versions`` → ``[]``). Serving the current instance under a past
   timestamp would be a fabricated answer wearing a real one's clothes, so
   :func:`resolve_as_of` raises :class:`AsOfUnsupported` instead. The capability
   is askable up front via :func:`store_supports_as_of`.
2. **"Not recorded" is not "not remembered".** ``VERSION_CHURN_RETENTION`` caps
   Engram at 3 retained versions precisely because autopilot rewrites the same
   memory thousands of times — so history genuinely runs out. When it does,
   :class:`AsOfResolution` comes back ``truncated``, and the caller reports the
   blind spot rather than reading "there was no such memory" out of "there is no
   such record".
3. **A historical read must not write.** ``recall`` reconsolidates every hit it
   surfaces (a cue append + a confidence bump). Under ``as_of`` that is a
   contradiction — the past does not get more confident because you looked at
   it — so the caller turns it off.

See ``Research/rsh-semantica-agi-avaliacao`` (finding
``f-lacuna-tempo-de-transacao-e-as-of``): the design reference is
``semantica/kg/temporal_query.py``'s ``query_at_time`` / ``reconstruct_at_time``,
read and discarded — we took the shape of the API, not the package.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from dna.kernel.errors import CapabilityRefusal

__all__ = [
    "AsOfResolution",
    "AsOfTruncated",
    "AsOfUnsupported",
    "normalize_as_of",
    "resolve_as_of",
    "store_supports_as_of",
]


class AsOfUnsupported(CapabilityRefusal, RuntimeError):
    """The store cannot answer a transaction-time read.

    Raised rather than degraded. A caller that asked "what did you believe at
    T?" and silently got "what you believe now" would hold a belief about the
    past it has no basis for — worse than not offering the read at all. The same
    reasoning the write path applies to ``if_absent``: refuse rather than
    degrade.

    A :class:`~dna.kernel.errors.CapabilityRefusal`: what is missing is a
    capability of the ADAPTER, so the remedy is a different deployment and never
    a different request. Still a ``RuntimeError`` — additive, so nothing that
    caught it before sees a change.
    """


class AsOfTruncated(CapabilityRefusal, LookupError):
    """History for THIS instance was pruned past ``as_of`` — the store cannot know.

    The sibling of :class:`AsOfUnsupported`, one granularity down: that one says
    *this deployment never retains history*, this one says *it does, and the
    stretch you asked about is gone* (``VERSION_CHURN_RETENTION`` caps Engram at
    3 versions precisely because autopilot rewrites the same memory thousands of
    times). Both are refusals; neither may degrade into today's state.

    It exists for the surfaces that resolve ONE instance, where the list
    surfaces' answer — collect the names into ``as_of_truncated`` beside the
    hits — has nowhere to live: a single-instance read either hands back a
    belief state or says it cannot. ``LookupError`` and not ``RuntimeError`` so
    the "nothing came back" family stays one family, and the *reason* is what
    distinguishes it: a plain ``LookupError`` means the instance DID NOT EXIST
    yet at ``as_of``, which is an ANSWER. Collapsing the two would let a caller
    read "there was no such instance" out of "there is no such record" — the one
    mistake a history read must never make (see :class:`AsOfResolution`).

    Also a :class:`~dna.kernel.errors.CapabilityRefusal`, and that second base
    is what keeps the distinction above ALIVE across a face. Being a
    ``LookupError`` is precisely why this one already fell inside tuples the
    faces caught — and being caught as a bare ``LookupError`` is exactly how it
    would be relayed as *"it did not exist yet"*, the collapse this class was
    created to prevent. The marker base lets a face catch it BEFORE the plain
    ``LookupError`` arm and name it.
    """


@dataclass(frozen=True)
class AsOfResolution:
    """One instance, resolved at a transaction instant.

    ``raw`` is ``None`` in two very different situations, and ``truncated`` is
    what tells them apart:

    ===============  ==========  ==================================================
    ``raw``          ``truncated``  meaning
    ===============  ==========  ==================================================
    envelope         ``False``   this is what the store believed at ``as_of``
    ``None``         ``False``   the instance DID NOT EXIST yet — an answer
    ``None``         ``True``    history was pruned past ``as_of`` — a refusal
    ===============  ==========  ==================================================
    """

    raw: dict[str, Any] | None = None
    version: int | None = None
    recorded_at: str | None = None
    truncated: bool = False

    @property
    def found(self) -> bool:
        return self.raw is not None

    @property
    def spec(self) -> dict[str, Any]:
        return dict((self.raw or {}).get("spec") or {})


def normalize_as_of(as_of: datetime | str) -> str:
    """Canonical ISO-8601 **UTC** string for comparison against ``created_at``.

    ``created_at`` is written by the adapter's ``_now()`` —
    ``datetime.now(timezone.utc).isoformat()`` — and compared as TEXT. ISO-8601
    with fixed-width fields and one fixed offset sorts lexicographically in
    chronological order, so the comparison is sound *only* while both sides are
    normalized the same way. Hence this function, rather than each caller
    formatting by hand.

    A naive datetime is read as UTC (never as local time: a local-time reading
    would silently shift the answer by the developer's offset).
    """
    if isinstance(as_of, str):
        text = as_of.strip()
        if text.endswith(("z", "Z")):
            text = text[:-1] + "+00:00"
        try:
            as_of = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(
                f"as_of is not an ISO-8601 timestamp: {as_of!r}"
            ) from exc
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return as_of.astimezone(timezone.utc).isoformat()


def as_of_datetime(as_of: datetime | str) -> datetime:
    """``as_of`` as an aware UTC ``datetime`` (for the world-time filter)."""
    return datetime.fromisoformat(normalize_as_of(as_of))


def _source_of(kernel: Any) -> Any | None:
    return getattr(kernel, "_source", None)


def store_supports_as_of(kernel: Any) -> bool:
    """Can this kernel's store answer a transaction-time read?

    Duck-typed on the method, the same way :mod:`dna.kernel.capabilities`
    derives every other source flag — and mirrored by the declared
    ``SourceCapabilities.as_of_reads``.
    """
    return callable(getattr(_source_of(kernel), "load_one_as_of", None))


async def resolve_as_of(
    kernel: Any,
    scope: str,
    kind: str,
    name: str,
    *,
    as_of: str,
    tenant: str | None = None,
    api_version: str | None = None,
) -> AsOfResolution:
    """Resolve ONE instance as the store recorded it at or before ``as_of``.

    ``as_of`` must already be normalized (:func:`normalize_as_of`). Raises
    :class:`AsOfUnsupported` when the store keeps no history — see rule 1 in the
    module docstring.

    Deliberately bypasses the kernel's 60s instance cache: that cache is keyed on
    ``(scope, kind, name, tenant)`` with no time axis, so routing an as-of read
    through it would either serve the present as the past or poison the present
    with the past.
    """
    src = _source_of(kernel)
    if not callable(getattr(src, "load_one_as_of", None)):
        raise AsOfUnsupported(
            f"as_of reads need a store that retains version history with a "
            f"transaction timestamp; {type(src).__name__} does not implement "
            f"load_one_as_of. Refusing rather than returning the CURRENT state "
            f"under a past timestamp."
        )
    row = await src.load_one_as_of(
        scope, kind, name,
        as_of=as_of, tenant=tenant, api_version=api_version,
    )
    row = row or {}
    return AsOfResolution(
        raw=row.get("raw"),
        version=row.get("version"),
        recorded_at=row.get("recorded_at"),
        truncated=bool(row.get("truncated")),
    )
