"""Story ``s-mcp-generic-document-tools`` — generic, registry-driven document
tools on the MCP face.

The gap: the MCP face ships 21 HAND-WRITTEN tools and never loops over the Kind
registry, so of the 76 registered Kinds only the handful someone hand-wrote a
tool for is reachable by an agent. The CLI already solved this generically
in-process (``dna_cli._ctx._LocalDocs`` → ``dna doc``); it was simply never
served. These four tools close that: ``list_kinds`` / ``list_documents`` /
``get_document`` / ``write_document``, resolved from the registry AT CALL TIME.

Four properties:

1. **the pure core is registry-driven** — the Kind catalog, the metering family
   and the bootstrap-write refusal are all DERIVED from the registered
   ``KindPort``, never from a hand-typed list of Kind names;

2. **the payoff** — a Kind with NO hand-written MCP tool (``Copilot`` /
   ``MCPFederation`` / ``ModelProfile``) is listable, readable and writable over
   the face, against a real scope;

3. **the write fails CLOSED** — the bootstrap Kinds (``KindDefinition`` /
   ``LayerPolicy`` / ``Genome``, i.e. exactly the ports the kernel marks
   ``is_overlayable=False``) are refused with a message that names the Kind and
   the reason, in the CORE so no face can reopen the hole;

4. **the metering cannot be gamed** — the quota family is derived from the
   TARGET KIND, and a generic write requires the tier to grant ``write`` for
   that family's access mode. A caller whose tier grants ``sdlc_mode: read``
   cannot reach an SDLC write through the generic tool, and a tier that declares
   no ``definitions_mode`` cannot write definitions at all (fail closed).
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

from dna.application import documents as D
from dna_cli import _mcp_quota as Q

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_ISSUER = "https://dna.test/"
_AUDIENCE = "dna-mcp"

# A Kind with NO hand-written MCP tool, that the example scope already carries.
_UNSERVED_KIND = "Copilot"
_UNSERVED_DOC = "memory-copilot"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _live(dna_dir):
    from dna_cli import _mcp_server as M

    return M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))


# ── 1. the pure core is registry-driven ─────────────────────────────────────


def test_bootstrap_kinds_are_derived_from_the_registry(dna_dir):
    """The generic write's refusal set is DERIVED (``KindPort.is_overlayable``
    is False), not a hand-typed list of names — and today that derivation is
    exactly the three bootstrap Kinds. A new bootstrap Kind declaring
    ``is_overlayable: false`` in its descriptor is refused with no code change;
    this assertion is the ratchet that makes such an arrival visible."""
    async def go():
        live = await _live(dna_dir)
        return D.bootstrap_kinds(live.kernel)

    assert asyncio.run(go()) == {"Genome", "LayerPolicy", "KindDefinition"}


def test_family_for_kind_is_derived_from_the_ports_api_version(dna_dir):
    """The quota family comes from the TARGET KIND's registered port — the
    caller cannot choose it."""
    async def go():
        live = await _live(dna_dir)
        k = live.kernel
        return {
            name: D.family_for_kind(D.resolve_kind_port(k, name))
            for name in ("Story", "Issue", "TestGuide", "Engram", "Research",
                         "Copilot", "Agent", "ModelProfile")
        }

    fams = asyncio.run(go())
    assert fams["Story"] == "sdlc"
    assert fams["Issue"] == "sdlc"
    assert fams["TestGuide"] == "sdlc"
    assert fams["Engram"] == "memory"
    assert fams["Research"] == "memory"
    # everything DNA stores that is not board or memory is `definitions`.
    assert fams["Copilot"] == "definitions"
    assert fams["Agent"] == "definitions"
    assert fams["ModelProfile"] == "definitions"
    # an unregistered Kind meters as `definitions` (so the probe is METERED
    # before the unknown-Kind refusal, rather than free).
    assert D.family_for_kind(None) == "definitions"


def test_unknown_kind_is_refused(dna_dir):
    async def go():
        live = await _live(dna_dir)
        with pytest.raises(D.UnknownKindError, match="Nope"):
            await D.list_documents_impl(live, kind="Nope", scope=_SCOPE)

    asyncio.run(go())


class _StubPort:
    def __init__(self, kind: str, api_version: str):
        self.kind = kind
        self.api_version = api_version
        self.alias = f"{api_version.split('/')[-2]}-{kind.lower()}"
        self.is_overlayable = True


class _StubKernel:
    def __init__(self, *ports):
        self._ports = list(ports)

    def kind_ports(self):
        return list(self._ports)


def test_ambiguous_bare_kind_name_is_refused_without_api_version():
    """A Kind NAME can be registered under two apiVersions — a per-scope
    ``KindDefinition`` shadowing a builtin is the live case (i-195). The kernel's
    own ``kind_port_for`` resolves such a name deterministically, which is right
    for a CLI and wrong here: the resolved port decides BOTH what gets written
    and which family the call is metered under, so guessing would let the
    registry pick a caller's quota family for them. Fail closed and ask."""
    kernel = _StubKernel(
        _StubPort("Doc", "github.com/ruinosus/dna/doc/v1"),
        _StubPort("Doc", "acme.example/v1"),
        _StubPort("Story", "github.com/ruinosus/dna/sdlc/v1"),
    )
    with pytest.raises(D.AmbiguousKindError, match="api_version"):
        D.resolve_kind_port(kernel, "Doc")
    # …and resolves exactly once disambiguated.
    port = D.resolve_kind_port(kernel, "Doc", api_version="acme.example/v1")
    assert port.api_version == "acme.example/v1"
    # an api_version that names no registered port is an unknown Kind, not a
    # silent fallback to the other one.
    with pytest.raises(D.UnknownKindError):
        D.resolve_kind_port(kernel, "Doc", api_version="nope/v1")


def test_list_kinds_reports_the_whole_registry_when_no_plan_filters_it(dna_dir):
    async def go():
        live = await _live(dna_dir)
        return await D.list_kinds_impl(live, scope=_SCOPE)

    out = asyncio.run(go())
    names = {k["kind"] for k in out["kinds"]}
    assert out["filtered_by_plan"] is False
    assert len(names) > 60  # the whole registry (76 today)
    assert _UNSERVED_KIND in names
    entry = next(k for k in out["kinds"] if k["kind"] == _UNSERVED_KIND)
    assert entry["family"] == "definitions"
    assert entry["writable"] is True
    assert entry["write_refusal"] is None
    boot = next(k for k in out["kinds"] if k["kind"] == "LayerPolicy")
    assert boot["writable"] is False
    assert "bootstrap" in boot["write_refusal"].lower()


def test_list_kinds_reports_only_what_the_plan_unlocks(dna_dir):
    """An honest, shorter catalog beats an inflated one: a Kind the caller's plan
    cannot act on is a 403 waiting to happen (and a wasted quota unit)."""
    async def go():
        live = await _live(dna_dir)
        return await D.list_kinds_impl(live, scope=_SCOPE, families=["memory"])

    out = asyncio.run(go())
    assert out["filtered_by_plan"] is True
    assert {k["family"] for k in out["kinds"]} == {"memory"}
    assert {k["kind"] for k in out["kinds"]} == {"Engram", "Research", "Evidence"}


# ── 2. the payoff: a Kind with no hand-written tool ─────────────────────────


def test_list_and_read_a_kind_with_no_hand_written_tool(dna_dir):
    async def go():
        live = await _live(dna_dir)
        listed = await D.list_documents_impl(live, kind=_UNSERVED_KIND, scope=_SCOPE)
        got = await D.get_document_impl(
            live, kind=_UNSERVED_KIND, name=_UNSERVED_DOC, scope=_SCOPE)
        return listed, got

    listed, got = asyncio.run(go())
    assert listed["kind"] == _UNSERVED_KIND
    assert _UNSERVED_DOC in {d["name"] for d in listed["documents"]}
    assert got["name"] == _UNSERVED_DOC
    assert got["document"]["kind"] == _UNSERVED_KIND
    assert got["document"]["spec"]  # the real stored spec, not a stub


def test_write_then_read_back_a_kind_with_no_hand_written_tool(dna_dir):
    """``ModelProfile`` has no hand-written MCP tool AND no document in the
    fixture — the generic write creates it and the generic read finds it."""
    async def go():
        live = await _live(dna_dir)
        res = await D.write_document_impl(
            live, kind="ModelProfile", name="gpt-x", scope=_SCOPE,
            spec={"model_id": "gpt-x", "provider": "openai"},
        )
        got = await D.get_document_impl(
            live, kind="ModelProfile", name="gpt-x", scope=_SCOPE)
        return res, got

    res, got = asyncio.run(go())
    assert res["kind"] == "ModelProfile" and res["name"] == "gpt-x"
    assert got["document"]["spec"]["model_id"] == "gpt-x"
    # the apiVersion was taken from the registered port, never from the caller.
    assert got["document"]["apiVersion"] == "github.com/ruinosus/dna/modelreg/v1"


def test_get_document_missing_name_raises(dna_dir):
    async def go():
        live = await _live(dna_dir)
        with pytest.raises(LookupError):
            await D.get_document_impl(
                live, kind=_UNSERVED_KIND, name="nope", scope=_SCOPE)

    asyncio.run(go())


# ── 3. the generic write fails CLOSED on the bootstrap Kinds ────────────────


@pytest.mark.parametrize("kind", ["KindDefinition", "LayerPolicy", "Genome"])
def test_generic_write_refuses_a_bootstrap_kind(dna_dir, kind):
    """Writing one of these changes what the system IS for that scope, so the
    generic tool refuses — in the CORE, for every face, with a message naming
    the Kind and the reason. And it writes NOTHING."""
    async def go():
        live = await _live(dna_dir)
        with pytest.raises(D.BootstrapKindWriteRefused) as ei:
            await D.write_document_impl(
                live, kind=kind, name="pwned", scope=_SCOPE, spec={})
        assert kind in str(ei.value)
        # the refusal is honest about WHY and about the supported path.
        assert "bootstrap" in str(ei.value).lower()
        # nothing landed.
        return await live.kernel.get_document(_SCOPE, kind, "pwned")

    assert asyncio.run(go()) is None


def test_bootstrap_kinds_stay_READABLE(dna_dir):
    """The refusal is on the WRITE only — an agent must still be able to read the
    Genome that governs the scope it is working in."""
    async def go():
        live = await _live(dna_dir)
        return await D.get_document_impl(
            live, kind="Genome", name="concierge", scope=_SCOPE)

    got = asyncio.run(go())
    assert got["kind"] == "Genome"


# ── 4. the four tools over the MCP face (unauthenticated / stdio parity) ────


def _call(server, tool, args):
    from fastmcp import Client

    async def go():
        async with Client(server) as client:
            return await client.call_tool(tool, args)

    return asyncio.run(go())


def test_the_four_tools_are_registered(dna_dir):
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))

    async def go():
        async with Client(server) as client:
            return {t.name for t in await client.list_tools()}

    names = asyncio.run(go())
    assert {"list_kinds", "list_documents", "get_document",
            "write_document"} <= names


def test_face_lists_and_reads_an_unserved_kind(dna_dir):
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    listed = _call(server, "list_documents",
                   {"kind": _UNSERVED_KIND, "scope": _SCOPE})
    assert _UNSERVED_DOC in {
        d["name"] for d in listed.structured_content["documents"]}
    got = _call(server, "get_document",
                {"kind": _UNSERVED_KIND, "name": _UNSERVED_DOC, "scope": _SCOPE})
    assert got.structured_content["document"]["kind"] == _UNSERVED_KIND


def test_face_refuses_a_bootstrap_write(dna_dir):
    pytest.importorskip("fastmcp")
    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir))
    with pytest.raises(Exception) as ei:  # noqa: PT011 — FastMCP ToolError
        _call(server, "write_document",
              {"kind": "LayerPolicy", "name": "pwned", "spec": {},
               "scope": _SCOPE})
    assert "bootstrap" in str(ei.value).lower()


# ── 5. metering: the family is the TARGET KIND's, and a write needs `write` ──


def _reset_store() -> None:
    Q.DEFAULT_STORE.reset()


def _tier_doc(tier_id: str, *, families: list[str], sdlc_mode: str,
              memory_mode: str = "read",
              definitions_mode: str | None = None) -> dict:
    spec = {
        "tier_id": tier_id,
        "display_name": tier_id.title(),
        "price_usd_month": 0,
        "calls_per_day": 10000,
        "rate_per_sec": 100,
        "max_tenants": 1,
        "feature_families": families,
        "memory_mode": memory_mode,
        "sdlc_mode": sdlc_mode,
    }
    if definitions_mode is not None:
        spec["definitions_mode"] = definitions_mode
    return {
        "apiVersion": "github.com/ruinosus/dna/cloud/v1",
        "kind": "PricingPlan",
        "metadata": {"name": tier_id},
        "spec": spec,
    }


async def _seed_tiers(dna_dir, **overrides) -> None:
    from dna_cli import _mcp_server as M

    live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
    await live.kernel.write_document(
        "_lib", "PricingPlan", "free",
        _tier_doc("free", families=["definitions", "sdlc", "memory"],
                  sdlc_mode="read"))
    await live.kernel.write_document(
        "_lib", "PricingPlan", "pro",
        _tier_doc("pro", families=["definitions", "sdlc", "memory", "emit"],
                  sdlc_mode="write", memory_mode="write",
                  definitions_mode=overrides.get("pro_definitions_mode")))


def _verifier_and_mint():
    from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

    kp = RSAKeyPair.generate()
    verifier = JWTVerifier(public_key=kp.public_key, issuer=_ISSUER,
                           audience=_AUDIENCE)

    def mint(*, tenant: str | None, plan: str | None):
        claims: dict = {}
        if tenant:
            claims["tenant"] = tenant
        if plan:
            claims["plan"] = plan
        return kp.create_token(
            issuer=_ISSUER, audience=_AUDIENCE, subject="user-1",
            scopes=["dna.read"], additional_claims=claims,
        )

    return verifier, mint


def test_generic_write_of_an_sdlc_kind_is_denied_on_a_read_tier(dna_dir, http_server):
    """THE anti-gaming property: a Free tier grants ``sdlc_mode: read``. Reaching
    an SDLC WRITE through the GENERIC tool must be denied by exactly the same
    gate ``create_story`` honors — because the family is derived from the target
    Kind, not chosen by the caller. The generic READ of the same Kind stays
    allowed."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    _reset_store()
    asyncio.run(_seed_tiers(dna_dir))
    verifier, mint = _verifier_and_mint()
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="free")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            # the READ half of the same family is allowed.
            listed = await client.call_tool(
                "list_documents", {"kind": "Story", "scope": _SCOPE})
            assert "documents" in listed.structured_content
            with pytest.raises(Exception) as ei:  # noqa: PT011
                await client.call_tool("write_document", {
                    "kind": "Story", "name": "s-smuggled",
                    "spec": {"title": "smuggled in through a generic tool"},
                    "scope": _SCOPE})
            assert "sdlc_mode" in str(ei.value)

    with http_server(server) as url:
        asyncio.run(go(url))
    # and nothing was written.
    assert not list((dna_dir / _SCOPE).rglob("s-smuggled*"))


def test_generic_write_of_an_sdlc_kind_is_allowed_on_a_write_tier(dna_dir, http_server):
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    _reset_store()
    asyncio.run(_seed_tiers(dna_dir))
    verifier, mint = _verifier_and_mint()
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="pro")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            out = await client.call_tool("write_document", {
                "kind": "Story", "name": "s-written-generically",
                "spec": {"title": "t", "description": "d", "status": "todo",
                         "feature": "f-dna-mcp-server"},
                "scope": _SCOPE})
            assert out.structured_content["name"] == "s-written-generically"

    with http_server(server) as url:
        asyncio.run(go(url))


def test_definitions_write_needs_an_explicitly_granted_definitions_mode(
    dna_dir, http_server,
):
    """There is no hand-written definitions WRITE on the MCP face, so the generic
    one is genuinely new capability — and gets the same uniform rule: a metered
    write needs ``<family>_mode: write``. A plan that never declared
    ``definitions_mode`` grants nothing (the Kind's schema default is ``none``),
    so the write is refused, and the refusal NAMES the cap."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    _reset_store()
    asyncio.run(_seed_tiers(dna_dir))  # pro declares NO definitions_mode
    verifier, mint = _verifier_and_mint()
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="pro")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            # the READ is fine (the family gate is the read gate).
            await client.call_tool(
                "list_documents", {"kind": _UNSERVED_KIND, "scope": _SCOPE})
            with pytest.raises(Exception) as ei:  # noqa: PT011
                await client.call_tool("write_document", {
                    "kind": "ModelProfile", "name": "sneaky",
                    "spec": {"model_id": "sneaky", "provider": "x"}, "scope": _SCOPE})
            assert "definitions_mode" in str(ei.value)

    with http_server(server) as url:
        asyncio.run(go(url))


def test_definitions_write_allowed_once_the_plan_grants_it(dna_dir, http_server):
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    _reset_store()
    asyncio.run(_seed_tiers(dna_dir, pro_definitions_mode="write"))
    verifier, mint = _verifier_and_mint()
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="pro")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            out = await client.call_tool("write_document", {
                "kind": "ModelProfile", "name": "granted",
                "spec": {"model_id": "sneaky", "provider": "x"}, "scope": _SCOPE})
            assert out.structured_content["name"] == "granted"

    with http_server(server) as url:
        asyncio.run(go(url))


def test_list_kinds_over_the_face_is_filtered_by_the_plan(dna_dir, http_server):
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    _reset_store()

    async def seed():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        await live.kernel.write_document(
            "_lib", "PricingPlan", "free",
            _tier_doc("free", families=["definitions"], sdlc_mode="read"))

    asyncio.run(seed())
    verifier, mint = _verifier_and_mint()
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir), auth=verifier)
    token = mint(tenant="acme", plan="free")

    async def go(url):
        async with Client(url, auth=BearerAuth(token)) as client:
            out = await client.call_tool("list_kinds", {"scope": _SCOPE})
            data = out.structured_content
            assert data["filtered_by_plan"] is True
            fams = {k["family"] for k in data["kinds"]}
            assert fams == {"definitions"}
            assert "Story" not in {k["kind"] for k in data["kinds"]}

    with http_server(server) as url:
        asyncio.run(go(url))


# ── 6. no new bypass: scope binding still denies a cross-workspace read ─────


def test_generic_tools_honor_cross_workspace_scope_binding(dna_dir, http_server,
                                                           monkeypatch):
    """The generic tools go through the SAME ``_guard`` seam: an authenticated
    caller bound to workspace B naming workspace A's scope is denied, exactly as
    ``list_agents`` is."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client
    from fastmcp.client.auth import BearerAuth

    from dna_cli import _mcp_server as M

    _reset_store()
    ws_vendor, ws_outside = "ws-vendor", "ws-outside"

    async def seed():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        for ws, email, oid in ((ws_vendor, "alice@a.com", "oid-alice"),
                               (ws_outside, "bob@b.com", "oid-bob")):
            name = f"{ws}--{email.replace('@', '-at-').replace('.', '-')}"
            await live.kernel.write_document("_lib", "WorkspaceMembership", name, {
                "apiVersion": "github.com/ruinosus/dna/tenant/v1",
                "kind": "WorkspaceMembership",
                "metadata": {"name": name},
                "spec": {"workspace_id": ws, "identity_email": email,
                         "identity_oid": oid, "role": "owner",
                         "status": "active"},
            })

    asyncio.run(seed())
    from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

    kp = RSAKeyPair.generate()
    verifier = JWTVerifier(public_key=kp.public_key, issuer=_ISSUER,
                           audience=_AUDIENCE)
    bob = kp.create_token(
        issuer=_ISSUER, audience=_AUDIENCE, subject="oid-bob",
        scopes=["dna.read"],
        additional_claims={"oid": "oid-bob", "email": "bob@b.com"})
    monkeypatch.setenv("DNA_VENDOR_WORKSPACE", ws_vendor)
    server = M.build_server(scope=_SCOPE, base_dir=str(dna_dir), auth=verifier)

    async def go(url):
        async with Client(url, auth=BearerAuth(bob)) as client:
            for tool, args in (
                ("list_kinds", {"scope": _SCOPE}),
                ("list_documents", {"kind": _UNSERVED_KIND, "scope": _SCOPE}),
                ("get_document", {"kind": _UNSERVED_KIND,
                                  "name": _UNSERVED_DOC, "scope": _SCOPE}),
                ("write_document", {"kind": "ModelProfile", "name": "x",
                                    "spec": {}, "scope": _SCOPE}),
            ):
                with pytest.raises(Exception) as ei:  # noqa: PT011
                    await client.call_tool(tool, args)
                assert "cross-workspace" in str(ei.value), (tool, str(ei.value))

    with http_server(server) as url:
        asyncio.run(go(url))
