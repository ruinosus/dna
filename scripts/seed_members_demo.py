#!/usr/bin/env python3
"""Seed the DNA Cloud **Membros** demo data — the RBAC graph for the ``dna``
project (Role ladder + Memberships).

Mirrors ``scripts/seed_portfolio_demo.py``: writes each doc through
``kernel.write_document`` (schema validation + cache invalidation fire, the same
funnel every writer uses), bound to a tenant so the source routes them into that
tenant's overlay. Works against either backend the runtime is pointed at:

    • Filesystem (default)     — DNA_BASE_DIR (defaults to ``<cwd>/.dna``); the
      YAMLs land under ``.dna/tenants/<tenant>/…`` and MUST be committed.
    • Postgres (durable board) — export ``DNA_SOURCE_URL`` and the docs are
      written into the ``dna_documents`` table with the tenant column.

Env knobs (all optional; the defaults seed the ``demo`` FS tenant):

    DNA_SEED_SCOPE   scope to seed        (default ``dna-development``)
    DNA_SEED_TENANT  tenant to seed into  (default ``demo``)
    DNA_SEED_ORG     org the memberships are scoped to (default ``barnabe-labs``)
    DNA_SEED_PROJECT project slug the project grants target (default ``dna``)

Example — seed the durable Postgres test tenant:

    DNA_SOURCE_URL=postgresql://dna@localhost:5433/dna \
    DNA_SEED_TENANT=c5b891f7-65c2-4417-a5af-22cab24dc1d5 \
    packages/cli/.venv/bin/python scripts/seed_members_demo.py

Idempotent: re-running overwrites the same docs.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

PORTFOLIO_API = "github.com/ruinosus/dna/portfolio/v1"

SCOPE = os.environ.get("DNA_SEED_SCOPE", "dna-development")
TENANT = os.environ.get("DNA_SEED_TENANT", "demo")
ORG = os.environ.get("DNA_SEED_ORG", "barnabe-labs")
PROJECT = os.environ.get("DNA_SEED_PROJECT", "dna")


def _role(role_id: str, display: str, rank: int, caps: list[str]) -> dict:
    return {
        "apiVersion": PORTFOLIO_API,
        "kind": "Role",
        "metadata": {"name": role_id},
        "spec": {
            "role_id": role_id,
            "display_name": display,
            "rank": rank,
            "capabilities": caps,
            "can_delete": role_id != "owner",
        },
    }


# The four standard rungs — the ladder AS DATA (rank drives highest-role-wins).
ROLES = [
    _role("owner", "Owner", 40,
          ["project.write", "member.invite", "member.remove", "billing.manage"]),
    _role("admin", "Admin", 30, ["project.write", "member.invite", "member.remove"]),
    _role("member", "Member", 20, ["project.write"]),
    _role("guest", "Guest", 10, ["project.read"]),
]

# The membership graph for the `dna` project:
#   • jefferson — org Owner (superuser → Owner on every project in the org)
#   • ana       — org Member + project Admin (highest-role-wins → Admin here)
#   • rafael    — project Guest only (no org grant → no access to sibling projects)
MEMBERS = [
    ("jefferson@barnabelabs.com", "org", ORG, "owner"),
    ("ana@barnabelabs.com", "org", ORG, "member"),
    ("ana@barnabelabs.com", "project", PROJECT, "admin"),
    ("rafael@contratado.dev", "project", PROJECT, "guest"),
]


async def _run() -> None:
    from dna_cli._mcp_server import boot_live
    from dna.application.runtime import _member_doc_name

    live = await boot_live(scope=SCOPE)
    kernel = live.kernel
    now = datetime.now(timezone.utc).isoformat()

    async def write(doc: dict) -> None:
        await kernel.write_document(
            SCOPE, doc["kind"], doc["metadata"]["name"], doc, tenant=TENANT,
        )
        print(f"  seeded {doc['kind']}/{doc['metadata']['name']}")

    print(f"Seeding Membros (scope={SCOPE}, tenant={TENANT}, org={ORG}, "
          f"project={PROJECT}) …")
    for role in ROLES:
        await write(role)
    for user, scope_type, scope_ref, role in MEMBERS:
        name = _member_doc_name(user, scope_type, scope_ref)
        await write({
            "apiVersion": PORTFOLIO_API,
            "kind": "Membership",
            "metadata": {"name": name},
            "spec": {
                "user": user,
                "scope_type": scope_type,
                "scope_ref": scope_ref,
                "role": role,
                "status": "active",
                "invited_at": now,
            },
        })
    print("done.")


if __name__ == "__main__":
    os.environ.setdefault("DNA_BASE_DIR", os.path.join(os.getcwd(), ".dna"))
    asyncio.run(_run())
