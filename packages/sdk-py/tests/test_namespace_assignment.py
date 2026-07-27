"""A workspace is born with a usable namespace, ASSIGNED and stored.

Never derived from the workspace id: apiVersion participates in a document's
identity key, so deriving would make renaming or migrating a workspace change
the identity of every document in it — the defect i-080's form (b) exists to
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
from dna.application.namespace_assignment import assign_namespace
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


@pytest.mark.asyncio
async def test_assignment_is_stored_not_derived(live_kernel):
    ns = await assign_namespace(live_kernel, "ws-abc", now="2026-07-26T00:00:00Z")
    assert ns, "a workspace must get a usable namespace"

    # Renaming the workspace must not change the namespace.
    doc = await live_kernel.get_document(SYSTEM_SCOPE, "KindNamespace", ns)
    assert doc["spec"]["namespace"] == ns
    assert "ws-abc" not in ns or doc["spec"].get("assigned") is True, (
        "if the id appears it must be a stored assignment, never a derivation"
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
    looks up, not merely a document that exists.

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
