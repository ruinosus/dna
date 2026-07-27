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

The ratchet has TWO halves, and for a while only one of them existed.
``test_no_new_kernel_exception_slips_past_the_refusal_base`` pins which
exception types are NOT refusals, so declaring a new one is a decision somebody
makes on purpose. ``test_every_refusal_is_enumerated`` pins the other
direction: the refusal LIST here must stay complete. Without it, a refusal that
is simply never added just shrinks a ``parametrize`` and everything stays green
— which is exactly what happened to the path-safety refusals.

Both halves scan ``_MODULES``, and ``dna.kernel.errors`` was missing from that
tuple: an entire module of exception types was invisible, so the ratchet had
quietly stopped ratcheting while still reading as coverage.
"""
from __future__ import annotations

import inspect

import pytest

import dna.kernel as K
import dna.kernel.errors as E
import dna.kernel.protocols as P
from dna.kernel.errors import KernelRefusal

#: The kernel's public exception modules, in lookup order. ``dna.kernel.errors``
#: was MISSING here, and that was not cosmetic: the ratchet below scans exactly
#: these, so an entire module's worth of exception types — every path-safety
#: refusal and every registration failure — was invisible to it. A ratchet that
#: cannot see a module silently stops ratcheting, which is worse than not
#: having one, because it reads as coverage.
_MODULES = (P, K, E)


def _refusal(name: str) -> type:
    """Resolve a refusal by name across the kernel's public error modules.

    ``getattr(P, name)`` alone was enough while every refusal lived in
    ``protocols``; the path-safety refusals live in ``dna.kernel.errors`` and
    are NOT re-exported from ``dna.kernel``, so the lookup has to span all
    three or the list below cannot name them."""
    for module in _MODULES:
        cls = getattr(module, name, None)
        if cls is not None and cls.__module__ == module.__name__:
            return cls
    raise AssertionError(f"{name!r} is in no kernel error module")


#: Everything the kernel's write/read facades document themselves as raising
#: when they deliberately say no — the set a face must be able to relay.
#: Kept complete by ``test_every_refusal_is_enumerated`` below, so dropping an
#: entry is a failure rather than a silently smaller parametrization.
_WRITE_REFUSALS = (
    "LayerPolicyViolationError", "SpecValidationError", "TenantNotAllowed",
    "TenantRequired", "InvalidTenantSlug", "VersionAlreadyPublished",
    # dna.kernel.errors — the name/path-safety family. ``InvalidDocumentName``
    # and ``InvalidScopeName`` guard ``write_document`` / ``delete_document`` /
    # the four bundle-entry doors / ``preview_document`` / ``serialize_document``;
    # ``PathEscapesStoreRoot`` is the filesystem adapter's own second layer;
    # ``DocumentNameTaken`` is the atomic ``if_absent`` claim losing the race.
    "DocumentNameTaken", "InvalidDocumentName", "InvalidScopeName",
    "PathEscapesStoreRoot",
)

#: The two that live on ``dna.kernel`` itself.
_KERNEL_REFUSALS = ("NotWritableError", "KindRetiredError")


@pytest.mark.parametrize("name", _WRITE_REFUSALS)
def test_protocol_refusals_share_the_marker_base(name):
    assert issubclass(_refusal(name), KernelRefusal)


@pytest.mark.parametrize("name", _KERNEL_REFUSALS)
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
    # The path-safety family carries a SECOND base on purpose: a face that
    # predates the marker base and still catches ``(ValueError, LookupError,
    # PermissionError)`` must report a security refusal, not mask it as a 500.
    for name in ("InvalidDocumentName", "InvalidScopeName",
                 "PathEscapesStoreRoot"):
        assert issubclass(_refusal(name), ValueError), name
    # ``DocumentNameTaken`` is a ``FileExistsError`` so a caller allocating a
    # name (``create_issue``) can catch the standard exception and try the next.
    assert issubclass(E.DocumentNameTaken, FileExistsError)


def test_one_except_clause_catches_every_write_refusal():
    """The property a face actually depends on."""
    for name in (*_WRITE_REFUSALS, *_KERNEL_REFUSALS):
        cls = _refusal(name) if not hasattr(K, name) else getattr(K, name)
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
    # ── dna.kernel.errors, newly in scope for this scan ──────────────────
    # BOOT-TIME registration/validation failures. They fire while the kernel is
    # being assembled, before any caller exists to relay a verdict to: a typo'd
    # `detect()`, a duplicate (api_version, kind), an Extension whose
    # `register` blew up. A misconfigured process, not a denied request.
    "KernelRegistrationError", "KindRegistrationError",
    "ReaderRegistrationError", "WriterRegistrationError",
    "ExtensionLoadError", "SourceRegistrationError",
    # LOOKUP MISSES on the read path — "there is no such Agent/Tool", not "you
    # may not have it". They subclass LookupError so a caller can catch the
    # miss narrowly; giving them the refusal base would make every face report
    # a typo'd agent name as a policy denial.
    "AgentNotFound", "ToolNotFound",
    # A typo'd `layout:` — an authoring error in the document, surfaced loudly
    # so it cannot silently fall through to the Kind default.
    "UnknownLayout",
}


def test_no_new_kernel_exception_slips_past_the_refusal_base():
    """Adding an exception type to the kernel's public modules is a fork in the
    road: it is either a refusal (give it the base, and every face relays it) or
    it is not (say so here). This test exists so the decision is made rather than
    defaulted — the previous default was "not caught by anybody"."""
    unclassified = _scan(refusals=False)
    assert unclassified == _NOT_REFUSALS


def _scan(*, refusals: bool) -> set[str]:
    """Every exception type DECLARED in the kernel's public error modules,
    split by whether it carries the refusal base."""
    found = set()
    for module in _MODULES:
        for name, obj in vars(module).items():
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseException)
                and obj.__module__ == module.__name__
                and obj is not KernelRefusal  # the base itself, not a refusal
                and issubclass(obj, KernelRefusal) is refusals
            ):
                found.add(name)
    return found


def test_every_refusal_is_enumerated():
    """The other half of the ratchet, and the half that was missing.

    ``_NOT_REFUSALS`` forced a decision about each NEW exception, but nothing
    forced ``_WRITE_REFUSALS`` to stay COMPLETE — it is a hand-written tuple
    feeding a ``parametrize``, so an entry that is never added (or is quietly
    deleted) just shrinks the parametrization and every test still passes
    green. That is how the two refusals ``606812c`` introduced sat unlisted
    with nothing red. Deriving the expected set from the modules themselves
    means a refusal declared tomorrow fails HERE until somebody names it."""
    assert _scan(refusals=True) == set(_WRITE_REFUSALS) | set(_KERNEL_REFUSALS)
