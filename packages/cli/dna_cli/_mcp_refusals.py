"""The refusals that say *this deployment cannot answer that at all*.

``dna.kernel.errors.KernelRefusal`` is the marker base for a **verdict about the
request** — a schema veto, a LayerPolicy veto, a tenancy rule, a retired Kind.
One ``except KernelRefusal`` therefore relays every one of them, and a refusal
declared upstream tomorrow is relayed by a face written today. That base exists
precisely because the alternative — each face enumerating the types it will
translate — had already been wrong once (see ``tests/test_mcp_write_refusals``).

**These are the other kind.** A capability refusal is not a verdict about the
caller: the request was well formed, the caller was entitled to it, and the
STORE WIRED INTO THIS DEPLOYMENT cannot produce the answer. The ports catalogue
(``docs/reference/ports/capabilities.md``) states each one as contract, because
the alternative in every case is a confident empty answer that reads as a fact:
``[]`` for *nothing points at this instance*, today's spec under a past
timestamp, a bare ``LookupError`` for *it did not exist yet*.

⚠️ **THIS FILE USED TO BE AN ENUMERATION, AND SAID SO.** It listed the four by
hand — ``AsOfUnsupported`` / ``AsOfTruncated`` / ``GraphUnsupported`` /
``InstanceIdLookupUnsupported`` — because they inherit from ``RuntimeError`` /
``NotImplementedError`` / ``LookupError`` and scattered across the builtin
hierarchy, so no ``except`` reached them as a family. Its own docstring named
the derivation that was missing: a ``CapabilityRefusal`` marker base in
``dna.kernel.errors``, sibling to ``KernelRefusal``.

**That base now exists**, so this tuple is ONE name and holds no list to go
stale. A capability refusal declared tomorrow — anywhere, in any module — is
relayed by every face that already catches this, on the day it is declared.
The tuple form survives only because the call sites splice it (``*``) and read
as a family; it is not a list of anything.

The guards that keep the collapse honest, both DERIVED rather than written:

* ``packages/cli/tests/test_face_refusal_parity.py`` reads the REST face's own
  AST and requires that anything REST answers **501/410** — its own signature
  for *this deployment cannot* — both carries the marker base and is named by an
  MCP handler. A fifth refusal that forgets the base is red there.
* ``packages/sdk-py/tests/test_capability_refusal_base.py`` walks ``dna`` for
  the family, pins that each member keeps its historical builtin base
  (additive, never a re-parenting) and that the two marker bases stay disjoint.
"""
from __future__ import annotations

from dna.kernel.errors import CapabilityRefusal

__all__ = ["CAPABILITY_REFUSALS"]

#: Every capability refusal, as ONE tuple, for any face that relays refusals.
#:
#: One entry, and that is the whole point — see the module docstring. Written as
#: a tuple rather than a bare class because the call sites splice it into their
#: own refusal tuples (``*CAPABILITY_REFUSALS``) and because the shape must
#: survive the day a second marker base is genuinely needed.
CAPABILITY_REFUSALS: tuple[type[BaseException], ...] = (CapabilityRefusal,)
