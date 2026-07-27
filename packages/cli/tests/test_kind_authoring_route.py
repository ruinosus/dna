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
import re
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402
from dna_cli import _rest_models as RM  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_WID = "ws-authoring00000000000001"

#: A SECOND workspace sharing the SAME scope. Not a fixture artefact: with
#: multi-workspace off (``vendor_workspace`` unset) ``LiveDna.default_scope``
#: answers ``base_scope`` for EVERY workspace, so one scope holding two
#: workspaces' authored Kinds is the default configuration and the one an OSS
#: self-host runs under.
_OTHER_WID = "ws-authoring00000000000002"

_SCHEMA = {
    "type": "object",
    "properties": {"titulo": {"type": "string"}},
    "required": ["titulo"],
}


def _store_at(dst: pathlib.Path, *, with_lib: bool = True) -> pathlib.Path:
    """A writable copy of the concierge scope rooted at ``dst``."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_BASE, dst)
    if with_lib:
        # The ``_lib`` registry — where a KindNamespace claim lives. Stood up the
        # same way ``sdk-py/tests/test_namespace_assignment.py``'s fixture stands
        # it up, because ``assign_namespace`` READS it before minting and a
        # filesystem source raises ``FileNotFoundError`` for a scope directory
        # that is not there. Every real deployment has it (a Postgres source has
        # no such notion, and workspace provisioning writes the claim at birth);
        # the example scope simply ships none.
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
    """A writable copy of the concierge scope, wired via DNA_BASE_DIR (same
    fixture shape as test_definitions_rest.py's ``dna_dir``)."""
    dst = _store_at(tmp_path / ".dna")
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


@pytest.fixture
def dna_dir_without_lib(tmp_path, monkeypatch):
    """The store as a FIRST author actually meets it — with no ``_lib``.

    ``dna_dir`` manufactures the registry scope so the happy path can run, and
    that manufacture is precisely what hides finding 2: on a filesystem source a
    missing scope directory raises ``FileNotFoundError``, which the route mapped
    to nothing and therefore surfaced as a 500. A fixture that stands the scope
    up cannot see it, so this one refuses to."""
    dst = _store_at(tmp_path / ".dna", with_lib=False)
    assert not (dst / "_lib").exists(), (
        "the shipped example scope is expected to ship NO _lib — if it starts "
        "shipping one, this test stops testing the precondition it names"
    )
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _client(dna_dir, *, raise_server_exceptions: bool = True, **app) -> TestClient:
    return TestClient(
        R.build_app(base_dir=str(dna_dir), scope=_SCOPE, **app),
        raise_server_exceptions=raise_server_exceptions,
    )


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
        # …and 403 for the RIGHT reason. A bare status assertion is satisfied by
        # any 403 the stack happens to produce (an auth denial, a plan gate), so
        # it would keep passing after the mechanism this docstring names had
        # stopped being the one doing the refusing.
        assert "non-overlayable" in r.text.lower(), r.text


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


# ── 4. the Kind name is the one body field that reaches a PATH ────────────
#
# The document name becomes a DIRECTORY on a filesystem-backed source
# (``<scope>/kinds/<name>/KIND.yaml``), and the caller supplies half of that
# name. An unvalidated ``kind`` is therefore a create-directories-anywhere +
# write-a-file primitive outside the store root, and a name aimed at another
# scope's existing ``kinds/<x>/KIND.yaml`` overwrites an APPROVED KindDefinition
# with an unapproved one — silently deregistering the victim's Kind on the next
# load.

#: The traversal, and its MEASURED landing point on the vulnerable code.
#:
#: Geometry matters here and guessing it produces a test that proves nothing.
#: The stored name is ``<namespace>--<kind>``, so the FIRST path segment is the
#: literal directory ``<namespace>--..`` — it absorbs one ``..``. Measured
#: against a store at ``<root>/.dna``: three segments write inside the store,
#: four land at ``<root>/.dna/ESCAPED``, five at ``<root>/ESCAPED``, and six —
#: the reported string — at ``<root>/../ESCAPED``, two levels above the ``.dna``
#: root. An earlier draft of this test used the three-segment form and passed
#: against the vulnerable code; that is why the six-segment form is the one the
#: filesystem assertion fires.
_ESCAPE = "../../../../../../ESCAPED"

#: How deep under ``tmp_path`` the escape test roots its store. The traversal
#: climbs two levels above the ``.dna`` root, so the store needs at least that
#: much headroom for the escape to land INSIDE ``tmp_path`` — which is what
#: makes the assertion hermetic (a shared ancestor like pytest's session dir
#: would couple this test to whatever else escaped during the run).
_NEST = ("deep", "nested", "root")


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(_ESCAPE, id="traversal"),
        pytest.param("a/b", id="separator"),
        pytest.param("C" * 65, id="too-long"),
        pytest.param("1Contrato", id="leading-digit"),
        pytest.param("contrato", id="lowercase-initial"),
        pytest.param("Contrato--Extra", id="ambiguous-name-separator"),
        pytest.param("", id="empty"),
        pytest.param("   ", id="whitespace"),
    ],
)
def test_a_kind_name_that_is_not_an_identifier_is_refused(dna_dir, bad):
    """``target_kind`` is documented as a CamelCase identifier — so validate it
    as one. An allow-list, not a deny-list of the characters we thought of.

    ``Contrato--Extra`` is in the list for a second reason: the document name
    joins namespace and Kind with ``--``, and only the namespace half is
    structurally free of it. An ambiguous name is a trap laid for the approval
    act, which addresses these documents by name.

    ``contrato`` is in it for a third: the guard's message says CamelCase and
    the guard must mean what it says. MEASURED — ``Contrato`` and ``contrato``
    generate the IDENTICAL alias, and on a case-insensitive filesystem (the
    macOS/Windows default) the second write lands in the same
    ``kinds/<name>/`` directory as the first and silently replaces it, with a
    201 in reply."""
    with _client(dna_dir) as c:
        r = c.post("/v1/kinds", params={"tenant": _WID},
                   json={"kind": bad, "schema": _SCHEMA})
        assert r.status_code == 400, r.text


def test_a_legitimate_camelcase_kind_still_authors(dna_dir):
    """The guard above must refuse the escape without refusing the product."""
    with _client(dna_dir) as c:
        r = c.post("/v1/kinds", params={"tenant": _WID},
                   json={"kind": "Contrato", "schema": _SCHEMA})
        assert r.status_code == 201, r.text
        assert r.json()["kind"] == "Contrato"


def test_a_traversing_kind_name_writes_no_file_outside_the_store(
    tmp_path, monkeypatch,
):
    """400 alone does not prove nothing was written — assert the FILESYSTEM.

    A route that validated after the write, or that wrote and then failed, would
    satisfy a status-only assertion while the directory it created is already
    there. Uses its own DEEP store (see ``_NEST``) so the measured landing point
    is inside this test's ``tmp_path`` and the assertion answers for this test
    alone."""
    dna_dir = _store_at(tmp_path.joinpath(*_NEST) / ".dna")
    monkeypatch.setenv("DNA_BASE_DIR", str(dna_dir))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)

    before = set(tmp_path.rglob("*"))
    with _client(dna_dir) as c:
        r = c.post("/v1/kinds", params={"tenant": _WID},
                   json={"kind": _ESCAPE, "schema": _SCHEMA})
        assert r.status_code == 400, r.text

    # Sweep for the marker across the store root and EVERY ancestor up to
    # tmp_path — no single directory is named, so the assertion survives a
    # change in the store's internal layout.
    probes, probe = [dna_dir], dna_dir
    while probe != tmp_path:
        probe = probe.parent
        probes.append(probe)
    landed = [str(p / "ESCAPED") for p in probes if (p / "ESCAPED").exists()]
    assert not landed, f"the traversal created directories outside the store: {landed}"

    # And the layout-independent half: nothing new appeared anywhere in the
    # test's tree outside the store root at all.
    strayed = sorted(
        str(p) for p in (set(tmp_path.rglob("*")) - before)
        if dna_dir not in p.parents and p != dna_dir
    )
    assert not strayed, f"paths created outside the store root: {strayed}"


# ── 5. WHO an unauthenticated door records as the proposer ────────────────
#
# This suite runs under ``--auth none``, so every author call above already
# executes the "no verified identity" branch of ``_actor_from_state`` and
# persists whatever it returns into ``proposed_by``. Until now nothing asserted
# the value. A brand-new string that lands in a persisted audit field is a
# contract with every future reader of the store, and it is exactly the kind of
# value a rename would change silently — so it is pinned as a LITERAL here,
# not merely as "whatever the constant happens to say".


def test_a_local_unauthenticated_author_is_recorded_as_rest_local(
    dna_dir, monkeypatch,
):
    monkeypatch.delenv("DNA_PERSONAL_ID", raising=False)
    with _client(dna_dir) as c:
        r = c.post("/v1/kinds", params={"tenant": _WID},
                   json={"kind": "Contrato", "schema": _SCHEMA})
        assert r.status_code == 201, r.text
        name = r.json()["name"]

    assert _stored_spec(dna_dir, name)["proposed_by"] == "rest:local"
    # The prefix names the CHANNEL, and it must be this face's own: reusing
    # ``mcp:local`` here would re-make, one layer over, the very conflation the
    # MCP constants exist to end.
    assert R._UNIDENTIFIED_LOCAL_ACTOR == "rest:local"


def test_a_declared_personal_id_outranks_the_local_sentinel(dna_dir, monkeypatch):
    """The sentinel is the FALLBACK, not the policy. An operator who declared
    ``DNA_PERSONAL_ID`` has named the offline caller, and a proposal recorded
    as ``rest:local`` when a real name was available is a worse audit."""
    monkeypatch.setenv("DNA_PERSONAL_ID", "barna@example.com")
    with _client(dna_dir) as c:
        r = c.post("/v1/kinds", params={"tenant": _WID},
                   json={"kind": "Contrato", "schema": _SCHEMA})
        assert r.status_code == 201, r.text
        name = r.json()["name"]

    assert _stored_spec(dna_dir, name)["proposed_by"] == "barna@example.com"


def test_a_shared_secret_deployment_does_not_call_its_caller_local(
    dna_dir, monkeypatch,
):
    """``--auth token`` is a REMOTE deployment behind a shared secret, and its
    caller is neither local nor a person.

    The bearer IS verified — against ``DNA_API_TOKEN`` — it simply carries no
    identity claim, which is precisely what ``rest:unidentified`` names. Before
    this, the branch fell through to ``rest:local`` (a mislabel inherited from
    the MCP precedent, where ``--auth token`` and ``--auth none`` were lumped
    together as "no token at all"), so every Kind proposed through a
    shared-secret deployment was audited as if somebody had typed it on the
    operator's laptop."""
    monkeypatch.delenv("DNA_PERSONAL_ID", raising=False)
    with _client(dna_dir, auth="token", token="s3cret") as c:
        r = c.post("/v1/kinds", params={"tenant": _WID},
                   headers={"Authorization": "Bearer s3cret"},
                   json={"kind": "Contrato", "schema": _SCHEMA})
        assert r.status_code == 201, r.text
        name = r.json()["name"]

    assert _stored_spec(dna_dir, name)["proposed_by"] == "rest:unidentified"


def test_the_local_sentinel_is_reserved_for_the_lane_that_verifies_nothing():
    """The branch keys on the FACT, not on one lane's configuration name.

    ``--auth none`` is the only lane that requires no credential, so it is the
    only one whose nameless caller is local. Every other lane verified something
    before the route ran, and a caller that got past verification and still
    names nobody is verified-and-anonymous. The branch used to select the LOCAL
    sentinel for everything that was not the literal string ``"token"`` — so
    ``--auth config`` reaching here with no claims recorded ``rest:local``, the
    same mislabel the sibling branch exists to end, one lane over.

    Asserted on the helper rather than through HTTP because the config lane's
    middleware stashes claims for every request it lets through: the branch is
    unreachable over the wire today, and an unreachable branch nothing can
    assert on is exactly how the wrong sentinel survives the next rename."""
    assert R._unidentified_actor("none") == R._UNIDENTIFIED_LOCAL_ACTOR
    assert R._unidentified_actor("token") == R._UNIDENTIFIED_TOKEN_ACTOR
    assert R._unidentified_actor("config") == R._UNIDENTIFIED_TOKEN_ACTOR, (
        "a VERIFIED lane's nameless caller is not a laptop"
    )


# ── 6. a first author on a store with no registry scope ───────────────────


def test_authoring_without_a_registry_scope_refuses_actionably(dna_dir_without_lib):
    """Not a 500. Authoring READS the namespace registry before it mints, and a
    filesystem source raises ``FileNotFoundError`` for a scope directory that is
    not there — which is the state of every store before anything provisioned
    one. The operator needs to be told WHAT is missing.

    (The deeper fix — reading a missing registry scope as "no claims yet"
    instead of raising — lives in the namespace-assignment module and is owned
    elsewhere. This asserts only the face's half: an actionable refusal.)"""
    with _client(dna_dir_without_lib, raise_server_exceptions=False) as c:
        r = c.post("/v1/kinds", params={"tenant": _WID},
                   json={"kind": "Contrato", "schema": _SCHEMA})
        assert r.status_code == 503, r.text
        detail = r.json()["detail"]
        assert "_lib" in detail, detail
        assert re.search(r"provision|not (been )?(set up|created)", detail, re.I), detail


# ── 7. reading ONE authored Kind, in full ─────────────────────────────────
#
# ``GET /v1/kinds`` deliberately projects ten SUMMARY fields and not
# ``spec.schema`` — so a reviewer deciding whether to confer effect cannot see
# what they would be approving. ``GET /v1/kinds/{kind}`` is that gap closed:
# the same ten fields plus the schema and the traits.
#
# It therefore hands over strictly MORE than the listing, which is what makes
# its three inherited decisions load-bearing rather than ceremonial — ownership
# resolved through the same ``owner_of`` the write gate decides with, a
# stranger's Kind answered exactly as a nonexistent one, and the shared Kind-name
# validator on the path segment.
#
# MEASURED, and recorded so nobody writes the test that would pass for the wrong
# reason: a URL-encoded traversal (``/v1/kinds/%2E%2E%2FESCAPED``) never reaches
# the handler at all — the ASGI server decodes the path BEFORE routing, so the
# ``/`` reappears, ``{kind}`` (``[^/]+``) does not match, and the answer is
# Starlette's own routing 404. A "traversal is refused" test written against
# this route would assert nothing about the guard. What the guard actually
# defends here is every malformed name that IS a single path segment, and the
# assertion below is that its refusal is byte-identical to the approval door's —
# i.e. the same validator, not a second copy of it.


#: The neighbour's schema, carrying a token that appears NOWHERE else in the
#: tree. A leak is then greppable in the raw response body, which is stronger
#: than comparing parsed fields: a route that leaked the schema under a
#: different key, or inside an error message, would still be caught.
_SECRET = "clausula_secreta"
_OTHER_SCHEMA = {
    "type": "object",
    "properties": {_SECRET: {"type": "string"}},
    "required": [_SECRET],
}


def _author(c, *, kind: str = "Contrato", tenant: str = _WID, **body):
    return c.post("/v1/kinds", params={"tenant": tenant},
                  json={"kind": kind, "schema": _SCHEMA, **body})


def _detail(c, kind: str = "Contrato", **params):
    return c.get(f"/v1/kinds/{kind}", params=params)


def test_the_detail_route_carries_the_schema_the_listing_withholds(dna_dir):
    """The whole reason the route exists — and the vocabulary is the LISTING's.

    Two halves, and both matter. First: the ten summary fields must come back
    IDENTICAL to the row ``GET /v1/kinds`` already publishes, so the audit
    screen is not reading two different descriptions of one document. Second:
    the schema and the traits — the fields the list does not carry — must be
    there, because a reviewer who cannot see what they would be approving is
    not reviewing anything.

    The listing's silence is asserted too. If a later change adds ``schema`` to
    the summary, this route stops being the answer to anything and the gap
    assertion is what says so."""
    with _client(dna_dir) as c:
        assert _author(c, traits=["auditable"]).status_code == 201

        listed = c.get("/v1/kinds", params={"tenant": _WID})
        assert listed.status_code == 200, listed.text
        rows = [k for k in listed.json()["kinds"] if k["kind"] == "Contrato"]
        assert rows, listed.json()
        row = rows[0]

        r = _detail(c, tenant=_WID)
        assert r.status_code == 200, r.text
        body = r.json()

    # The gap this route closes — stated as a fact about the LIST.
    assert "schema" not in row, (
        "the listing already carries the schema; this route has no gap to close"
    )

    # …and closed: the thing a reviewer is actually deciding about.
    assert body["schema"] == _SCHEMA, body
    assert body["traits"] == ["auditable"], body

    # One vocabulary, not two: every summary field, same value, same name.
    summary = set(RM.AuthoredKindSummary.model_fields)
    assert {k: body[k] for k in summary} == {k: row[k] for k in summary}, body
    # And the detail is exactly the summary plus those two — a third field here
    # is a third vocabulary for the same document.
    assert set(body) == summary | {"schema", "traits"}, sorted(body)

    # The audit half is real, not defaulted: an authored document names its
    # proposer and its birth, and a route that returned the model's defaults
    # for everything would satisfy the equality above on two empty dicts.
    assert body["kind"] == "Contrato", body
    assert body["approved"] is False, body
    assert body["proposed_by"] == "rest:local", body
    assert body["created_at"], body


def test_a_neighbours_kind_is_a_404_that_hands_over_no_schema(dna_dir):
    """Strictly more data than the listing ⇒ at least as tight a filter.

    B authors ``Contrato``; A authors NOTHING, so a refusal here cannot be an
    accident of finding the caller's own document. Without the ownership filter
    the scope holds exactly one ``…--Contrato``, the Kind half is all the URL
    carries, and A gets back B's namespace AND B's JSON Schema — the design of
    the workspace's data model, which is a great deal more than the identity
    strings the listing leaked before it was filtered."""
    with _client(dna_dir) as c:
        b = _author(c, tenant=_OTHER_WID, schema=_OTHER_SCHEMA)
        assert b.status_code == 201, b.text

        r = _detail(c, tenant=_WID)
        assert r.status_code == 404, (
            f"workspace {_WID} read a Kind authored by {_OTHER_WID}: "
            f"{r.status_code} {r.text}"
        )
        # Not Starlette's routing 404 — the handler's own, naming what it could
        # not find. A bare status assertion here would have passed before the
        # route existed at all.
        assert "Contrato" in r.json()["detail"], r.text
        # The payload, greppable in the RAW body: a leak through any key, or
        # inside the refusal's own message, is still a leak.
        assert _SECRET not in r.text, r.text
        assert b.json()["namespace"] not in r.text, r.text


def test_a_stranger_gets_the_same_answer_as_a_nonexistent_kind(dna_dir):
    """The approval door's decision, inherited exactly: 404, never 403.

    "It exists but is not yours" IS the probe — a workspace could enumerate
    what its neighbours are authoring one Kind name at a time without ever
    reading a document. So the two answers must be indistinguishable, and this
    compares the whole refusal rather than the status alone: a 404 whose detail
    said "not yours" would satisfy a status-only test and give the game away in
    the body."""
    with _client(dna_dir) as c:
        assert _author(c, tenant=_OTHER_WID, schema=_OTHER_SCHEMA).status_code == 201

        stranger = _detail(c, "Contrato", tenant=_WID)
        absent = _detail(c, "NuncaExistiu", tenant=_WID)

    assert (stranger.status_code, absent.status_code) == (404, 404), (
        stranger.text, absent.text,
    )
    # FIRST, the anti-tautology. Without these two lines this test PASSED
    # before the route existed at all: both calls got Starlette's routing 404,
    # ``{"detail": "Not Found"}``, and two identical strings are trivially
    # indistinguishable. Requiring each refusal to name the Kind it could not
    # find is what makes the comparison below a statement about the handler.
    assert "Contrato" in stranger.json()["detail"], stranger.text
    assert "NuncaExistiu" in absent.json()["detail"], absent.text
    # Modulo the Kind name the caller itself supplied, the two refusals must be
    # the same string.
    assert (stranger.json()["detail"].replace("Contrato", "<kind>")
            == absent.json()["detail"].replace("NuncaExistiu", "<kind>")), (
        f"the refusal distinguishes a neighbour's Kind from a nonexistent one, "
        f"which is the probe:\n  stranger: {stranger.json()['detail']}\n"
        f"  absent:   {absent.json()['detail']}"
    )


def test_an_unattributed_request_is_not_filtered(dna_dir):
    """No resolved tenant ⇒ no filter — the ``--auth none`` self-host and the
    explicit operator ``scope=`` call, the same hinge
    ``NamespaceOwnershipGate`` uses for an unattributed write.

    A filter that unconditionally demanded ownership would answer every
    self-hoster 404 for a Kind sitting right there in their own store."""
    with _client(dna_dir) as c:
        authored = _author(c, tenant=_WID)
        assert authored.status_code == 201, authored.text

        r = _detail(c, scope=_SCOPE)
        assert r.status_code == 200, r.text
        assert r.json()["name"] == authored.json()["name"], r.json()
        assert r.json()["schema"] == _SCHEMA, r.json()


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param("contrato", id="lowercase-initial"),
        pytest.param("1Contrato", id="leading-digit"),
        pytest.param("C" * 65, id="too-long"),
        pytest.param("Contrato--Extra", id="ambiguous-name-separator"),
        pytest.param("a.b", id="dotted"),
    ],
)
def test_a_kind_name_that_is_not_an_identifier_is_refused_on_the_read_door(
    dna_dir, bad,
):
    """``kind`` is a path-shaped input on this door too — and the guard has to
    be the SHARED one, not a third copy that drifts from the other two.

    Asserted by byte-equality with the approval door's refusal for the same
    name: two independent implementations agreeing character for character is
    not something a copy survives. (Only names that are a single path segment
    appear here — see the section comment for why the encoded traversal never
    reaches either handler.)"""
    with _client(dna_dir) as c:
        r = _detail(c, bad, tenant=_WID)
        assert r.status_code == 400, r.text
        assert "CamelCase" in r.json()["detail"], r.text

        twin = c.post(f"/v1/kinds/{bad}/approve", params={"tenant": _WID})
        assert twin.status_code == 400, twin.text
        assert r.json()["detail"] == twin.json()["detail"], (
            f"the read door refuses {bad!r} differently from the approval "
            f"door — that is a second copy of the validator:\n"
            f"  read:    {r.json()['detail']}\n  approve: {twin.json()['detail']}"
        )


def test_an_unreadable_registry_refuses_the_read_rather_than_answering(
    dna_dir, monkeypatch,
):
    """Fail CLOSED — 503, never the unfiltered answer.

    Ownership is decided from the ``KindNamespace`` claim registry, and without
    it a stranger cannot be told from an owner. For a route that hands over the
    schema, "degrade to answering anyway" is the one outcome that is not
    acceptable. Injected at the seam (``kind_namespaces`` raising something
    that is NOT a missing file) because on a filesystem store the honest
    ``FileNotFoundError`` hides the gap that only Postgres shows."""
    from dna.kernel import Kernel

    async def boom(self, *a, **kw):
        raise RuntimeError("connection reset by peer")

    with _client(dna_dir) as c:
        assert _author(c, tenant=_WID).status_code == 201

    monkeypatch.setattr(Kernel, "kind_namespaces", boom, raising=True)

    with _client(dna_dir, raise_server_exceptions=False) as c:
        r = _detail(c, tenant=_WID)
        assert r.status_code == 503, (
            f"an unreadable registry answered {r.status_code}; the one outcome "
            f"that is not acceptable is answering with the document: {r.text}"
        )
        detail = r.json()["detail"]
        assert "connection reset by peer" in detail, detail
        assert re.search(r"provision", detail, re.I), detail
        assert "titulo" not in r.text, r.text
