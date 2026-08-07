"""``record.invalidate-only`` — the Kind-level gate on the delete path (i-130).

The sibling of :mod:`dna.kernel.write.target_delete`, one question earlier. That
gate asks *"does anything still point at this instance?"* — a question about the
GRAPH, answered per instance. This one asks *"may an instance of this Kind be
removed at all?"* — a question about the KIND, answered from a declaration on
its descriptor, before any store is touched.

The contradiction it settles
----------------------------
``dna.memory.forget`` says in its own docstring that a memory is *"NEVER
hard-deleted (auditable, point-in-time reconstructable, revivable)"*, and the
Engram descriptor repeats it. Measured on 06/08/2026, in both dialects: a
generic delete removed the row AND its three ``dna_versions`` rows, and
``forget`` afterwards raised ``KeyError: not found``. All three words fell
together — not auditable, not reconstructable, not revivable. The founder's
decision (07/08/2026) kept the promise and dropped the behaviour: **the memory
is immortal**, and the delete has to say so honestly.

Why the gate is HERE and not beside ``delete_refusal``
-------------------------------------------------------
``dna.application.instances.delete_refusal`` already refused two categories —
bootstrap Kinds and ``record.append-only`` records — and it is consulted by
exactly one caller, the generic MCP delete. That is the right reach for what
those two categories actually say: *"never deletable through a GENERIC tool"*,
with the purpose-built path left open. A rule about a tool is enforced at the
tool.

``record.invalidate-only`` is not a rule about a tool. It is a promise about the
ROW, made in the descriptor and relied on by ``recall(as_of=)``, the
contradiction report and the ``valid_at`` column the topology's slice 3 just
built. A promise about the row that holds in one door and not the others is a
promise about that door — and this house has a name for the shape (*"the guard
exists, the door does not call it"*). So it sits in ``WritePipeline.delete``,
the chokepoint :mod:`dna.kernel.write.target_delete` counted the doors into:
five of the six delete call sites funnel there (REST, MCP, CLI, the internal
callers, and the facade itself), and the sixth — ``kernel.source.sync`` — is
deliberately below the kernel for a reason that still holds: a replication path
is not answering a request, and a destination store's declarations must not veto
a mirror of data that is already consistent where it came from.

What it costs when nobody declared it
-------------------------------------
One ``frozenset`` membership test against an in-memory port, per delete, and no
store access at all. Same requirement ``target_delete`` set for itself.

The refusal names the WAY OUT, which is the whole reason it is not a silent no
--------------------------------------------------------------------------------
A refusal that only says "no" is a wall, and a wall is what makes somebody go
around it — in this case with ``psql``, which is the one outcome worse than the
delete. So the message states the mechanism (stamp ``valid_to``; the row stays)
and the verb that performs it.

The verb is looked up per Kind in :data:`INVALIDATE_VERBS` — a MAP and not a
sentence baked into the message, because "which verb retires this?" is a
Kind-level fact and the trait is open: a Kind may carry it without ever having
been named here, and then the refusal still holds and simply names the mechanism
instead of the verb. That is the honest degradation. What it must never do is
name the WRONG verb, which is what a single hard-coded ``forget`` would do the
day a second Kind takes the trait.

The search, including the nothing
---------------------------------
*Already installed:* nothing in the tree refuses a delete by Kind declaration —
the only "soft delete" in the dependency set is our own ``tenant`` extension's
``status=deleted`` + purge cron, which is a workflow on one Kind, not a gate.
*On GitHub:* ``gh api search/repositories`` for bi-temporal/soft-delete gates
came back empty; a code search for ``record.append-only`` returns only this repo
and dna-cloud. *Designs borrowed:* Gel's ``on target delete`` (already borrowed
next door), Kubernetes finalizers — an object marked for deletion that the API
server refuses to remove until its owner acts — and Datomic's immutable log,
where retraction is an assertion rather than an erasure. Nobody packaged the
mechanism; the vocabulary to declare it already existed here.
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "INVALIDATE_VERBS",
    "TRAIT_INVALIDATE_ONLY",
    "hard_delete_refusal",
    "is_invalidate_only_kind",
]

#: A Kind carrying this trait is retired by stamping ``valid_to``, never by
#: removing the row — at EVERY door, which is what separates it from
#: ``record.append-only`` (a rule about the generic tool). See the module
#: docstring, and ``dna.kernel.kinds.traits.CORE_TRAITS`` for the vocabulary.
TRAIT_INVALIDATE_ONLY = "record.invalidate-only"

#: Kind → the verb that retires an instance of it, for the refusal to name.
#:
#: NOT the set of refused Kinds — that is derived from the trait, and a Kind
#: absent from this map is refused exactly the same. This map answers only
#: *"and what should I call instead?"*, which is a per-Kind fact no trait can
#: carry. A missing entry costs the caller one sentence of the message and
#: never the refusal itself.
INVALIDATE_VERBS: dict[str, str] = {
    "Engram": (
        "`forget` retires it — `dna memory forget <name>`, the `forget` MCP "
        "tool, or `dna.memory.forget(kernel, scope, name)`. It stamps "
        "`valid_to`, drops the memory out of default recall, and leaves the "
        "instance and its history in place."
    ),
}


def is_invalidate_only_kind(port: Any) -> bool:
    """Whether ``port`` declares :data:`TRAIT_INVALIDATE_ONLY`."""
    if port is None:
        return False
    from dna.kernel.kinds.traits import port_has_trait

    return port_has_trait(port, TRAIT_INVALIDATE_ONLY)


def hard_delete_refusal(port: Any) -> str | None:
    """Why a hard delete of ``port``'s Kind is refused, or ``None``.

    DERIVED from the declared trait, never from a list of Kind names: an Engram
    is refused because its descriptor says ``record.invalidate-only``, and a
    tenant-authored Kind that declares the same trait tomorrow is covered on
    arrival rather than the next time somebody remembers. A special case for
    ``"Engram"`` on the delete path would have been the enumeration this house
    has already lost four guards to.

    ``None`` for every other Kind, including the two categories
    :func:`dna.application.instances.delete_refusal` refuses: those stay where
    they are, because they are rules about a generic TOOL and this is a rule
    about the row.
    """
    if not is_invalidate_only_kind(port):
        return None
    kind = getattr(port, "kind", None) or "?"
    verb = INVALIDATE_VERBS.get(kind) or (
        "Stamp `valid_to` on it instead: the instance stays, and stays "
        "auditable."
    )
    return (
        f"{kind!r} is an INVALIDATE-ONLY record: it is retired by stamping the "
        f"end of its world-time validity, never by removing the row. A hard "
        f"delete takes the history with it — the versions an `as_of` read "
        f"reconstructs from, and the row a revival would write back to — so "
        f"the guarantee the Kind's own descriptor states (auditable, "
        f"point-in-time reconstructable, revivable) would stop being true. "
        f"{verb}"
    )
