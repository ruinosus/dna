"""Every DELIBERATE kernel refusal is catchable as ONE type.

The hole this closes was a face problem with a kernel cause. A face wanting to
turn "the kernel said no" into an honest client message had to ENUMERATE the
refusal types, and the enumeration was wrong: the MCP write tool caught
``(ValueError, LookupError, PermissionError)``, but ``LayerPolicyViolationError``,
``TenantNotAllowed``, ``TenantRequired`` and ``InvalidTenantSlug`` are plain
``Exception`` and ``NotWritableError`` is a ``RuntimeError`` — so NONE of them was
caught. The LayerPolicy veto, which is the single likeliest refusal on a tenant
write, escaped as an unhandled exception and reached the client as a masked
failure with no cause and no remedy.

Enumeration per face is the bug. :class:`~dna.kernel.errors.KernelRefusal` is the
marker base, so a face catches one type and a NEW refusal Kind is surfaced by
every face on the day it is declared.

The second test is the ratchet: it pins which exception types in the kernel's
public modules are NOT refusals, so declaring a new one is a decision somebody
has to make on purpose rather than a silent re-opening of the same hole.
"""
from __future__ import annotations

import inspect

import pytest

import dna.kernel as K
import dna.kernel.protocols as P
from dna.kernel.errors import KernelRefusal

#: Everything ``kernel.write_document`` documents itself as raising when it
#: deliberately says no — the set a write face must be able to relay.
_WRITE_REFUSALS = (
    "LayerPolicyViolationError", "SpecValidationError", "TenantNotAllowed",
    "TenantRequired", "InvalidTenantSlug", "VersionAlreadyPublished",
)


@pytest.mark.parametrize("name", _WRITE_REFUSALS)
def test_protocol_refusals_share_the_marker_base(name):
    assert issubclass(getattr(P, name), KernelRefusal)


@pytest.mark.parametrize("name", ["NotWritableError", "KindRetiredError"])
def test_kernel_refusals_share_the_marker_base(name):
    assert issubclass(getattr(K, name), KernelRefusal)


def test_the_historical_bases_are_kept():
    """Additive, not a re-parenting: code that already catches these by their
    old base keeps working. ``NotWritableError`` in particular is caught as a
    ``RuntimeError`` in the wild, and ``SpecValidationError`` as ``ValueError``
    by the ``pre_save`` guard convention."""
    assert issubclass(K.NotWritableError, RuntimeError)
    assert issubclass(K.KindRetiredError, ValueError)
    assert issubclass(P.SpecValidationError, ValueError)
    for name in ("LayerPolicyViolationError", "TenantNotAllowed",
                 "TenantRequired", "InvalidTenantSlug"):
        assert issubclass(getattr(P, name), Exception)


def test_one_except_clause_catches_every_write_refusal():
    """The property a face actually depends on."""
    for name in (*_WRITE_REFUSALS, "NotWritableError", "KindRetiredError"):
        cls = getattr(P, name, None) or getattr(K, name)
        try:
            raise cls("nope")
        except KernelRefusal as exc:
            assert str(exc) == "nope"


# ── the ratchet ─────────────────────────────────────────────────────────────

#: Exception types in the kernel's public modules that are deliberately NOT
#: refusals — a bug, a boot-time misconfiguration, or a transport failure. None
#: of them is a "the kernel says no to your write" a client can act on.
_NOT_REFUSALS = {
    # A malformed query is a caller bug, not a policy decision, and it is
    # raised on the READ path where there is nothing to refuse.
    "QueryError",
    # Ref RESOLUTION transport failures (network / auth / 404 against a remote
    # ref) — an availability problem, not a kernel verdict.
    "ResolveError", "ResolveAuthError", "ResolveNetworkError",
    "ResolveNotFoundError",
}


def test_no_new_kernel_exception_slips_past_the_refusal_base():
    """Adding an exception type to the kernel's public modules is a fork in the
    road: it is either a refusal (give it the base, and every face relays it) or
    it is not (say so here). This test exists so the decision is made rather than
    defaulted — the previous default was "not caught by anybody"."""
    unclassified = set()
    for module in (P, K):
        for name, obj in vars(module).items():
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseException)
                and obj.__module__ == module.__name__
                and not issubclass(obj, KernelRefusal)
            ):
                unclassified.add(name)
    assert unclassified == _NOT_REFUSALS
