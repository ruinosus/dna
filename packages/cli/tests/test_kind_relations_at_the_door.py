"""A tenant Kind may finally say what it POINTS AT — through both doors, and
still only through a human.

``KindDefinitionSpec`` has carried ``relations`` and ``plane`` since the block
was made first-class; ``TypedKindDefinition.from_raw`` parses both and the
meta-schema admits both. What was missing was the DOOR: ``author_kind_impl``
builds its spec field by field and never merged the body, and neither field was
on the list. So a Kind authored by a tenant could not declare one link — not for
lack of a contract, but for lack of a way in. Every tenant Kind was an island BY
CONSTRUCTION, which is a product that says "model your domain" and then refuses
the half of a model that is the edges.

This file pins the fix and, more importantly, pins what the fix must NOT move.

**The human gate.** Sections 3 and 4 are the reason this suite exists rather
than a pair of round-trip assertions. A relation is resolved by the write path
and drawn by the graph only for a REGISTERED Kind, and registration is what
approval turns on — so a declared relation proposes an edge and cannot create
one. Two tests measure that against a kernel booted FRESH over the same store
(the process that wrote the instance could trivially "not have it registered"
because nothing reloaded): unapproved, the port does not exist at all;
approved, the port carries exactly the relations that were declared. And the
second half, which is where a loosening would actually land: ADDING a relation
to an already-approved Kind clears the approval, so the new edge goes back in
front of a person instead of past one.

**The suggestion is a suggestion.** Section 5 pins i-117's three states
transplanted — declared → silence, exactly one candidate → the paste-ready
line, nothing or several → silence. The third state is the one that carries the
design: a note that fires on every call is a note every caller learns to skip,
and it would take the other two down with it.

**``plane`` is stored only when DECLARED.** Section 2. The default
(``composition``) is a live question with a named owner
(``spec-kind-taxonomia-o-que-eu-sou`` §12.2, the founder's), and an instance
that records the default cannot be told from one whose author meant it — which
would settle the question silently and leave it unsettleable. So the absence is
asserted on the STORED spec, not merely on the response.

Both doors, because a Kind born in one face and absent from the others is worth
nothing: the REST route (``POST /v1/kinds``, what the portal calls) and the MCP
tool (``author_kind``, what an agent calls). Valid and invalid on each — a door
that accepts the good shape and also accepts the broken one has not gained a
field, it has gained a way to store nonsense.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")
pytest.importorskip("fastmcp")

from fastapi.testclient import TestClient  # noqa: E402
from fastmcp.exceptions import ToolError  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_WID = "ws-relations00000000000001"

#: A schema with a field for every shape the relations block can take: a scalar
#: reference, an array one, and a plain data field that is not a relation at
#: all. The last one matters — a suite whose every property is a relation
#: cannot see a derivation that suggests one for everything.
_SCHEMA = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string"},
        "cliente": {"type": "string", "description": "quem contratou"},
        "anexos": {"type": "array", "items": {"type": "string"}},
    },
}

_RELATIONS = {
    "cliente": {"to": "Agent", "cardinality": "one"},
    "anexos": {"to": "Skill", "cardinality": "many"},
}


def _store_at(dst: pathlib.Path) -> pathlib.Path:
    """A writable copy of the concierge scope, with the ``_lib`` registry scope
    ``assign_namespace`` reads before it mints. Same fixture shape as
    ``test_kind_authoring_route.py``'s — the example scope ships no ``_lib``
    and a filesystem source raises for a scope directory that is not there."""
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
    monkeypatch.delenv("DNA_PERSONAL_ID", raising=False)
    return dst


@pytest.fixture
def client(dna_dir) -> TestClient:
    """``--auth none`` — the OSS self-host lane, which serves these doors and is
    where the unattributed behaviour is the correct one."""
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE))


@pytest.fixture
def mcp(dna_dir):
    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))

    def call(args: dict, *, tool: str = "author_kind") -> dict:
        from fastmcp import Client

        async def go():
            async with Client(server) as c:
                return await c.call_tool(tool, {"tenant": _WID, **args})

        return asyncio.run(go()).structured_content

    return call


def _on_fresh_kernel(dna_dir, fn):
    """Run ``fn(live)`` against a kernel booted FRESH over the same store, after
    the real 2-phase load has parsed every stored ``KindDefinition`` and applied
    the real approval gate."""
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        await live.kernel.instance_async(_SCOPE)
        return await fn(live)

    return asyncio.run(go())


def _stored_spec(dna_dir, name: str) -> dict:
    async def probe(live):
        raw = await live.kernel.get_instance(_SCOPE, "KindDefinition", name)
        return dict((raw or {}).get("spec") or {})

    return _on_fresh_kernel(dna_dir, probe)


def _registered_port(dna_dir, kind: str):
    async def probe(live):
        return live.kernel.kind_port_for(kind, scope=_SCOPE)

    return _on_fresh_kernel(dna_dir, probe)


# ── 1. the field arrives — through both doors ─────────────────────────────


def test_the_rest_door_stores_the_declared_relations(client, dna_dir):
    r = client.post(
        "/v1/kinds",
        json={"kind": "Contrato", "schema": _SCHEMA, "relations": _RELATIONS},
        params={"tenant": _WID},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["relations"] == _RELATIONS, body
    # …and on the INSTANCE, which is the only claim worth making: the response
    # could echo a field the write dropped and nothing would notice.
    spec = _stored_spec(dna_dir, body["name"])
    assert spec["relations"] == _RELATIONS, spec


def test_the_mcp_door_stores_the_declared_relations(mcp, dna_dir):
    r = mcp({"kind": "Contrato", "schema": _SCHEMA, "relations": _RELATIONS})
    assert r["relations"] == _RELATIONS, r
    assert _stored_spec(dna_dir, r["name"])["relations"] == _RELATIONS


def test_the_rest_door_still_keeps_traits_and_presentation(client, dna_dir):
    """The three tenant-facing declarations travel TOGETHER or the surface is
    still partial. ``traits`` and ``presentation`` were already accepted by this
    door; asserting them beside ``relations`` is what stops the next edit from
    trading one for another."""
    r = client.post(
        "/v1/kinds",
        json={
            "kind": "Contrato", "schema": _SCHEMA, "relations": _RELATIONS,
            "traits": ["describable"], "presentation": ["titulo", "cliente"],
            "plane": "record",
        },
        params={"tenant": _WID},
    )
    assert r.status_code == 201, r.text
    spec = _stored_spec(dna_dir, r.json()["name"])
    assert spec["traits"] == ["describable"], spec
    assert spec["presentation"], spec
    assert spec["relations"] == _RELATIONS, spec
    assert spec["plane"] == "record", spec


@pytest.mark.parametrize(
    "relations, needle",
    [
        # No cardinality — REQUIRED, and deliberately not defaulted from
        # `type: array`. A door that filled it in would be the inference the
        # relations block was written to kill, wearing the door's clothes.
        ({"cliente": {"to": "Agent"}}, "cardinality"),
        # `many` against a scalar property: the model and the data disagree
        # about multiplicity, and only this call holds both halves.
        ({"cliente": {"to": "Agent", "cardinality": "many"}}, "not an array"),
        # A relation naming a property the schema does not declare — the value
        # has nowhere to live.
        ({"fantasma": {"to": "Agent", "cardinality": "one"}}, "no `fantasma`"),
        # `*` mixed with names: "the target is chosen per value" is not a
        # longer list of alternatives.
        ({"cliente": {"to": ["*", "Agent"], "cardinality": "one"}}, "*"),
    ],
)
def test_the_rest_door_refuses_a_broken_relation_by_name(
    client, dna_dir, relations, needle,
):
    r = client.post(
        "/v1/kinds",
        json={"kind": "Contrato", "schema": _SCHEMA, "relations": relations},
        params={"tenant": _WID},
    )
    assert r.status_code == 400, r.text
    assert needle in r.json()["detail"], r.text
    # A refused declaration writes NOTHING. Half a Kind is worse than none: it
    # would be listed, reviewable and wrong.
    listed = client.get("/v1/kinds", params={"tenant": _WID}).json()["kinds"]
    assert listed == [], listed


@pytest.mark.parametrize(
    "relations, needle",
    [
        ({"cliente": {"to": "Agent"}}, "cardinality"),
        ({"cliente": {"to": "Agent", "cardinality": "many"}}, "not an array"),
    ],
)
def test_the_mcp_door_refuses_a_broken_relation_legibly(mcp, relations, needle):
    """Over a conversational face an illegible refusal is a refusal the agent
    retries forever, so the reason has to reach the client intact — the type
    name plus the sentence, which is what ``_refuse`` is for."""
    with pytest.raises(ToolError) as exc:
        mcp({"kind": "Contrato", "schema": _SCHEMA, "relations": relations})
    assert "ValueError" in str(exc.value)
    assert needle in str(exc.value)


# ── 2. `plane` — declared, or genuinely absent ────────────────────────────


def test_an_undeclared_plane_is_not_written_down(client, dna_dir):
    """§12.2 is the founder's to answer, and this is what keeps it answerable.

    ``KindDefinitionSpec`` defaults ``plane`` to ``composition``; if this door
    stamped that default onto every instance, "how many tenant Kinds are on the
    composition plane BY CHOICE?" would have no answer, because a Kind whose
    author meant it and a Kind that was never asked would read identically.
    Asserted on the STORED spec — the response echoing ``None`` proves nothing
    about what the write persisted."""
    r = client.post(
        "/v1/kinds", json={"kind": "Contrato", "schema": _SCHEMA},
        params={"tenant": _WID},
    )
    assert r.status_code == 201, r.text
    assert r.json()["plane"] is None, r.text
    spec = _stored_spec(dna_dir, r.json()["name"])
    assert "plane" not in spec, spec


@pytest.mark.parametrize("plane", ["composition", "record"])
def test_a_declared_plane_is_written_down(client, dna_dir, plane):
    r = client.post(
        "/v1/kinds", json={"kind": "Contrato", "schema": _SCHEMA, "plane": plane},
        params={"tenant": _WID},
    )
    assert r.status_code == 201, r.text
    assert _stored_spec(dna_dir, r.json()["name"])["plane"] == plane


def test_a_plane_outside_the_vocabulary_is_refused_at_the_door(client):
    """The registry lint refuses it at REGISTRATION — which is the one moment
    the author is not there. Refusing here costs nothing and reaches a person."""
    r = client.post(
        "/v1/kinds", json={"kind": "Contrato", "schema": _SCHEMA, "plane": "graph"},
        params={"tenant": _WID},
    )
    assert r.status_code == 400, r.text
    assert "composition" in r.json()["detail"] and "record" in r.json()["detail"]


def test_the_mcp_door_refuses_a_plane_outside_the_vocabulary(mcp):
    with pytest.raises(ToolError) as exc:
        mcp({"kind": "Contrato", "schema": _SCHEMA, "plane": "graph"})
    assert "composition" in str(exc.value)


# ── 3. ⭐ the human gate — a declared relation is a PROPOSED edge ──────────


def test_a_declared_relation_has_no_effect_until_a_human_approves(client, dna_dir):
    """The load-bearing property of this whole slice.

    Measured against a kernel booted FRESH over the same store, so the answer
    is the real 2-phase load's and not this process's: the Kind is authored,
    listed, reviewable — and has NO PORT. No port is no registration, and no
    registration is no resolution: nothing reads these relations, nothing draws
    them, nothing validates against them. The declaration is a proposal."""
    r = client.post(
        "/v1/kinds",
        json={"kind": "Contrato", "schema": _SCHEMA, "relations": _RELATIONS},
        params={"tenant": _WID},
    )
    assert r.status_code == 201, r.text
    assert r.json()["approved"] is False
    assert _stored_spec(dna_dir, r.json()["name"])["relations"] == _RELATIONS
    assert _registered_port(dna_dir, "Contrato") is None, (
        "an UNAPPROVED Kind is registered, so its relations are in effect — "
        "the gate this feature had to keep is gone"
    )


def test_the_relations_take_effect_only_once_approved(client, dna_dir):
    """The other half, and it has to be here: a test that only shows the Kind
    inert would also pass if ``relations`` were dropped on the floor entirely.
    After the HUMAN act, the registered port carries exactly what was declared —
    read through ``relations_of``, the reading every consumer uses, not through
    a second parse written here."""
    from dna.kernel.kinds.relations import relations_of

    client.post(
        "/v1/kinds",
        json={"kind": "Contrato", "schema": _SCHEMA, "relations": _RELATIONS},
        params={"tenant": _WID},
    )
    approved = client.post("/v1/kinds/Contrato/approve", params={"tenant": _WID})
    assert approved.status_code == 200, approved.text

    port = _registered_port(dna_dir, "Contrato")
    assert port is not None, "approval did not register the Kind"
    declared = relations_of(port)
    assert set(declared) == set(_RELATIONS), declared
    assert declared["cliente"].to == ("Agent",)
    assert declared["anexos"].cardinality == "many"


def test_adding_a_relation_to_an_approved_kind_withdraws_the_approval(
    client, dna_dir,
):
    """⭐ Where a loosening would actually land.

    The gate is not "an agent cannot approve" alone — it is that no shape takes
    effect unreviewed. Authoring is also the EDIT path, so a Kind approved
    WITHOUT relations that could be edited to HAVE them, with the approval
    surviving, would let an agent add an edge that a human conferred effect on
    without ever seeing it. The edit clears the marker; the new shape waits."""
    client.post(
        "/v1/kinds", json={"kind": "Contrato", "schema": _SCHEMA},
        params={"tenant": _WID},
    )
    client.post("/v1/kinds/Contrato/approve", params={"tenant": _WID})
    name = client.get("/v1/kinds", params={"tenant": _WID}).json()["kinds"][0]["name"]
    assert _stored_spec(dna_dir, name).get("approved_by"), "precondition: approved"

    edited = client.post(
        "/v1/kinds",
        json={"kind": "Contrato", "schema": _SCHEMA, "relations": _RELATIONS},
        params={"tenant": _WID},
    )
    assert edited.status_code == 201, edited.text
    assert edited.json()["approved"] is False
    spec = _stored_spec(dna_dir, name)
    assert spec["relations"] == _RELATIONS, spec
    assert not spec.get("approved_by"), (
        "the edit that added the relation kept the approval — an agent can now "
        "confer an edge a human never saw"
    )


def test_the_mcp_face_offers_no_way_to_approve_a_relation(mcp):
    """Stated where it would be missed: ``author_kind`` grew two parameters and
    neither is an approval in disguise.

    Two assertions, because they fail for different reasons. The tool's input
    schema has no ``approved_by`` at all — the face refuses the forged argument
    before the core sees it — and the Kind that DOES declare relations still
    answers ``approved: false``, so the new field bought no shortcut through the
    gate."""
    with pytest.raises(ToolError) as exc:
        mcp({"kind": "Contrato", "schema": _SCHEMA, "relations": _RELATIONS,
             "approved_by": "me@example.com"})
    assert "approved_by" in str(exc.value)

    r = mcp({"kind": "Contrato", "schema": _SCHEMA, "relations": _RELATIONS})
    assert r["approved"] is False, r


# ── 4. the reviewer is SHOWN what they would confer ───────────────────────


def test_the_detail_route_carries_the_relations_and_the_plane(client):
    """A gate that shows the reviewer less than approval confers is a gate that
    has stopped gating. The detail route is where the portal reads what is
    pending, so the two new declarations belong beside ``schema``/``traits``/
    ``presentation`` — the other three things registration turns on."""
    client.post(
        "/v1/kinds",
        json={"kind": "Contrato", "schema": _SCHEMA, "relations": _RELATIONS,
              "plane": "record"},
        params={"tenant": _WID},
    )
    body = client.get("/v1/kinds/Contrato", params={"tenant": _WID}).json()
    assert body["relations"] == _RELATIONS, body
    assert body["plane"] == "record", body
    assert body["approved"] is False, body


def test_the_detail_route_says_null_for_a_kind_that_declares_neither(client):
    """``null`` and not ``{}``/``"composition"``: "declares nothing" and
    "declares the default" are different facts about what is being approved."""
    client.post(
        "/v1/kinds", json={"kind": "Contrato", "schema": _SCHEMA},
        params={"tenant": _WID},
    )
    body = client.get("/v1/kinds/Contrato", params={"tenant": _WID}).json()
    assert body["relations"] is None, body
    assert body["plane"] is None, body


# ── 5. the SUGGESTION — i-117's three states, transplanted ────────────────


def test_a_field_naming_a_live_kind_is_suggested_not_demanded(client):
    """State two: the prose names exactly one Kind that exists, and the answer
    carries the line to paste. Crucially the write SUCCEEDED — this is a
    suggestion, not a gate. Demanding a relation would be the fix that destroys
    itself: a field everyone must fill is a field everyone fills with anything.
    """
    r = client.post(
        "/v1/kinds",
        json={"kind": "Contrato", "schema": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string"},
                "agent": {"type": "string"},
            },
        }},
        params={"tenant": _WID},
    )
    assert r.status_code == 201, r.text
    assert r.json()["suggested_relations"] == [
        {"field": "agent", "to": "Agent", "cardinality": "one"},
    ], r.text
    assert "relations:" in r.json()["suggestion"], r.text


def test_a_kind_that_declared_its_links_is_asked_nothing(client):
    """State one. There is nothing to ask about a field that answered, and a
    question asked anyway is how the other two states get ignored."""
    r = client.post(
        "/v1/kinds",
        json={"kind": "Contrato", "schema": _SCHEMA, "relations": _RELATIONS},
        params={"tenant": _WID},
    )
    assert r.json()["suggested_relations"] is None, r.text
    assert r.json()["suggestion"] is None, r.text


def test_a_kind_whose_prose_names_nothing_is_asked_nothing(client):
    """State three, and the one that carries the design. NOT a warning: a
    fourth line that fires on every call is how a reader learns to skip the
    first three."""
    r = client.post(
        "/v1/kinds",
        json={"kind": "Contrato", "schema": {
            "type": "object",
            "properties": {"titulo": {"type": "string"},
                           "valor": {"type": "integer"}},
        }},
        params={"tenant": _WID},
    )
    assert r.status_code == 201, r.text
    assert r.json()["suggested_relations"] is None, r.text


def test_the_suggestion_is_never_stored(client, dna_dir):
    """The whole difference between this derivation and the name-shape guess
    ``spec.relations`` replaced. That one ran on the WRITE path and produced
    edges nobody declared. This one returns a sentence and touches nothing —
    so the instance of a Kind that was suggested a relation and did not take it
    is byte-identical to one that was suggested none."""
    r = client.post(
        "/v1/kinds",
        json={"kind": "Contrato", "schema": {
            "type": "object", "properties": {"agent": {"type": "string"}},
        }},
        params={"tenant": _WID},
    )
    assert r.json()["suggested_relations"], "precondition: something was suggested"
    spec = _stored_spec(dna_dir, r.json()["name"])
    assert "relations" not in spec, spec
    assert "suggested_relations" not in spec, spec


def test_the_mcp_door_suggests_too(mcp):
    """Both doors, or the derivation is a fence one caller walks around. The
    agent is the caller that most needs it: it is the one authoring Kinds
    without a screen to show it the neighbours."""
    r = mcp({"kind": "Contrato", "schema": {
        "type": "object", "properties": {"agent": {"type": "string"}},
    }})
    assert r["suggested_relations"] == [
        {"field": "agent", "to": "Agent", "cardinality": "one"},
    ], r


# ── 6. the derivation itself, as a pure function ──────────────────────────
#
# Driven directly because the doors above can only reach the states their
# fixture scope's registry happens to allow, and the AMBIGUOUS state — the
# prose naming two live Kinds — is the one that decides whether this is a
# suggestion or a menu.


@pytest.mark.parametrize(
    "props, expected",
    [
        # exactly one → suggested, cardinality read off the JSON Schema (which
        # this may do, and `normalize_relations` may not: one is confirmed by
        # the author, the other is enforced by the kernel).
        ({"cliente": {"type": "string"}},
         [{"field": "cliente", "to": "Cliente", "cardinality": "one"}]),
        ({"clientes": {"type": "array"}},
         [{"field": "clientes", "to": "Cliente", "cardinality": "many"}]),
        # the words INSIDE a compound name, so `_id` costs nothing and needs no
        # denylist of suffixes.
        ({"cliente_id": {"type": "string"}},
         [{"field": "cliente_id", "to": "Cliente", "cardinality": "one"}]),
        # the description is prose the author already wrote.
        ({"dono": {"type": "string", "description": "o Cliente responsável"}},
         [{"field": "dono", "to": "Cliente", "cardinality": "one"}]),
        # ⭐ TWO candidates → SILENCE. A menu is a question the author answers
        # by picking the first row.
        ({"parte": {"type": "string", "description": "Cliente ou Fornecedor"}}, []),
        # nothing named → silence.
        ({"valor": {"type": "integer"}}, []),
        # a word that merely CONTAINS a Kind name is not a mention.
        ({"clientela": {"type": "string"}}, []),
    ],
)
def test_the_derivation_speaks_only_when_there_is_one_candidate(props, expected):
    from dna.application.kind_authoring import derive_relation_candidates

    got = derive_relation_candidates(
        {"type": "object", "properties": props},
        ["Cliente", "Fornecedor", "Contrato"],
    )
    assert got == expected, got


def test_the_derivation_skips_what_was_already_declared():
    from dna.application.kind_authoring import derive_relation_candidates

    schema = {"type": "object", "properties": {
        "cliente": {"type": "string"}, "fornecedor": {"type": "string"},
    }}
    got = derive_relation_candidates(
        schema, ["Cliente", "Fornecedor"], declared={"cliente"},
    )
    assert got == [{"field": "fornecedor", "to": "Fornecedor",
                    "cardinality": "one"}], got
