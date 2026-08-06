"""The refusals that say *this deployment cannot answer that at all*.

``dna.kernel.errors.KernelRefusal`` is the marker base for a **verdict about the
request** — a schema veto, a LayerPolicy veto, a tenancy rule, a retired Kind.
One ``except KernelRefusal`` therefore relays every one of them, and a refusal
declared upstream tomorrow is relayed by a face written today. That base exists
precisely because the alternative — each face enumerating the types it will
translate — had already been wrong once (see ``tests/test_mcp_write_refusals``).

**These are the other kind, and no base reaches them.** A capability refusal is
not a verdict about the caller: the request was well formed, the caller was
entitled to it, and the STORE WIRED INTO THIS DEPLOYMENT cannot produce the
answer. The ports catalogue (``docs/reference/ports/capabilities.md``) states
each one as contract, because the alternative in every case is a confident empty
answer that reads as a fact:

===============================  ============  ==================================
refusal                          REST          the lie it exists to refuse
===============================  ============  ==================================
``AsOfUnsupported``              **501**       today's instance under a past stamp
``AsOfTruncated``                **410**       ``LookupError`` — *"it did not exist
                                               yet"* is a different answer from
                                               *"I no longer hold the record"*
``GraphUnsupported``             **501**       ``[]`` — reads as *nothing points
                                               at this instance*
``InstanceIdLookupUnsupported``  **501**       an empty result set
===============================  ============  ==================================

They inherit from ``RuntimeError`` / ``NotImplementedError`` / ``LookupError``,
so they scatter across the builtin hierarchy and only ``AsOfTruncated`` fell
inside a tuple this face already caught. The REST face maps all four; the MCP
face translated one (``_mcp_instances`` catches ``InstanceIdLookupUnsupported``
inline). So ``recall(as_of=…)`` against a store with no version history — the
filesystem adapter, which declares ``versions=True`` and retains nothing —
reached the client as FastMCP's masked ``Error calling tool 'recall'``: the
documented refusal, delivered in the shape of a crash.

⚠️ **This tuple is an ENUMERATION, and this house has measured what enumerations
cost.** It is written here rather than derived because the derivation it wants
does not exist yet: a ``CapabilityRefusal`` marker base in ``dna.kernel.errors``,
sibling to ``KernelRefusal``, that ``AsOfUnsupported`` and friends inherit. With
that base this file collapses to one name and a new capability refusal is
honest on both faces on the day it is declared. Until then the staleness is held
off by a GUARD rather than by memory: ``tests/test_face_refusal_parity.py``
derives the REST face's refusal map from its own source and fails when the MCP
face cannot translate something REST maps. A name missing here is red, not
quietly absent.
"""
from __future__ import annotations

from dna.kernel.errors import InstanceIdLookupUnsupported
from dna.kernel.query.graph import GraphUnsupported
from dna.memory.as_of import AsOfTruncated, AsOfUnsupported

__all__ = ["CAPABILITY_REFUSALS"]

#: Every capability refusal, as ONE tuple, for any face that relays refusals.
#:
#: ``AsOfTruncated`` is a ``LookupError`` and was therefore already caught by
#: the tuples that list ``LookupError``. It is named anyway: a reader checking
#: whether this face honours the catalogue must be able to find all four here,
#: and "covered by inheritance from an unrelated entry" is not something anyone
#: verifies twice.
CAPABILITY_REFUSALS: tuple[type[BaseException], ...] = (
    AsOfUnsupported,
    AsOfTruncated,
    GraphUnsupported,
    InstanceIdLookupUnsupported,
)
