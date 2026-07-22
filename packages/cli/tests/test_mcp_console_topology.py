"""The CONSOLE topology, end-to-end — the exact production shape twice missed.

The dna-cloud console (i-044) connects to the per-workspace URL
``/w/<workspace-id>/mcp``; the session is BOUND to a Model-B workspace whose
scope ``tenant-<id>`` is born with a Genome declaring ``parent_scope`` = the
vendor's base scope (i-058). The 2026-07-21 production regression was reported
from THIS topology, and neither #209's suites nor the first i-069 tests pinned
it: they exercised a single scope, no workspace binding, no transport.

This suite boots the REAL server (``build_server`` + ``build_http_app``), real
JWT auth, a real HTTP client on the BOUND URL, and pins the three facts the
console depends on:

  1. a personal ``remember`` and a personal ``recall`` in a workspace-bound
     session resolve the SAME home — (base scope, ``personal:<oid>``) — and the
     recall FINDS the write (the workspace binding never leaks into the
     personal branch);
  2. the bound session's WORKSPACE surfaces (``list_memories``, non-personal
     ``recall``) resolve to ``tenant-<ws>`` and never surface the personal
     partition — the honest empty that a console canvas fed by them will show
     (isolation, and the UX trap documented by the i-069 forensics);
  3. the REST personal read (``GET /v1/memories/personal``) SURVIVES a
     forwarded workspace scope — the console lives on ``tenant-<ws>`` and the
     0.25.0 route forwards its ``scope`` query param, which is exactly the
     retargeting defect i-069 fixed (reverting the ``_resolve_memory_target``
     pin makes this test fail).
"""
from __future__ import annotations

import asyncio
import contextlib
import pathlib
import shutil
import socket
import threading
import time

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE_DNA = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_BASE_SCOPE = "concierge"  # stands in for the vendor base (dna-development)
_VENDOR_WS = "founder-tid-1111"  # Model B: vendor workspace id == founder tid
_WS = "w-gen-123"  # a GENERATED (D5) workspace — resolves to tenant-w-gen-123
_WS_SCOPE = f"tenant-{_WS}"
_OID = "59064647-9976-4bd7-b25c-e1eed545e07f"
_ISSUER = "https://dna.test/"
_AUD = "dna-mcp"
_SUMMARY = "nome-barna: o fundador chama-se Jefferson Barnabe"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@contextlib.contextmanager
def _serve(app):
    """Serve an ASGI app (the FULL Starlette wrapper, /w/ mount included) on a
    background uvicorn; yields the root URL. The stock ``http_server`` fixture
    serves ``server.http_app()`` — the bare ``/mcp`` — and can never exercise
    the per-workspace mount, which is the whole point here."""
    import uvicorn

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    uv = uvicorn.Server(config)
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        uv.should_exit = True
        thread.join(timeout=10)


async def _seed(base_dir: str) -> None:
    """The console world: the founder's active membership in the generated
    workspace + the workspace scope's i-058 Genome (parent = base)."""
    from dna_cli import _mcp_server as M

    live = await M.boot_live(scope=_BASE_SCOPE, base_dir=base_dir)
    await live.kernel.write_document(
        "_lib", "WorkspaceMembership", f"{_WS}--founder",
        {"apiVersion": "github.com/ruinosus/dna/cloud/v1",
         "kind": "WorkspaceMembership",
         "metadata": {"name": f"{_WS}--founder"},
         "spec": {"workspace_id": _WS, "identity_email": "barna@x.com",
                  "identity_oid": _OID, "role": "owner", "status": "active"}})
    await live.kernel.write_document(
        _WS_SCOPE, "Genome", _WS_SCOPE,
        {"apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
         "metadata": {"name": _WS_SCOPE},
         "spec": {"parent_scope": _BASE_SCOPE}})


@pytest.fixture
def console(tmp_path, monkeypatch):
    """The bound-session scenario, run ONCE over real transport; yields the
    captured tool results + the base dir for kernel-level assertions."""
    pytest.importorskip("fastmcp")
    pytest.importorskip("uvicorn")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth
    from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

    from dna_cli import _mcp_server as M

    dst = tmp_path / ".dna"
    shutil.copytree(_BASE_DNA, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.setenv("DNA_VENDOR_WORKSPACE", _VENDOR_WS)
    monkeypatch.setenv("DNA_WORKSPACE_DEFINITIONS_BASE", _BASE_SCOPE)
    for var in ("DNA_SOURCE_URL", "DNA_PERSONAL_ID", "DNA_QUOTA_DSN",
                "DNA_QUOTA_REQUIRE_TIERS"):
        monkeypatch.delenv(var, raising=False)

    asyncio.run(_seed(str(dst)))

    kp = RSAKeyPair.generate()
    verifier = JWTVerifier(public_key=kp.public_key, issuer=_ISSUER,
                           audience=_AUD)
    token = kp.create_token(
        issuer=_ISSUER, audience=_AUD, subject=_OID,
        scopes=["dna.read", "dna.write"],
        additional_claims={"oid": _OID, "tid": _VENDOR_WS,
                           "email": "barna@x.com"})

    server = M.build_server(scope=_BASE_SCOPE, base_dir=str(dst), auth=verifier)
    app = M.build_http_app(server)

    async def drive(url: str) -> dict:
        out: dict = {}
        async with Client(url, auth=BearerAuth(token)) as client:
            r = await client.call_tool(
                "remember", {"summary": _SUMMARY, "personal": True})
            out["remember"] = r.structured_content
            r = await client.call_tool(
                "recall", {"query": "nome-barna fundador",
                           "personal": True, "k": 5})
            out["recall_personal"] = r.structured_content
            r = await client.call_tool("list_memories", {})
            out["list_workspace"] = r.structured_content
            r = await client.call_tool(
                "recall", {"query": "nome-barna fundador", "k": 5})
            out["recall_workspace"] = r.structured_content
        return out

    with _serve(app) as root:
        # The console's URL (i-044): the workspace named IN THE PATH.
        out = asyncio.run(drive(f"{root}/w/{_WS}/mcp"))
    out["base_dir"] = str(dst)
    return out


def test_bound_session_personal_write_and_read_share_one_home(console):
    """The founder's test, replayed over the wire: a personal remember in the
    workspace-BOUND session lands at (base scope, ``personal:<oid>``) — and the
    personal recall in the SAME bound session finds it. The workspace in the
    URL must never retarget either half."""
    from dna_cli import _mcp_server as M

    hits = console["recall_personal"]["hits"]
    assert any(_SUMMARY.split(":")[0] in (h.get("name") or "") for h in hits), hits
    # The recall answered from the BASE scope, not the bound workspace's.
    assert console["recall_personal"]["scope"] == _BASE_SCOPE

    async def where() -> tuple[list, list]:
        live = await M.boot_live(scope=_BASE_SCOPE,
                                 base_dir=console["base_dir"])
        base = [d async for d in live.kernel.query(
            _BASE_SCOPE, "Engram", tenant=f"personal:{_OID}")]
        ws = [d async for d in live.kernel.query(
            _WS_SCOPE, "Engram", tenant=f"personal:{_OID}")]
        return base, ws

    base, ws = asyncio.run(where())
    assert [d for d in base if d["spec"].get("summary") == _SUMMARY]
    # ... and NOTHING personal was written under the workspace scope.
    assert not [d for d in ws if d["spec"].get("summary") == _SUMMARY]


def test_bound_session_workspace_surfaces_never_leak_personal(console):
    """The bound session's WORKSPACE surfaces resolve to ``tenant-<ws>`` and
    honestly exclude the personal partition — the isolation invariant, and the
    documented trap: a console canvas fed by ``list_memories`` / non-personal
    ``recall`` shows EMPTY while the personal memory sits safe in its home."""
    lw = console["list_workspace"]
    assert lw["scope"] == _WS_SCOPE
    assert not any(m.get("summary") == _SUMMARY
                   for m in lw.get("memories", []))
    rw = console["recall_workspace"]
    assert rw["scope"] == _WS_SCOPE
    assert not any(_SUMMARY.split(":")[0] in (h.get("name") or "")
                   for h in rw.get("hits", []))


def test_rest_personal_read_survives_forwarded_workspace_scope(tmp_path,
                                                               monkeypatch):
    """``GET /v1/memories/personal?scope=tenant-<ws>`` — the console's own
    scope, forwarded exactly as the 0.25.0 route does — still serves the
    caller's partition from its ONE home (i-069). Before the fix the resolver
    honored the forwarded scope and read a (scope, partition) pair nothing
    writes to: an honest-looking EMPTY over intact data."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from dna_cli import _mcp_server as M
    from dna_cli import _rest_api as R

    dst = tmp_path / ".dna"
    shutil.copytree(_BASE_DNA, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    for var in ("DNA_SOURCE_URL", "DNA_PERSONAL_ID"):
        monkeypatch.delenv(var, raising=False)

    async def seed_memory() -> None:
        live = await M.boot_live(scope=_BASE_SCOPE, base_dir=str(dst))
        await M.remember_impl(live, _SUMMARY, None,
                              memory_scope="personal", oid=_OID)

    asyncio.run(seed_memory())

    class _Access:
        claims = {"oid": _OID, "email": "barna@x.com"}

    class _Verifier:
        async def verify_token(self, token):
            return _Access() if token == "founder" else None

    app = R.build_app(base_dir=str(dst), scope=_BASE_SCOPE, auth="config",
                      verifier=_Verifier())
    with TestClient(app) as c:
        r = c.get("/v1/memories/personal",
                  params={"scope": _WS_SCOPE},  # the forwarded console scope
                  headers={"Authorization": "Bearer founder"})
    assert r.status_code == 200, r.text
    body = r.json()
    personal = [m for m in body["memories"] if m.get("personal")]
    assert any(m.get("summary") == _SUMMARY for m in personal), body
