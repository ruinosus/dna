"""Every "this deployment cannot answer that" is catchable as ONE type.

The cross-face sibling of ``test_kernel_refusal_base``, for the other category
of refusal — and it exists because the enumeration it replaced had already been
measured wrong. ``KernelRefusal`` marks a **verdict about the request**; a
capability refusal is not that. The request was well formed and the caller was
entitled to it; what is missing is a capability of the ADAPTER wired into this
deployment, so the remedy is a different deployment and never a different call.

The four members inherit from ``RuntimeError`` / ``NotImplementedError`` /
``LookupError`` and scatter across the builtin hierarchy, so until
:class:`~dna.kernel.errors.CapabilityRefusal` existed no ``except`` reached them
as a family. The MCP face therefore held a hand-written tuple, and the one
member that happened to be a ``LookupError`` was the only one an existing tuple
caught — which is exactly how ``recall(as_of=…)`` against a store with no
version history reached the client as FastMCP's ``Error calling tool 'recall'``:
a documented refusal delivered in the shape of a crash.

WHAT THIS FILE PINS, and each half has a different failure it prevents:

* **the family is DERIVED** — the members are found by walking ``dna``, not
  listed here, so a fifth one is in scope the day it is declared. A floor guards
  the walk itself: a scan that resolves nothing would pass vacuously, which is
  how every guard this house lost was lost.
* **the historical bases are kept** — additive, never a re-parenting. Code that
  catches ``LookupError`` around an as-of read must be untouched by this.
* **the two marker bases are DISJOINT** — the distinction is the reason there
  are two, and a member that drifted into ``KernelRefusal`` would be relayed as
  a denial the caller could appeal.

The cross-face half — "anything the REST face answers 501/410 with carries this
base" — lives in ``packages/cli/tests/test_face_refusal_parity.py``, where the
REST source is. It is derived from REST's own AST rather than from a list here.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import warnings

import pytest

from dna.kernel.errors import CapabilityRefusal, KernelRefusal


def _capability_refusals() -> dict[str, type]:
    """Every ``CapabilityRefusal`` subclass declared under ``dna``, by name.

    WALKED, not listed, for the same reason ``test_kernel_refusal_base``'s
    ``_kernel_modules`` is walked: a hand-written reach ratchets only as far as
    somebody remembered to point it, and this family deliberately spans two
    packages — ``dna.kernel`` (the graph and the id lane) and ``dna.memory``
    (the two as-of refusals). A tuple of modules would have missed half of it.

    ``__subclasses__`` only sees classes whose module has been IMPORTED, which
    is precisely why the walk comes first.
    """
    import dna

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for info in pkgutil.walk_packages(dna.__path__, "dna."):
            try:
                importlib.import_module(info.name)
            except Exception:  # noqa: BLE001 — an optional extra is not installed
                continue

    found: dict[str, type] = {}
    stack = [CapabilityRefusal]
    while stack:
        for sub in stack.pop().__subclasses__():
            if sub.__name__ not in found:
                found[sub.__name__] = sub
                stack.append(sub)
    return found


#: The builtin base each member had BEFORE the marker base existed, and must
#: keep. Written out because "additive, never a re-parenting" is a promise to
#: code this repo cannot see — an ``except LookupError`` around an as-of read in
#: dna-cloud, in a copilot, in somebody's adapter.
_HISTORICAL_BASES = {
    "AsOfUnsupported": RuntimeError,
    "AsOfTruncated": LookupError,
    "GraphUnsupported": RuntimeError,
    "InstanceIdLookupUnsupported": NotImplementedError,
}


def test_the_walk_itself_still_finds_the_family():
    """The blindness check, first: a scan that resolves nothing passes vacuously.

    The floor is the four that exist today. It is a floor and not an equality on
    purpose — a fifth capability refusal is meant to be added without editing
    this file, and only DROPPING one should be red here.
    """
    found = _capability_refusals()
    missing = sorted(set(_HISTORICAL_BASES) - set(found))
    assert not missing, (
        f"the walk did not find {missing} — either they lost the marker base, "
        "or this scan went blind and is now passing without looking"
    )


@pytest.mark.parametrize("name", sorted(_HISTORICAL_BASES))
def test_the_historical_bases_are_kept(name):
    """Additive, not a re-parenting — the promise the SDK's consumers rely on."""
    cls = _capability_refusals()[name]
    assert issubclass(cls, _HISTORICAL_BASES[name]), (
        f"{name} lost its {_HISTORICAL_BASES[name].__name__} base; every "
        "``except`` written before the marker base existed just stopped working"
    )


def test_one_except_clause_catches_every_capability_refusal():
    """The property a face actually depends on — and the whole point of the base.

    ``dna_cli._mcp_refusals.CAPABILITY_REFUSALS`` is one name because of this.
    """
    for name, cls in _capability_refusals().items():
        try:
            raise cls("this deployment cannot answer that")
        except CapabilityRefusal as exc:
            assert str(exc) == "this deployment cannot answer that", name


def test_the_two_marker_bases_stay_disjoint():
    """⚠️ The distinction that justifies a SECOND base rather than a wider first.

    ``KernelRefusal`` is a verdict about the REQUEST: policy said no, and the
    remedy is a different request. A capability refusal is a fact about the
    DEPLOYMENT: the remedy is a different adapter, and nothing the caller can
    say will change the answer. A member that acquired both bases would be
    relayed by every face as a denial the caller may appeal — sending them to
    look for an entitlement they already have.
    """
    assert not issubclass(CapabilityRefusal, KernelRefusal)
    assert not issubclass(KernelRefusal, CapabilityRefusal)
    both = sorted(
        name for name, cls in _capability_refusals().items()
        if issubclass(cls, KernelRefusal)
    )
    assert not both, (
        f"{both} carry BOTH marker bases. A capability refusal is not a verdict "
        "on the request; whichever ``except`` runs first decides how it reads, "
        "which means it reads differently on each face."
    )


def test_a_capability_refusal_is_not_swallowed_by_the_kernel_relay():
    """The negative that gives the test above its teeth.

    Faces relay ``KernelRefusal`` in one arm and ``CapabilityRefusal`` in
    another, and the two arms say different things. This proves the first arm
    does NOT catch the second's members — if it did, the split would be
    decorative and every capability refusal would arrive as a policy denial.
    """
    from dna.kernel.query.graph import GraphUnsupported

    with pytest.raises(GraphUnsupported):
        try:
            raise GraphUnsupported("no edge store here")
        except KernelRefusal:  # pragma: no cover — must not match
            pytest.fail("a capability refusal was relayed as a policy verdict")


def test_the_face_tuple_is_the_base_and_not_a_list():
    """The collapse this base was created for, asserted from the face's end.

    ``CAPABILITY_REFUSALS`` was four hand-written names whose own docstring said
    it was an enumeration and named the missing derivation. It is one name now.
    Should it ever grow back into a list of concrete types, that is a per-face
    enumeration returning — the exact defect, and it should be argued for here
    rather than typed in silently.
    """
    cli = pytest.importorskip(
        "dna_cli._mcp_refusals",
        reason="the MCP face lives in the sibling dna-cli package",
    )
    assert cli.CAPABILITY_REFUSALS == (CapabilityRefusal,)
