"""s-account-scoped-plan — the AccountPlan Kind (BILLING ACCOUNT→Tier) +
``kernel.account_plan()`` / ``kernel.account_for_workspace()``.

**The product decision under test:** a subscription belongs to a billing
ACCOUNT. One plan covers every workspace the account owns; creating a second
workspace is not a second charge. So the plan is keyed on ``account_id`` and
enforcement resolves ``workspace → Workspace.account_id → AccountPlan``.

This REPLACES ``tests/test_cloud_workspace_plan_kind.py``. The old model keyed
the plan per workspace, which forced whoever owned billing to fan out one doc
per workspace — and workspace enumeration is by MEMBERSHIP, not ownership, so
that fan-out would have handed a paid tier to workspaces the account never
bought. The tests here pin the properties that make the fan-out unnecessary and
its failure mode impossible.

What is covered:

1. the ``cloud`` extension registers AccountPlan from its descriptor
   (``kinds/account-plan.kind.yaml`` — record plane, GLOBAL, alias
   ``cloud-account-plan``), and ``WorkspacePlan`` is GONE and WRITE-BLOCKED
   (tombstoned in ``Kernel._REMOVED_KINDS``, not silently deleted);
2. ``kernel.account_plan`` resolves by ``spec.account_id`` — the assignment
   comes from the DOC dna-cloud writes, never a literal;
3. **one plan, many workspaces** — the whole point: N workspaces sharing an
   ``account_id`` all resolve to the ONE plan, with no per-workspace write;
4. **fail-closed** — a workspace with no ``account_id`` resolves to no plan
   (⇒ the Free floor), and never borrows one;
5. **isolation** — one account's plan NEVER reaches another account's
   workspace, including against malformed/blank-keyed docs;
6. the legacy workspace #1 case: its ``account_id`` is BACKFILLED as data
   (``scripts/seed_workspace_one.py``), and there is deliberately NO code
   fallback that treats a workspace id as its own account.
"""
from __future__ import annotations

import pytest

from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.cloud import CloudExtension
from dna.extensions.tenant import TenantExtension
from dna.kernel import Kernel
from dna.kernel.protocols import TenantScope

_CLOUD_API = "github.com/ruinosus/dna/cloud/v1"
_TENANT_API = "github.com/ruinosus/dna/tenant/v1"


def _account_plan(account_id: str, *, tier_id: str, source: str = "stripe",
                  status: str = "active") -> dict:
    """An AccountPlan doc. The assignment lives HERE (the doc), which dna-cloud's
    Stripe webhook writes — never in code."""
    return {
        "apiVersion": _CLOUD_API,
        "kind": "AccountPlan",
        "metadata": {"name": account_id},
        "spec": {
            "account_id": account_id,
            "tier_id": tier_id,
            "source": source,
            "status": status,
        },
    }


def _workspace(workspace_id: str, *, account_id: str | None,
               name: str = "W") -> dict:
    """A Workspace doc carrying (or deliberately NOT carrying) its billing
    account."""
    return {
        "apiVersion": _TENANT_API,
        "kind": "Workspace",
        "metadata": {"name": workspace_id},
        "spec": {
            "workspace_id": workspace_id,
            "name": name,
            "slug": workspace_id,
            "created_by": "someone@example.com",
            "created_at": "2026-01-01T00:00:00+00:00",
            "account_id": account_id,
        },
    }


async def _kernel(tmp_path) -> Kernel:
    """A kernel with the cloud + tenant Kinds and a writable `_lib`."""
    k = Kernel()
    k.load(CloudExtension())
    k.load(TenantExtension())
    src = FilesystemWritableSource(str(tmp_path / ".dna"))
    k.source(src)
    src.attach_kernel(k)
    return k


# ---------------------------------------------------------------------------
# 1. Kind registration + the WorkspacePlan tombstone
# ---------------------------------------------------------------------------

def test_account_plan_kind_registered_from_descriptor():
    k = Kernel()
    k.load(CloudExtension())
    kp = k.kind_port_for("AccountPlan")
    assert kp is not None
    assert kp.alias == "cloud-account-plan"
    assert kp.plane == "record"
    # GLOBAL — a shared base registry, no per-tenant override. It HAS to be: an
    # account sits above every workspace it owns.
    assert kp.scope == TenantScope.GLOBAL
    assert kp.storage.container == "account-plans"
    assert getattr(kp, "__declarative__", False) is True


def test_cloud_registers_tier_and_account_plan_and_no_workspace_plan():
    """The cloud extension registers Tier + AccountPlan. ``WorkspacePlan`` is
    RETIRED (and ``TenantPlan`` before it); ``Plan`` remains the SDLC Kind and is
    never registered here."""
    k = Kernel()
    k.load(CloudExtension())
    assert k.kind_port_for("Tier") is not None
    assert k.kind_port_for("AccountPlan") is not None
    assert k.kind_port_for("WorkspacePlan") is None
    assert k.kind_port_for("TenantPlan") is None
    assert k.kind_port_for("Plan") is None


def test_workspace_plan_is_tombstoned_not_silently_deleted():
    """``WorkspacePlan`` is an explicit WRITE-BLOCK tombstone, not a quiet
    deletion.

    This guard is load-bearing for MONEY, not hygiene. Writing an UNREGISTERED
    kind succeeds SILENTLY in the generic writer (an orphan doc with typed=None),
    so a stale dna-cloud deploy still calling the old per-workspace bridge would
    keep writing WorkspacePlan docs that NOTHING reads — a paying customer
    silently metered at Free, with no error anywhere to notice. The tombstone
    turns that into a loud failure, and the note tells the writer where to go."""
    assert "WorkspacePlan" in Kernel._REMOVED_KINDS
    note = Kernel._REMOVED_KIND_NOTES["WorkspacePlan"]
    assert "AccountPlan" in note


@pytest.mark.asyncio
async def test_writing_a_workspace_plan_is_refused(tmp_path):
    k = await _kernel(tmp_path)
    with pytest.raises(Exception) as exc:
        await k.write_document(
            "_lib", "WorkspacePlan", "acme",
            {"apiVersion": _CLOUD_API, "kind": "WorkspacePlan",
             "metadata": {"name": "acme"},
             "spec": {"workspace_id": "acme", "tier_id": "pro"}},
        )
    # The error must NAME the replacement — a blocked writer has to learn where
    # the data went, not merely that it is blocked.
    assert "AccountPlan" in str(exc.value)


# ---------------------------------------------------------------------------
# 2. Resolution — the assignment comes from the DOC
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_account_plan_resolves_from_doc(tmp_path):
    k = await _kernel(tmp_path)
    await k.write_document("_lib", "AccountPlan", "acct-acme",
                           _account_plan("acct-acme", tier_id="pro"))

    plan = await k.account_plan("acct-acme")
    assert plan is not None
    spec = plan.get("spec") or {}
    assert spec["tier_id"] == "pro"
    assert spec["account_id"] == "acct-acme"
    assert spec["source"] == "stripe"


@pytest.mark.asyncio
async def test_account_plan_unknown_account_returns_none(tmp_path):
    k = await _kernel(tmp_path)
    await k.write_document("_lib", "AccountPlan", "acct-acme",
                           _account_plan("acct-acme", tier_id="pro"))
    assert await k.account_plan("acct-globex") is None


@pytest.mark.asyncio
async def test_account_plan_assignment_is_data_not_code(tmp_path):
    """Rewrite the assignment, re-read, new tier — no redeploy."""
    k = await _kernel(tmp_path)
    await k.write_document("_lib", "AccountPlan", "acct-acme",
                           _account_plan("acct-acme", tier_id="pro"))
    assert (await k.account_plan("acct-acme"))["spec"]["tier_id"] == "pro"
    await k.write_document(
        "_lib", "AccountPlan", "acct-acme",
        _account_plan("acct-acme", tier_id="free", status="canceled"),
    )
    assert (await k.account_plan("acct-acme"))["spec"]["tier_id"] == "free"


@pytest.mark.asyncio
async def test_account_id_is_an_opaque_key_of_any_shape(tmp_path):
    """The account key is OPAQUE — matched, never parsed or validated.

    An Entra ``tid`` is a GUID, a WorkOS ``org_id`` is ``org_...``, a Google
    Workspace ``hd`` is a domain. All three are accounts. A future "validate the
    account id format" would turn this red, which is the point."""
    k = await _kernel(tmp_path)
    for account_id in ("c5b891f7-65c2-4417-a5af-22cab24dc1d5",
                       "org_01HXYZABCDEF", "example.com"):
        await k.write_document("_lib", "AccountPlan", account_id,
                               _account_plan(account_id, tier_id="enterprise"))
        plan = await k.account_plan(account_id)
        assert plan is not None
        assert plan["spec"]["tier_id"] == "enterprise"
        assert plan["spec"]["account_id"] == account_id


# ---------------------------------------------------------------------------
# 3. ONE plan, MANY workspaces — the decision itself
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_one_account_plan_covers_every_workspace_the_account_owns(tmp_path):
    """THE point of the re-keying: the account buys once, and every workspace it
    owns is covered — including ones created AFTER the purchase, with no billing
    write of any kind. Under the old per-workspace model each of these needed its
    own doc, and the third (created later) would have been stranded on Free until
    something remembered to fan out to it."""
    k = await _kernel(tmp_path)
    await k.write_document("_lib", "AccountPlan", "acct-acme",
                           _account_plan("acct-acme", tier_id="pro"))
    for ws in ("ws-aaa", "ws-bbb", "ws-ccc"):
        await k.write_document("_lib", "Workspace", ws,
                               _workspace(ws, account_id="acct-acme"))

    for ws in ("ws-aaa", "ws-bbb", "ws-ccc"):
        account_id = await k.account_for_workspace(ws)
        assert account_id == "acct-acme"
        assert (await k.account_plan(account_id))["spec"]["tier_id"] == "pro"


@pytest.mark.asyncio
async def test_a_new_workspace_needs_no_second_write_to_be_covered(tmp_path):
    """Creating the second workspace is not a second charge and not a second
    write. Assert the AccountPlan doc is untouched by the new workspace."""
    k = await _kernel(tmp_path)
    await k.write_document("_lib", "AccountPlan", "acct-acme",
                           _account_plan("acct-acme", tier_id="pro"))
    before = await k.account_plan("acct-acme")

    await k.write_document("_lib", "Workspace", "ws-second",
                           _workspace("ws-second", account_id="acct-acme"))

    after = await k.account_plan("acct-acme")
    assert (after or {}).get("spec") == (before or {}).get("spec")
    assert (await k.account_plan(
        await k.account_for_workspace("ws-second")))["spec"]["tier_id"] == "pro"


# ---------------------------------------------------------------------------
# 4. FAIL-CLOSED — no account ⇒ no plan ⇒ Free (never a borrowed tier)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workspace_without_account_id_resolves_to_no_plan(tmp_path):
    """A workspace with NO ``account_id`` gets NO plan — which the MCP guard
    turns into the **Free floor**.

    Crucially it does not get a plan even though a paid AccountPlan exists in the
    same store: "no account" must never degrade into "some account"."""
    k = await _kernel(tmp_path)
    await k.write_document("_lib", "AccountPlan", "acct-acme",
                           _account_plan("acct-acme", tier_id="pro"))
    await k.write_document("_lib", "Workspace", "ws-orphan",
                           _workspace("ws-orphan", account_id=None))

    assert await k.account_for_workspace("ws-orphan") is None
    # And the guard's second hop, given that None-ish key, yields nothing.
    assert await k.account_plan("") is None
    assert await k.account_plan(None) is None


@pytest.mark.asyncio
async def test_unknown_workspace_resolves_to_no_account(tmp_path):
    k = await _kernel(tmp_path)
    await k.write_document("_lib", "AccountPlan", "acct-acme",
                           _account_plan("acct-acme", tier_id="pro"))
    assert await k.account_for_workspace("ws-does-not-exist") is None


@pytest.mark.asyncio
async def test_blank_account_key_cannot_match_a_blank_keyed_doc(tmp_path):
    """A workspace with no account must not be able to match a malformed plan
    doc whose own ``account_id`` is blank.

    Without the pre-query blank guard, ``"" == ""`` would hand every accountless
    workspace in the deployment whatever tier that one malformed doc names. The
    lookup refuses a blank key BEFORE querying, so the doc below is unreachable
    no matter what it says."""
    k = await _kernel(tmp_path)
    # Write the malformed doc past schema validation, as a raw source write would.
    await k.write_document(
        "_lib", "AccountPlan", "blank",
        {"apiVersion": _CLOUD_API, "kind": "AccountPlan",
         "metadata": {"name": "blank"},
         "spec": {"account_id": "", "tier_id": "enterprise"}},
    )
    await k.write_document("_lib", "Workspace", "ws-orphan",
                           _workspace("ws-orphan", account_id=""))

    account_id = await k.account_for_workspace("ws-orphan")
    assert account_id is None            # "" is normalized to None, not kept.
    assert await k.account_plan("") is None
    assert await k.account_plan("   ") is None


# ---------------------------------------------------------------------------
# 5. ISOLATION — one account's plan never reaches another account's workspace
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_one_accounts_plan_never_reaches_another_accounts_workspace(tmp_path):
    """The money invariant. Acme pays for Pro; Globex pays for nothing. No
    resolution path may give a Globex workspace Acme's tier — not by ordering,
    not by fallback, not by "the only plan in the store"."""
    k = await _kernel(tmp_path)
    await k.write_document("_lib", "AccountPlan", "acct-acme",
                           _account_plan("acct-acme", tier_id="pro"))
    await k.write_document("_lib", "Workspace", "ws-acme",
                           _workspace("ws-acme", account_id="acct-acme"))
    await k.write_document("_lib", "Workspace", "ws-globex",
                           _workspace("ws-globex", account_id="acct-globex"))

    assert (await k.account_plan(
        await k.account_for_workspace("ws-acme")))["spec"]["tier_id"] == "pro"

    globex_account = await k.account_for_workspace("ws-globex")
    assert globex_account == "acct-globex"
    assert await k.account_plan(globex_account) is None  # ⇒ Free floor.


@pytest.mark.asyncio
async def test_a_guest_workspace_does_not_inherit_the_payers_plan(tmp_path):
    """The exact failure the abandoned portal-side fan-out would have shipped.

    Acme's owner is also an invited member of a workspace FOUNDED BY GLOBEX. A
    fan-out driven by ``GET /v1/workspaces`` — which enumerates by MEMBERSHIP,
    not ownership — would have written Acme's Pro tier onto that Globex
    workspace, giving Globex a tier nobody paid for. Here the tier is read from
    the workspace's OWN ``account_id``, so membership is irrelevant and the guest
    workspace stays on its founder's account."""
    k = await _kernel(tmp_path)
    await k.write_document("_lib", "AccountPlan", "acct-acme",
                           _account_plan("acct-acme", tier_id="pro"))
    # Founded by Globex; Acme's owner merely holds a membership in it.
    await k.write_document("_lib", "Workspace", "ws-globex-founded",
                           _workspace("ws-globex-founded", account_id="acct-globex"))

    assert await k.account_for_workspace("ws-globex-founded") == "acct-globex"
    assert await k.account_plan("acct-globex") is None


# ---------------------------------------------------------------------------
# 6. The legacy workspace — backfilled as DATA, with no code fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_legacy_workspace_resolves_once_its_account_is_backfilled(tmp_path):
    """Workspace #1 predates ``account_id``. Its account is the founder's Entra
    ``tid`` — the same string the portal's plan table and the Stripe customer's
    ``metadata.tenant`` are keyed by. That this workspace's ID also happens to be
    that GUID is a historical coincidence (the id was adopted from the tid so the
    ``tenant`` column needed no rewrite), NOT a rule the code may rely on.

    Backfilled (``scripts/seed_workspace_one.py``), it resolves normally — no
    special case anywhere in the resolver."""
    k = await _kernel(tmp_path)
    tid = "c5b891f7-65c2-4417-a5af-22cab24dc1d5"
    await k.write_document("_lib", "AccountPlan", tid,
                           _account_plan(tid, tier_id="pro"))
    await k.write_document("_lib", "Workspace", tid,
                           _workspace(tid, account_id=tid))

    assert await k.account_for_workspace(tid) == tid
    assert (await k.account_plan(tid))["spec"]["tier_id"] == "pro"


@pytest.mark.asyncio
async def test_there_is_no_workspace_id_is_its_own_account_fallback(tmp_path):
    """The trap that was deliberately NOT built.

    A tolerant "no ``account_id`` ⇒ the account is the workspace_id" rule would
    have made the legacy workspace work with zero data changes — and would have
    resurrected the per-workspace plan model as a permanent silent default. Every
    future workspace whose account failed to record (a lane with no account
    claim, a bug, a partial write) would quietly become its own billing account
    instead of failing closed to Free.

    So: even with an AccountPlan keyed on the workspace's OWN id, an
    account-less workspace resolves to nothing. The legacy case is fixed by
    writing the fact down, not by a rule that would outlive it."""
    k = await _kernel(tmp_path)
    tid = "c5b891f7-65c2-4417-a5af-22cab24dc1d5"
    await k.write_document("_lib", "AccountPlan", tid,
                           _account_plan(tid, tier_id="pro"))
    # The SAME workspace, but its account_id was never backfilled.
    await k.write_document("_lib", "Workspace", tid,
                           _workspace(tid, account_id=None))

    assert await k.account_for_workspace(tid) is None


@pytest.mark.asyncio
async def test_seed_script_backfills_the_account_id(tmp_path):
    """The backfill itself: re-running the seed writes workspace #1's
    ``account_id``, which is what makes its AccountPlan apply. This pins the
    backfill to a test so "the migration" cannot silently stop happening."""
    import importlib.util
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "_seed_ws_one", root / "scripts" / "seed_workspace_one.py"
    )
    seed_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed_mod)

    k = await _kernel(tmp_path)
    ws_name, _ = await seed_mod.seed(
        k, workspace_id="c5b891f7", founder_tid="c5b891f7",
        account_id="c5b891f7",
    )
    doc = await k.get_document("_lib", "Workspace", ws_name)
    assert (doc["spec"] if "spec" in doc else doc)["account_id"] == "c5b891f7"
    assert await k.account_for_workspace("c5b891f7") == "c5b891f7"
