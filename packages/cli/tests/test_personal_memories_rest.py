"""``GET /v1/memories/personal`` — the READ face of the personal partition.

The write face (``POST /v1/memories/import``) shipped with identity derived
SERVER-SIDE from the verified token (INV-PERSONAL layer 1); until this route
the partition had ZERO reads — a memory imported by the founder appeared
nowhere. This suite pins the read to the SAME identity contract, mirroring
``test_memory_import_rest.py``:

  * a personal identity named in the QUERY is ignored — the read serves the
    TOKEN's partition, never the named victim's;
  * two identities never see each other's memories;
  * an authenticated token with no identity claim reads NOTHING (403), and
    ``DNA_PERSONAL_ID`` never rescues an authenticated request;
  * a SHARED bearer (``--auth token``) is not an identity — 403 ALWAYS;
  * ``--auth none`` reads the partition only via ``DNA_PERSONAL_ID``
    (single-user local); without it, 403.

Plus the shape contract: the item is the ``list_memories`` shape enriched
(i-068) with the per-item ``personal`` flag, and the response never echoes the
server-derived oid. Every read asserts against a seeded WRITE through the same
partition (anti-vacuity: the empty-before / populated-after baseline proves the
route reads real data, not a fixture echo).
"""
from __future__ import annotations

import pathlib
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"

_ALICE = {"oid": "oid-alice", "email": "alice@a.com"}
_BOB = {"oid": "oid-bob", "email": "bob@b.com"}
#: A verified token that carries NO durable identity claim at all.
_NO_ID = {"email": "ghost@x.com"}

_VICTIM_OID = "oid-victim"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
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


def _client(dna_dir, table=None) -> TestClient:
    return TestClient(R.build_app(
        base_dir=str(dna_dir), scope=_SCOPE, auth="config",
        verifier=_FakeVerifier(table if table is not None else
                               {"alice": _ALICE, "bob": _BOB, "ghost": _NO_ID}),
    ))


def _mif(doc_id: str, content: str, title: str | None = None) -> dict:
    return {
        "id": doc_id,
        "type": "semantic",
        "content": content,
        "created": "2026-07-19T10:00:00Z",
        "title": title or f"title for {doc_id}",
    }


def _import(c, token, *docs):
    """Seed the TOKEN's personal partition through the already-proven write
    face — the read under test must then surface exactly this."""
    r = c.post("/v1/memories/import",
               params={"scope": _SCOPE},
               headers={"Authorization": f"Bearer {token}"},
               json={"bundle": {"@graph": list(docs)}})
    assert r.status_code == 201, r.text
    return r


def _read(c, token, params=None):
    return c.get("/v1/memories/personal",
                 params={"scope": _SCOPE, **(params or {})},
                 headers={"Authorization": f"Bearer {token}"})


def _personal_items(body: dict) -> list[dict]:
    return [m for m in body["memories"] if m["personal"]]


# ── the happy path + shape ──────────────────────────────────────────────────


def test_read_surfaces_the_callers_own_import(dna_dir):
    """Empty before, populated after — the anti-vacuity baseline: the route
    reads the REAL partition the import wrote, not an echo."""
    with _client(dna_dir) as c:
        before = _read(c, "alice")
        assert before.status_code == 200, before.text
        assert _personal_items(before.json()) == []

        _import(c, "alice", _mif("mif-1", "the deploy needs 127.0.0.1",
                                 title="deploy lesson"))
        after = _read(c, "alice")

    assert after.status_code == 200, after.text
    body = after.json()
    assert body["partition"] == "personal"
    assert body["scope"] == _SCOPE
    mine = _personal_items(body)
    assert len(mine) == 1, body["memories"]
    # the item is the enriched list shape, values from the imported MIF.
    item = mine[0]
    assert item["personal"] is True
    assert item["summary"] == "deploy lesson"
    assert item["created_at"] == "2026-07-19T10:00:00Z"
    assert set(item) >= {"name", "summary", "area", "tags", "affect",
                         "created_at", "personal"}
    # the response never echoes the server-derived identity onto the wire.
    assert "oid-alice" not in after.text


def test_shared_base_memories_ride_along_flagged_not_personal(dna_dir):
    """The personal read unions the shared base scope — base items appear with
    ``personal: False``, so a UI can chip them apart."""
    import asyncio

    from dna_cli import _mcp_server as M

    async def seed_base():
        live = await M.boot_live(base_dir=str(dna_dir))
        await M.remember_impl(live, "a shared base note", scope=_SCOPE, tenant=None)

    asyncio.run(seed_base())
    with _client(dna_dir) as c:
        _import(c, "alice", _mif("mif-1", "a private note", title="private note"))
        r = _read(c, "alice")

    body = r.json()
    flags = {m["summary"]: m["personal"] for m in body["memories"]}
    assert flags.get("private note") is True
    assert flags.get("a shared base note") is False


# ── INV-PERSONAL layer 1: the identity is NEVER a caller argument ───────────


def test_identity_in_query_is_ignored(dna_dir):
    """`tenant`/`oid`/`personal_id` query params must not steer the read — the
    response is the TOKEN's partition, never the named victim's."""
    with _client(dna_dir) as c:
        _import(c, "alice", _mif("a-1", "alice private", title="alice note"))
        _import(c, "bob", _mif("b-1", "bob private", title="bob note"))
        r = _read(c, "alice", params={
            "tenant": f"personal:{_VICTIM_OID}",
            "oid": "oid-bob",
            "personal_id": "oid-bob",
            "memory_scope": "workspace",
            "family": "google",
        })
    assert r.status_code == 200, r.text
    summaries = {m["summary"] for m in _personal_items(r.json())}
    assert summaries == {"alice note"}
    assert "bob note" not in r.text


def test_two_identities_never_see_each_others_memories(dna_dir):
    with _client(dna_dir) as c:
        _import(c, "alice", _mif("a-1", "alice secret", title="alice secret"))
        _import(c, "bob", _mif("b-1", "bob secret", title="bob secret"))
        alice = _read(c, "alice").json()
        bob = _read(c, "bob").json()

    alice_sums = {m["summary"] for m in _personal_items(alice)}
    bob_sums = {m["summary"] for m in _personal_items(bob)}
    assert alice_sums == {"alice secret"}
    assert bob_sums == {"bob secret"}
    assert alice_sums.isdisjoint(bob_sums)


def test_no_identity_in_token_reads_nothing(dna_dir):
    """An authenticated token with no identity claim is denied — fail-closed,
    never a fallback to a workspace or a null partition."""
    with _client(dna_dir) as c:
        _import(c, "alice", _mif("a-1", "alice private"))
        r = _read(c, "ghost")
    assert r.status_code == 403, r.text
    assert "personal memory" in r.text.lower() or "identity" in r.text.lower()
    assert "alice" not in r.text


def test_env_personal_id_never_rescues_an_authenticated_request(dna_dir, monkeypatch):
    """THE multi-user footgun, read side: in a container serving N people,
    DNA_PERSONAL_ID cannot mean "the person of THIS request" — honoring it
    would serve one shared partition to every identity-less token."""
    with _client(dna_dir) as c:
        _import(c, "alice", _mif("a-1", "alice private"))
        monkeypatch.setenv("DNA_PERSONAL_ID", "oid-alice")
        r = _read(c, "ghost")
    assert r.status_code == 403, r.text


def test_missing_and_invalid_tokens_are_401(dna_dir):
    with _client(dna_dir) as c:
        anon = c.get("/v1/memories/personal", params={"scope": _SCOPE})
        bad = _read(c, "not-a-token")
    assert anon.status_code == 401
    assert bad.status_code == 401


def test_read_works_without_any_workspace_membership(dna_dir):
    """Personal memory is ORTHOGONAL to the workspace (decision B1): the person
    who just imported with no workspace yet must be able to READ it back — the
    fixture seeds no membership at all."""
    with _client(dna_dir) as c:
        _import(c, "alice", _mif("a-1", "wedge", title="the wedge"))
        r = _read(c, "alice")
    assert r.status_code == 200, r.text
    assert {m["summary"] for m in _personal_items(r.json())} == {"the wedge"}


# ── the other auth modes: shared bearer ≠ identity; env only offline ────────


def test_shared_bearer_is_always_403(dna_dir, monkeypatch):
    """``--auth token`` authenticates the DEPLOYMENT, not a person — the read
    face must refuse it even when DNA_PERSONAL_ID is set (a shared secret must
    never unlock one person's partition for every holder)."""
    app = R.build_app(base_dir=str(dna_dir), scope=_SCOPE,
                      auth="token", token="s3cret")
    with TestClient(app) as c:
        plain = c.get("/v1/memories/personal", params={"scope": _SCOPE},
                      headers={"Authorization": "Bearer s3cret"})
        monkeypatch.setenv("DNA_PERSONAL_ID", "oid-somebody")
        with_env = c.get("/v1/memories/personal", params={"scope": _SCOPE},
                         headers={"Authorization": "Bearer s3cret"})
        wrong = c.get("/v1/memories/personal", params={"scope": _SCOPE},
                      headers={"Authorization": "Bearer wrong"})
    assert plain.status_code == 403, plain.text
    assert with_env.status_code == 403, with_env.text
    assert wrong.status_code == 401  # the bearer gate still answers first


def test_auth_none_requires_env_identity(dna_dir, monkeypatch):
    """``--auth none`` is the single-user local deployment: DNA_PERSONAL_ID is
    the ONLY identity source, and without it the read fails closed."""
    import asyncio

    from dna_cli import _mcp_server as M

    async def seed():
        live = await M.boot_live(base_dir=str(dna_dir))
        await M.remember_impl(
            live, "my local note", scope=_SCOPE,
            memory_scope="personal", oid="oid-local")

    asyncio.run(seed())
    app = R.build_app(base_dir=str(dna_dir), scope=_SCOPE, auth="none")
    with TestClient(app) as c:
        denied = c.get("/v1/memories/personal", params={"scope": _SCOPE})
        monkeypatch.setenv("DNA_PERSONAL_ID", "oid-local")
        ok = c.get("/v1/memories/personal", params={"scope": _SCOPE})
    assert denied.status_code == 403, denied.text
    assert ok.status_code == 200, ok.text
    assert {m["summary"] for m in _personal_items(ok.json())} == {"my local note"}
