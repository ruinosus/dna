"""One Kind, authored once, alive on every face that can reach it.

This is the founder's actual requirement stated as a test: *a Kind born on one
face and absent from the others is worth nothing.* Every other suite on this
branch proves ONE face — the MCP tools (``test_mcp_kind_authoring.py``), the
authoring route (``test_kind_authoring_route.py``), the approval act
(``test_kind_approval_audit.py``). None of them follows a single artefact
across the boundary, and "each half works" is not the same claim as "the whole
thing is one thing".

**Three faces, and exactly three.** The reviewing UI lives in a SEPARATE
repository and cannot be exercised from here, so nothing below claims to cover
it. What is covered is:

* **MCP** — an agent calls ``author_kind`` over a real ``fastmcp`` client;
* **REST** — ``GET /v1/kinds``, ``GET /v1/kinds/{kind}`` and
  ``POST /v1/kinds/{kind}/approve``, which is *the exact API the reviewing UI
  consumes*: proving the artefact is correct on this wire is the strongest
  statement this repository can make about that face;
* **the SDK / kernel** — a kernel booted fresh over the same store, which is
  where "the Kind has effect" is a fact rather than a field.

**The thread that ties them together is one string.** The apiVersion is MINTED
by the MCP call (``<assigned-namespace>/v1``), PUBLISHED by the REST listing,
and becomes the kernel registry's KEY. And the instance ends up carrying one
identity from each of the two acting faces: ``proposed_by`` is the MCP face's
own actor, ``approved_by`` is the REST face's verified caller. A single instance
that no one face could have written alone is what "the same artefact" means
here.

**The central assertion, and why it is the sharp one.** The brief asked for "a
instance of it can now be written and read back". That is a weak proof on its
own: writing succeeds either way, because an unregistered Kind's instances are
simply accepted unvalidated. Registration is what confers **schema validation
and storage routing**, so the decisive contrast is the same write before and
after:

===================  ===========================================================
before approval      a ``Contrato`` instance that VIOLATES the declared schema
                     is accepted, and lands unrouted at the root of the scope
after approval       the byte-identical write is REFUSED
                     (``SpecValidationError``), and a conforming one is routed
                     into the Kind's own declared container
===================  ===========================================================

Both halves are measured on the FILESYSTEM as well as on the return value: a
route that reported a refusal after writing, or reported a container it did not
use, would satisfy a return-value assertion and lie to the store.

**Everything that asks "did this take effect?" runs on a FRESH kernel.** The
registry is per-kernel and outlives the ``instance_async`` of the process that
wrote the instance, so probing effect in the writing process can be true for the
wrong reason. :func:`_on_fresh_kernel` is the neighbouring suites' helper, kept
identical on purpose.

**And then the agent can use it.** The mechanism above is the kernel's; the
DELIVERY is that the agent reaches its new Kind through the same generic MCP
tools it uses for every other one —
:func:`test_the_kind_the_agent_authored_is_usable_by_the_agent_that_authored_it`
discovers it in ``list_kinds``, writes a conforming instance through
``write_instance`` into the container the Kind declares, and is refused a
violating one by the Kind's own schema.

That last part did not work when this file was first written, and the reason is
recorded because it is the kind of thing that regrows: the MCP server boots its
kernel through a LAZY manifest instance, and the lazy path used to parse the
bootstrap instances without ever running the registration pass over them — so
NO per-scope declarative Kind was reachable from those tools. It was a boot-path
gap and NOT the approval gate, which is what
:func:`test_the_generic_mcp_document_face_does_not_discriminate_on_approval`
pins: whatever that face does with a per-scope Kind, approval is not what
decides it. That discriminator held while both Kinds were refused and holds now
that both are accepted, which is what a discriminator is for.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")
pytest.importorskip("fastmcp", reason="the MCP face needs the optional 'mcp' extra")

from fastapi.testclient import TestClient  # noqa: E402
from fastmcp import Client  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"

#: The ONE workspace this journey belongs to. Both faces speak for it — the MCP
#: tool takes it as the bound ``tenant`` (over a real transport an authenticated
#: door resolves it from the token), the REST lane as the query param the config
#: middleware would overwrite with a membership-bound value if the fake claims
#: carried one.
_WID = "ws-threefaces000000000001"

#: The Kind the agent declares, and the shape it declares for it. ``required``
#: is not decoration: without it a violating instance is only violating by TYPE,
#: and the two halves of the central contrast want a violation that is
#: unambiguous in the schema's own terms.
_KIND = "Contrato"
_SCHEMA = {
    "type": "object",
    "properties": {"titulo": {"type": "string"}},
    "required": ["titulo"],
}

#: An instance of that Kind that the declared schema forbids — ``titulo`` is
#: declared a string. Written with the SAME name on both sides of the approval
#: so the contrast is one call repeated, not two calls compared.
_VIOLATING = {"titulo": 12345}
_VIOLATING_DOC = "prova-de-forma"

#: …and one the schema allows, for the after-approval half. A refusal alone
#: would be satisfied by a Kind that refuses everything.
_CONFORMING = {"titulo": "Acordo de nivel de servico"}
_CONFORMING_DOC = "prova-conforme"

#: Where an approved ``Contrato``'s instances must land. The authoring door
#: declares ``storage: {type: yaml, container: "<kind>s"}``, and the container is
#: the storage-routing half of what registration confers — invisible in any
#: return value, visible on disk.
_CONTAINER = "contratos"

#: The REST reviewer. A verified identity, because the approval half of the
#: audit is only worth reading when it names somebody the server proved.
_HUMAN = {"oid": "oid-human", "email": "human@tenant.example"}
_HUMAN_TOKEN = "human"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    """A writable copy of the example scope, with the ``_lib`` registry scope.

    Same fixture shape as ``test_kind_approval_audit.py``'s: authoring READS the
    ``KindNamespace`` registry before it mints a namespace, a filesystem source
    raises ``FileNotFoundError`` for a scope directory that is not there, and the
    shipped example scope ships none.

    ``DNA_PERSONAL_ID`` is cleared because the MCP face honours it when resolving
    an unauthenticated caller's actor — an operator's own environment would
    otherwise decide what ``proposed_by`` says, and this file asserts on that
    field to prove WHICH face stamped it."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
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


# ── the three faces, as three call helpers ────────────────────────────────


def _mcp(dna_dir, tool: str, args: dict) -> dict:
    """Call ``tool`` on a real MCP server over a real ``fastmcp`` client.

    A NEW server per call, deliberately: each one boots its own kernel over the
    store as it now stands, so nothing this file reads through the MCP face can
    be an artefact of a process that never reloaded. Sync over ``asyncio.run``
    because the ``packages/cli`` venv carries no ``pytest-asyncio`` — the shape
    every neighbouring suite uses."""
    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))

    async def go():
        async with Client(server) as client:
            return await client.call_tool(tool, args)

    return asyncio.run(go()).structured_content


class _FakeAccess:
    def __init__(self, claims):
        self.claims = claims


class _FakeVerifier:
    """The bearer string is a KEY into a claims table; an unknown token → None
    (→ 401), mirroring the composite N-provider verifier's contract. The
    ``test_kind_approval_audit.py`` shape, because the Kind routes are mounted
    only on the identity-bound lane and that is the lane they must be exercised
    on."""

    def __init__(self, table):
        self._table = table

    async def verify_token(self, token):
        claims = self._table.get(token)
        return _FakeAccess(claims) if claims is not None else None


def _rest(dna_dir, *, raise_server_exceptions: bool = True) -> TestClient:
    """The REST face on ``--auth config`` — the only lane the Kind routes are
    mounted on, because every ownership property they decide rests on a
    ``tenant`` bound to a verified identity rather than typed by the caller."""
    return TestClient(
        R.build_app(
            base_dir=str(dna_dir), scope=_SCOPE, auth="config",
            verifier=_FakeVerifier({_HUMAN_TOKEN: _HUMAN}),
        ),
        raise_server_exceptions=raise_server_exceptions,
        headers={"Authorization": f"Bearer {_HUMAN_TOKEN}"},
    )


def _on_fresh_kernel(dna_dir, fn):
    """Run ``fn(live)`` against a kernel booted FRESH over the same store, with
    the scope's manifest instance built — i.e. after the real 2-phase load has
    parsed every stored ``KindDefinition`` and applied the approval gate.

    Identical to the helper in ``test_kind_authoring_route.py`` /
    ``test_kind_approval_audit.py``, and identical on purpose: the registry is
    per-kernel and outlives an ``instance_async`` call, so a probe run inside the
    process that did the writing can report registration that no other process
    would see."""
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        await live.kernel.instance_async(_SCOPE)
        return await fn(live)

    return asyncio.run(go())


# ── the journey ───────────────────────────────────────────────────────────


def _author_over_mcp(dna_dir, kind: str = _KIND, schema: dict | None = None) -> dict:
    """Face one: the agent declares the Kind. Returns the tool's own payload."""
    out = _mcp(dna_dir, "author_kind", {
        "tenant": _WID, "kind": kind,
        "schema": _SCHEMA if schema is None else schema,
    })
    assert out["approved"] is False, out
    return out


def _approve_over_rest(dna_dir, kind: str = _KIND):
    """Face two: the human confers effect, through the API the reviewing UI
    calls."""
    with _rest(dna_dir) as c:
        return c.post(f"/v1/kinds/{kind}/approve", params={"tenant": _WID})


def _scope_files(dna_dir) -> set[pathlib.Path]:
    return {p for p in (dna_dir / _SCOPE).rglob("*") if p.is_file()}


def _written_document_file(dna_dir, before: set[pathlib.Path]) -> pathlib.Path:
    """The ONE file a write added under the scope, whatever the layout.

    Read off the filesystem rather than from a path this test builds, so the
    assertions below say where the instance LANDED and not where we assumed it
    would."""
    added = sorted(_scope_files(dna_dir) - before)
    assert len(added) == 1, f"expected exactly one new file, got {added}"
    return added[0]


# ── 1. one artefact, two faces, one apiVersion ────────────────────────────


def test_the_kind_the_agent_authored_is_the_one_the_reviewers_api_serves(dna_dir):
    """Face one writes it; face two reads back the SAME artefact — not a
    similarly-shaped one.

    Three things are compared, and each would survive the loss of the other two:
    the apiVersion the MCP call minted is the one the REST listing publishes; the
    JSON Schema the agent typed is the one the reviewer's detail route hands
    back, byte for byte (a reviewer deciding whether to confer effect is deciding
    about the schema, so a listing that agreed on the name while serving a
    different shape would be worse than no listing); and ``proposed_by`` names
    the MCP face's own actor, which is how we know the row describes the
    instance that face wrote rather than one this test's REST client authored on
    the side."""
    from dna_cli._mcp_auth import UNIDENTIFIED_LOCAL_ACTOR

    authored = _author_over_mcp(dna_dir)

    with _rest(dna_dir) as c:
        listed = c.get("/v1/kinds", params={"tenant": _WID})
        assert listed.status_code == 200, listed.text
        rows = [k for k in listed.json()["kinds"] if k["kind"] == _KIND]
        assert rows, listed.json()
        row = rows[0]

        detail = c.get(f"/v1/kinds/{_KIND}", params={"tenant": _WID})
        assert detail.status_code == 200, detail.text
        body = detail.json()

    # The same INSTANCE — addressed by the name the MCP tool minted.
    assert row["name"] == authored["name"] == body["name"], (row, authored, body)
    # The same apiVersion — the string the MCP call minted, keyed by the registry
    # further down and published here.
    assert authored["namespace"] == row["namespace"], (authored, row)
    assert row["api_version"] == f"{authored['namespace']}/v1", row
    # The same SHAPE. This is the field the listing withholds and the detail
    # route exists to carry, and it is what a reviewer actually approves.
    assert body["schema"] == _SCHEMA, body
    # Authored by the MCP face, and identifiably so: the actor is that face's
    # own constant, which the REST face would never write (its sentinels are
    # ``rest:local`` / ``rest:unidentified``). A row assembled by anything but
    # the MCP call cannot carry it.
    assert row["proposed_by"] == UNIDENTIFIED_LOCAL_ACTOR, row
    assert UNIDENTIFIED_LOCAL_ACTOR != R._UNIDENTIFIED_LOCAL_ACTOR, (
        "the two faces' local sentinels collapsed into one string — this test "
        "can no longer tell which face stamped the proposer"
    )
    # …and inert, on both faces' vocabulary for it.
    assert row["approved"] is False and body["approved"] is False, (row, body)
    assert row["approved_by"] is None, row


def test_the_approved_document_carries_one_identity_from_each_acting_face(dna_dir):
    """The audit is the cross-face evidence: one instance, two actors, neither
    of which the other face could have produced.

    ``proposed_by`` is the MCP face's server-resolved actor and ``approved_by``
    is the REST face's VERIFIED caller. A single instance holding both is a
    stronger statement than either face's own suite can make — each of those can
    only show that its own stamp is right."""
    from dna_cli._mcp_auth import UNIDENTIFIED_LOCAL_ACTOR

    _author_over_mcp(dna_dir)
    approved = _approve_over_rest(dna_dir)
    assert approved.status_code == 200, approved.text

    async def probe(live):
        raw = await live.kernel.get_instance(
            _SCOPE, "KindDefinition", approved.json()["name"])
        return dict((raw or {}).get("spec") or {})

    # On the STORED instance, through a kernel that did not write it: a response
    # body can be right about an instance that is wrong.
    spec = _on_fresh_kernel(dna_dir, probe)
    assert spec["proposed_by"] == UNIDENTIFIED_LOCAL_ACTOR, spec
    assert spec["approved_by"] == _HUMAN["email"], spec
    assert spec["proposed_at"] and spec["approved_at"], spec
    # The shape the agent declared survived the second act untouched — approval
    # confers effect on the proposal, it does not restate it.
    assert spec["schema"] == _SCHEMA, spec


# ── 2. the central one: approval is what confers schema validation ────────


def _violating_document(api_version: str) -> dict:
    """The one raw instance both halves of the contrast write, byte for byte.

    ``api_version`` is the Kind's OWN — ``<assigned-namespace>/v1``, the string
    the MCP call minted. It has to be, and the first draft of this test learned
    it the hard way: the write pipeline resolves the port to validate against
    from ``(kind, the instance's own apiVersion, scope)``, so an instance
    carrying any OTHER apiVersion resolves to no port and is never validated,
    approved or not. Written that way the "accepted before approval" half would
    have been true for the wrong reason — accepted because the apiVersion
    matched nothing, not because the Kind was unregistered — and the
    "refused after" half was RED for the same reason.

    So both halves carry the apiVersion of the very Kind under test. Before
    approval nothing answers to it; after approval the registry does."""
    return {
        "apiVersion": api_version,
        "kind": _KIND,
        "metadata": {"name": _VIOLATING_DOC},
        "spec": dict(_VIOLATING),
    }


def _probe_before(dna_dir, api_version: str):
    """What the kernel face can do with the Kind BEFORE a human approved it."""

    async def probe(live):
        from dna.application.instances import UnknownKindError, write_instance_impl

        out: dict = {"port": live.kernel.kind_port_for(_KIND, scope=_SCOPE)}
        # The generic SDK write door — the core the MCP ``write_instance`` tool
        # and the CLI both delegate to. It resolves the Kind through the
        # registry, so an unapproved Kind is not merely unvalidated here: it does
        # not exist.
        with pytest.raises(UnknownKindError) as unknown:
            await write_instance_impl(
                live, kind=_KIND, name=_VIOLATING_DOC, spec=dict(_VIOLATING),
                scope=_SCOPE,
            )
        out["generic_refusal"] = str(unknown.value)
        # …and the kernel write itself, which is where "accepted unvalidated" is
        # literally true: no registered port ⇒ no schema to enforce, and no
        # storage descriptor to route by.
        out["version"] = await live.kernel.write_instance(
            _SCOPE, _KIND, _VIOLATING_DOC, _violating_document(api_version),
        )
        return out

    return _on_fresh_kernel(dna_dir, probe)


def _probe_after(dna_dir, api_version: str):
    """…and after. The violating write is the SAME call."""

    async def probe(live):
        from dna.kernel.protocols import SpecValidationError

        from dna.application.instances import get_instance_impl, write_instance_impl

        out: dict = {"port": live.kernel.kind_port_for(_KIND, scope=_SCOPE)}
        with pytest.raises(SpecValidationError) as vetoed:
            await live.kernel.write_instance(
                _SCOPE, _KIND, _VIOLATING_DOC, _violating_document(api_version),
            )
        out["veto"] = str(vetoed.value)
        out["written"] = await write_instance_impl(
            live, kind=_KIND, name=_CONFORMING_DOC, spec=dict(_CONFORMING),
            scope=_SCOPE,
        )
        out["read_back"] = await get_instance_impl(
            live, kind=_KIND, name=_CONFORMING_DOC, scope=_SCOPE,
        )
        return out

    return _on_fresh_kernel(dna_dir, probe)


def test_approval_is_what_gives_the_kind_schema_validation_and_storage_routing(
    dna_dir,
):
    """The whole branch, stated as one measurable fact.

    The same violating write is ACCEPTED before approval and REFUSED after —
    that pair is the proof that "unapproved has no effect" is the absence of a
    mechanism and not a promise. Approval is the ONLY thing that changes between
    the two probes; both run on kernels booted fresh over the same directory.

    The filesystem is asserted alongside the return values, because routing is
    the half no return value can show: before approval the instance lands
    unrouted at the root of the scope (nothing declares where a ``Contrato``
    goes), and after approval a conforming one lands in the container the
    approved ``KindDefinition`` declares."""
    authored = _author_over_mcp(dna_dir)
    api_version = f"{authored['namespace']}/v1"

    # ── before ────────────────────────────────────────────────────────────
    before_files = _scope_files(dna_dir)
    before = _probe_before(dna_dir, api_version)
    assert before["port"] is None, before["port"]
    assert _KIND in before["generic_refusal"], before["generic_refusal"]
    assert "not registered" in before["generic_refusal"], before["generic_refusal"]
    # Accepted — the adapter answered with a version for an instance its own
    # declared schema forbids.
    assert before["version"] is not None, before

    unrouted = _written_document_file(dna_dir, before_files)
    assert unrouted.parent.name != _CONTAINER, (
        f"the pre-approval write was routed into {_CONTAINER!r} — routing is "
        f"supposed to be one of the things approval confers: {unrouted}"
    )
    assert unrouted.parent == dna_dir / _SCOPE, unrouted

    # ── the single act that separates the two halves ──────────────────────
    approved = _approve_over_rest(dna_dir)
    assert approved.status_code == 200, approved.text
    assert approved.json()["approved"] is True, approved.text

    # ── after ─────────────────────────────────────────────────────────────
    midpoint = _scope_files(dna_dir)
    after = _probe_after(dna_dir, api_version)

    # The kernel took the Kind — and it took the one the AGENT declared: the
    # registry's key is the apiVersion the MCP call minted, and the port's
    # schema is the shape the agent typed.
    port = after["port"]
    assert port is not None, "approval did not register the Kind"
    assert port.api_version == api_version, port.api_version
    assert port.schema() == _SCHEMA, port.schema()

    # The byte-identical write is now refused, and refused BY THE SCHEMA — a
    # bare exception-type assertion would also pass on a Kind that refuses
    # everything, or on a veto raised for an unrelated reason.
    assert "schema validation failed" in after["veto"], after["veto"]
    assert "titulo" in after["veto"], after["veto"]

    # …and the conforming instance is written, routed, and read back — the
    # brief's "an instance of it can now be written and read back", wired.
    assert after["written"]["api_version"] == api_version, after["written"]
    assert after["read_back"]["instance"]["spec"] == _CONFORMING, after["read_back"]

    routed = _written_document_file(dna_dir, midpoint)
    assert routed.parent.name == _CONTAINER, (
        f"an approved Kind's instance did not land in the container its own "
        f"KindDefinition declares ({_CONTAINER!r}): {routed}"
    )
    assert routed.parent.parent == dna_dir / _SCOPE, routed


# ── 3. …and the agent can then USE it, on the face it authored it from ────


def _mcp_write(dna_dir, kind: str, name: str, spec: dict) -> dict:
    """``write_instance`` over MCP, unmasked — for the half that must SUCCEED."""
    return _mcp(dna_dir, "write_instance", {
        "kind": kind, "name": name, "spec": dict(spec), "scope": _SCOPE,
    })


def _mcp_generic_write_of(
    dna_dir, kind: str, name: str, spec: dict,
) -> tuple[str, str]:
    """``write_instance`` over MCP → ``(outcome, message)``, no masking."""
    from fastmcp.exceptions import ToolError

    try:
        _mcp_write(dna_dir, kind, name, spec)
    except ToolError as exc:
        return ("refused", str(exc))
    return ("accepted", "")


def test_the_kind_the_agent_authored_is_usable_by_the_agent_that_authored_it(
    dna_dir,
):
    """The point of the whole feature, on the face the agent actually holds.

    The kernel face already proves that approval confers schema validation and
    storage routing. That is the mechanism; this is the DELIVERY. An agent
    authors a Kind over MCP, a human approves it, and the agent then reaches
    for it through the SAME generic tools it uses for every other Kind —
    ``list_kinds`` to find it, ``write_instance`` to use it. If those tools
    cannot see it, the feature has a working engine and no wheels.

    Three assertions, none of which stands in for another:

    * the CATALOG carries it, under the apiVersion the authoring call minted —
      an agent that cannot discover a Kind cannot use it, and a catalog entry
      under the wrong apiVersion would send every later exact-resolution call
      to nothing;
    * a CONFORMING instance is written and lands in the container the approved
      ``KindDefinition`` declares (read off the filesystem — routing is
      invisible in the response);
    * a VIOLATING one is REFUSED, by the schema. Acceptance alone would also be
      produced by a tool that resolved no port at all and skipped validation,
      which is exactly the failure mode this file's ``_violating_document``
      docstring records; the refusal is what proves the port was resolved and
      the agent's own declared shape is what enforced it."""
    authored = _author_over_mcp(dna_dir)
    api_version = f"{authored['namespace']}/v1"
    assert _approve_over_rest(dna_dir).status_code == 200

    catalog = {k["kind"]: k for k in
               _mcp(dna_dir, "list_kinds", {"scope": _SCOPE})["kinds"]}
    assert _KIND in catalog, (
        f"the agent cannot discover the Kind it authored and a human approved: "
        f"{sorted(catalog)}"
    )
    assert catalog[_KIND]["api_version"] == api_version, catalog[_KIND]

    before = _scope_files(dna_dir)
    written = _mcp_write(dna_dir, _KIND, _CONFORMING_DOC, _CONFORMING)
    assert written["api_version"] == api_version, written

    routed = _written_document_file(dna_dir, before)
    assert routed.parent.name == _CONTAINER, (
        f"an MCP-written instance of the approved Kind did not land in the "
        f"container its own KindDefinition declares ({_CONTAINER!r}): {routed}"
    )

    outcome, message = _mcp_generic_write_of(dna_dir, _KIND, _VIOLATING_DOC, _VIOLATING)
    assert outcome == "refused", (
        "the generic MCP write accepted an instance its Kind's own schema "
        "forbids — the tool resolved the Kind but nothing validated against it"
    )
    assert "schema validation failed" in message, message
    assert "titulo" in message, message


# ── 4. the discriminator: whatever that face does, approval does not decide it ──


def _seed_approved_kind_document(dna_dir, *, kind: str, namespace: str) -> str:
    """An ALREADY-APPROVED ``KindDefinition``, written straight through the
    kernel — the shape an operator has been able to seed since long before the
    authoring door existed, and one that never met the approval gate at all."""
    name = f"{namespace}--{kind}"

    async def seed(live):
        await live.kernel.write_instance(
            _SCOPE, "KindDefinition", name,
            {"apiVersion": "github.com/ruinosus/dna/core/v1",
             "kind": "KindDefinition", "metadata": {"name": name},
             "spec": {"target_api_version": f"{namespace}/v1",
                      "target_kind": kind,
                      "alias": f"{namespace.replace('.', '-')}-{kind.lower()}",
                      "origin": namespace,
                      "schema": _SCHEMA,
                      "approved_by": "operator@example.com",
                      "approved_at": "2020-01-01T00:00:00+00:00",
                      "storage": {"type": "yaml",
                                  "container": f"{kind.lower()}s"}}},
        )
        return name

    return _on_fresh_kernel(dna_dir, seed)


def _mcp_generic_write(dna_dir, kind: str) -> tuple[str, str]:
    """``write_instance`` over MCP for ``kind`` → ``(outcome, message)``.

    The Kind name is MASKED out of the message so two answers about two
    different Kinds are comparable as strings — the comparison is about which
    MECHANISM answered, not about which name it echoed back."""
    from fastmcp.exceptions import ToolError

    try:
        _mcp(dna_dir, "write_instance", {
            "kind": kind, "name": f"{kind.lower()}-1",
            "spec": dict(_CONFORMING), "scope": _SCOPE,
        })
    except ToolError as exc:
        return ("refused", str(exc).replace(kind, "<kind>"))
    return ("accepted", "")


def test_the_generic_mcp_document_face_does_not_discriminate_on_approval(dna_dir):
    """A DISCRIMINATOR, not a bug pinned as behaviour — and it survived the fix.

    When this was written the MCP face's generic ``write_instance`` could not
    use the approved tenant Kind, and the tempting conclusion — that the
    approval gate had not finished its job — was wrong: the lazy boot path
    registered no per-scope declarative Kind at all, including one an operator
    seeded already-approved, which never met the authoring door or the gate.

    So the property asserted is the comparison, never the outcome: whatever that
    face does with a per-scope Kind, approval is not what decides it. Both
    outcomes agreed when both were refused and agree now that both are accepted
    — this test did not change when the boot path was fixed, which is precisely
    what keeps it from having written a bug down as a requirement. If they ever
    DIVERGE, the approval gate has grown a second, unintended meaning on a face
    that is not supposed to have one."""
    _author_over_mcp(dna_dir)
    assert _approve_over_rest(dna_dir).status_code == 200

    seeded = _seed_approved_kind_document(
        dna_dir, kind="Curada", namespace="curada.example")

    async def control(live):
        return (
            await live.kernel.get_instance(_SCOPE, "KindDefinition", seeded),
            live.kernel.kind_port_for("Curada", scope=_SCOPE),
        )

    # The control has to be real, or the comparison below is between one honest
    # answer and one about a Kind that was never there.
    instance, port = _on_fresh_kernel(dna_dir, control)
    assert instance, seeded
    assert port is not None, (
        "the operator-seeded approved Kind is not registered on a fresh kernel "
        "— it is not a usable control for what the MCP face should see"
    )

    # …and so does the FACE. Without this line the comparison below is
    # satisfiable by an MCP server that answers everything with an error — two
    # identical failures are trivially identical, which is the shape of a test
    # that passes while measuring nothing.
    catalog = {k["kind"] for k in
               _mcp(dna_dir, "list_kinds", {"scope": _SCOPE})["kinds"]}
    assert catalog, "the MCP face advertised no Kinds at all — nothing below means anything"

    approved_by_the_gate = _mcp_generic_write(dna_dir, _KIND)
    approved_by_an_operator = _mcp_generic_write(dna_dir, "Curada")

    assert (_KIND in catalog) == ("Curada" in catalog), (
        f"the MCP catalog carries one of the two approved Kinds and not the "
        f"other: {sorted(catalog)}"
    )
    # Compared in FULL — outcome and refusal text, with the Kind name masked.
    # Comparing only the label would let one be refused by the registry and the
    # other by, say, a quota gate while the test called them the same answer.
    assert approved_by_the_gate == approved_by_an_operator, (
        f"the generic MCP instance face treats a gate-approved Kind differently "
        f"from an operator-approved one — approval has acquired a meaning on a "
        f"face that has no approval gate:\n"
        f"  gate-approved:     {approved_by_the_gate}\n"
        f"  operator-approved: {approved_by_an_operator}"
    )
