"""``POST /v1/memories/import`` — the remote MIF import face.

The route writes PERSONAL data, so the boundary under test is the IDENTITY.
INV-PERSONAL layer 1 says the personal ``oid`` is derived SERVER-SIDE from the
verified token and is NEVER a caller argument; these tests pin that at the HTTP
edge, where a caller controls the body and the query string:

  * a personal identity named in the BODY or the QUERY is ignored — the write
    lands in the TOKEN's partition, and never in the named victim's;
  * an authenticated request whose token carries no identity claim writes
    NOTHING (403, fail-closed) — and ``DNA_PERSONAL_ID`` must not rescue it,
    which is the multi-user footgun the REST seam exists to avoid;
  * two identities never see each other's import.

Plus the shape contract: happy path + dedupe idempotence, and the bounded/
malformed payloads that must fail CLEARLY with nothing written (never a silent
partial import).
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


def _mif(doc_id: str, content: str) -> dict:
    return {
        "id": doc_id,
        "type": "semantic",
        "content": content,
        "created": "2026-07-19T10:00:00Z",
        "title": f"title for {doc_id}",
    }


def _bundle(*docs) -> dict:
    return {"@graph": list(docs)}


def _read_partition(dna_dir, tenant: str, kind: str = "Engram") -> list[str]:
    """Every doc name in a partition, read straight off the kernel (bypassing the
    HTTP face) — the ground truth for 'what was actually written where'."""
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        names = []
        async for raw in live.kernel.query(_SCOPE, kind, tenant=tenant):
            meta = raw.get("metadata") or {}
            names.append(meta.get("name") or raw.get("name"))
        return names

    return asyncio.run(go())


def _post(c, token, body):
    return c.post("/v1/memories/import",
                  params={"scope": _SCOPE},
                  headers={"Authorization": f"Bearer {token}"},
                  json=body)


# ── the happy path + dedupe idempotence ─────────────────────────────────────


def test_import_writes_to_the_callers_personal_partition(dna_dir):
    with _client(dna_dir) as c:
        r = _post(c, "alice", {"bundle": _bundle(
            _mif("mif-1", "the deploy needs 127.0.0.1, not localhost"),
            _mif("mif-2", "the plan bridge is PUT /v1/workspace-plan"),
        )})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["imported"] == 2 and body["skipped"] == 0 and body["failed"] == 0
    assert body["received"] == 2
    assert body["partition"] == "personal"
    # the response never echoes the server-derived identity back onto the wire
    assert "oid-alice" not in r.text

    # ... and it is physically in Alice's PERSONAL partition, both faces of
    # --as both: the verbatim MIF passthrough AND the recallable Engram.
    engrams = _read_partition(dna_dir, "personal:oid-alice", "Engram")
    mifs = _read_partition(dna_dir, "personal:oid-alice", "Memory")
    assert len(engrams) == 2, engrams
    assert len(mifs) == 2, mifs


def test_reimport_is_idempotent_by_mif_id(dna_dir):
    payload = {"bundle": _bundle(_mif("mif-1", "alpha"), _mif("mif-2", "beta"))}
    with _client(dna_dir) as c:
        first = _post(c, "alice", payload)
        second = _post(c, "alice", payload)

    assert first.json()["imported"] == 2
    # the SAME ids again → all skipped, nothing rewritten (the §6 contract)
    assert second.status_code == 201
    assert second.json() == {**second.json(), "imported": 0, "skipped": 2, "failed": 0}
    assert len(_read_partition(dna_dir, "personal:oid-alice", "Engram")) == 2


def test_dedupe_off_rewrites_the_same_ids(dna_dir):
    payload = {"bundle": _bundle(_mif("mif-1", "alpha")), "dedupe": "off"}
    with _client(dna_dir) as c:
        _post(c, "alice", payload)
        again = _post(c, "alice", payload)
    assert again.json()["imported"] == 1 and again.json()["skipped"] == 0
    # same MIF id → same deterministic slot, so no duplicate doc
    assert len(_read_partition(dna_dir, "personal:oid-alice", "Engram")) == 1


def test_as_passthrough_writes_only_the_verbatim_mif(dna_dir):
    with _client(dna_dir) as c:
        r = _post(c, "alice",
                  {"bundle": _bundle(_mif("mif-1", "alpha")), "as": "passthrough"})
    assert r.status_code == 201 and r.json()["imported"] == 1
    assert len(_read_partition(dna_dir, "personal:oid-alice", "Memory")) == 1
    assert _read_partition(dna_dir, "personal:oid-alice", "Engram") == []


# ── INV-PERSONAL layer 1: the identity is NEVER a caller argument ───────────


def test_personal_identity_in_body_is_ignored(dna_dir):
    """A body naming someone else's partition must not steer the write."""
    with _client(dna_dir) as c:
        r = _post(c, "alice", {
            "bundle": _bundle(_mif("mif-1", "alpha")),
            # every plausible spelling of "write this somewhere else"
            "oid": _VICTIM_OID,
            "personal_id": _VICTIM_OID,
            "tenant": f"personal:{_VICTIM_OID}",
            "memory_scope": "workspace",
            "family": "google",
        })
    assert r.status_code == 201, r.text

    # It landed in the TOKEN's partition ...
    assert len(_read_partition(dna_dir, "personal:oid-alice", "Engram")) == 1
    # ... and nowhere the caller named.
    assert _read_partition(dna_dir, f"personal:{_VICTIM_OID}", "Engram") == []
    assert _read_partition(dna_dir, "personal:google:oid-alice", "Engram") == []


def test_personal_identity_in_query_is_ignored(dna_dir):
    """A `tenant`/`oid` query param must not steer the write either."""
    with _client(dna_dir) as c:
        r = c.post("/v1/memories/import",
                   params={"scope": _SCOPE, "tenant": f"personal:{_VICTIM_OID}",
                           "oid": _VICTIM_OID},
                   headers={"Authorization": "Bearer alice"},
                   json={"bundle": _bundle(_mif("mif-1", "alpha"))})
    assert r.status_code == 201, r.text
    assert len(_read_partition(dna_dir, "personal:oid-alice", "Engram")) == 1
    assert _read_partition(dna_dir, f"personal:{_VICTIM_OID}", "Engram") == []


def test_no_identity_in_token_writes_nothing(dna_dir):
    """An authenticated request whose token carries no identity claim is denied
    — fail-closed, never a fallback to a workspace or a null partition."""
    with _client(dna_dir) as c:
        r = _post(c, "ghost", {"bundle": _bundle(_mif("mif-1", "alpha"))})
    assert r.status_code == 403, r.text
    assert "personal memory" in r.text.lower() or "identity" in r.text.lower()

    # NOTHING was written, anywhere.
    assert _read_partition(dna_dir, "personal:oid-alice", "Engram") == []
    assert _read_partition(dna_dir, None, "Engram") == []
    assert _read_partition(dna_dir, None, "Memory") == []


def test_env_personal_id_never_rescues_an_authenticated_request(dna_dir, monkeypatch):
    """THE multi-user footgun: DNA_PERSONAL_ID is documented as the offline
    single-user identity. In a container serving N people it cannot mean "the
    person of THIS request" — so on an authenticated deployment it must never be
    consulted, or every caller would share one partition."""
    monkeypatch.setenv("DNA_PERSONAL_ID", "oid-the-container")
    with _client(dna_dir) as c:
        r = _post(c, "ghost", {"bundle": _bundle(_mif("mif-1", "alpha"))})
    assert r.status_code == 403, r.text
    assert _read_partition(dna_dir, "personal:oid-the-container", "Engram") == []


def test_missing_and_invalid_tokens_are_refused(dna_dir):
    with _client(dna_dir) as c:
        anon = c.post("/v1/memories/import",
                      json={"bundle": _bundle(_mif("mif-1", "alpha"))})
        bad = _post(c, "not-a-token", {"bundle": _bundle(_mif("mif-1", "alpha"))})
    assert anon.status_code == 401
    assert bad.status_code == 401
    assert _read_partition(dna_dir, "personal:oid-alice", "Engram") == []


def test_two_identities_never_see_each_others_import(dna_dir):
    with _client(dna_dir) as c:
        _post(c, "alice", {"bundle": _bundle(_mif("a-1", "alice private note"))})
        _post(c, "bob", {"bundle": _bundle(_mif("b-1", "bob private note"))})

    alice = _read_partition(dna_dir, "personal:oid-alice", "Engram")
    bob = _read_partition(dna_dir, "personal:oid-bob", "Engram")
    assert len(alice) == 1 and len(bob) == 1
    assert set(alice).isdisjoint(set(bob))


def test_import_works_without_any_workspace_membership(dna_dir):
    """Personal memory is ORTHOGONAL to the workspace (decision B1): a person
    with no workspace must still be able to import their own memory — the whole
    product wedge. The fixture seeds no membership at all."""
    with _client(dna_dir) as c:
        r = _post(c, "alice", {"bundle": _bundle(_mif("mif-1", "alpha"))})
    assert r.status_code == 201, r.text
    assert r.json()["imported"] == 1


# ── bounded + malformed payloads: fail clearly, never a partial import ──────


def test_malformed_bundle_is_400_and_writes_nothing(dna_dir):
    """A doc missing MIF Level 1 core fields fails the WHOLE bundle before any
    write — the valid sibling in the same payload must not be half-imported."""
    bad = {"id": "mif-2", "type": "semantic"}  # no content, no created
    with _client(dna_dir) as c:
        r = _post(c, "alice", {"bundle": _bundle(_mif("mif-1", "valid"), bad)})
    assert r.status_code == 400, r.text
    assert "missing required field" in r.text
    assert _read_partition(dna_dir, "personal:oid-alice", "Engram") == []


def test_unrecognized_bundle_shape_is_400(dna_dir):
    with _client(dna_dir) as c:
        r = _post(c, "alice", {"bundle": "just a string"})
    assert r.status_code == 400 and "unrecognized MIF" in r.text


def test_missing_bundle_field_is_400(dna_dir):
    with _client(dna_dir) as c:
        r = _post(c, "alice", {"as": "both"})
    assert r.status_code == 400 and "bundle" in r.text


def test_bad_as_and_dedupe_values_are_400(dna_dir):
    with _client(dna_dir) as c:
        bad_as = _post(c, "alice",
                       {"bundle": _bundle(_mif("m", "x")), "as": "sideways"})
        bad_dd = _post(c, "alice",
                       {"bundle": _bundle(_mif("m", "x")), "dedupe": "vibes"})
    assert bad_as.status_code == 400 and "passthrough/native/both" in bad_as.text
    assert bad_dd.status_code == 400 and "id/content-hash/off" in bad_dd.text
    assert _read_partition(dna_dir, "personal:oid-alice", "Engram") == []


def test_oversized_bundle_is_413_and_writes_nothing(dna_dir, monkeypatch):
    monkeypatch.setattr(R, "_MAX_IMPORT_BYTES", 512)
    with _client(dna_dir) as c:
        r = _post(c, "alice",
                  {"bundle": _bundle(_mif("mif-1", "x" * 4000))})
    assert r.status_code == 413, r.text
    assert "limit" in r.text
    assert _read_partition(dna_dir, "personal:oid-alice", "Engram") == []


def test_too_many_docs_is_413_and_writes_nothing(dna_dir, monkeypatch):
    monkeypatch.setattr(R, "_MAX_IMPORT_DOCS", 2)
    with _client(dna_dir) as c:
        r = _post(c, "alice", {"bundle": _bundle(
            _mif("m-1", "a"), _mif("m-2", "b"), _mif("m-3", "c"))})
    assert r.status_code == 413, r.text
    assert _read_partition(dna_dir, "personal:oid-alice", "Engram") == []


def test_counts_always_reconcile_with_the_bundle_size(dna_dir):
    """imported + skipped + failed == received, always — so a partial import is
    reported, never silent."""
    docs = [_mif(f"m-{i}", f"body {i}") for i in range(5)]
    with _client(dna_dir) as c:
        _post(c, "alice", {"bundle": _bundle(*docs[:2])})
        r = _post(c, "alice", {"bundle": _bundle(*docs)})
    b = r.json()
    assert b["imported"] + b["skipped"] + b["failed"] == b["received"] == 5
    assert b["skipped"] == 2
