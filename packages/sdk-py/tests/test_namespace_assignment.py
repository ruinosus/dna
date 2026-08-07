"""A workspace is born with a usable namespace, ASSIGNED and stored.

Never derived from the workspace id: apiVersion participates in an instance's
identity key, so deriving would make renaming or migrating a workspace change
the identity of every instance in it — the defect i-080's form (b) exists to
avoid.

The kernel here is built the way ``test_kind_approval_gate.py`` builds its
own (there is no shared ``live_kernel`` fixture), with one addition:
``TenantExtension`` is loaded so ``KindNamespace`` is REALLY registered. That
matters — registration is what confers write-time schema validation, so a test
without it would happily store a claim shape the real runtime refuses.
"""
from __future__ import annotations

import pytest

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application.namespace_assignment import TENANT_API_VERSION, assign_namespace
from dna.extensions.helix import HelixExtension
from dna.extensions.kinddef import KindDefinitionExtension
from dna.extensions.tenant import TenantExtension
from dna.kernel import Kernel
from dna.kernel.kinds.namespaces import namespace_of, owner_of
from dna.kernel.protocols import SYSTEM_SCOPE


@pytest.fixture
def live_kernel(tmp_path):
    """A writable Kernel whose ``_lib`` registry is the real store — the place
    a ``KindNamespace`` claim actually lives."""
    scope_dir = tmp_path / SYSTEM_SCOPE
    scope_dir.mkdir(parents=True)
    (scope_dir / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        f"metadata:\n  name: {SYSTEM_SCOPE}\n"
        "spec: {}\n"
    )

    k = Kernel()
    k.load(HelixExtension())
    k.load(KindDefinitionExtension())
    k.load(TenantExtension())
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    k.cache(FilesystemCache(str(tmp_path)))
    return k


async def _store_claim(
    live_kernel, *, namespace: str, owner: str, notes: str,
    claimed_at: str = "2026-07-25T00:00:00Z",
) -> None:
    """Write a ``KindNamespace`` claim directly — a claim that was already there
    before ``assign_namespace`` ever ran, in exactly the shape it must find."""
    await live_kernel.write_instance(
        SYSTEM_SCOPE, "KindNamespace", namespace,
        {
            "apiVersion": TENANT_API_VERSION,
            "kind": "KindNamespace",
            "metadata": {"name": namespace},
            "spec": {
                "owner": owner,
                "namespace": namespace,
                "claimed_at": claimed_at,
                "notes": notes,
            },
        },
        invalidate_mode="doc",
    )


@pytest.mark.asyncio
async def test_a_pre_existing_assignment_is_returned_verbatim(live_kernel):
    """The one test in this module NO DERIVATION CAN PASS.

    Every other test here is satisfied by an implementation that computes the
    namespace from the workspace id and stores the result: such a value exists as
    an instance, is deterministic across calls, and resolves through the ownership
    gate. It is also precisely the defect — consolidate or migrate a workspace to
    a new id and its namespace silently changes, taking the identity of every
    instance it owns with it.

    So: pre-store a namespace nothing about ``ws-abc`` could produce, and require
    it back. A derivation returns its own hash and fails here."""
    stored = "ws-deadbeefcafe.dna.local"
    await _store_claim(live_kernel, namespace=stored, owner="ws-abc",
                       notes="assigned before this call ever ran")

    got = await assign_namespace(live_kernel, "ws-abc", now="2026-07-26T00:00:00Z")

    assert got == stored, (
        f"assign_namespace returned {got!r}, not the STORED assignment {stored!r}"
        " — a value it could have computed from 'ws-abc' means the namespace is"
        " DERIVED, and renaming or migrating the workspace would then change the"
        " apiVersion, and so the identity, of every instance it owns"
    )


@pytest.mark.asyncio
async def test_assignment_is_stored_not_derived(live_kernel):
    ns = await assign_namespace(live_kernel, "ws-abc", now="2026-07-26T00:00:00Z")
    assert ns, "a workspace must get a usable namespace"

    # Renaming the workspace must not change the namespace.
    doc = await live_kernel.get_instance(SYSTEM_SCOPE, "KindNamespace", ns)
    assert doc["spec"]["namespace"] == ns
    assert "ws-abc" not in ns, (
        "the workspace id must not appear in the namespace: a stored assignment "
        "is opaque, and an id visible in the value is the shape a derivation "
        "leaves behind (nothing in the schema could mark it as assigned — it is "
        "`additionalProperties: false` with no such field)"
    )


@pytest.mark.asyncio
async def test_assignment_is_idempotent(live_kernel):
    a = await assign_namespace(live_kernel, "ws-abc", now="2026-07-26T00:00:00Z")
    b = await assign_namespace(live_kernel, "ws-abc", now="2026-07-27T00:00:00Z")
    assert a == b, "re-assigning must return the existing namespace, not mint a second"


@pytest.mark.asyncio
async def test_the_assignment_is_a_claim_the_ownership_gate_resolves(live_kernel):
    """The point of assigning at birth is that the FIRST authored Kind waits for
    nothing — so the stored claim has to be the thing ``NamespaceOwnershipGate``
    looks up, not merely an instance that exists.

    That pins the shape against the near-miss the brief for this task carried:
    storing the whole apiVersion (``…/v1``) as ``spec.namespace``. It reads fine
    and stores fine, and the gate would still refuse every write, because
    ``namespace_of`` strips the version segment before looking a claim up. The
    assigned value is the PREFIX; ``f"{ns}/v1"`` is the apiVersion built from it.
    """
    ns = await assign_namespace(live_kernel, "ws-abc", now="2026-07-26T00:00:00Z")

    api_version = f"{ns}/v1"
    verdict = owner_of(namespace_of(api_version), await live_kernel.kind_namespaces())
    assert verdict.owner == "ws-abc", (
        "the workspace must own the namespace of the apiVersion it will declare "
        f"its Kinds under ({api_version!r}) — otherwise the namespace was "
        "assigned in a shape the write path cannot resolve"
    )


@pytest.mark.asyncio
async def test_the_answer_is_the_assigned_claim_and_never_flips(live_kernel):
    """A workspace MAY own several namespaces — the ``KindNamespace`` descriptor
    says nothing constrains the count — so "the workspace's namespace" is not a
    function of the workspace. ``assign_namespace`` answers with the ASSIGNED one
    and only that.

    Both halves matter, and both are about apiVersion participating in instance
    identity: a workspace that proves ownership of a public domain must not have
    its assigned namespace silently swapped out from under Kinds already declared
    under it (authoring under the proven claim is a caller's explicit choice), and
    an extra assigned row must not flip the answer either — the choice is over the
    EARLIEST-``claimed_at`` assigned claim, not over how the namespace strings
    happen to sort or the order the registry yields them in. The second row
    below is deliberately built to sort ALPHABETICALLY LOWER than the first
    (``0000000000ff`` < ``0000deadbeef``) while being claimed LATER — the exact
    case a ``min``-over-the-string reduction would get wrong."""
    assigned = "ws-0000deadbeef.dna.local"
    await _store_claim(live_kernel, namespace="acme.example", owner="ws-abc",
                       notes="proven ownership of a public domain")
    await _store_claim(live_kernel, namespace=assigned, owner="ws-abc",
                       notes="assigned automatically at workspace creation",
                       claimed_at="2026-07-25T00:00:00Z")

    first = await assign_namespace(live_kernel, "ws-abc", now="2026-07-26T00:00:00Z")
    assert first == assigned, (
        f"got {first!r}: a differently-shaped PROVEN claim must never become what "
        "the workspace's assigned namespace is"
    )

    # A second ASSIGNED row that sorts BELOW the first as a string but was
    # claimed LATER — the double-mint two simultaneous first calls could leave
    # behind — must not move the answer either.
    await _store_claim(live_kernel, namespace="ws-0000000000ff.dna.local",
                       owner="ws-abc", notes="assigned automatically at workspace creation",
                       claimed_at="2026-07-26T12:00:00Z")

    again = await assign_namespace(live_kernel, "ws-abc", now="2026-07-27T00:00:00Z")
    assert again == first, (
        f"the assigned namespace flipped from {first!r} to {again!r} when a second "
        "claim appeared — a caller authoring across two sessions would land its "
        "Kinds under two different apiVersions"
    )
