"""Approval is the human act, and it is what gives the Kind effect.

Authoring writes an INERT document (``test_kind_authoring_route.py``);
this suite covers the second act — the one that confers effect — and the audit
trail that makes it worth anything.

Three properties, each checked against the thing that would actually break:

1. **approval confers effect** — the same Kind has NO port on a kernel booted
   fresh over the store before approval, and HAS one after. Asserting on a fresh
   kernel is the whole point: the registry is per-kernel and outlives the
   ``instance_async`` of the process that wrote the document, so probing
   registration in the writing process can be true for the wrong reason.
2. **each act records its OWN verified actor** — the proposer is stamped at the
   authoring door from the identity that authored, the approver at the approval
   door from the identity that approved. Not "two different people": see
   :func:`test_a_solo_author_may_approve_their_own_proposal` — the audit REPORTS
   a coincidence, it does not refuse it. What must never happen is one act
   wearing the other's name.
3. **neither actor comes from the request body** — a caller-supplied
   ``approved_by``/``proposed_by`` is dropped, verified on the STORED document.

Auth is ``config`` with a fake verifier (the ``test_personal_memories_rest.py``
shape): a bearer string is a key into a claims table, so two tokens are two
distinct VERIFIED identities — which is the only way to test attribution at all.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_WID = "ws-approval00000000000001"

_SCHEMA = {
    "type": "object",
    "properties": {"titulo": {"type": "string"}},
    "required": ["titulo"],
}

#: The two actors. The AGENT proposes (that is the product: a tenant authors a
#: Kind through an agent); the HUMAN approves.
_AGENT = {"oid": "oid-agent", "email": "agent@tenant.example"}
_HUMAN = {"oid": "oid-human", "email": "human@tenant.example"}


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    # The ``_lib`` registry scope — where a KindNamespace claim lives. Authoring
    # READS it before minting and a filesystem source raises for a scope
    # directory that is not there; the shipped example scope ships none.
    lib = dst / "_lib"
    lib.mkdir(parents=True, exist_ok=True)
    (lib / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        "metadata:\n  name: _lib\n"
        "spec: {}\n"
    )
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv("DNA_PERSONAL_ID", raising=False)
    return dst


class _FakeAccess:
    def __init__(self, claims):
        self.claims = claims


class _FakeVerifier:
    """The bearer string is a KEY into a claims table; an unknown token → None
    (→ 401), mirroring the composite N-provider verifier's contract."""

    def __init__(self, table):
        self._table = table

    async def verify_token(self, token):
        claims = self._table.get(token)
        return _FakeAccess(claims) if claims is not None else None


def _client(dna_dir) -> TestClient:
    return TestClient(R.build_app(
        base_dir=str(dna_dir), scope=_SCOPE, auth="config",
        verifier=_FakeVerifier({"agent": _AGENT, "human": _HUMAN}),
    ))


def _on_fresh_kernel(dna_dir, fn):
    """Run ``fn(live)`` against a kernel booted FRESH over the same store, with
    the scope's manifest instance built — i.e. after the real 2-phase load has
    parsed every stored ``KindDefinition`` and applied the approval gate."""
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        await live.kernel.instance_async(_SCOPE)
        return await fn(live)

    return asyncio.run(go())


def _registered_port(dna_dir, kind: str):
    async def probe(live):
        return live.kernel.kind_port_for(kind, scope=_SCOPE)

    return _on_fresh_kernel(dna_dir, probe)


def _stored_spec(dna_dir, name: str) -> dict:
    async def probe(live):
        raw = await live.kernel.get_document(_SCOPE, "KindDefinition", name)
        return dict((raw or {}).get("spec") or {})

    return _on_fresh_kernel(dna_dir, probe)


def _author(c, token, kind="Contrato", **body):
    return c.post("/v1/kinds", params={"tenant": _WID},
                  headers={"Authorization": f"Bearer {token}"},
                  json={"kind": kind, "schema": _SCHEMA, **body})


def _approve(c, token, kind="Contrato", **body):
    return c.post(f"/v1/kinds/{kind}/approve", params={"tenant": _WID},
                  headers={"Authorization": f"Bearer {token}"},
                  json=body or None)


def _row(c, token, kind="Contrato") -> dict:
    listed = c.get("/v1/kinds", params={"tenant": _WID},
                   headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200, listed.text
    rows = [k for k in listed.json()["kinds"] if k["kind"] == kind]
    assert rows, listed.json()
    return rows[0]


# ── 1. approval is what confers effect ────────────────────────────────────


def test_approval_registers_the_kind_and_names_both_actors(dna_dir):
    with _client(dna_dir) as c:
        assert _author(c, "agent").status_code == 201

        # Before approval: the Kind exists as a document and has NO effect.
        assert _registered_port(dna_dir, "Contrato") is None

        r = _approve(c, "human")
        assert r.status_code == 200, r.text
        assert r.json()["approved"] is True

        # After approval — on a kernel that loads the store from scratch, so
        # this cannot be true merely because nothing reloaded.
        assert _registered_port(dna_dir, "Contrato") is not None

        row = _row(c, "human")

    assert row["approved"] is True
    # Each act carries ITS OWN verified actor. Not "two different people" (see
    # the solo test below) — the property is that neither act wears the other's
    # name, which is what makes the audit worth reading.
    assert row["proposed_by"] == _AGENT["email"], row
    assert row["approved_by"] == _HUMAN["email"], row
    assert row["proposed_at"] and row["approved_at"], row


# ── 2. the policy: coincidence is a FACT, not a refusal ───────────────────


def test_a_solo_author_may_approve_their_own_proposal(dna_dir):
    """The risk is an AGENT approving its own proposal, and that is already
    prevented mechanically: the authoring door cannot write ``approved_by`` at
    all, so approval takes a second call to a different route. A solo developer
    whose agent proposes and who then approves with their own login is two
    credentials and is exactly the product. Refusing on identity equality would
    block the most common user for no security gain — so the audit REPORTS the
    coincidence. (Four-eyes is a workspace policy, for when there is a home for
    workspace policy.)"""
    with _client(dna_dir) as c:
        assert _author(c, "human").status_code == 201
        r = _approve(c, "human")
        assert r.status_code == 200, r.text
        row = _row(c, "human")

    assert row["proposed_by"] == row["approved_by"] == _HUMAN["email"], row
    assert row["approved"] is True, row
    assert _registered_port(dna_dir, "Contrato") is not None


# ── 3. neither actor comes from the body ──────────────────────────────────


def test_neither_actor_can_be_supplied_by_the_caller(dna_dir):
    """Attribution a caller can forge is not attribution. Verified on the
    STORED document — a route that reported the truth while persisting the
    caller's string would hand the next reader a forged audit."""
    with _client(dna_dir) as c:
        r = _author(c, "agent", proposed_by="ceo@tenant.example",
                    approved_by="ceo@tenant.example")
        assert r.status_code == 201, r.text
        name = r.json()["name"]
        assert r.json()["approved"] is False, r.text

        assert _approve(c, "human", approved_by="ceo@tenant.example",
                        proposed_by="ceo@tenant.example").status_code == 200

    spec = _stored_spec(dna_dir, name)
    assert spec["proposed_by"] == _AGENT["email"], spec
    assert spec["approved_by"] == _HUMAN["email"], spec


def test_approving_a_kind_that_was_never_authored_is_a_404(dna_dir):
    """The approval door confers effect; a door that silently created the
    document it was asked to approve would be an authoring door with an
    approval marker — exactly what must not exist.

    The detail is asserted, not just the status: before the route existed this
    test passed on FastAPI's own routing 404 (``{"detail": "Not Found"}``) —
    a test that passes for the wrong reason. The refusal must name the Kind it
    could not find."""
    with _client(dna_dir) as c:
        r = _approve(c, "human", kind="NuncaExistiu")
        assert r.status_code == 404, r.text
        assert "NuncaExistiu" in r.json()["detail"], r.text
    assert _registered_port(dna_dir, "NuncaExistiu") is None
