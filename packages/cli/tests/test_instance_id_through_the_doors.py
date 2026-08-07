"""``metadata.id`` — i-114, asserted THROUGH the doors, not against the kernel.

The design in one line: identity and address are separated by WHO WRITES them.
The ``.dna/`` a human authors and reviews keeps the NAME; the ``dna_edges`` row
the write path derives keeps ID AND NAME — Kubernetes' rule, whose
``apiVersion/kind/metadata/spec`` grammar this repo already speaks.

Everything here goes through REST or MCP, because every property below has a
kernel-level test that would still pass while the FEATURE is broken. The two
that matter most:

* the id must SURVIVE a write that carries no id. The application-level write
  path rebuilds the envelope as ``{"metadata": {"name": name}, "spec": …}`` and
  throws the caller's metadata away — so EVERY write through REST and MCP
  arrives at the kernel with no id at all. A kernel test that hands the
  pipeline an envelope keeps whatever it put there and proves nothing.
* an ambiguous prefix must be REFUSED. A resolver that returned the first match
  passes every "resolves an id" test ever written; only asking it a question
  with two right answers can tell the difference.
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
_WID = "ws-documents000000000001"

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["titulo"],
    "properties": {"titulo": {"type": "string"}},
}


def _store_at(dst: pathlib.Path) -> pathlib.Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_BASE, dst)
    lib = dst / "_lib"
    lib.mkdir(parents=True, exist_ok=True)
    (lib / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        "metadata:\n  name: _lib\n"
        "spec: {}\n"
    )
    return dst


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = _store_at(tmp_path / ".dna")
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _client(dna_dir, **kwargs) -> TestClient:
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE, **kwargs))


def _author_and_approve(c: TestClient, *, kind="Contrato", schema=None):
    r = c.post("/v1/kinds", params={"tenant": _WID},
               json={"kind": kind, "schema": schema or _SCHEMA})
    assert r.status_code == 201, r.text
    a = c.post(f"/v1/kinds/{kind}/approve", params={"tenant": _WID})
    assert a.status_code == 200, a.text
    return r.json()


def _write(c: TestClient, name, *, kind="Contrato", titulo="t", **params):
    r = c.post(f"/v1/kinds/{kind}/instances",
               params={"tenant": _WID, **params},
               json={"metadata": {"name": name}, "spec": {"titulo": titulo}})
    assert r.status_code == 201, r.text
    return r.json()


def _get(c: TestClient, name, *, kind="Contrato"):
    r = c.get(f"/v1/kinds/{kind}/instances/{name}", params={"tenant": _WID})
    assert r.status_code == 200, r.text
    return r.json()


def _id_of(c: TestClient, name, *, kind="Contrato") -> str:
    return _get(c, name, kind=kind)["instance"]["metadata"]["id"]


# ── 1. a written instance HAS an id, and it is well formed ──────────────────


def test_a_write_through_the_door_mints_an_id(dna_dir):
    """The floor. Identity has to arrive without anybody asking for it — the
    POST body carries ``metadata`` and ``spec`` and no id, because a caller
    must not be able to choose one."""
    from dna.kernel.identity import INSTANCE_ID_LENGTH, is_instance_id

    with _client(dna_dir) as c:
        _author_and_approve(c)
        _write(c, "c1")
        got = _id_of(c, "c1")
        assert is_instance_id(got), got
        assert len(got) == INSTANCE_ID_LENGTH


def test_a_caller_cannot_choose_the_id(dna_dir):
    """An id supplied in the request body is IGNORED, not honoured.

    Identity a caller can name is identity a caller can COLLIDE, on purpose or
    by copy-paste — and two instances holding one id breaks the derived graph
    silently, in the direction where nothing raises."""
    with _client(dna_dir) as c:
        _author_and_approve(c)
        r = c.post("/v1/kinds/Contrato/instances", params={"tenant": _WID},
                   json={"metadata": {"name": "c1", "id": "aaaaaaaaaaaa"},
                         "spec": {"titulo": "t"}})
        assert r.status_code == 201, r.text
        assert _id_of(c, "c1") != "aaaaaaaaaaaa"


# ── 2. THE MUTANT: the id survives a write that carries none ────────────────


def test_the_id_survives_every_subsequent_write(dna_dir):
    """⚠️ The test this feature lives or dies by.

    ``write_instance_impl`` rebuilds the envelope from scratch —
    ``{"metadata": {"name": name}, "spec": …}`` — so the caller's metadata,
    id included, never reaches the kernel. If the pipeline minted a fresh id
    whenever the envelope arrived without one, EVERY write through REST and
    MCP would re-identify the instance, and every ``to_id`` pointing at it
    would go stale with nothing raising anywhere.

    MUTANT: change ``_ensure_instance_id`` to ``mint_instance_id()`` instead of
    adopting the stored id, and only this assertion moves.
    """
    with _client(dna_dir) as c:
        _author_and_approve(c)
        _write(c, "c1", titulo="one")
        first = _id_of(c, "c1")
        for titulo in ("two", "three", "four"):
            _write(c, "c1", titulo=titulo)
            assert _id_of(c, "c1") == first, (
                "the id changed on a plain update — the instance was "
                "re-identified by its own edit"
            )
        assert _get(c, "c1")["instance"]["spec"]["titulo"] == "four"


def test_two_instances_never_share_an_id(dna_dir):
    with _client(dna_dir) as c:
        _author_and_approve(c)
        _write(c, "c1")
        _write(c, "c2")
        assert _id_of(c, "c1") != _id_of(c, "c2")


def test_deleting_and_recreating_under_the_same_name_is_a_different_instance(dna_dir):
    """Kubernetes' uid property, and the reason the id is RANDOM rather than
    derived from the content or from the key: delete-and-recreate under the
    same name is a DIFFERENT object, and a machine holding the old id must be
    able to tell. A content-derived or key-derived id would hand the corpse's
    identity to its replacement — which is precisely the confusion
    ``ownerReferences`` carries a uid to prevent.

    Runs on the MCP lane because that is where ``delete_instance`` is served;
    REST has no delete door for a generic Kind.
    """
    pytest.importorskip("fastmcp")
    _mcp_write(dna_dir, "c-recreate")
    before = _mcp_id(dna_dir, "c-recreate")

    _call(dna_dir, "delete_instance", kind=_MCP_KIND, name="c-recreate",
          api_version=_MCP_API_VERSION, scope=_SCOPE)
    _mcp_write(dna_dir, "c-recreate")

    assert _mcp_id(dna_dir, "c-recreate") != before, (
        "the recreated instance inherited the deleted one's identity"
    )


# ── 3. resolution by prefix, and the refusal ────────────────────────────────


def test_a_short_prefix_resolves_to_the_instance(dna_dir):
    """The git move: quote the first few characters, get the whole thing —
    and the response echoes the FULL id, the way ``git rev-parse`` does."""
    with _client(dna_dir) as c:
        _author_and_approve(c)
        _write(c, "c1", titulo="hello")
        full = _id_of(c, "c1")

        r = c.get(f"/v1/instances/{full[:5]}", params={"tenant": _WID})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == full
        assert body["kind"] == "Contrato"
        assert body["name"] == "c1"
        assert body["instance"]["spec"]["titulo"] == "hello"


def test_the_full_id_resolves_too(dna_dir):
    with _client(dna_dir) as c:
        _author_and_approve(c)
        _write(c, "c1")
        full = _id_of(c, "c1")
        r = c.get(f"/v1/instances/{full}", params={"tenant": _WID})
        assert r.status_code == 200, r.text
        assert r.json()["id"] == full


def test_an_ambiguous_prefix_is_refused_and_names_the_candidates(dna_dir):
    """⚠️ The second mutant, and the harder one to catch by accident.

    A resolver that returned ``candidates[0]`` passes every other test in this
    file. The only question that separates it from a correct one is a question
    with two right answers — so this test MANUFACTURES the collision instead of
    waiting for a 60-bit birthday: it writes two instances and then rewrites
    their ids on disk so they share a four-character prefix.

    The refusal must also NAME the candidates, because "ambiguous" without them
    leaves the caller with no move.
    """
    import json
    import yaml

    with _client(dna_dir) as c:
        _author_and_approve(c)
        _write(c, "c1")
        _write(c, "c2")

    # Rewrite the two ids on disk so they collide on their first four chars.
    twins = ("zzzz" + "aaaaaaaa", "zzzz" + "bbbbbbbb")
    paths = sorted(pathlib.Path(dna_dir).rglob("c[12].yaml"))
    assert len(paths) == 2, paths
    for path, new_id in zip(paths, twins):
        raw = yaml.safe_load(path.read_text())
        raw["metadata"]["id"] = new_id
        path.write_text(yaml.safe_dump(raw, sort_keys=False))

    with _client(dna_dir) as c:
        r = c.get("/v1/instances/zzzz", params={"tenant": _WID})
        assert r.status_code == 409, (r.status_code, r.text)
        detail = json.dumps(r.json())
        assert twins[0] in detail and twins[1] in detail, detail

        # ...and one more character disambiguates, which is what makes the
        # refusal actionable rather than a dead end.
        ok = c.get(f"/v1/instances/{twins[0][:5]}", params={"tenant": _WID})
        assert ok.status_code == 200, ok.text
        assert ok.json()["id"] == twins[0]


def test_a_prefix_that_matches_nothing_is_a_404(dna_dir):
    with _client(dna_dir) as c:
        _author_and_approve(c)
        _write(c, "c1")
        r = c.get("/v1/instances/qqqqqqqq", params={"tenant": _WID})
        assert r.status_code == 404, r.text


def test_a_prefix_too_short_to_be_a_question_is_refused_as_such(dna_dir):
    """422 and NOT 409: a one-character prefix matching everything is not an
    ambiguity in the data, it is a malformed query. Reporting it as "ambiguous"
    would send the caller lengthening a prefix when the real answer is that
    they have not asked anything yet."""
    with _client(dna_dir) as c:
        _author_and_approve(c)
        _write(c, "c1")
        for bad in ("a", "ab", "abc"):
            r = c.get(f"/v1/instances/{bad}", params={"tenant": _WID})
            assert r.status_code == 422, (bad, r.status_code, r.text)


def test_a_prefix_outside_the_id_alphabet_is_refused(dna_dir):
    """``0``/``1``/``8``/``9`` are not in ``[a-z2-7]``. Refused as malformed
    rather than answered "no such instance" — the two are different facts."""
    with _client(dna_dir) as c:
        _author_and_approve(c)
        _write(c, "c1")
        r = c.get("/v1/instances/ab0189", params={"tenant": _WID})
        assert r.status_code == 422, r.text


# ── 4. the derived edge carries id AND name ─────────────────────────────────


def test_the_derived_edge_records_the_targets_id_beside_its_name(dna_dir):
    """The half of the Kubernetes rule that lives in the DERIVED layer.

    The author wrote a NAME — ``to_name`` preserves it, and that is what keeps
    the ``.dna/`` diff legible. WHICH instance that name hit is a fact only the
    write path knew; ``to_id`` is where it is kept.

    MUTANT: drop ``to_id`` from ``_replace_edges`` and the edge still resolves,
    still reports ``resolved: true``, and this is the only assertion that
    notices.
    """
    ref_schema = {
        "type": "object", "additionalProperties": False,
        "required": ["titulo"],
        "properties": {"titulo": {"type": "string"},
                       "contrato": {"type": "string"}},
    }
    with _client(dna_dir) as c:
        _author_and_approve(c)
        r = c.post("/v1/kinds", params={"tenant": _WID}, json={
            "kind": "Anexo", "schema": ref_schema,
            "relations": [{"name": "contrato", "to": ["Contrato"],
                           "cardinality": "one"}],
        })
        if r.status_code != 201:
            pytest.skip(f"this store cannot author a relation Kind here: {r.text}")
        assert c.post("/v1/kinds/Anexo/approve",
                      params={"tenant": _WID}).status_code == 200

        _write(c, "c1")
        target_id = _id_of(c, "c1")

        w = c.post("/v1/kinds/Anexo/instances", params={"tenant": _WID},
                   json={"metadata": {"name": "a1"},
                         "spec": {"titulo": "t", "contrato": "c1"}})
        assert w.status_code == 201, w.text

        refs = c.get("/v1/kinds/Contrato/instances/c1/refs",
                     params={"tenant": _WID, "direction": "in"})
        if refs.status_code == 501:
            pytest.skip("this store keeps no derived edge graph")
        assert refs.status_code == 200, refs.text
        edges = refs.json()["edges"]
        assert edges, refs.text
        edge = edges[0]
        assert edge["to_name"] == "c1", edge
        assert edge["to_id"] == target_id, (
            "the derived edge lost the target's identity — it kept only the "
            "name, which is exactly what a rename erases"
        )


# ── 5. the MCP door tells the same story ───────────────────────────────────
#
# These run on the MCP lane end to end — write AND read — instead of writing
# through REST and reading through MCP. That is not convenience: the REST
# helpers above write under a TENANT, which lands the instance in a tenant
# overlay, and an MCP call with no tenant cannot see it. Crossing the lanes
# would have made this suite assert tenant leakage while claiming to assert
# identity.

_MCP_KIND = "Copilot"
_MCP_API_VERSION = "github.com/ruinosus/dna/v1"


def _mcp(dna_dir):
    from fastmcp import Client
    from dna_cli import _mcp_server as M
    return Client(M.build_server(scope=_SCOPE, base_dir=str(dna_dir)))


def _call(dna_dir, tool, **args):
    async def go():
        async with _mcp(dna_dir) as client:
            res = await client.call_tool(tool, args)
            return res.data if getattr(res, "data", None) is not None \
                else res.structured_content
    return asyncio.run(go())


def _mcp_write(dna_dir, name, *, path="/agui"):
    return _call(
        dna_dir, "write_instance", kind=_MCP_KIND, name=name, scope=_SCOPE,
        spec={"mounts": [{"id": "m", "agent": "memory-agent", "path": path}],
              "serving": {"transport": "ag-ui"}},
    )


def _mcp_id(dna_dir, name):
    got = _call(dna_dir, "get_instance", kind=_MCP_KIND, name=name,
                scope=_SCOPE)
    return got["instance"]["metadata"]["id"]


def test_the_mcp_face_resolves_the_same_id(dna_dir):
    """The id lane exists on BOTH faces or it exists on neither — a capability
    reachable through one door and not the other is the "capacidade existe,
    porta não" defect this house has already paid for three times."""
    pytest.importorskip("fastmcp")
    _mcp_write(dna_dir, "c-mcp")
    full = _mcp_id(dna_dir, "c-mcp")

    got = _call(dna_dir, "resolve_instance", id=full[:6])
    assert got["id"] == full, got
    assert got["name"] == "c-mcp"
    assert got["kind"] == _MCP_KIND


def test_the_mcp_id_survives_a_rewrite_too(dna_dir):
    """The mutant, on the second face. The MCP write path is the SAME
    ``write_instance_impl`` that discards metadata, so if the adoption clause
    regressed both faces would lose identity together."""
    pytest.importorskip("fastmcp")
    _mcp_write(dna_dir, "c-mcp", path="/one")
    first = _mcp_id(dna_dir, "c-mcp")
    _mcp_write(dna_dir, "c-mcp", path="/two")
    assert _mcp_id(dna_dir, "c-mcp") == first


def test_the_mcp_face_refuses_an_ambiguous_prefix_too(dna_dir):
    """The refusal is a KERNEL rule, so it must be the same refusal on every
    face. A door that arbitrated for itself is a door that will eventually
    arbitrate differently."""
    pytest.importorskip("fastmcp")
    import yaml
    from fastmcp.exceptions import ToolError

    _mcp_write(dna_dir, "c-twin-a")
    _mcp_write(dna_dir, "c-twin-b")

    twins = ("yyyy" + "aaaaaaaa", "yyyy" + "bbbbbbbb")
    paths = sorted(pathlib.Path(dna_dir).rglob("c-twin-*.yaml"))
    assert len(paths) == 2, paths
    for path, new_id in zip(paths, twins):
        raw = yaml.safe_load(path.read_text())
        raw["metadata"]["id"] = new_id
        path.write_text(yaml.safe_dump(raw, sort_keys=False))

    with pytest.raises(ToolError) as exc:
        _call(dna_dir, "resolve_instance", id="yyyy")
    assert "yyyy" in str(exc.value)
    assert twins[0] in str(exc.value) and twins[1] in str(exc.value)


def test_get_instance_still_answers_by_NAME_only(dna_dir):
    """The two lanes stay apart.

    ``get_instance`` takes a NAME; handing it an id must MISS rather than
    helpfully resolve. A single door that accepted "a name, or maybe an id"
    would eventually answer a name query with an id match, and nothing in the
    response would say so — which is the whole failure mode this design is
    arranged to make impossible."""
    pytest.importorskip("fastmcp")
    from fastmcp.exceptions import ToolError

    _mcp_write(dna_dir, "c-mcp")
    full = _mcp_id(dna_dir, "c-mcp")

    with pytest.raises(ToolError):
        _call(dna_dir, "get_instance", kind=_MCP_KIND, name=full, scope=_SCOPE)
