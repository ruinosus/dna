#!/usr/bin/env python3
"""Seed **workspace #1** — the founder's DNA tenancy root (ADR "Model B", F1).

THE ZERO-MIGRATION HINGE. Model B decouples the DNA tenant from the Azure
``tid`` and makes it a DNA-native *workspace id*. The founder's live data is
already physically keyed by his Azure tenant id in the ``dna_documents.tenant``
column. So we seed **workspace #1 with ``workspace_id`` == that exact tid** —
every existing row is then *already* this workspace's data. No move, no rewrite,
no downtime. This is a DECLARATIVE SEED (two docs), NOT a migration that touches
existing rows.

  ⚠️  ``workspace_id`` MUST equal the physical ``tenant`` column value byte-for-byte,
      else the zero-migration guarantee breaks. The ADR writes the tid as its
      short form ``c5b891f7`` (the GUID's first segment) for readability; the
      LIVE column value is the FULL Azure tenant GUID
      ``c5b891f7-65c2-4417-a5af-22cab24dc1d5`` — verified against the DB. That
      full GUID is the default below.

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
    DNA_FOUNDER_TID      Azure tid (provenance; default == DNA_WORKSPACE_ID)
"""
from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timezone
from typing import Any

TENANT_API = "github.com/ruinosus/dna/tenant/v1"
LIB_SCOPE = "_lib"  # GLOBAL Kinds live here (tenant column empty).

# The founder's LIVE Azure tenant id — the value already in dna_documents.tenant
# for all 19 of his rows. workspace #1's id == this → zero migration.
DEFAULT_WORKSPACE_ID = "c5b891f7-65c2-4417-a5af-22cab24dc1d5"
DEFAULT_WORKSPACE_NAME = "Barnabé Labs"
DEFAULT_FOUNDER_EMAIL = "jefferson.barnabe@gmail.com"

WORKSPACE_ID = os.environ.get("DNA_WORKSPACE_ID", DEFAULT_WORKSPACE_ID)
WORKSPACE_NAME = os.environ.get("DNA_WORKSPACE_NAME", DEFAULT_WORKSPACE_NAME)
FOUNDER_EMAIL = os.environ.get("DNA_FOUNDER_EMAIL", DEFAULT_FOUNDER_EMAIL)
FOUNDER_TID = os.environ.get("DNA_FOUNDER_TID", WORKSPACE_ID)


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
    workspace_id: str, name: str, created_by: str, created_at: str
) -> dict[str, Any]:
    """The Workspace identity doc (GLOBAL). The id is opaque + immutable and
    equals the physical ``tenant`` column value on every row it owns."""
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
    created_at: str | None = None,
) -> tuple[str, str]:
    """Write workspace #1 + its owner grant through ``kernel.write_document``
    (schema validation + cache invalidation fire, the same funnel every writer
    uses). GLOBAL → written into ``_lib`` with no tenant binding. Idempotent.

    Returns ``(workspace_doc_name, membership_doc_name)``.
    """
    now = created_at or datetime.now(timezone.utc).isoformat()

    ws = workspace_doc(workspace_id, name, founder_email, now)
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
        f"owner={FOUNDER_EMAIL}) into `{LIB_SCOPE}` …"
    )
    ws_name, mem_name = await seed(live.kernel)
    print(f"  seeded Workspace/{ws_name}")
    print(f"  seeded WorkspaceMembership/{mem_name}")
    print(
        "done. Every existing row keyed `tenant = "
        f"{WORKSPACE_ID}` is now workspace #1's data — zero migration."
    )


if __name__ == "__main__":
    os.environ.setdefault("DNA_BASE_DIR", os.path.join(os.getcwd(), ".dna"))
    asyncio.run(_run())
