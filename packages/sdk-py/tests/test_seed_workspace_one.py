"""f-ws-kinds F1 — the workspace #1 seed (ADR "Model B", S1.3).

The seed is the ZERO-MIGRATION hinge: it declares two GLOBAL docs (a Workspace
whose id == the founder's live Azure tid, + an owner WorkspaceMembership). It
must NOT move existing rows, and re-running it must be idempotent (overwrite the
SAME two docs — never duplicate). These tests drive the importable seed builders
+ ``seed()`` against a real filesystem-backed kernel.

The seed script lives at ``scripts/seed_workspace_one.py``; we import it by path
(scripts/ isn't a package).
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.tenant import TenantExtension
from dna.kernel import Kernel

_SEED_PATH = (
    pathlib.Path(__file__).resolve().parents[3] / "scripts" / "seed_workspace_one.py"
)


def _load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_workspace_one", _SEED_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


seed_mod = _load_seed_module()


def _kernel(tmp_path) -> Kernel:
    k = Kernel()
    k.load(TenantExtension())
    src = FilesystemWritableSource(str(tmp_path / ".dna"))
    k.source(src)
    src.attach_kernel(k)
    return k


# ---------------------------------------------------------------------------
# 1. Builders — the id/name shape (documented, not invented)
# ---------------------------------------------------------------------------

def test_default_workspace_id_is_the_full_azure_tid():
    """The ADR shorthand is `c5b891f7`; the LIVE tenant column value is the full
    GUID — the seed default MUST be the full value or zero-migration breaks."""
    assert seed_mod.DEFAULT_WORKSPACE_ID == "c5b891f7-65c2-4417-a5af-22cab24dc1d5"
    # It starts with the ADR's shorthand segment.
    assert seed_mod.DEFAULT_WORKSPACE_ID.startswith("c5b891f7")


def test_membership_doc_name_is_deterministic():
    n1 = seed_mod.membership_doc_name("ws-1", "Founder@Example.com")
    n2 = seed_mod.membership_doc_name("ws-1", "founder@example.com")
    # Case-folded + slugified → same key regardless of input casing (the
    # idempotency key that stops a re-run duplicating the grant).
    assert n1 == n2 == "ws-1--founder-at-example-com"


def test_owner_membership_doc_shape():
    doc = seed_mod.owner_membership_doc("ws-1", "founder@example.com", "tid-9", "2026-07-15T00:00:00+00:00")
    spec = doc["spec"]
    assert doc["kind"] == "WorkspaceMembership"
    assert spec["role"] == "owner"
    assert spec["status"] == "active"          # founder is the owner, not a pending invitee
    assert spec["identity_oid"] is None        # binds on first Model-B sign-in
    assert spec["identity_tid"] == "tid-9"     # provenance only
    assert spec["identity_email"] == "founder@example.com"


# ---------------------------------------------------------------------------
# 2. Idempotency — run twice → exactly one Workspace + one Membership
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_is_idempotent(tmp_path):
    k = _kernel(tmp_path)

    async def counts():
        docs = await k.list_documents("_lib")
        ws = [n for (kind, n) in docs if kind == "Workspace"]
        mem = [n for (kind, n) in docs if kind == "WorkspaceMembership"]
        return ws, mem

    await seed_mod.seed(k, workspace_id="ws-1", founder_email="founder@example.com")
    ws1, mem1 = await counts()
    assert ws1 == ["ws-1"]
    assert mem1 == ["ws-1--founder-at-example-com"]

    # Re-run — overwrites the SAME two docs, no duplicates, no data move.
    await seed_mod.seed(k, workspace_id="ws-1", founder_email="founder@example.com")
    ws2, mem2 = await counts()
    assert ws2 == ["ws-1"]
    assert mem2 == ["ws-1--founder-at-example-com"]


# ---------------------------------------------------------------------------
# 3. The seeded workspace_id == the row key (the zero-migration guarantee)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seeded_workspace_id_equals_its_doc_key(tmp_path):
    """A row already keyed `tenant = <tid>` is readable as workspace #1 iff the
    seeded Workspace.workspace_id == that tid. We assert the seed keys the doc on
    the id it declares — the hinge that makes existing rows 'already his'."""
    k = _kernel(tmp_path)
    tid = "c5b891f7-65c2-4417-a5af-22cab24dc1d5"
    ws_name, _ = await seed_mod.seed(k, workspace_id=tid, founder_email="f@x.com")
    assert ws_name == tid
    got = await k.get_document("_lib", "Workspace", tid)
    assert got is not None
    spec = got.spec if hasattr(got, "spec") else got["spec"]
    assert spec["workspace_id"] == tid
