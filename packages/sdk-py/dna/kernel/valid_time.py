"""World time — *when the fact was true*, as a column instead of a convention.

The sibling of :mod:`dna.memory.as_of`, and the two must be read together or
not at all, because mixing them is the classic bitemporal mistake and this
codebase has one of each axis:

===================  ==========================================  ===============
axis                 where it lives                              who reads it
===================  ==========================================  ===============
**transaction**      ``dna_versions.created_at`` — *when this    ``as_of``
                     store came to BELIEVE it*
**valid** (world)    ``dna_instances.valid_at`` — *when the      this module
                     fact IS TRUE*
===================  ==========================================  ===============

They come apart the moment a fact is recorded late or corrected: a note written
today about last year is **valid** last year and **believed** today. A
transaction-time read at last year must not find it; a valid-time read must.
Neither answers for the other, and a surface that offers one under the other's
name hands back a confident wrong answer — which is why the two parameters are
separate on every door that carries them.

**What was here before, and why it was not enough.** World time is not new:
``spec.valid_from`` / ``spec.valid_to`` have existed on the ``Engram`` Kind
since the memory verbs did, ``remember`` seeds the first and ``forget`` writes
the second, and :func:`dna.memory.decay.currently_valid` filters on it in
Python on every recall. All of that was **JSON inside ``content``, with no
column and no index** — so:

* nothing could ask the STORE "which instances were true at T"; the filter had
  to load every candidate and run a Python loop (``verbs.py``'s recall);
* nothing could REFUSE two overlapping validity periods for the same instance,
  because there was nowhere to state the constraint;
* the convention was reachable only from the memory verbs, so every other Kind
  was silently outside it — the axis existed for 14 rows of 414 (measured
  06/08/2026) and no reader could tell whether the other 400 had no window or
  had never been asked.

Promoting it to ``tstzrange`` + ``EXCLUDE USING gist (id WITH =, valid_at WITH
&&)`` changes none of the authored data and none of the verbs. The JSON stays
where it is and stays authoritative — this module PROJECTS it, exactly as
``dna_instances.id`` projects ``metadata.id`` (see :mod:`dna.kernel.identity`)
— and the column is what the store can index, constrain and be asked about.

Two decisions worth stating because the alternatives look equally reasonable:

1. **ONE range column, not two scalar columns.** The slice is called "valid
   time as two columns" for the shape of the fact (a start and an end), and the
   obvious reading is ``valid_from timestamptz`` + ``valid_to timestamptz``.
   That reading does not survive: PostgreSQL 18 (25/09/2025) implements
   temporal keys as ``PRIMARY KEY (id, valid_at WITHOUT OVERLAPS)``, and its
   documentation is explicit — *"the WITHOUT OVERLAPS column must have a range
   or multirange type"*. Two scalars cannot be adopted by the engine without a
   rewrite; one ``tstzrange`` becomes an engine-enforced temporal key on a
   major upgrade by replacing the constraint and touching no data.
2. **Half-open ``[from, to)``**, matching what
   :mod:`dna.memory.contradiction` already asserts about claim windows
   (*"under the closed-open convention ``[valid_from, valid_to)``"*). Two
   windows that merely touch — one ending at T, the next starting at T — do not
   overlap, which is what makes a supersession chain expressible at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from dna.kernel.errors import CapabilityRefusal

__all__ = [
    "ValidWindow",
    "ValidTimeUnsupported",
    "normalize_valid_at",
    "store_supports_valid_time",
    "valid_window_of",
]


class ValidTimeUnsupported(CapabilityRefusal, RuntimeError):
    """This deployment's store keeps no world-time column — it cannot filter by it.

    The exact sibling of :class:`~dna.memory.as_of.AsOfUnsupported`, one axis
    over, and it exists to refuse the same shape of confident lie: serving the
    CURRENT instance to a caller who asked which instances were true at T. That
    answer is right only when nothing in the store has ever declared a window,
    and no store may bet on that.

    Deliberately NOT collapsible into "the instance was not valid then", which
    is an ANSWER. Only a store that keeps the column may make that statement.

    A :class:`~dna.kernel.errors.CapabilityRefusal`, so every face that already
    catches that base relays it as a 501 without being taught this name — the
    lesson ``CapabilityRefusal`` was created for. ``RuntimeError`` as its second
    base, additively, exactly like ``AsOfUnsupported``.

    ⚠️ **The axis is Postgres-only, and that is a property of the DIALECT, not
    of the adapter class.** ``SqlAlchemySource`` serves both dialects from one
    class; SQLite has no range type, no GiST and no ``EXCLUDE`` constraint, so
    the same class declares ``valid_time=False`` when it is bound to SQLite.
    The filesystem source has no column at all. Both refuse here rather than
    filtering nothing and calling the result an answer.
    """


@dataclass(frozen=True)
class ValidWindow:
    """A half-open world-time window ``[lower, upper)``.

    ``None`` on either endpoint is UNBOUNDED, not missing: an instance whose
    ``spec`` says nothing about world time is true for all of it. That is not
    an assumption invented here — it is the behaviour
    :func:`dna.memory.decay.currently_valid` has always implemented (*"``True``
    when ``valid_to`` is unset OR in the future"*), stated in a type instead of
    re-derived at each call site.
    """

    lower: datetime | None = None
    upper: datetime | None = None

    @property
    def bounded(self) -> bool:
        """True when the instance said ANYTHING about world time.

        The reason this is worth a property: ``ValidWindow()`` (both ends
        unbounded) and "the instance declared no window" are the same VALUE and
        different FACTS, and only the second is a thing a report may count.
        """
        return self.lower is not None or self.upper is not None

    def contains(self, instant: datetime) -> bool:
        """Half-open containment — ``lower <= instant < upper``."""
        if self.lower is not None and instant < self.lower:
            return False
        if self.upper is not None and instant >= self.upper:
            return False
        return True


def _parse(value: Any) -> datetime | None:
    """An ISO-8601 instant, normalized to aware UTC, or ``None``.

    Fail-OPEN on garbage, and that is a deliberate asymmetry with
    :func:`normalize_valid_at`, which fails LOUD. The difference is who wrote
    the value. Here it is stored data: a malformed ``spec.valid_to`` written
    months ago must not make the instance unreadable, so it reads as "no
    endpoint declared" — the same fail-open
    :func:`dna.memory.decay.currently_valid` chose, for the same reason. There
    it is a caller's argument arriving now, and a typo in a query parameter is
    the caller's mistake to hear about immediately.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        if not isinstance(value, str) or not value.strip():
            return None
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def valid_window_of(raw: object) -> ValidWindow:
    """The world-time window an instance envelope DECLARES, or the unbounded one.

    Reads ``spec.valid_from`` / ``spec.valid_to`` — the fields ``remember`` and
    ``forget`` have always written. This is a PROJECTION and never a mint: the
    JSON is the authored fact and stays authoritative, the column is derived
    from it on every save. An adapter that invented a window here would be
    asserting something about the world that nobody wrote down.

    Tolerant of both envelope shapes for the same reason
    :func:`dna.kernel.identity.instance_id_of` is: reading through only one of
    them turns a projection into something that is silently always empty on the
    other, and an always-empty projection is indistinguishable from a store
    where nobody declares windows.

    An INVERTED window (``valid_to`` at or before ``valid_from``) reads as
    unbounded on the offending end rather than raising. A range type would
    reject it outright and take the whole write down with it — refusing to save
    an instance because a text field disagrees with itself turns a data typo
    into an outage, and the write path is not the place to adjudicate world
    time. The store still refuses OVERLAPS, which is the invariant that matters.
    """
    if raw is None:
        return ValidWindow()
    spec: object
    if isinstance(raw, dict):
        spec = raw.get("spec")
    else:
        spec = getattr(raw, "spec", None)
    if not isinstance(spec, dict):
        spec = getattr(spec, "__dict__", None) if spec is not None else None
        if not isinstance(spec, dict):
            return ValidWindow()
    lower = _parse(spec.get("valid_from"))
    upper = _parse(spec.get("valid_to"))
    if lower is not None and upper is not None and upper <= lower:
        # Not an error, and not silence either: the endpoints are kept only
        # where they still say something. Dropping BOTH would erase the one
        # half that was well formed.
        return ValidWindow(lower=lower, upper=None)
    return ValidWindow(lower=lower, upper=upper)


def normalize_valid_at(valid_at: datetime | str) -> datetime:
    """A caller-supplied world-time instant as an aware UTC ``datetime``.

    Raises ``ValueError`` on anything that is not ISO-8601 — BEFORE the store's
    capability is consulted, so a typo is relayed as the caller's mistake and
    never as "this deployment cannot read world time". The two have different
    remedies and only the message can carry which; the same ordering
    ``get_instance(as_of=…)`` already enforces for its own axis.
    """
    if isinstance(valid_at, datetime):
        dt = valid_at
    else:
        text = str(valid_at).strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            raise ValueError(
                f"valid_at is not an ISO-8601 instant: {valid_at!r}"
            ) from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def store_supports_valid_time(kernel: Any) -> bool:
    """Whether this deployment's source keeps the world-time column.

    Asked BEFORE the read, never discovered during it — the whole point of
    :class:`~dna.kernel.capabilities.SourceCapabilities`. Reads the DECLARATION
    (``valid_time``) rather than probing for a method, because the answer is
    dialect-dependent: one adapter class, and only the Postgres binding has the
    column.
    """
    from dna.kernel.capabilities import source_capabilities

    src = getattr(kernel, "_source", None)
    if src is None:
        return False
    try:
        return bool(source_capabilities(src).valid_time)
    except Exception:  # noqa: BLE001 — a broken declaration is not a capability
        return False
