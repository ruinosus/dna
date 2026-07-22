#!/usr/bin/env python3
"""Seed **workspace #1** — the founder's EXISTING DNA tenancy root (ADR "Model B").

⚠️  **SUPERSEDED for new workspaces.** Since decision **D5** a workspace is
created through ``POST /v1/workspaces`` (``create_workspace_impl``), which mints
its own opaque id server-side. Do NOT use this script to make a new workspace —
a hand-chosen id is exactly the thing D5 removed. What this script is still for
is re-declaring the ONE pre-existing workspace whose rows predate the write path.

That workspace's id is the GUID below. It is that value because the founder's
live rows were already physically keyed by his Azure tenant id in the
``dna_documents.tenant`` column, so adopting it as the workspace id meant no data
move. Post-D5 that is **historical trivia, not a rule**: the ``tid`` is a fact of
authentication and nothing in the runtime derives, compares or validates a
workspace id against one. The GUID below is simply this workspace's id.

  ⚠️  It MUST equal the physical ``tenant`` column value byte-for-byte, else the
      seeded docs describe a workspace that owns nothing. The ADR writes it in
      short form ``c5b891f7`` (the GUID's first segment) for readability; the
      LIVE column value is the FULL GUID
      ``c5b891f7-65c2-4417-a5af-22cab24dc1d5`` — verified against the DB. That
      full GUID is the default below.

This is a DECLARATIVE SEED (two docs), NOT a migration that touches existing rows.

What it writes (both GLOBAL, into the ``_lib`` scope — no tenant binding):
  1. a ``Workspace`` doc (``workspaces/<workspace_id>.yaml``) — the tenancy root
     identity;
  2. an owner ``WorkspaceMembership`` doc
     (``workspace-memberships/<workspace_id>--<email>.yaml``) — the founder's
     identity→workspace grant (role=owner, status=active).

The owner grant is seeded ``active`` (the founder IS the owner, not a pending
invitee) with ``identity_oid = null``: his Entra ``oid`` is not known at seed
time and binds on his first Model-B-aware sign-in (F2 resolution matches an
active-but-unbound grant on the verified email until the oid is captured). The
tid is recorded as provenance only.

Idempotent: re-running overwrites the SAME two docs (keyed by name) — no
duplicates. Works against whichever backend the runtime is pointed at
(Filesystem default, or Postgres via ``DNA_SOURCE_URL``).

Example — seed the durable Postgres board:

    DNA_SOURCE_URL=postgresql://dna@localhost:5433/dna \
    packages/cli/.venv/bin/python scripts/seed_workspace_one.py

Env knobs (all optional; defaults seed the real founder workspace #1):

    DNA_WORKSPACE_ID     workspace #1 id  (default: the founder's full Azure tid)
    DNA_WORKSPACE_NAME   display name     (default "Barnabé Labs")
    DNA_FOUNDER_EMAIL    owner identity   (default jefferson.barnabe@gmail.com)
    DNA_FOUNDER_TID      Azure tid. Recorded on the GRANT as PROVENANCE only —
                         there it authorizes nothing. It is ALSO this workspace's
                         BILLING ACCOUNT (see below). Default == DNA_WORKSPACE_ID,
                         for this one workspace where the two strings coincide.
    DNA_ACCOUNT_ID       the billing account that owns the workspace (default:
                         the founder's tid in the Entra ORG namespace,
                         ``entra-org:<DNA_FOUNDER_TID>`` — the account id must be
                         the NAMESPACED form the runtime mints, not the bare tid)

**This script is also the account_id BACKFILL** (s-account-scoped-plan). The
subscription is now keyed on the BILLING ACCOUNT, so ``Workspace.account_id``
records who pays; ``create_workspace_impl`` stamps it from verified claims at
creation, but workspace #1 predates that field and has none. Re-running this
seed writes it — the backfill is one idempotent re-run of the script that
already OWNS this workspace's declaration, using the ``tid`` knob it already
had. No new script, no migration, no schema change (Kind docs are rows in a
generic ``dna_documents`` table — the physical schema is untouched).

Why data and not a code fallback: a "workspace with no account_id ⇒ the account
IS the workspace_id" rule in the resolver would be the per-workspace plan model
resurrected as a silent default. Every future workspace whose account failed to
record — a lane with no account claim, a bug, a partial write — would quietly
become its own billing account instead of failing closed to Free. That is a trap
for the next person; a one-time backfill is not. The resolver therefore stays
strictly fail-closed and workspace #1 is fixed by writing the fact down.

Safe to do now, precisely: the portal's plan table is EMPTY (0 rows verified), so
no workspace is on a paid tier today. If the backfill were skipped entirely, the
worst outcome is workspace #1 resolving to Free — which is what it already is.
"""
from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from typing import Any

from dna.tenancy import PROVIDER_ACCOUNT_NAMESPACES, namespaced_account_id

TENANT_API = "github.com/ruinosus/dna/tenant/v1"
LIB_SCOPE = "_lib"  # GLOBAL Kinds live here (tenant column empty).

# Workspace #1's id — the value already in dna_documents.tenant for all 19 of the
# founder's rows (it was his Azure tenant id, which is how it came to be this
# string; post-D5 it is just this workspace's opaque id).
DEFAULT_WORKSPACE_ID = "c5b891f7-65c2-4417-a5af-22cab24dc1d5"
DEFAULT_WORKSPACE_NAME = "Barnabé Labs"
DEFAULT_FOUNDER_EMAIL = "jefferson.barnabe@gmail.com"

WORKSPACE_ID = os.environ.get("DNA_WORKSPACE_ID", DEFAULT_WORKSPACE_ID)
WORKSPACE_NAME = os.environ.get("DNA_WORKSPACE_NAME", DEFAULT_WORKSPACE_NAME)
FOUNDER_EMAIL = os.environ.get("DNA_FOUNDER_EMAIL", DEFAULT_FOUNDER_EMAIL)
FOUNDER_TID = os.environ.get("DNA_FOUNDER_TID", WORKSPACE_ID)
# The BILLING ACCOUNT that owns workspace #1: the founder's Entra `tid`, in the
# Entra ORGANIZATION namespace.
#
# ⚠️ THE NAMESPACE IS NOT DECORATION — it must match byte-for-byte what
# `dna.tenancy.account_id_from_claims` mints for the founder's own sign-in, or
# this workspace resolves to an AccountPlan nobody writes and silently meters as
# Free. Every account id carries WHICH KIND of account it is (`entra-org:` an
# Entra org, `workos-user:` a person on the consumer lane, ...) so a `tid` and a
# `sub` that happen to be the same literal string can never be the same account.
# It is built HERE through the SDK's own helper rather than by string-concat, so
# a change to the format cannot leave this backfill behind.
#
# That the tid also equals WORKSPACE_ID is a coincidence of this one workspace's
# history (its id was adopted from the tid so the `tenant` column needed no
# rewrite) — NOT a rule. Nothing in the runtime derives an account from a
# workspace id; if it did, every workspace would be its own account and the plan
# would be per-workspace again.
#
# ⚠️ dna-cloud must send this SAME namespaced string: the Stripe customer's
# `metadata.tenant` and the plan-table key were the BARE tid and now have to be
# `entra-org:<tid>`.
ACCOUNT_ID = os.environ.get(
    "DNA_ACCOUNT_ID",
    namespaced_account_id(PROVIDER_ACCOUNT_NAMESPACES["entra"].org, FOUNDER_TID),
)


def membership_doc_name(workspace_id: str, email: str) -> str:
    """Stable composite name for a (workspace, identity) grant.

    Format ``{workspace_id}--{email-slugified}``. Deterministic so a re-run of
    the seed (or a later invite of the same identity) updates the SAME doc
    instead of creating a duplicate — the idempotency key.
    """
    email_part = email.strip().lower().replace("@", "-at-").replace(".", "-")
    email_part = re.sub(r"[^a-z0-9-]", "-", email_part).strip("-")
    return f"{workspace_id}--{email_part}"


def workspace_doc(
    workspace_id: str, name: str, created_by: str, created_at: str,
    account_id: str | None = None,
) -> dict[str, Any]:
    """The Workspace identity doc (GLOBAL). The id is opaque + immutable and
    equals the physical ``tenant`` column value on every row it owns. For a NEW
    workspace this doc is written by ``create_workspace_impl`` with a minted id;
    here the id is supplied because the workspace already exists.

    ``account_id`` is the BILLING ACCOUNT that owns it — the backfill of the
    field workspace #1 predates. Writing it is what makes the account's plan
    (``AccountPlan``) apply to this workspace; leaving it null means the Free
    floor, never another account's tier."""
    return {
        "apiVersion": TENANT_API,
        "kind": "Workspace",
        "metadata": {"name": workspace_id},
        "spec": {
            "workspace_id": workspace_id,
            "name": name,
            "slug": "barnabe-labs",
            "created_by": created_by,
            "created_at": created_at,
            "account_id": account_id,
        },
    }


def owner_membership_doc(
    workspace_id: str, email: str, tid: str, created_at: str
) -> dict[str, Any]:
    """The founder's owner grant (GLOBAL). Active (he IS the owner); oid null
    until his first Model-B sign-in binds it; tid is provenance only."""
    return {
        "apiVersion": TENANT_API,
        "kind": "WorkspaceMembership",
        "metadata": {"name": membership_doc_name(workspace_id, email)},
        "spec": {
            "workspace_id": workspace_id,
            "identity_email": email.strip().lower(),
            "identity_oid": None,
            "identity_tid": tid,
            "role": "owner",
            "status": "active",
            "invited_by": None,
            "invited_at": created_at,
            "accepted_at": created_at,
        },
    }


async def seed(
    kernel: Any,
    *,
    workspace_id: str = WORKSPACE_ID,
    name: str = WORKSPACE_NAME,
    founder_email: str = FOUNDER_EMAIL,
    founder_tid: str = FOUNDER_TID,
    account_id: str | None = ACCOUNT_ID,
    created_at: str | None = None,
) -> tuple[str, str]:
    """Write workspace #1 + its owner grant through ``kernel.write_document``
    (schema validation + cache invalidation fire, the same funnel every writer
    uses). GLOBAL → written into ``_lib`` with no tenant binding. Idempotent.

    Returns ``(workspace_doc_name, membership_doc_name)``.
    """
    now = created_at or datetime.now(timezone.utc).isoformat()

    ws = workspace_doc(workspace_id, name, founder_email, now, account_id)
    await kernel.write_document(
        LIB_SCOPE, "Workspace", ws["metadata"]["name"], ws
    )

    mem = owner_membership_doc(workspace_id, founder_email, founder_tid, now)
    await kernel.write_document(
        LIB_SCOPE, "WorkspaceMembership", mem["metadata"]["name"], mem
    )
    return ws["metadata"]["name"], mem["metadata"]["name"]


async def _run() -> None:
    from dna_cli._mcp_server import boot_live

    live = await boot_live(scope=LIB_SCOPE)
    print(
        f"Seeding workspace #1 (id={WORKSPACE_ID}, name={WORKSPACE_NAME!r}, "
        f"owner={FOUNDER_EMAIL}, account={ACCOUNT_ID}) into `{LIB_SCOPE}` …"
    )
    ws_name, mem_name = await seed(live.kernel)
    print(f"  seeded Workspace/{ws_name}")
    print(f"  seeded WorkspaceMembership/{mem_name}")
    print(
        "done. Every existing row keyed `tenant = "
        f"{WORKSPACE_ID}` is this workspace's data."
    )
    print(
        f"  account_id={ACCOUNT_ID} — this workspace now resolves its Tier via "
        f"AccountPlan/{ACCOUNT_ID} (one plan covers every workspace this account "
        f"owns). Absent that doc: the Free floor."
    )
    print(
        "note: to CREATE a new workspace use POST /v1/workspaces — it mints its "
        "own opaque id (decision D5) and stamps account_id from the caller's "
        "verified account claim. This script only re-declares the pre-existing "
        "one (and backfills its account_id)."
    )


if __name__ == "__main__":
    os.environ.setdefault("DNA_BASE_DIR", os.path.join(os.getcwd(), ".dna"))
    asyncio.run(_run())
