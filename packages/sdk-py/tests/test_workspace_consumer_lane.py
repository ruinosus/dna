"""Issue ``i-072`` — the CONSUMER lane can own a workspace end to end.

The workspace axis used to read the Entra ``oid`` claim for every provider, so a
consumer-lane sign-in (WorkOS/AuthKit, Google, Clerk, Auth0 — durable subject in
``sub``) distilled to ``Identity(oid=None)``. Two things broke at once and they
are proven together here, because fixing only one is worse than fixing neither:

* **creation** — ``create_workspace_impl`` / ``provision_workspace_owner_impl``
  raised ``ValueError("the verified identity must carry an oid claim")``, so a
  consumer could never obtain a workspace at all;
* **binding** — even with a grant, the durable key written at creation had to be
  the SAME string the MCP/REST doors later derive from the token, or the grant
  would match nobody. That round trip (create here → resolve with the pure
  resolver) is the real assertion of this module.

The pure derivation is covered in ``test_workspace_resolution.py``; this is the
application half. No ``dna_cli`` import — the sdk-py CI job does not install it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application.live import LiveDna
from dna.application.runtime import (
    create_workspace_impl,
    list_workspaces_impl,
    provision_workspace_owner_impl,
)
from dna.kernel import Kernel
from dna.tenancy import Membership, identity_from_token, resolve_workspace

_BASE_SCOPE = "dna-development"

#: The WorkOS user id — the durable subject of the consumer lane. The portal
#: session supplies the email (an access token has none); the durable KEY is
#: the subject, and that is the whole point.
_WORKOS_SUB = "user_01JQCONSUMERLANEUSER"

#: What the portal sends for a Lane-B sign-in: the provider stamp + the token's
#: own claims. There is deliberately NO ``oid`` — inventing one is the bug.
_CONSUMER_CLAIMS = {
    "_dna_provider_family": "workos",
    "sub": _WORKOS_SUB,
    "org_id": "org_01JQCONSUMERORG",
    "email": "consumer@example.com",
    "email_verified": True,
}

#: The Entra lane, unchanged — the back-compat control for every assertion.
_ENTRA_CLAIMS = {"oid": "oid-founder", "email": "founder@example.com",
                 "tid": "tid-azure"}


def _doc(kind: str, name: str, spec: dict[str, Any]) -> dict[str, Any]:
    return {"apiVersion": "github.com/ruinosus/dna/v1", "kind": kind,
            "metadata": {"name": name}, "spec": spec}


@pytest.fixture()
def live(tmp_path: Path) -> LiveDna:
    base = tmp_path / ".dna"
    path = base / _BASE_SCOPE / "Genome.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(_doc("Genome", _BASE_SCOPE, {}),
                              default_flow_style=False))
    (base / "_lib").mkdir(parents=True)
    kernel = Kernel.auto()
    kernel.source(FilesystemWritableSource(str(base), kernel=kernel))
    kernel.cache(FilesystemCache(str(base)))
    return LiveDna(base_scope=_BASE_SCOPE, kernel=kernel, provider=None)


async def _grants(live: LiveDna) -> list[dict[str, Any]]:
    return [row.get("spec") or {} for row in await live.kernel.workspace_memberships()]


# ── creation binds the provider's OWN durable subject ──────────────────────


@pytest.mark.asyncio
async def test_consumer_lane_can_create_a_workspace(live: LiveDna) -> None:
    out = await create_workspace_impl(live, "Consumer Co", _CONSUMER_CLAIMS)

    assert out["role"] == "owner"
    # The grant is keyed on the WorkOS user id — NOT on a fabricated `oid`,
    # and NOT left null (a null key would fall back to email matching, which
    # an access token cannot supply on the tool-call path).
    grants = await _grants(live)
    assert len(grants) == 1
    assert grants[0]["identity_oid"] == _WORKOS_SUB
    assert grants[0]["status"] == "active"


@pytest.mark.asyncio
async def test_the_created_grant_is_the_one_the_doors_resolve(live: LiveDna) -> None:
    """The round trip that matters: the key written by the CREATION path is the
    key the MCP/REST doors derive from a bare ACCESS token (no email at all)."""
    out = await create_workspace_impl(live, "Consumer Co", _CONSUMER_CLAIMS)
    memberships = [Membership.from_spec(spec) for spec in await _grants(live)]

    access_token_claims = {  # what the door actually sees — no email, no oid.
        "_dna_provider_type": "workos", "sub": _WORKOS_SUB,
        "org_id": "org_01JQCONSUMERORG", "sid": "session_01JQ",
    }
    assert resolve_workspace(
        token_present=True,
        identity=identity_from_token(access_token_claims),
        requested=None,
        memberships=memberships,
    ) == out["workspace_id"]


@pytest.mark.asyncio
async def test_consumer_lane_provision_owner_and_list(live: LiveDna) -> None:
    """The every-sign-in reconcile (``provision-owner``) and the switcher's
    enumeration both accept the consumer identity."""
    out = await create_workspace_impl(live, "Consumer Co", _CONSUMER_CLAIMS)
    wid = out["workspace_id"]

    reconciled = await provision_workspace_owner_impl(live, wid, _CONSUMER_CLAIMS)
    assert reconciled["reason"] == "already_member"
    assert reconciled["membership"]["role"] == "owner"

    listed = await list_workspaces_impl(live, _CONSUMER_CLAIMS)
    assert [w["workspace_id"] for w in listed["workspaces"]] == [wid]


@pytest.mark.asyncio
async def test_consumer_lane_does_not_reach_another_lanes_workspace(
    live: LiveDna,
) -> None:
    """Widening WHICH claim is durable must not widen WHO is authorized."""
    entra = await create_workspace_impl(live, "Founder Co", _ENTRA_CLAIMS)
    memberships = [Membership.from_spec(spec) for spec in await _grants(live)]

    from dna.tenancy import CrossWorkspaceError

    with pytest.raises(CrossWorkspaceError):
        resolve_workspace(
            token_present=True,
            identity=identity_from_token(
                {"_dna_provider_family": "workos", "sub": _WORKOS_SUB}
            ),
            requested=entra["workspace_id"],
            memberships=memberships,
        )


# ── the Entra lane is untouched ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_entra_lane_still_binds_the_oid(live: LiveDna) -> None:
    await create_workspace_impl(live, "Founder Co", _ENTRA_CLAIMS)
    grants = await _grants(live)
    assert grants[0]["identity_oid"] == "oid-founder"
    assert grants[0]["identity_tid"] == "tid-azure"


@pytest.mark.asyncio
async def test_a_provider_with_no_durable_subject_still_fails_closed(
    live: LiveDna,
) -> None:
    """An unknown/`oidc` IdP has no claim DNA is willing to call durable, so a
    sign-in with no ``oid`` is still refused — and the message names the claim
    that provider actually needs, not a generic 'oid'."""
    with pytest.raises(ValueError, match="oid"):
        await create_workspace_impl(
            live, "Mystery Co",
            {"_dna_provider_type": "oidc", "sub": "s1", "email": "x@example.com"},
        )
