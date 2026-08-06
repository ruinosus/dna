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

Both halves scan ``_MODULES``, and that tuple was the ratchet's own blind spot
— TWICE. First ``dna.kernel.errors`` was missing from it, so an entire module
of exception types was invisible and the ratchet had quietly stopped ratcheting
while still reading as coverage. Adding the module fixed the instance and left
the CAUSE: a hand-maintained list of three modules cannot see a fourth, and
``NamespaceOwnershipError`` (``dna.kernel.kinds.namespaces``) — a genuine
refusal, via ``LayerPolicyViolationError`` — sat outside all three with nothing
red. The exact failure mode the previous commit set out to fix, reproduced one
level out.

``_MODULES`` is therefore DERIVED now (``pkgutil.walk_packages`` over
``dna.kernel``), not listed. The reach of a ratchet must not itself be
something somebody has to remember to update.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest

import dna.kernel as K
import dna.kernel.errors as E
import dna.kernel.protocols as P
from dna.kernel.errors import KernelRefusal


def _kernel_modules() -> tuple:
    """Every module in the ``dna.kernel`` PACKAGE, DERIVED by walking it.

    This replaced a hand-maintained ``_MODULES = (P, K, E)`` tuple, and the
    replacement is the point rather than a tidy-up. The previous wave fixed
    exactly this bug one level in — ``dna.kernel.errors`` was missing from the
    tuple, so a whole module of exception types was invisible while the ratchet
    still read as coverage — and then REPRODUCED it one level out, because a
    tuple of three modules cannot see a fourth.

    It really was blind. ``NamespaceOwnershipError``
    (``dna.kernel.kinds.namespaces``) IS a ``KernelRefusal`` — it subclasses
    ``LayerPolicyViolationError`` — and lives outside all three modules, so
    ``test_every_refusal_is_enumerated`` could not see it and nothing was red.
    A ratchet whose SCOPE is hand-written ratchets only as far as somebody
    remembered to point it.

    Derived, therefore, not listed: a refusal declared in a new submodule
    tomorrow is in scope the moment the file exists. ``dna.kernel`` itself is
    included explicitly (``walk_packages`` yields a package's children, not the
    package), and an import failure PROPAGATES rather than being skipped — a
    module the ratchet cannot import is a module it cannot scan, which is the
    failure mode this test exists to refuse.

    THE PRICE OF THE DERIVATION, stated because the paragraph above frames only
    its upside. Force-importing every module in the package makes the ratchet
    take an IMPORT-SIDE-EFFECT dependency on all of them: whatever any kernel
    submodule does at import time, this test now does too. It showed up
    immediately — ``dna.kernel.compose.composition`` is a deprecated shim that
    warns on import, so the file ran ``18 passed, 1 warning`` and the warning
    had nothing to do with what was being tested. Test output that carries
    unrelated noise stops being read.

    The warning is SUPPRESSED HERE, at the derivation, and nowhere else. It is
    scoped to this loop and to ``DeprecationWarning``, so a deprecation warning
    raised by the code under test still surfaces normally; only the cost of
    walking the package is silenced. The shim is not modified and the module
    stays in scope — a refusal declared inside a deprecated module is still a
    refusal, and dropping it from the walk to dodge the warning would put a
    hole back in the ratchet.
    """
    import warnings

    import dna.kernel

    modules = [dna.kernel]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        for info in pkgutil.walk_packages(dna.kernel.__path__, "dna.kernel."):
            modules.append(importlib.import_module(info.name))
    return tuple(modules)


#: Every module the ratchet scans. ``P``, ``K`` and ``E`` are listed first only
#: so ``_refusal`` resolves the three historically-public modules before any
#: re-export; the SET is derived, not maintained.
_MODULES = (P, K, E, *(m for m in _kernel_modules() if m not in (P, K, E)))


def _refusal(name: str) -> type:
    """Resolve a refusal by name across the kernel's error modules.

    ``getattr(P, name)`` alone was enough while every refusal lived in
    ``protocols``; the path-safety refusals live in ``dna.kernel.errors``, the
    namespace-ownership one in ``dna.kernel.kinds.namespaces``, and none of
    them is re-exported from ``dna.kernel`` — so the lookup has to span the
    whole package or the list below cannot name them."""
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
    # ``InvalidBundleEntry`` closes the third door of the same family — a
    # bundle ENTRY, which is a relative PATH rather than a component, and which
    # writers derive from document CONTENT (``spec.source_files`` et al);
    # ``DocumentNameTaken`` is the atomic ``if_absent`` claim losing the race,
    # and ``StaleDocumentWrite`` (i-083) is its UPDATE counterpart — a guarded
    # ``if_match`` write refusing to land on a document that moved since the
    # caller read it. Both are adjudicated by the ADAPTER against the store, and
    # both have to reach the caller as a denial rather than a 500 because their
    # remedies differ and only the refusal can say which: take another name, or
    # re-read and re-apply to the fresh etag.
    "DocumentNameTaken", "StaleDocumentWrite", "InvalidDocumentName",
    "InvalidScopeName", "PathEscapesStoreRoot", "InvalidBundleEntry",
    # dna.kernel.kinds.namespaces — a write declaring a Kind in a namespace its
    # author does not own. It IS a refusal and always was (a subclass of
    # ``LayerPolicyViolationError``, so every face already relays it); it was
    # simply invisible to a ratchet whose module list was hand-written. That it
    # appears here now is the derivation working.
    "NamespaceOwnershipError",
    # dna.kernel.errors — a write whose Kind has been REVOKED (i-085). It is a
    # refusal in the strictest sense of this file: the kernel DECIDED, on a
    # workspace's own instruction, and the caller can act on it — but only if it
    # arrives with its reason intact. Told "validation failed" instead, an author
    # would edit a document that no edit can save; told nothing, they would
    # retry forever. It also carries the one piece of reassurance the moment
    # needs: existing documents were not deleted.
    "RevokedKindWrite",
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
                 "PathEscapesStoreRoot", "InvalidBundleEntry"):
        assert issubclass(_refusal(name), ValueError), name
    # ``DocumentNameTaken`` is a ``FileExistsError`` so a caller allocating a
    # name (``create_issue``) can catch the standard exception and try the next.
    assert issubclass(E.DocumentNameTaken, FileExistsError)


def test_one_except_clause_catches_every_write_refusal():
    """The property a face actually depends on."""
    for name in (*_WRITE_REFUSALS, *_KERNEL_REFUSALS):
        # ``_refusal`` already spans ``K`` — the ``hasattr(K, name)`` fork this
        # replaced was a second lookup for the same answer.
        cls = _refusal(name)
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
    # ── newly in scope once the module list became DERIVED ────────────────
    # Each of these was always in ``dna.kernel``; none of them was ever
    # scanned, because the scan's reach was a hand-written tuple of three
    # modules. Classified now, one reason each, rather than left to default.
    #
    # WARNINGS, not exceptions on any control-flow path. A caller never
    # catches them; a bad hook name and a malformed frontmatter block are
    # surfaced so an author fixes them while loading continues.
    "UnknownHookNameWarning", "FrontmatterParseWarning",
    # A CORRUPT DOCUMENT on the read path, opt-in via ``strict=True``. The
    # SQL source catches it and falls back to the canonical row — a recovery
    # signal between an adapter and itself, not a verdict for a client.
    "FrontmatterParseError",
    # PARSE failures of a pure value type (a malformed semver string or
    # range). No I/O, no policy, no request — the caller handed in text that
    # is not a version.
    "InvalidConstraint", "InvalidVersion",
    # AUTHOR-TIME schema validation of a KindDefinition's own JSON Schema,
    # raised through the same funnels as the boot-time registration errors
    # above (raise at boot for builtins, warn-and-skip per scope). It refuses
    # a descriptor, not somebody's write.
    "SchemaGuardError",
    # A COMPOSITION-time budget: the assembled instruction is larger than the
    # target model's own declared cap. Not a policy denial the caller may
    # appeal — an arithmetic fact about the prompt, raised on the read/compose
    # path where there is no write to refuse.
    "PromptBudgetExceededError",
    # A CAPABILITY statement about the DEPLOYMENT, not a verdict on the
    # request: the active source keeps no derived reference graph, so there is
    # no answer to give. It is an exception rather than an empty list on
    # purpose — ``[]`` reads as "nothing points at this document", a claim only
    # a store that records edges may make — but relaying it as a refusal would
    # tell the caller they were denied something they might appeal. The faces
    # map it to 501, and the caller's remedy is a different adapter, not a
    # different request.
    "GraphUnsupported",
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
