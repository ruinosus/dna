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
import re
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_WID = "ws-approval00000000000001"

#: A SECOND workspace, sharing one scope with the first. That sharing is not an
#: artefact of the fixture: with multi-workspace off (``vendor_workspace``
#: unset) ``LiveDna.default_scope`` answers ``base_scope`` for EVERY workspace,
#: so this is the configuration the whole suite — and an OSS self-host — runs
#: under. Two workspaces, one scope, two different namespaces they each own.
_OTHER_WID = "ws-approval00000000000002"

_SCHEMA = {
    "type": "object",
    "properties": {"titulo": {"type": "string"}},
    "required": ["titulo"],
}

#: Vocabulary a "no such Kind here" refusal may NEVER use — the words with which
#: a 404 stops being a 404 and becomes "it is there, it is simply not yours".
#: See :func:`test_a_stranger_gets_the_same_answer_as_a_nonexistent_kind` for why
#: this is asserted POSITIVELY and not only by comparing the two refusals.
#:
#: Kept in step with the copy in ``test_kind_authoring_route.py``: the read door
#: and this one raise from ONE place, so a leak reworded there surfaces on both
#: and each file has to be able to see it on its own.
#:
#: What is deliberately absent matters as much: the refusal legitimately says
#: "under a namespace workspace X owns", naming the CALLER's own workspace, so a
#: blanket ban on the word "own" would forbid the true sentence.
_OWNERSHIP_TELL = re.compile(
    r"not\s+yours|not\s+your\b|belongs\s+to|owned\s+by|"
    r"(?:an|other|another|different)\s+workspace(?:'s)?\s+(?:kind|document|namespace)|"
    r"someone\s+else|exists?\s+but|but\s+it\s+(?:is|does)|"
    r"forbidden|unauthori[sz]ed|not\s+authori[sz]ed|permission|access\s+denied",
    re.I,
)

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


@pytest.fixture
def clock(monkeypatch):
    """A settable ``now`` for the routes, because the real one is too coarse.

    ``now_iso`` has SECONDS precision, so an author-then-edit inside one test
    stamps the same string twice and "created_at was preserved" would be
    indistinguishable from "created_at was overwritten with an identical
    value" — a test that passes without touching the behaviour it names. The
    handlers import ``now_iso`` from the module at call time, so patching the
    attribute reaches them."""
    import dna.application.sdlc as S

    state = {"now": "2020-01-01T00:00:00+00:00"}
    monkeypatch.setattr(S, "now_iso", lambda *a, **k: state["now"])
    return state


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


#: A VERIFIED token that carries no identity claim at all — a service token.
#: Verified and anonymous is a different fact from unauthenticated, and the
#: audit field has to be able to say so.
_SERVICE: dict = {}


def _client(dna_dir, *, raise_server_exceptions: bool = True) -> TestClient:
    return TestClient(
        R.build_app(
            base_dir=str(dna_dir), scope=_SCOPE, auth="config",
            verifier=_FakeVerifier(
                {"agent": _AGENT, "human": _HUMAN, "service": _SERVICE},
            ),
        ),
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


def _author(c, token, kind="Contrato", tenant=_WID, **body):
    return c.post("/v1/kinds", params={"tenant": tenant},
                  headers={"Authorization": f"Bearer {token}"},
                  json={"kind": kind, "schema": _SCHEMA, **body})


def _approve(c, token, kind="Contrato", tenant=_WID, **body):
    return c.post(f"/v1/kinds/{kind}/approve", params={"tenant": tenant},
                  headers={"Authorization": f"Bearer {token}"},
                  json=body or None)


def _row(c, token, kind="Contrato", tenant=_WID) -> dict:
    listed = c.get("/v1/kinds", params={"tenant": tenant},
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


# ── 4. what an EDIT does to the audit, and what a re-approval does ────────
#
# Hot-editing an approved Kind is supported (a second ``POST /v1/kinds`` for a
# name that already exists), and the authoring door rebuilds the spec field by
# field and PERSISTS it — ``write_document`` does not merge. So an edit decides,
# by omission, what happens to every audit field on the document. The semantics,
# decided here and pinned below:
#
#   created_at   — the BIRTH of the document. Preserved across edits; only a
#                  document that does not yet exist gets ``now``. The schema
#                  says "when the document was created", and it must stay true.
#   proposed_by  — the CURRENT proposal. Re-stamped on every author call: it
#                  answers "who proposed the shape that is pending or approved
#                  right now", and after an edit that is the editor. The
#                  original proposer stays recoverable through the kernel's
#                  version history.
#   approved_by  — DROPPED. An edit changes the shape a human approved, so the
#                  approval no longer applies to it and the Kind must lose its
#                  effect until someone approves the new shape.


def _edit_cycle(c, dna_dir, clock):
    """Author (agent, T1) → approve (human, T2) → EDIT (human, T3).

    Returns ``(name, spec_after_edit)``. Shared by the two tests below because
    they are two halves of one cycle: the edit withdraws effect, the second
    approval restores it."""
    clock["now"] = "2020-01-01T00:00:00+00:00"
    first = _author(c, "agent")
    assert first.status_code == 201, first.text
    name = first.json()["name"]

    clock["now"] = "2021-02-02T00:00:00+00:00"
    assert _approve(c, "human").status_code == 200

    clock["now"] = "2022-03-03T00:00:00+00:00"
    edited = _author(c, "human", schema={"type": "object",
                                         "properties": {"valor": {"type": "number"}}})
    assert edited.status_code == 201, edited.text
    assert edited.json()["name"] == name, "an edit must address the same document"
    return name, _stored_spec(dna_dir, name)


def test_an_edit_keeps_the_birth_date_restamps_the_proposer_and_drops_approval(
    dna_dir, clock,
):
    """RED against the pre-fix code on the FIRST assertion: ``created_at`` came
    back ``2022-03-03…`` — the edit's clock — because the door stamped ``now``
    unconditionally, which made the schema's "when the document was created"
    false from the first edit onward."""
    with _client(dna_dir) as c:
        name, spec = _edit_cycle(c, dna_dir, clock)

        assert spec["created_at"] == "2020-01-01T00:00:00+00:00", spec
        # The current proposal is the EDIT's, and it is the editor who made it.
        assert spec["proposed_by"] == _HUMAN["email"], spec
        assert spec["proposed_at"] == "2022-03-03T00:00:00+00:00", spec
        # And the approval is gone: a human approved a different shape.
        assert not spec.get("approved_by"), spec
        assert not spec.get("approved_at"), spec

        row = _row(c, "human")
        assert row["approved"] is False, row

    # Withdrawn in FACT, not just on the row: a fresh kernel no longer takes it.
    assert _registered_port(dna_dir, "Contrato") is None


def test_a_re_approval_after_an_edit_confers_effect_again(dna_dir, clock):
    """Last approval wins, and it is what puts the EDITED shape into effect.

    Nothing else pins this: the edit→de-approval→re-approval cycle is the whole
    point of the route, and a refactor that turned a second approval into a 409
    or a no-op would leave every edited Kind permanently inert."""
    with _client(dna_dir) as c:
        name, spec = _edit_cycle(c, dna_dir, clock)
        assert not spec.get("approved_by"), spec

        clock["now"] = "2023-04-04T00:00:00+00:00"
        again = _approve(c, "agent")
        assert again.status_code == 200, again.text

        spec = _stored_spec(dna_dir, name)
        # The SECOND approver, not the first — the record is of what happened.
        assert spec["approved_by"] == _AGENT["email"], spec
        assert spec["approved_at"] == "2023-04-04T00:00:00+00:00", spec
        # …and the proposal half of the audit survived the approval untouched.
        assert spec["proposed_by"] == _HUMAN["email"], spec
        assert spec["created_at"] == "2020-01-01T00:00:00+00:00", spec

    assert _registered_port(dna_dir, "Contrato") is not None


# ── 5. approval reaches only Kinds in namespaces the CALLER owns ──────────


def test_a_workspace_cannot_approve_another_workspaces_kind(dna_dir):
    """One scope, two workspaces, two namespaces — and approval must not cross.

    The document name is ``<namespace>--<kind>``, and the approval door
    addresses it by the Kind half alone. Without an ownership filter, workspace
    A asking to approve ``Contrato`` finds the ONLY ``…--Contrato`` in the
    scope — which is B's — and confers effect on it. Nothing downstream stops
    it: the approval write passes no ``tenant=``, so the namespace gate
    attributes it to the scope's own owner, not to the caller.

    RED against the pre-fix code: this returned 200, B's stored document came
    back carrying ``approved_by: human@tenant.example``, and a fresh kernel
    registered B's Kind — A having authored nothing at all."""
    with _client(dna_dir) as c:
        # B authors. A authors NOTHING — it has no Contrato of its own, so a
        # 404 here cannot be a coincidence of finding the caller's own document.
        r = _author(c, "agent", tenant=_OTHER_WID)
        assert r.status_code == 201, r.text
        victims_document = r.json()["name"]

        stolen = _approve(c, "human", tenant=_WID)
        assert stolen.status_code == 404, (
            f"workspace {_WID} approved a Kind it never authored: "
            f"{stolen.status_code} {stolen.text}"
        )

    # The refusal is the whole point, but the STORE is the evidence: a route
    # that answered 404 after writing the marker would have conferred effect
    # anyway on the next load.
    spec = _stored_spec(dna_dir, victims_document)
    assert not spec.get("approved_by"), spec
    assert _registered_port(dna_dir, "Contrato") is None


def test_the_owner_still_approves_its_own_kind_in_a_shared_scope(dna_dir):
    """The filter above must refuse the stranger without refusing the owner —
    with a second workspace's identically-named Kind sitting in the same scope,
    which is exactly the case a too-broad filter would break."""
    with _client(dna_dir) as c:
        assert _author(c, "agent", tenant=_OTHER_WID).status_code == 201
        mine = _author(c, "agent", tenant=_WID)
        assert mine.status_code == 201, mine.text

        r = _approve(c, "human", tenant=_WID)
        assert r.status_code == 200, r.text
        assert r.json()["name"] == mine.json()["name"], r.json()

    assert _stored_spec(dna_dir, mine.json()["name"])["approved_by"] == _HUMAN["email"]


def test_a_stranger_gets_the_same_answer_as_a_nonexistent_kind(dna_dir):
    """404, never 403 — and the SENTENCE must not say which of the two it is.

    The test above proves the neighbour's Kind is not approved. It says nothing
    about what the caller LEARNS from being refused, and that is the second half
    of the same boundary: "it exists but is not yours" is a probe. A workspace
    that can tell the two refusals apart can enumerate what its neighbours are
    authoring, one Kind name at a time, without ever reading a document — and it
    needs no 403 to do it, one distinguishing word in a 404 body is enough.

    Until this test existed, NOTHING compared the approval door's two 404s. The
    door had (and has) exactly one ``raise`` for both facts, which is why the
    property held; but a fence that is only a property of today's code shape is
    not a fence. Two assertions, failing on two different mutations:

    1. neither refusal uses ownership vocabulary (:data:`_OWNERSHIP_TELL`) —
       the only thing that catches a REWORDED refusal, since a rewrite reaches
       both refusals equally and leaves any comparison green;
    2. the stranger's 404 equals the OWNER's own wrong-name 404 — same caller,
       holding a namespace claim of its own, naming a Kind it owns nothing by.
       That catches a handler that grows a SECOND refusal on the "found it,
       dropped it for ownership" path.

    The caller authors a Kind of its own first, on purpose: a workspace that has
    authored nothing owns no namespace, and its two refusals would match for the
    uninteresting reason that it is a stranger to the entire scope."""
    with _client(dna_dir) as c:
        neighbour = _author(c, "agent", tenant=_OTHER_WID)
        assert neighbour.status_code == 201, neighbour.text
        # The caller is an author too — it owns a namespace, and a Kind under
        # it, and still must not be able to feel its neighbour's.
        mine = _author(c, "agent", kind="Acordo", tenant=_WID)
        assert mine.status_code == 201, mine.text

        stranger = _approve(c, "human", kind="Contrato", tenant=_WID)
        owners_wrong_name = _approve(c, "human", kind="NuncaExistiu", tenant=_WID)
        # …and the door still works for what the caller does own: a door that
        # 404'd for everybody would satisfy every assertion below.
        assert _approve(c, "human", kind="Acordo", tenant=_WID).status_code == 200

    assert (stranger.status_code, owners_wrong_name.status_code) == (404, 404), (
        stranger.text, owners_wrong_name.text,
    )
    # The anti-tautology: FastAPI's own routing 404 is ``{"detail": "Not Found"}``
    # for both, and two identical strings are trivially indistinguishable. Each
    # refusal naming the Kind it could not find is what makes the comparison
    # below a statement about the handler.
    assert "Contrato" in stranger.json()["detail"], stranger.text
    assert "NuncaExistiu" in owners_wrong_name.json()["detail"], owners_wrong_name.text

    # (1) The refusal must not TELL.
    for label, r in (("stranger", stranger), ("absent", owners_wrong_name)):
        tell = _OWNERSHIP_TELL.search(r.json()["detail"])
        assert tell is None, (
            f"the {label} refusal says {tell.group(0)!r} — a refusal that speaks "
            f"of ownership at all is the probe this door exists to close, "
            f"whether or not the two refusals happen to match:\n  "
            f"{r.json()['detail']}"
        )
    # …nor name the neighbour: the workspace id, or the namespace it authored
    # under, is the same fact by another spelling.
    assert _OTHER_WID not in stranger.text, stranger.text
    assert neighbour.json()["namespace"] not in stranger.text, stranger.text

    # (2) Modulo the Kind name the caller itself supplied, one string.
    assert (stranger.json()["detail"].replace("Contrato", "<kind>")
            == owners_wrong_name.json()["detail"].replace("NuncaExistiu", "<kind>")), (
        f"the approval refusal distinguishes a neighbour's Kind from a "
        f"nonexistent one, which is the probe:\n"
        f"  stranger: {stranger.json()['detail']}\n"
        f"  absent:   {owners_wrong_name.json()['detail']}"
    )


def _claim_namespace(dna_dir, *, namespace: str, owner: str,
                     name: str | None = None) -> None:
    """Write ONE ``KindNamespace`` claim into the registry scope.

    ``name`` defaults to the namespace (the ordinary one-claim-per-namespace
    shape); passing a different document name is how a SECOND, conflicting
    claim for the same namespace is seeded — the doubly-claimed record
    ``owner_of`` refuses to resolve."""
    from dna.application.namespace_assignment import TENANT_API_VERSION
    from dna.kernel.protocols import SYSTEM_SCOPE

    doc = name or namespace

    async def claim(live):
        await live.kernel.write_document(
            SYSTEM_SCOPE, "KindNamespace", doc,
            {"apiVersion": TENANT_API_VERSION, "kind": "KindNamespace",
             "metadata": {"name": doc},
             "spec": {"owner": owner, "namespace": namespace,
                      "claimed_at": "2099-01-01T00:00:00+00:00",
                      "notes": "test seed"}},
            invalidate_mode="doc",
        )

    _on_fresh_kernel(dna_dir, claim)


def _seed_second_namespace(dna_dir, *, owner: str, namespace: str,
                           kind: str = "Contrato") -> str:
    """Give ``owner`` a SECOND namespace and a Kind of the same name under it.

    A workspace may own several namespaces — the ``KindNamespace`` descriptor
    says nothing constrains the count, and the proof-of-ownership flow is how a
    workspace gets a public one (``acme.example``) beside its assigned
    ``ws-….dna.local``. The door cannot author under the second (assignment
    always answers the earliest ASSIGNED claim), so the second document is
    seeded through the kernel — the same call the authoring door itself makes.

    ``acme.example`` deliberately lacks the ``.dna.local`` suffix, so
    ``assign_namespace`` filters it out and authoring keeps landing under the
    assigned namespace. Returns the seeded document's name."""
    name = f"{namespace}--{kind}"
    _claim_namespace(dna_dir, namespace=namespace, owner=owner)

    async def seed(live):
        await live.kernel.write_document(
            _SCOPE, "KindDefinition", name,
            {"apiVersion": "github.com/ruinosus/dna/core/v1",
             "kind": "KindDefinition", "metadata": {"name": name},
             "spec": {"target_api_version": f"{namespace}/v1",
                      "target_kind": kind,
                      "alias": f"{namespace.replace('.', '-')}-{kind.lower()}",
                      "origin": namespace,
                      "schema": _SCHEMA,
                      "storage": {"type": "yaml", "container": f"{kind.lower()}s"}}},
        )
        return name

    return _on_fresh_kernel(dna_dir, seed)


def test_one_kind_under_two_namespaces_the_caller_owns_is_an_ambiguity(dna_dir):
    """Refusing to pick a winner — and the refusal now MEANS "you own both".

    Before the ownership filter this same 400 also fired when the two documents
    belonged to two DIFFERENT workspaces, which is not an ambiguity at all: one
    of them simply was not the caller's. The filter is what makes the message
    true, so this test pins the refusal in its only honest configuration — one
    workspace, two namespaces it owns, the same Kind declared under both."""
    seeded = _seed_second_namespace(dna_dir, owner=_WID, namespace="acme.example")
    assert _stored_spec(dna_dir, seeded).get("target_kind") == "Contrato", (
        "the seeded second-namespace document did not land — without it there "
        "is only one match and this test would assert an ambiguity that the "
        "code never had the chance to detect"
    )
    with _client(dna_dir) as c:
        assigned = _author(c, "agent", tenant=_WID)
        assert assigned.status_code == 201, assigned.text

        r = _approve(c, "human", tenant=_WID)
        assert r.status_code == 400, r.text
        detail = r.json()["detail"]
        # Named, both of them — a reviewer resolves this by document name and
        # cannot do that from a refusal that hides which two it means.
        assert "acme.example" in detail, detail
        assert assigned.json()["namespace"] in detail, detail
        # …and it must tell them WHAT to do. The instruction is the whole point
        # of refusing instead of guessing, and nothing pinned it: the verb
        # silently changed from "approve it" to "address it" when
        # ``_authored_document_name`` became shared with the READ door — where
        # "approve it" would have been wrong advice. "address it" is the one
        # that is true on both doors, and it is pinned here as a literal so the
        # next caller cannot narrow it back without saying so.
        assert "address it by document name, not by Kind name" in detail, detail

    for name in (seeded, assigned.json()["name"]):
        assert not _stored_spec(dna_dir, name).get("approved_by"), name
    assert _registered_port(dna_dir, "Contrato") is None


def test_a_doubly_claimed_namespace_refuses_the_approval(dna_dir):
    """The third control path out of ``_authored_document_name``, and the only
    one that had no test — its two siblings (404 for a stranger's Kind, 400 for
    a Kind the caller declared twice) are both covered above.

    ``owner_of`` REFUSES to resolve a namespace two ``KindNamespace`` claims
    give to different owners, rather than picking a winner — so ``owns()``
    raises mid-iteration and the approval never happens. That is the right
    answer: an ambiguous authorization record is not a tie to break, and
    breaking it either way would let one of the two workspaces confer effect
    inside a namespace the registry also says belongs to somebody else. The
    refusal is a ``NamespaceOwnershipError`` (a ``LayerPolicyViolationError``),
    so the face answers 403 — and it must NAME both claimants, or the operator
    cannot find the row to delete."""
    with _client(dna_dir) as c:
        mine = _author(c, "agent", tenant=_WID)
        assert mine.status_code == 201, mine.text
        namespace = mine.json()["namespace"]

    # The conflicting claim lands AFTER authoring — authoring itself resolves
    # the same registry, so seeding first would refuse the setup instead.
    intruder = "ws-intruder0000000000001"
    _claim_namespace(dna_dir, namespace=namespace, owner=intruder,
                     name=f"{namespace}-conflict")

    with _client(dna_dir, raise_server_exceptions=False) as c:
        r = c.post(f"/v1/kinds/Contrato/approve", params={"tenant": _WID},
                   headers={"Authorization": "Bearer human"})
        assert r.status_code == 403, r.text
        detail = r.json()["detail"]
        assert namespace in detail, detail
        assert _WID in detail and intruder in detail, detail

    assert not _stored_spec(dna_dir, mine.json()["name"]).get("approved_by")
    assert _registered_port(dna_dir, "Contrato") is None


# ── 5b. the shared lookup's precondition is structural, not documentary ────
#
# ``_authored_document_name`` is reached by two doors with OPPOSITE tenancy
# preconditions: approval refuses a missing tenant before it calls, while the
# read passes ``None`` straight through to the deliberately UNFILTERED lane
# (the operator ``scope=`` call, the self-host). That difference used to live
# in a docstring and in the ORDER the approval impl does its checks — which is
# a promise, not a mechanism: a third caller that forgot it would get a search
# across every workspace sharing the scope, silently, with the Kind half of a
# document name as the only key.


def test_the_unfiltered_lane_must_be_asked_for_by_name(dna_dir):
    """The parameter has NO default, so nobody can reach the unfiltered lane by
    omission — the question has to be answered at every call site.

    Asserted on the signature because that is where the property lives: a
    behavioural test alone would keep passing the day somebody adds
    ``allow_unattributed=True`` as a default, which is exactly the regression
    this pins."""
    import inspect

    from dna.application import kind_authoring as K

    param = inspect.signature(K._authored_document_name).parameters[
        "allow_unattributed"
    ]
    assert param.default is inspect.Parameter.empty, (
        "`allow_unattributed` grew a default — the precondition is documentary "
        "again, and a caller that forgets it gets an unfiltered search over "
        "every workspace sharing the scope"
    )
    assert param.kind is inspect.Parameter.KEYWORD_ONLY, param.kind


def test_the_filtered_lane_refuses_an_unattributed_call_rather_than_searching(
    dna_dir,
):
    """And the enforcement half — with the discriminator that makes it mean
    something: the SAME call on the unfiltered lane finds the document. So the
    refusal is the precondition firing, not an empty store."""
    from dna.application import kind_authoring as K

    with _client(dna_dir) as c:
        # Authored by a workspace the unattributed caller is emphatically not.
        authored = _author(c, "agent", tenant=_OTHER_WID)
        assert authored.status_code == 201, authored.text

    async def probe(live):
        with pytest.raises(ValueError) as refused:
            await K._authored_document_name(
                live, scope=_SCOPE, kind="Contrato", tenant=None,
                allow_unattributed=False,
            )
        found, _namespace = await K._authored_document_name(
            live, scope=_SCOPE, kind="Contrato", tenant=None,
            allow_unattributed=True,
        )
        return type(refused.value), str(refused.value), found

    raised, message, found = _on_fresh_kernel(dna_dir, probe)

    assert found == authored.json()["name"], found
    # A ValueError proper — the face maps that to 400 ("this request is
    # malformed"), which is what an unattributed call to a filtered act IS.
    # ``AuthoredKindNotFound`` is a ``LookupError`` and would be a 404, i.e.
    # "no such Kind", sending the caller after the wrong bug entirely.
    assert raised is ValueError, raised
    assert "Contrato" in message, message
    assert "workspace is required" in message, message


# ── 6. the sentinel a token with no identity leaves behind ────────────────


def test_a_verified_anonymous_token_is_recorded_as_unidentified(dna_dir):
    """``rest:unidentified`` — pinned as a LITERAL, on a stored document.

    The label is a brand-new value that lands in a persisted audit field, and
    an audit field's values are a contract with every future reader of the
    store. Nothing else in the tree asserted it. It must also stay DISTINCT
    from ``rest:local``: verified-and-anonymous (a service token) is not the
    same fact as no-token-at-all, and collapsing the two would tell a reviewer
    a remote automated caller was somebody at a laptop."""
    with _client(dna_dir) as c:
        r = _author(c, "service")
        assert r.status_code == 201, r.text
        name = r.json()["name"]
        assert _approve(c, "service").status_code == 200

    spec = _stored_spec(dna_dir, name)
    assert spec["proposed_by"] == "rest:unidentified", spec
    assert spec["approved_by"] == "rest:unidentified", spec
    assert R._UNIDENTIFIED_TOKEN_ACTOR == "rest:unidentified"
    assert R._UNIDENTIFIED_LOCAL_ACTOR != R._UNIDENTIFIED_TOKEN_ACTOR


def test_approving_without_a_registry_scope_refuses_actionably(dna_dir):
    """Not a 500 — the same 503 its sibling door has always given.

    Approval resolves the ``KindNamespace`` registry to check the caller owns
    the namespace the Kind was authored under, so a store whose ``_lib`` scope
    is not provisioned hits the same deployment precondition the authoring
    route already maps (``test_kind_authoring_route.py``). Only one of the two
    routes mapped it, which is how one missing directory answered honestly on
    one door and with an unmapped 500 on the other.

    The registry is removed AFTER authoring, and a second client is opened, so
    the refusal is not merely a cached read: the second app boots its own live
    kernel over the store as it now stands."""
    with _client(dna_dir) as c:
        assert _author(c, "agent").status_code == 201

    shutil.rmtree(dna_dir / "_lib")

    with _client(dna_dir, raise_server_exceptions=False) as c:
        r = _approve(c, "human")
        assert r.status_code == 503, r.text
        detail = r.json()["detail"]
        assert "_lib" in detail, detail
        assert re.search(r"provision", detail, re.I), detail


# ── 7. the listing must withhold what the approval door already withholds ──
#
# ``GET /v1/kinds`` is the sibling of the approval door and reads the SAME
# shared scope. Approval answers 404 for a neighbour's Kind on the stated
# ground that "it exists but is not yours" hands a stranger a probe for what
# its neighbours are authoring — and then the listing handed over the whole
# roster: the neighbour's Kind names, its namespace, and ``proposed_by`` /
# ``approved_by``, which are identity strings (emails).
#
# The counter-argument — "the listing is also the operator's audit view" — is
# the conflation this section refuses: an operator view needs a different
# authorization and a different result set (every workspace), and serving it by
# leaving the TENANT route unfiltered makes the tenant's default the operator's
# power.
#
# Three things the filter must NOT break, all load-bearing:
#   * the unattributed lane (``--auth none`` self-host, an explicit operator
#     ``scope=`` call) resolves no tenant — filtering it would answer every
#     self-hoster with an empty list. Same hinge ``NamespaceOwnershipGate`` uses
#     for an unattributed write: no resolved tenant ⇒ not filtered.
#   * NON-NAMESPACED documents. A name without ``--`` has no namespace half to
#     test at all — an operator-seeded ``KindDefinition`` is the ordinary case.
#   * INHERITED rows — a curated base Kind a workspace consumes through
#     ``parent_scope`` is nobody's to own, so "owned by the caller" alone would
#     delete it from the roster. MEASURED, and the reason the seed below lives
#     in the caller's own scope rather than in ``_lib``: no inherited row can
#     reach this listing TODAY. ``KindDefinition`` is a BOOTSTRAP Kind, and
#     ``Kernel._NON_INHERITABLE_KINDS`` unions ``_BOOTSTRAP_KINDS``, so
#     ``kernel.query``'s catalog and parent passes are both skipped for it and
#     ``origin="all"`` is exactly ``origin="local"``. A ``KindDefinition``
#     written into ``_lib`` (the ``DEFAULT_BASE_SCOPE`` parent) does NOT appear
#     in the ``concierge`` listing even UNFILTERED — verified. The rule is
#     implemented anyway, because it costs one pass and because the day
#     ``scope_inheritable`` flips is not the day to discover the listing eats
#     the base catalogue; :func:`test_an_inherited_row_survives_the_filter`
#     pins the branch directly against the use-case.


def _seed_unnamespaced_kind_document(dna_dir, *, name: str = "operatorseeded") -> str:
    """A ``KindDefinition`` in the CALLER's scope whose document name carries no
    ``--`` — so there is no namespace half for the ownership test to read.

    Not an exotic shape: every ``KindDefinition`` that predates the authoring
    door, and every one an operator writes by hand, looks like this. A filter
    that split the name unconditionally would drop the whole class."""

    async def seed(live):
        await live.kernel.write_document(
            _SCOPE, "KindDefinition", name,
            {"apiVersion": "github.com/ruinosus/dna/core/v1",
             "kind": "KindDefinition", "metadata": {"name": name},
             "spec": {"target_api_version": "curated.example/v1",
                      "target_kind": "Curada",
                      "alias": "curated-example-curada",
                      "origin": "curated.example",
                      "schema": _SCHEMA,
                      "storage": {"type": "yaml", "container": "curadas"}}},
        )
        return name

    return _on_fresh_kernel(dna_dir, seed)


def test_the_listing_does_not_hand_a_workspace_its_neighbours_kinds(dna_dir):
    """RED against the pre-filter code: A's listing carried B's document name,
    B's namespace AND ``proposed_by: agent@tenant.example`` — the neighbour's
    identity string, which is the very fact the approval door's 404 withholds.

    A authors one Kind of its own and an operator-seeded, non-namespaced one
    sits beside it, so a filter that over-corrected (empty list, or a blind
    ``rsplit`` on every name) fails here too."""
    curated = _seed_unnamespaced_kind_document(dna_dir)
    with _client(dna_dir) as c:
        # B — the neighbour. Proposed by the AGENT identity, so the leak is
        # attributable to a specific email and not merely to "a row appeared".
        b = _author(c, "agent", kind="Contrato", tenant=_OTHER_WID)
        assert b.status_code == 201, b.text
        neighbours_document = b.json()["name"]

        # A — the caller. A Kind of its own, under a different Kind name so the
        # two rows can never be confused for one another.
        mine = _author(c, "human", kind="Proposta", tenant=_WID)
        assert mine.status_code == 201, mine.text
        my_document = mine.json()["name"]

        listed = c.get("/v1/kinds", params={"tenant": _WID},
                       headers={"Authorization": "Bearer human"})
        assert listed.status_code == 200, listed.text
        rows = listed.json()["kinds"]

    by_name = {r["name"]: r for r in rows}
    # The sanity half FIRST: if the seeds did not land, every assertion below
    # would pass on an empty listing for the wrong reason.
    assert my_document in by_name, rows
    assert curated in by_name, (
        f"the non-namespaced Kind {curated!r} is not in the listing — the "
        f"filter deleted a document with no namespace half to test: "
        f"{sorted(by_name)}"
    )

    leaked = by_name.get(neighbours_document)
    assert leaked is None, (
        f"workspace {_WID}'s listing carries workspace {_OTHER_WID}'s authored "
        f"Kind: {leaked!r}"
    )
    # …and the identity half, named on its own: `proposed_by` is an email, and
    # a projection that dropped `name` while keeping the actors would satisfy
    # the assertion above while still leaking the thing that matters.
    assert not [r for r in rows if r.get("proposed_by") == _AGENT["email"]], rows
    assert not [r for r in rows if r.get("namespace") == b.json()["namespace"]], rows


def test_an_inherited_row_survives_the_filter():
    """"Owned by the caller OR inherited from the parent" — the second half,
    pinned against the use-case with a stub kernel.

    It cannot be reached through the store today (see the section comment: a
    BOOTSTRAP Kind never runs ``kernel.query``'s parent pass), and a rule with
    no test is a rule the next refactor deletes. The stub answers ``origin=
    "local"`` with the caller's own document only, and the default
    ``origin="all"`` with that document plus one the caller does not own — which
    is exactly the shape an inherited curated Kind arrives in."""
    from dna.application.kind_authoring import list_authored_kinds_impl

    mine = "ws-1a2b3c.dna.local--Proposta"
    inherited = "curated.example--Curada"

    def _doc(name, *, proposed_by):
        return {"metadata": {"name": name},
                "spec": {"target_kind": name.split("--")[1],
                         "target_api_version": f"{name.split('--')[0]}/v1",
                         "origin": name.split("--")[0],
                         "proposed_by": proposed_by}}

    class _Kernel:
        async def kind_namespaces(self):
            return [{"spec": {"namespace": "ws-1a2b3c.dna.local",
                              "owner": "ws-caller"}}]

        async def query(self, scope, kind, *, tenant=None, origin="all", **kw):
            yield _doc(mine, proposed_by="me@tenant.example")
            if origin != "local":
                yield _doc(inherited, proposed_by="curator@base.example")

    class _Live:
        kernel = _Kernel()

        def default_scope(self, tenant):
            return "concierge"

    out = asyncio.run(list_authored_kinds_impl(_Live(), tenant="ws-caller"))
    names = {k["name"] for k in out["kinds"]}
    assert names == {mine, inherited}, names


def test_an_unattributed_listing_is_not_filtered(dna_dir):
    """No resolved tenant ⇒ no filter — the ``--auth none`` self-host and the
    explicit operator ``scope=`` call.

    A filter that unconditionally demands ownership answers every self-hoster
    with an empty list, because there is no workspace to own anything. The hinge
    is the one ``NamespaceOwnershipGate`` already uses for an unattributed
    write, and it rests on the same standing invariant: a hosted face never
    issues an unattributed request on a user's behalf."""
    with _client(dna_dir) as c:
        a = _author(c, "agent", kind="Contrato", tenant=_WID)
        b = _author(c, "agent", kind="Acordo", tenant=_OTHER_WID)
        assert (a.status_code, b.status_code) == (201, 201), (a.text, b.text)

        listed = c.get("/v1/kinds", params={"scope": _SCOPE},
                       headers={"Authorization": "Bearer human"})
        assert listed.status_code == 200, listed.text
        names = {k["name"] for k in listed.json()["kinds"]}

    assert {a.json()["name"], b.json()["name"]} <= names, sorted(names)


def test_an_ambiguous_ownership_record_refuses_the_listing(dna_dir):
    """Fail CLOSED, never silently unfiltered.

    Two ``KindNamespace`` claims naming different owners for one namespace make
    ``owner_of`` raise rather than pick a winner, and the listing must not
    answer that by falling back to the unfiltered roster — the one outcome that
    is not acceptable, because it turns an unreadable authorization record into
    a grant.

    The second claim needs its own DOCUMENT name: reusing the namespace as the
    document name overwrites the first claim instead of contradicting it, and
    the listing then answers a perfectly well-formed 200 with the caller's row
    filtered out — a test that would have asserted the wrong mechanism."""
    with _client(dna_dir) as c:
        mine = _author(c, "agent", kind="Contrato", tenant=_WID)
        assert mine.status_code == 201, mine.text
        namespace = mine.json()["namespace"]

    intruder = "ws-intruder0000000000001"
    _claim_namespace(dna_dir, namespace=namespace, owner=intruder,
                     name=f"{namespace}-conflict")

    with _client(dna_dir, raise_server_exceptions=False) as c:
        r = c.get("/v1/kinds", params={"tenant": _WID},
                  headers={"Authorization": "Bearer human"})
        assert r.status_code == 403, r.text
        detail = r.json()["detail"]
        assert namespace in detail, detail
        assert _WID in detail and intruder in detail, detail


def test_a_registry_read_error_that_is_not_a_missing_file_still_refuses(
    dna_dir, monkeypatch,
):
    """The gap ``FileNotFoundError``-only mapping left, on BOTH read doors.

    The write path's ``NamespaceOwnershipGate`` catches a BROAD ``Exception`` on
    the registry read and converts it to an honest refusal; the read doors
    caught only ``FileNotFoundError``. On a filesystem store the two coincide (a
    missing ``_lib`` DIRECTORY is exactly a ``FileNotFoundError``), which is why
    ``test_approving_without_a_registry_scope_refuses_actionably`` could not see
    this — on Postgres a transient registry read error is a driver exception,
    and it 500'd on approval while the identical failure refused honestly one
    path over.

    Simulated at the seam rather than by standing up Postgres: the failure being
    tested is "``kind_namespaces()`` raised something that is not a missing
    file", and that is precisely what is injected. 503 because it is a
    deployment PRECONDITION, not the caller's fault — and never a silent
    success, which for the LISTING would mean the unfiltered roster."""
    from dna.kernel import Kernel

    async def boom(self, *a, **kw):
        raise RuntimeError("connection reset by peer")

    with _client(dna_dir) as c:
        assert _author(c, "agent").status_code == 201

    monkeypatch.setattr(Kernel, "kind_namespaces", boom, raising=True)

    with _client(dna_dir, raise_server_exceptions=False) as c:
        approved = _approve(c, "human")
        assert approved.status_code == 503, approved.text
        assert "connection reset by peer" in approved.json()["detail"], approved.text

        listed = c.get("/v1/kinds", params={"tenant": _WID},
                       headers={"Authorization": "Bearer human"})
        assert listed.status_code == 503, (
            f"an unreadable registry made the listing answer "
            f"{listed.status_code}; the one outcome that is not acceptable is "
            f"the unfiltered list: {listed.text}"
        )


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
