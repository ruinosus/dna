"""The authoring door accepts a ``KindDefinition`` WITHOUT relaxing the generic
bootstrap refusal — a dedicated route with its own authorization. What it writes
is inert: no approval marker, so the registry never takes it.

Three properties, and each is checked against the thing that would actually
break if it regressed:

1. **the write is real and auditable** — ``POST /v1/kinds`` persists a document
   a later ``GET /v1/kinds`` lists — **and it has no effect**: a FRESH kernel
   booted over the same store, which runs the real 2-phase load and therefore
   the real approval gate, has no port for the authored Kind. Asserting against
   a fresh kernel is the point: the process that wrote the document could
   trivially "not have it registered" simply because nothing reloaded.
2. **the generic doors stay shut** — both of them. ``write_document_impl`` is
   the core the MCP ``write_document`` tool delegates to, and it refuses every
   BOOTSTRAP Kind: ``KindDefinition`` (door one) *and* ``Genome``, the ROOT
   document whose ``spec.custom_kinds`` entries are the SECOND store-loaded
   registration door — the one that needs no new document and would otherwise
   let a tenant approve their own Kind by writing a manifest. The REST
   tenant-layer ``PUT /v1/definitions/KindDefinition/...`` is checked too: it is
   a different mechanism (the layer-policy gate) reaching the same verdict.
3. **the door cannot approve its own write** — a caller-supplied
   ``approved_by`` is dropped on the floor, verified on the STORED document, not
   merely in the response body.

The routes are auth-guarded (``dependencies=guarded`` — bearer verification
only) and not plan-gated, so ``--auth none`` exercises the exact same handler
code the token/config lanes would; mirrors ``test_definitions_rest.py``.
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
_WID = "ws-authoring00000000000001"

_SCHEMA = {
    "type": "object",
    "properties": {"titulo": {"type": "string"}},
    "required": ["titulo"],
}


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A writable copy of the concierge scope, wired via DNA_BASE_DIR (same
    fixture shape as test_definitions_rest.py's ``dna_dir``)."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    # The ``_lib`` registry — where a KindNamespace claim lives. Stood up the
    # same way ``sdk-py/tests/test_namespace_assignment.py``'s fixture stands it
    # up, because ``assign_namespace`` READS it before minting and a filesystem
    # source raises ``FileNotFoundError`` for a scope directory that is not
    # there. Every real deployment has it (a Postgres source has no such
    # notion, and workspace provisioning writes the claim at birth); the
    # example scope simply ships none.
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
    return dst


def _client(dna_dir) -> TestClient:
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE))


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


# ── 1. it exists, and it has no effect ────────────────────────────────────


def test_an_authored_kind_exists_and_has_no_effect(dna_dir):
    with _client(dna_dir) as c:
        r = c.post(
            "/v1/kinds",
            params={"tenant": _WID},
            json={"kind": "Contrato", "schema": _SCHEMA},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["approved"] is False
        assert body["kind"] == "Contrato"
        # The assigned value is an apiVersion PREFIX, never an apiVersion —
        # a claim stored with a version segment resolves to nothing.
        assert "/" not in body["namespace"], body

        # It EXISTS as a document — that is what makes it auditable…
        listed = c.get("/v1/kinds", params={"tenant": _WID})
        assert listed.status_code == 200, listed.text
        rows = [k for k in listed.json()["kinds"] if k["kind"] == "Contrato"]
        assert rows, listed.json()
        assert rows[0]["approved"] is False

    # …and it has NO effect: a kernel that loads this store from scratch does
    # not register it, so nothing validates or routes documents of that Kind.
    assert _registered_port(dna_dir, "Contrato") is None


# ── 2. neither generic door opened ────────────────────────────────────────


def test_the_generic_bootstrap_refusal_is_untouched(dna_dir):
    """The dedicated door must not open a generic one — and there are TWO."""
    from dna.application.documents import (
        BootstrapKindWriteRefused,
        write_document_impl,
    )

    async def probe(live):
        out = {}
        # Door one: a KindDefinition through the generic write-any-document core.
        with pytest.raises(BootstrapKindWriteRefused) as one:
            await write_document_impl(
                live, kind="KindDefinition", name="anything",
                spec={"target_api_version": "evil.example/v1",
                      "target_kind": "Contrato", "alias": "evil-contrato",
                      "origin": "evil.example", "storage": {"type": "yaml"},
                      "approved_by": "me@example.com"},
                scope=_SCOPE,
            )
        out["kinddef"] = str(one.value)
        # Door two: the ROOT document, whose spec.custom_kinds entries are the
        # OTHER store-loaded registration path — and each entry carries its own
        # approved_by. If a tenant could write this, self-approval would be one
        # manifest away and the whole gate decorative.
        with pytest.raises(BootstrapKindWriteRefused) as two:
            await write_document_impl(
                live, kind="Genome", name=_SCOPE,
                spec={"custom_kinds": [
                    {"apiVersion": "evil.example/v1", "kind": "Contrato",
                     "alias": "evil-contrato", "approved_by": "me@example.com"},
                ]},
                scope=_SCOPE,
            )
        out["root"] = str(two.value)
        return out

    refusals = _on_fresh_kernel(dna_dir, probe)
    assert "BOOTSTRAP" in refusals["kinddef"], refusals["kinddef"]
    assert "BOOTSTRAP" in refusals["root"], refusals["root"]

    # And the REST tenant-layer write — a different mechanism (the layer-policy
    # gate), the same verdict.
    with _client(dna_dir) as c:
        r = c.put(
            "/v1/definitions/KindDefinition/anything",
            params={"tenant": _WID},
            json={"spec": {}},
        )
        assert r.status_code == 403, r.text


# ── 3. the door cannot approve its own write ──────────────────────────────


def test_the_route_cannot_approve_its_own_write(dna_dir):
    """Approval comes from a different path, with a different actor."""
    with _client(dna_dir) as c:
        r = c.post(
            "/v1/kinds",
            params={"tenant": _WID},
            json={"kind": "Contrato", "schema": {"type": "object"},
                  "approved_by": "me@example.com"},
        )
        assert r.status_code == 201, r.text
        assert r.json()["approved"] is False, (
            "a caller-supplied approval must be ignored — otherwise the agent "
            "approves its own proposal and the gate is decorative"
        )
        name = r.json()["name"]

    # The response is not the evidence — the STORED document is. A route that
    # merely reported `approved: false` while persisting the caller's marker
    # would register the Kind on the next load.
    spec = _stored_spec(dna_dir, name)
    assert not spec.get("approved_by"), spec
    assert _registered_port(dna_dir, "Contrato") is None
