"""i-107 slice 1 — scope inheritance is DECLARED by the Kind, not listed by the kernel.

``compose/resolver.py::get_composition_rule`` decided scope inheritance from
``DEFAULT_NON_INHERITABLE_KINDS_V1``, a literal list of Kind names in
``query/resolver.py``. The Kernel already derived the same answer from
``KindPort.scope_inheritable`` (``Kernel._NON_INHERITABLE_KINDS``), which is
declarable both on a Kind class and from a ``.kind.yaml`` descriptor
(``spec.scope_inheritable``, in the KindDefinition schema).

So this was never a missing mechanism. It was a **fourth copy** of a list the
kernel's own comment already names as dangerous:

    "There were FOUR byte-identical copies of this triple in the tree; the v1.3
    Milestone->Epic rename is the standing proof of what happens when a Kind
    list has copies — it updated one and missed another, and Epic silently
    inherited across scopes for a release."

⚠️ THE COPY HAD ALREADY DRIFTED AGAIN, and that is what these tests lock.
Measured 12/08/2026, the literal list held 13 names and the derived set 17.
Four Kinds — KindNamespace, Memory, Sprint, WorkspaceScopeGrant — declare
``scope_inheritable: false`` in their own descriptors and were MISSING from the
list, so ``get_composition_rule`` returned ``enabled`` for them: they inherited
across scopes against their own declaration. Third occurrence of the same
failure, found by trying to delete the list rather than by anything noticing.

⭐ NOT A NEW TRAIT, and that is deliberate. ``vocabulary.py`` sets the bar for
adding a name to the trait vocabulary — *"a trait that merely restates [a fact]
already declared twice"* is the overdo it exists to refuse. ``scope_inheritable``
is already a KindPort attribute AND a descriptor field; a
``scope.non-inheritable`` trait would be its third spelling and would make the
drift measured above possible in a NEW place. The fix is to delete the copy, not
to add a vocabulary.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.kinds.base import KindBase
from dna.kernel.protocols import StorageDescriptor

# The literal list as it stood immediately before deletion (commit 055ee235).
# Frozen HERE, in the test, on purpose: a parity proof whose "before" side can
# be edited by the change it is proving is not a proof. This constant must
# never be imported from production code — it is a historical record.
LITERAL_BEFORE_DELETION = frozenset({
    "Story", "Issue", "Feature", "Epic", "Milestone", "Roadmap",
    "Narrative", "VibeSession", "Engram", "Plan",
    "Genome", "KindDefinition", "LayerPolicy",
})

# The four the literal list had drifted away from.
DRIFTED_AWAY = frozenset({"KindNamespace", "Memory", "Sprint", "WorkspaceScopeGrant"})


@pytest.fixture(scope="module")
def kernel():
    return Kernel.auto()


def test_the_derived_set_preserves_every_member_of_the_old_list(kernel):
    """FIDELITY. Nothing the literal list refused to inherit may start
    inheriting because the list went away. This is the assertion that had to
    pass BEFORE the list was deleted."""
    derived = kernel._NON_INHERITABLE_KINDS
    lost = sorted(LITERAL_BEFORE_DELETION - derived)
    assert not lost, (
        "Deleting the literal list changed behaviour for these Kinds — they "
        f"used to be non-inheritable and now are not: {lost}\n\n"
        "Each one must declare `scope_inheritable = False` on its Kind class "
        "or `scope_inheritable: false` in its descriptor. Do NOT re-add the "
        "list; that is what let it drift in the first place."
    )


def test_the_tombstones_survive_the_derivation(kernel):
    """``Milestone`` and ``VibeSession`` have no Kind class to declare
    anything — they are retired names that may still sit in an un-migrated
    ``_lib`` on disk. They ride on ``Kernel._LEGACY_NON_INHERITABLE``, and a
    stale row must not START leaking into child scopes just because its Kind
    was retired."""
    derived = kernel._NON_INHERITABLE_KINDS
    assert "Milestone" in derived
    assert "VibeSession" in derived


def test_the_four_kinds_the_literal_list_had_drifted_away_from(kernel):
    """THE BUG THE DELETION FIXES. Each of these declares
    ``scope_inheritable: false`` in its own descriptor and was absent from the
    literal list, so the resolver let it inherit across scopes anyway."""
    derived = kernel._NON_INHERITABLE_KINDS
    for kind in sorted(DRIFTED_AWAY):
        port = kernel.kind_port_for(kind)
        assert port is not None, f"{kind} is not registered"
        assert getattr(port, "scope_inheritable", True) is False, (
            f"{kind} no longer declares scope_inheritable=False — if that is "
            "intentional, drop it from DRIFTED_AWAY and say why in the PR."
        )
        assert kind in derived, (
            f"{kind} declares scope_inheritable=False but the derived "
            "non-inheritable set does not contain it — the derivation is not "
            "reading the declaration."
        )
        assert kind not in LITERAL_BEFORE_DELETION, (
            f"{kind} was in the literal list after all — the drift measurement "
            "was wrong, re-measure before trusting the rest of this file."
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", sorted(DRIFTED_AWAY))
async def test_the_resolver_now_refuses_inheritance_for_the_drifted_four(kernel, kind):
    """End to end, through the door that had the bug:
    ``get_composition_rule`` must answer ``disabled``. Before the fix it
    answered ``enabled`` for all four."""
    rule, _merge, _tenant = await kernel._get_composition_rule("some-scope", kind)
    assert rule == "disabled", (
        f"{kind} declares scope_inheritable=False but get_composition_rule "
        f"still says {rule!r} — the resolver is reading a list again, not the "
        "declaration."
    )


@pytest.mark.asyncio
async def test_an_ordinary_kind_still_inherits(kernel):
    """The negative case, so the test above cannot pass by everything being
    non-inheritable."""
    rule, _m, _t = await kernel._get_composition_rule("some-scope", "Agent")
    assert rule == "enabled"


@pytest.mark.asyncio
async def test_a_kind_the_kernel_has_never_heard_of_can_declare_it():
    """⭐ THE POINT OF THE WHOLE SLICE — and the thing a literal list could
    never do.

    A Kind invented here, registered at runtime, that the kernel has no line
    of code about, declares ``scope_inheritable = False`` and gets EXACTLY the
    behaviour the built-in ledger Kinds get. That is what turns "adopt a
    market Kind" from aspiration into mechanism: the adopter declares, the
    kernel obeys, and nobody edits the kernel.
    """
    class _TenantLedger(KindBase):
        api_version = "market.example/v1"
        kind = "TenantLedger"
        alias = "market-tenantledger"
        storage = StorageDescriptor.yaml("tenantledgers")
        scope_inheritable = False

    class _TenantCatalog(KindBase):
        api_version = "market.example/v1"
        kind = "TenantCatalog"
        alias = "market-tenantcatalog"
        storage = StorageDescriptor.yaml("tenantcatalogs")
        # declares nothing → inherits, the default

    k = Kernel.auto()
    k.kind(_TenantLedger())
    k.kind(_TenantCatalog())

    assert "TenantLedger" in k._NON_INHERITABLE_KINDS
    assert "TenantCatalog" not in k._NON_INHERITABLE_KINDS

    declared, _m, _t = await k._get_composition_rule("some-scope", "TenantLedger")
    default, _m2, _t2 = await k._get_composition_rule("some-scope", "TenantCatalog")
    assert declared == "disabled", (
        "a Kind that DECLARES scope_inheritable=False must be refused "
        "inheritance even though the kernel has never heard of it — if this "
        "fails, the kernel is still deciding by name"
    )
    assert default == "enabled"


def test_the_literal_list_is_gone():
    """The list must not come back. If someone re-adds it, the copies start
    drifting again and this whole file becomes decoration."""
    import dna.kernel.query.resolver as res

    assert not hasattr(res, "DEFAULT_NON_INHERITABLE_KINDS_V1"), (
        "DEFAULT_NON_INHERITABLE_KINDS_V1 is back. Scope inheritance is "
        "declared by the Kind (`scope_inheritable`), derived by "
        "`Kernel._NON_INHERITABLE_KINDS`. A literal list is a fourth copy and "
        "has drifted three times now."
    )
