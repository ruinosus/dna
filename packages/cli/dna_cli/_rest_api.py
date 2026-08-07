"""``dna_cli._rest_api`` — the DNA **REST read-API face** (server).

The THIRD face of DNA serving runtimes, and the correct HTTP boundary for a WEB
app (the DNA Cloud portal). It is a sibling of the MCP server, NOT a replacement:

    MCP  — a stateful, long-lived session protocol for AI clients (Claude
           Code/Desktop, Cursor, Copilot). A client opens ONE session and keeps
           it. Opening an MCP session per web page render is the wrong pattern —
           fragile, off-label.
    REST — a normal request/response HTTP API. The portal is a Next.js web app;
           each page render is a stateless GET. This face is exactly that: a thin
           HTTP surface a browser/BFF calls with a ``tenant`` query param today,
           an OAuth bearer later.

**One core, three faces.** This module does ZERO business logic of its own — it
imports and calls the SAME ``*_impl`` use-cases from the CORE application layer
(``dna.application``: ``list_agents_impl`` / ``compose_prompt_impl`` /
``list_tools_impl`` / ``recall_impl``), the same ones the MCP server delegates to,
booted by the SAME ``boot_live`` / ``LiveDna`` (adr-faces-reorg move #1: the
shared ``*_impl`` moved OUT of the CLI face INTO the core). The memory LIST +
DELETE endpoints (which have no MCP twin) query the memory Kind
(``Engram``) directly through the kernel, tenant-aware — mirroring exactly
how ``recall`` and the kernel query/delete paths already work. (Those two
REST-only memory cores are a tracked follow-up to also lift into the core.)

**Tenant isolation is load-bearing.** Every endpoint scopes to the ``tenant``
query param via the kernel's tenant-aware read/write paths — the SAME base +
own-overlay resolution recall uses, and the SAME overlay-only delete the local
docs facade uses. A tenant never reads or deletes another tenant's memory, and a
tenant can never delete the shared base (the filesystem source routes a
tenant-bound delete to that tenant's overlay layout, raising ``not_found`` for a
base doc).

``fastapi`` is imported **lazily** (optional ``dna-cli[api]`` extra) inside
:func:`build_app`, so the base install never carries it — ``import dna_cli`` (and
even importing this module) stays FastAPI-free.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from typing import Any

from dna.kernel.errors import DeleteRefused
from dna.memory.contradiction import WHEN_TO_CLAIM
from dna.tenancy.enforcement import enforcement_boot_message

logger = logging.getLogger(__name__)

# NOTE: no top-level ``import fastapi`` — it is optional. ``build_app`` imports it
# lazily so the base CLI/SDK install never requires it (guarded by a test).


# ── memory read/delete cores (no MCP twin — query the kernel directly) ──────
#
# The definitions + search endpoints reuse the MCP server's impls verbatim (see
# build_app). These two are the memory LIST + DELETE the portal needs and the
# MCP surface does not have; they go straight to the memory Kind through the
# kernel, tenant-aware, mirroring how recall/the local docs facade already read
# and delete.

_MEMORY_KIND = "Engram"

# ── who an audited write is attributed to, when the token says nothing ──────
#
# The REST twins of ``_mcp_auth``'s UNIDENTIFIED_{LOCAL,TOKEN}_ACTOR, and they
# carry THIS face's channel prefix for the reason those constants exist at all:
# ``mcp`` was recorded as an identity for so long that the board could not tell
# the founder from an agent, and reusing an ``mcp:`` label on the REST face
# would re-make the same conflation one layer over. See ``_actor_from_state``.

#: No token at all — a local / OSS self-host call (``--auth none``) whose
#: operator declared no ``DNA_PERSONAL_ID``.
_UNIDENTIFIED_LOCAL_ACTOR = "rest:local"

#: A VERIFIED token that carries no identity claim (a service token). Verified
#: yet anonymous — a different fact from "local", and worth its own label.
_UNIDENTIFIED_TOKEN_ACTOR = "rest:unidentified"


def _unidentified_actor(auth: str) -> str:
    """Which sentinel a request with NO identity claim is recorded as.

    Keyed on the FACT the two labels actually distinguish — was this request
    verified at all? — and ``auth="none"`` is that fact stated exactly: it is
    the one lane that requires no credential, so its caller is the local/OSS
    self-host operator and nobody else. Every other lane put a credential
    through verification before the route ran; a caller that got past it and
    still names nobody is verified-and-anonymous, which is what
    ``rest:unidentified`` means.

    It used to key on ``auth == "token"``, i.e. on ONE lane of "verified"
    spelled as a configuration name. Under ``--auth config`` a request that
    reached a route with no claims was therefore recorded as ``rest:local`` —
    the same mislabel that branch was written to end, one lane over, telling a
    reviewer that a remote federated caller was somebody at a laptop.
    Unreachable while ``guarded`` requires a verified token and the config
    middleware stashes claims for every request it lets through, so this is the
    branch being made honest rather than a live bug — but the next lane added
    inherits whichever rule is written here.

    Module-level and not a closure so it is testable on its own: the value is a
    string that lands in a PERSISTED audit field, and an unreachable branch that
    nothing can assert on is how the wrong sentinel survives a rename."""
    return (
        _UNIDENTIFIED_LOCAL_ACTOR if auth == "none" else _UNIDENTIFIED_TOKEN_ACTOR
    )


# ── MIF import bounds ───────────────────────────────────────────────────────
#
# The import route buffers and parses the whole bundle (dedupe + validation are
# whole-payload gates — that is what makes "no partial import" true), so the
# payload must be BOUNDED or a single upload can exhaust the container. Two
# independent bounds, because they fail differently: bytes caps the transport +
# JSON parse, doc count caps the write amplification (each doc can become TWO
# kernel writes under ``--as both``). Both answer 413 with the actual limit, and
# both are refused BEFORE anything is written. Overridable per deployment; a
# non-numeric/absent env keeps the default.


def _no_registry_scope_detail(why: str, exc: Exception) -> str:
    """The 503 body for a store whose namespace-registry scope was never
    provisioned — shared by BOTH Kind doors.

    Authoring READS the ``KindNamespace`` registry before it mints; approval
    reads it to check the caller owns the namespace the Kind was authored
    under. On a filesystem-backed source a missing scope directory raises
    ``FileNotFoundError``, so either door can meet this — and unmapped it
    surfaces as a 500 with a bare path in the log. It is a deployment
    PRECONDITION, not a bad request and not the caller's fault: 503, naming
    what is missing and how to satisfy it. One helper because two copies of an
    operator-facing message drift, and the half that drifts is the one the
    operator happens to hit."""
    return (
        f"the namespace registry scope (`_lib`) is not provisioned in this "
        f"store, so no Kind can be {why}. Provision the `_lib` scope (a Genome "
        f"manifest at <base>/_lib/manifest.yaml) and retry. Underlying: {exc}"
    )


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        val = int(raw) if raw else default
    except ValueError:
        return default
    return val if val > 0 else default


#: Max MIF bundle body, bytes (``DNA_API_MAX_IMPORT_BYTES``, default 10 MiB —
#: comfortably a large Claude export, far below a container's memory).
_MAX_IMPORT_BYTES = _int_env("DNA_API_MAX_IMPORT_BYTES", 10 * 1024 * 1024)

#: Max Memory Units per request (``DNA_API_MAX_IMPORT_DOCS``, default 5000).
_MAX_IMPORT_DOCS = _int_env("DNA_API_MAX_IMPORT_DOCS", 5000)


# ``list_memories_impl`` DELETED here (i-079) — this face now delegates to
# ``dna.application.list_memories_impl``, the one every other memory surface
# already used.
#
# It was a copy of the core's, and it had drifted in the way copies do. The
# measured divergence: the copy dropped a memory carrying ANY ``valid_to``,
# while the core and ``recall`` decide with ``currently_valid``, which KEEPS a
# memory whose expiry has not arrived. So a memory with a future expiry showed
# up under ``GET /v1/memories/personal`` — a sibling route of this same app,
# which already delegated — and was missing from ``GET /v1/memories``. One
# screen, two answers, and neither of them wrong on its own terms.
#
# Reachable today rather than in principle: ``dna.memory.interchange`` writes an
# imported ``temporal.validUntil`` through verbatim as ``spec.valid_to``, and
# ``import_memories_impl`` defaults to ``memory_scope="workspace"``.
#
# Three adjacent drifts go with it, each invisible until you looked for it: no
# ``affect`` (stored on every Engram, and what a memory card renders), no
# per-item ``personal`` flag (i-068), and a sort by NAME — which for a
# hash-prefixed slug is arbitrary — where every other memory surface answers
# newest-first.


#: The remedy in THIS lane, appended to the kernel's hard-delete refusal.
#:
#: ``dna.kernel.write.hard_delete`` names the verb, the CLI command, the MCP
#: tool and the Python function — everything except an HTTP path, and rightly
#: so: the kernel does not know a REST face exists, and a kernel message that
#: named a route would be a layer inversion that goes stale the first time the
#: route moves.
#:
#: But the caller reading a 403 here has none of those four doors — it has this
#: one — and until i-136 there was no fifth. That gap IS i-136: a refusal that
#: names a remedy the reader cannot perform sends them around the wall, and the
#: way around this particular wall is ``psql``. So the lane appends its own
#: door to the kernel's sentence, at the only layer that knows both.
_FORGET_LANE_HINT = (
    "In THIS (REST) lane that verb is `POST /v1/memories/{name}/forget`, with "
    "an optional `superseded_by` naming the memory that replaces this one."
)


class MemoryNotFound(Exception):
    """The requested memory is not in the tenant's OWN overlay (so this tenant
    cannot delete it) — mapped to HTTP 404 by the route.

    ⚠️ Unreachable through ``DELETE /v1/memories/{name}`` since i-130: the
    kernel refuses the hard delete before any store lookup happens, so the
    route answers 403 for a name that does not exist too. Kept because
    ``delete_memory_impl`` still raises it and the refusal is a policy that
    could be re-scoped; a 404 branch that stops being reachable is a fact about
    the ORDER of two guards, not a dead branch to delete quietly."""


async def delete_memory_impl(
    live: Any, name: str, scope: str | None = None, tenant: str | None = None
) -> dict[str, Any]:
    """Delete ONE memory from the tenant's OWN overlay — never base, never
    another tenant. This is the single write on the read-API, so it is guarded:

    * ``tenant`` set → the kernel's tenant-bound delete routes to that tenant's
      overlay layout. A doc that lives only in base (or in another tenant's
      overlay) is not present there, so the source raises ``not_found`` and this
      surfaces a 404 — the base/other-tenant memory is untouched.
    * ``tenant`` unset (local dev / ``--auth none``) → the caller's own (base)
      store, symmetric with how an unauthenticated request reads it.
    """
    sc = scope or live.base_scope
    kernel = live.kernel.with_tenant(tenant) if tenant else live.kernel
    try:
        await kernel.delete_instance(
            sc, _MEMORY_KIND, name, invalidate_mode="doc"
        )
    except ValueError as exc:  # filesystem source raises ValueError("not_found")
        if "not_found" in str(exc).lower():
            raise MemoryNotFound(
                f"memory {name!r} not found in tenant {tenant!r}'s own memory "
                f"(scope {sc!r}) — nothing to delete"
            ) from None
        raise
    return {"deleted": name, "scope": sc, "tenant": tenant}


# ── FastAPI wiring ─────────────────────────────────────────────────────────


def _resolve_cors_origins(cors_origins: list[str] | None) -> list[str]:
    """Resolve the allowed browser origins for the portal: explicit arg wins,
    else ``DNA_API_CORS_ORIGINS`` (comma-separated), else a dev default."""
    if cors_origins:
        return list(cors_origins)
    env = os.environ.get("DNA_API_CORS_ORIGINS")
    if env:
        return [o.strip() for o in env.split(",") if o.strip()]
    # Dev default: the portal's local Next.js origin.
    return ["http://localhost:3000"]


#: Caminhos PÚBLICOS por definição — nunca exigem bearer.
#:
#: `/.well-known/*` é o espaço de descoberta reservado pela RFC 8615, e o que
#: mora ali existe para ser lido por quem AINDA NÃO tem credencial: o Agent Card
#: do A2A diz como alcançar o agente e como se autenticar a ele, e a instância
#: de recurso protegido do OAuth diz onde fica o autorizador.
#:
#: Exigir bearer neles é um deadlock silencioso — o cliente precisa da instância
#: para saber como obter o token, e do token para ler a instância. O sintoma não
#: é "401" no lugar certo: é um terceiro que simplesmente não consegue começar, e
#: nenhuma mensagem explicando por quê.
#:
#: Achado rodando a porta A2A do dna-cloud no lane de produto: o Card respondia
#: 401 e a descoberta do cliente oficial morria antes da primeira mensagem.
_PUBLICO = ("/health",)


def _e_publico(path: str) -> bool:
    return path in _PUBLICO or path.startswith("/.well-known/")


#: Query params this FACE reads on every path, whatever the route declares.
#:
#: Not an escape hatch and not a convenience: these two are read by the auth
#: middlewares themselves — ``scope`` for the i-034 scope-grant check
#: (``scope_is_bound``) on every non-public path, ``tenant`` for the Model-B
#: workspace bind, which then **WRITES ``tenant`` BACK into the query string**
#: from the verified membership. So a route that never names them is still a
#: route on which they were read, and on which the server may have injected one
#: itself. Refusing them per-route would have the undeclared-param guard bill
#: the caller for the face's own doing — the exact shape of dishonesty the
#: guard exists to remove.
#:
#: DERIVED, not decided: ``test_rest_undeclared_query_params.py`` reads THIS
#: module for ``request.query_params.get(...)`` calls outside the routes and
#: asserts the two sets are equal. A middleware that starts reading a third
#: param fails that test until this tuple says so; one that stops reading
#: ``scope`` fails it until the tuple shrinks.
_FACE_WIDE_QUERY_PARAMS = ("scope", "tenant")


def build_app(
    *,
    scope: str | None = None,
    base_dir: str | None = None,
    auth: str = "none",
    token: str | None = None,
    cors_origins: list[str] | None = None,
    verifier: Any = None,
    auth_providers: Any = None,
    token_scopes: list[str] | None = None,
    quota_store: Any = None,
) -> Any:
    """Build the DNA REST read-API (a ``FastAPI`` app) over the live kernel.

    ``scope`` fixes the default scope (else the source's sole/first scope);
    ``base_dir`` overrides the source directory (tests / embedding — same seam as
    the MCP server's ``build_server``). The live kernel handle is booted LAZILY on
    the first request, on the running event loop, via the SAME ``boot_live`` the
    MCP server uses — so the source pool binds to the serving loop.

    ``auth``:
      * ``"none"`` — local dev, no bearer required.
      * ``"token"`` — every route (except ``/health``) requires
        ``Authorization: Bearer <token>``; the expected token is ``token`` (arg)
        or ``DNA_API_TOKEN`` (env). A shared token for the MVP.
      * ``"config"`` — the Model B (ADR §2.2 / S2.4) verified-identity path: every
        request carries a bearer JWT verified by the pluggable N-provider layer.
        The provider layer comes from ``auth_providers`` (a list of provider
        mappings — ``{type, issuer, audience, tenant_claim, …}`` — or already-parsed
        :class:`ProviderConfig` objects), OR a fully-built ``verifier``. This core
        builder does NO file I/O: reading providers from a ``dna.config.yaml`` is a
        CLI concern (``api_cmd`` loads the file and passes ``auth_providers=`` here),
        and an in-process composer (e.g. dna-cloud's apps) passes providers built
        from its own environment — the CLI is ONE consumer of this seam, not the
        only path. Passing neither under ``"config"`` is a loud error.
        The token→identity middleware then BINDS the effective workspace from the
        identity's active :class:`WorkspaceMembership` (the ``tenant`` query param
        is OVERWRITTEN from membership, never trusted from the caller) — mirroring
        the MCP ``--auth config`` path. A no-membership / cross-workspace request is
        denied (fail-closed).

    ``quota_store`` — an optional :class:`dna_cli._mcp_quota.QuotaStore` for the
    plan gates on the WRITE routes (tests / embedding). Default: selected from
    the environment via ``store_from_env`` (a Postgres DSN → the durable
    counter, the SAME one the MCP face meters into — one budget, two channels).
    Never consulted under ``--auth none``: the plan gate does not exist there.

    ``token_scopes`` — the scope grant for a WORKSPACE-LESS authenticated caller
    (``--auth token``'s shared service credential, and the ``--auth config``
    legacy-passthrough case where the source configured no workspaces). Falls back
    to ``DNA_TOKEN_SCOPES`` (comma-separated). Absent, the credential is bound
    to the ONE scope the server was booted on; ``"*"`` is the conscious opt-out
    back to unrestricted multi-scope reads. This is the i-034 fix: before it, a
    caller that resolved no workspace could name ANY scope precisely *because* it
    had no workspace to be bound to (absence of evidence became a right).

    Raises a clean ``RuntimeError`` if the optional ``fastapi`` dependency is absent.
    """
    try:
        from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
        # `from __future__ import annotations` turns route annotations into STRINGS
        # that FastAPI resolves against the module globals; since fastapi is imported
        # lazily (here, inside build_app) `Request` is not a module global, so a
        # `request: Request` route param would be mis-read as a query field. Publish
        # it to the module namespace so the string annotation resolves.
        globals()["Request"] = Request
    except ModuleNotFoundError as exc:  # pragma: no cover — exercised via CLI
        raise RuntimeError(
            "the REST read-API needs the optional 'fastapi' dependency — install "
            "it with:  pip install 'dna-cli[api]'"
        ) from exc

    # The shared use-cases live in the CORE application layer (adr-faces-reorg,
    # move #1): this face imports them from ``dna.application`` and only shapes
    # HTTP. ``boot_live`` is the CLI's composition root (it wires the CLI's own
    # source/provider boot path), so it stays in ``dna_cli._mcp_server``.
    from dna.application import (
        AmbiguousKindError,
        AuthoredKindNotFound,
        BoardItemNotFound,
        BootstrapKindWriteRefused,
        ConcurrentWriteError,
        MemberForbidden,
        MemberNotFound,
        NamespaceRegistryUnreadable,
        ProjectNotFound,
        UnknownKindError,
        WorkspaceForbidden,
        WorkspaceLastOwner,
        WorkspaceMemberNotFound,
        accept_invites_impl,
        adopt_workspace_scope_on_access,
        apply_definition_impl,
        approve_kind_impl,
        author_kind_impl,
        board_item_impl,
        board_summary_impl,
        compose_prompt_impl,
        create_project_impl,
        forget_impl,
        register_artifact_impl,
        get_instance_impl,
        resolve_instance_impl,
        graph_refs_impl,
        list_instances_impl,
        list_kinds_impl,
        write_instance_impl,
        create_workspace_impl,
        genome_view_impl,
        get_authored_kind_impl,
        get_project_impl,
        import_memories_impl,
        invite_member_impl,
        kind_graph_impl,
        list_agents_impl,
        list_authored_kinds_impl,
        list_bundle_entries_impl,
        list_members_impl,
        list_orgs_impl,
        list_projects_impl,
        list_repos_impl,
        list_tools_impl,
        list_workspace_members_impl,
        list_workspaces_impl,
        provision_tenant_owner_impl,
        provision_workspace_owner_impl,
        read_bundle_entry_impl,
        read_definition_impl,
        read_registered_kind_impl,
        recall_impl,
        reconcile_forks_impl,
        remember_impl,
        remove_member_impl,
        revert_bundle_entry_impl,
        revert_definition_impl,
        revoke_kind_impl,
        revoke_workspace_member_impl,
        set_member_impl,
        set_account_plan_impl,
        write_bundle_entry_impl,
    )
    from dna.application.live import parse_scope_grants
    from dna.kernel.errors import StaleInstanceWrite
    from dna.kernel.protocols import LayerPolicyViolationError
    from dna.tenancy import Identity
    from dna_cli._mcp_server import boot_live
    # The intel face delegates to the CORE engine (adr-faces-reorg: logic in the
    # core, faces thin). These handlers only translate transport + call in.
    from dna.extensions.intel import engine as intel_engine
    # Typed response models — declared on every route as ``response_model`` so the
    # OpenAPI response schemas (and the clients generated from them) carry the real
    # payload shape instead of an opaque ``object``. Imported lazily here (with
    # fastapi) so ``import dna_cli`` stays FastAPI/pydantic-face-free. See
    # ``dna_cli._rest_models`` for the fidelity contract.
    from dna_cli import _rest_models as m
    # ``m.WriteBundleEntryRequest`` is used as a PARAMETER annotation (not just a
    # response_model= kwarg), and `from __future__ import annotations` turns that
    # annotation into the STRING "m.WriteBundleEntryRequest" — resolved by
    # FastAPI/typing.get_type_hints against the module globals. `m` is a local
    # import inside build_app, so it must be published the same way `Request`
    # is above, or the annotation fails to resolve and the body param silently
    # degrades to an unannotated (required, missing) query param.
    globals()["m"] = m

    # LOUD, NOT SILENT (i-074): this door shares the workspace boundary with the
    # MCP one, so it announces the same thing at boot — silent in the default
    # (enforcing) posture, and loud when the boundary is open or when the knob
    # carries a value this build does not recognise. See dna.tenancy.enforcement.
    _enforcement_line = enforcement_boot_message()
    if _enforcement_line:
        logger.warning("%s", _enforcement_line)

    app = FastAPI(
        title="DNA REST read-API",
        version="1",
        description=(
            "The correct HTTP boundary for a WEB app (the DNA Cloud portal) — a "
            "thin request/response REST face over the SAME DNA kernel + impls the "
            "MCP server uses. Read-focused, tenant-aware."
        ),
    )

    origins = _resolve_cors_origins(cors_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # -- auth (shared bearer token for the MVP) ------------------------------
    # TODO(hosted): OAuth 2.1 / per-tenant bearer — swap this shared-token gate
    # for a verified-token → tenant bridge (the SAME tenancy model as the MCP
    # server's dna_cli._mcp_auth: the token's tenant claim becomes the effective
    # tenant, and a cross-tenant request is denied), so `tenant` stops being a
    # query param a caller can forge and becomes bound to the verified token.
    def _auth_dep(authorization: str | None = Header(default=None)) -> None:
        if auth != "token":
            return
        expected = token or os.environ.get("DNA_API_TOKEN")
        if not expected:
            raise HTTPException(
                status_code=500,
                detail="token auth is enabled but no token is configured "
                "(set DNA_API_TOKEN or pass --token)",
            )
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing bearer token")
        provided = authorization[len("Bearer "):].strip()
        if not secrets.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="invalid bearer token")

    # -- lazy live kernel (booted once, on the serving loop) -----------------
    _state: dict[str, Any] = {"live": None}
    _boot_lock = asyncio.Lock()

    async def _live() -> Any:
        if _state["live"] is None:
            async with _boot_lock:
                if _state["live"] is None:
                    _state["live"] = await boot_live(scope, base_dir)
        return _state["live"]

    # -- i-106: a query param this face does not implement is REFUSED --------
    #
    # FastAPI drops an undeclared query param in SILENCE. That is a sane
    # default for the public web (analytics tack `utm_*` onto every URL) and
    # the wrong one for an API whose parameters change what the answer MEANS:
    # `GET /v1/kinds/Issue/instances/<name>?as_of=<yesterday>` returned 200
    # with TODAY's instance, because `as_of` existed on `/v1/memories` and
    # nowhere else. Nothing in that response contradicted the caller's belief
    # that they were reading the past. Measured 06/08/2026 against the local
    # runtime; the route now implements `as_of` (above), but the CLASS of
    # defect is the point — one instance was found by accident, so the others
    # would be too.
    #
    # PROCUREI ANTES DE CONSTRUIR (02/08's lesson, applied): FastAPI DOES ship
    # a mechanism — a Pydantic query MODEL with `model_config =
    # {"extra": "forbid"}` (tutorial "Query Parameter Models", ≥0.115) — but it
    # is per-route and would mean rewriting all 55 signatures into models,
    # which is a large diff that a new route silently opts out of. There is no
    # app-wide switch (fastapi#2859 / #4764 / discussions #7697, #9016: "would
    # not be acceptable as a default"), and no PyPI package for it
    # (`fastapi-strict-query`, `fastapi-query-guard` → 404). So: our own
    # dependency, derived from the route's OWN declared params rather than from
    # a list somebody must remember to update — the derivation-not-enumeration
    # rule this repo already learned the hard way, plus the two FACE-WIDE names
    # the middlewares genuinely read on every path (`_FACE_WIDE_QUERY_PARAMS`).
    #
    # Blast radius, MEASURED rather than assumed (06/08/2026): every call site
    # in dna-cloud that reaches this face was inventoried — ~100 of them across
    # `apps/web/lib/**` — and each sends only params its route declares, or
    # `scope`/`tenant`. Zero of them start failing. The one that would have
    # (`POST /v1/kinds/{kind}/approve`, which dna-cloud calls with `scope` and
    # which declares only `tenant`) is precisely a face-wide read, not an
    # ignored one.
    _declared_query_cache: dict[int, frozenset[str]] = {}

    def _declared_query_names(route: Any) -> frozenset[str]:
        """Every query key ``route`` actually reads, walked off its dependant.

        DERIVED, never listed: sub-dependencies contribute their params too, so
        a shared `Depends` that grows a param does not need this guard edited.
        A Pydantic query model (FastAPI ≥0.115) is expanded to its own fields —
        this face declares none today, and the guard must not start refusing
        real params the day one appears.
        """
        cached = _declared_query_cache.get(id(route))
        if cached is not None:
            return cached
        names: set[str] = set()
        dep = getattr(route, "dependant", None)
        stack: list[Any] = [dep] if dep is not None else []
        seen: set[int] = set()
        while stack:
            d = stack.pop()
            if id(d) in seen:
                continue
            seen.add(id(d))
            for f in getattr(d, "query_params", ()) or ():
                annotation = getattr(getattr(f, "field_info", None), "annotation", None)
                model_fields = getattr(annotation, "model_fields", None)
                if isinstance(model_fields, dict):
                    names.update(
                        (getattr(info, "alias", None) or fname)
                        for fname, info in model_fields.items()
                    )
                    continue
                names.add(getattr(f, "alias", None) or getattr(f, "name", ""))
            stack.extend(getattr(d, "dependencies", ()) or ())
        frozen = frozenset(n for n in names if n)
        _declared_query_cache[id(route)] = frozen
        return frozen

    def _refuse_undeclared_query(request: Request) -> None:
        """400 on a query param the matched route does not read.

        Ordered AFTER ``_auth_dep`` in ``guarded`` on purpose: an
        unauthenticated caller must still get 401, not a 400 that quietly
        enumerates which parameters a route it cannot reach would accept.
        """
        route = request.scope.get("route")
        if route is None or getattr(route, "dependant", None) is None:
            return  # not a route this face declared — nothing to compare against
        declared = _declared_query_names(route) | frozenset(_FACE_WIDE_QUERY_PARAMS)
        extra = sorted({k for k in request.query_params.keys() if k not in declared})
        if not extra:
            return
        accepted = ", ".join(sorted(declared)) or "no query parameters"
        raise HTTPException(
            status_code=400,
            detail=(
                f"{request.method} {getattr(route, 'path', request.url.path)} "
                f"does not implement the query parameter(s) "
                f"{', '.join(repr(e) for e in extra)}; it accepts: {accepted}. "
                f"Refused rather than ignored — answering 200 here would let "
                f"you believe this route used a value it never read."
            ),
        )

    guarded = [Depends(_auth_dep), Depends(_refuse_undeclared_query)]

    # The scope grant for a workspace-less authenticated credential (i-034).
    # Resolved ONCE here so every enforcement point reads the same configured set.
    _token_scopes = (
        frozenset(token_scopes)
        if token_scopes
        else parse_scope_grants(os.environ.get("DNA_TOKEN_SCOPES"))
    )

    def _scope_denied(req_scope: str, live: Any) -> Any:
        return JSONResponse(
            {"detail": f"scope {req_scope!r} is not granted to this credential; "
                       f"a request that resolves no workspace may only read the "
                       f"scopes explicitly granted to its token "
                       f"(default: {live.base_scope!r}). Set DNA_TOKEN_SCOPES "
                       f"(or --token-scope) to widen the grant."},
            status_code=403,
        )

    # -- i-034: shared-token scope binding ------------------------------------
    # `--auth token` is a SERVICE credential: authenticated, but it resolves no
    # workspace and never did, so the workspace binder below could not see it —
    # this is the path dna-cloud's portal actually uses, and the path i-028 left
    # wide open. An authenticated caller that resolves no workspace is now bound to
    # the scopes explicitly granted to its token. 401 stays the Depends' job: this
    # middleware only speaks once the bearer is known-good, so an unauthenticated
    # request still gets 401 (not a 403 that would leak which scopes exist).
    if auth == "token":

        @app.middleware("http")
        async def _token_scope_bind(request: Request, call_next):  # type: ignore[no-untyped-def]
            if _e_publico(request.url.path):
                return await call_next(request)
            req_scope = request.query_params.get("scope")
            req_tenant = request.query_params.get("tenant")
            if req_scope is None and not req_tenant:
                return await call_next(request)
            expected = token or os.environ.get("DNA_API_TOKEN")
            authz = request.headers.get("authorization") or ""
            if not expected or not authz.startswith("Bearer "):
                return await call_next(request)  # let _auth_dep answer 401/500.
            provided = authz[len("Bearer "):].strip()
            if not secrets.compare_digest(provided, expected):
                return await call_next(request)  # let _auth_dep answer 401.
            live = await _live()
            if req_scope is not None and not live.scope_is_bound(
                req_scope, None, authenticated=True, granted_scopes=_token_scopes
            ):
                return _scope_denied(req_scope, live)
            # Adopt-on-access (i-058 hardening): under the portal's TRUSTED
            # shared bearer the workspace arrives as the `tenant` query param
            # (this lane resolves no membership — the portal already did).
            # This is the token lane's "request resolved a workspace" moment:
            # if that workspace's scope has no declared parent and a
            # definitions base is configured, declare it before the route
            # impl reads. Cached + single-flighted; NO-OP without the env
            # (OSS untouched); fail-soft (never fails the request).
            if req_tenant:
                await adopt_workspace_scope_on_access(live, req_tenant)
            return await call_next(request)

    # -- Model B config-auth: token→identity→workspace binding (S2.4) ---------
    # The verified-identity ingress (ADR §2.2): a bearer JWT is verified by the
    # N-provider layer; the identity's active WorkspaceMembership BINDS the
    # effective workspace, which OVERWRITES the `tenant` query param (a caller can
    # no longer forge it). Mirrors the MCP `_guard` — same resolver, same
    # fail-closed denial. The `/v1/workspaces/*` boundary routes are EXEMPT from the
    # bind (they name the workspace in the path and do their OWN RBAC via the
    # verified identity stashed on `request.state`): notably `accept`, where the
    # invitee is still PENDING and by definition holds no active membership yet.
    if auth == "config":
        from urllib.parse import parse_qs, urlencode

        from dna.tenancy import (
            CrossWorkspaceError,
            Membership,
            UnmeterableIdentityError,
            enforcement_is_open,
            identity_from_token,
            resolve_workspace,
            unenforced_metering_key,
        )

        # Build the N-provider verifier from what the CALLER supplied — never from
        # a file. Either a prebuilt ``verifier``, or ``auth_providers`` (raw provider
        # mappings, which we parse, or already-parsed ``ProviderConfig`` objects).
        # Reading a dna.config.yaml is the CLI's job (api_cmd passes auth_providers=).
        if verifier is None:
            if not auth_providers:
                raise RuntimeError(
                    "build_app(auth='config') needs `auth_providers` (a list of "
                    "provider mappings / ProviderConfig) or a prebuilt `verifier`. "
                    "Reading providers from a dna.config.yaml is a CLI concern — "
                    "api_cmd loads the file and passes auth_providers= here; an "
                    "in-process caller passes providers from its own environment."
                )
            from dna_cli._mcp_auth import _multi_provider_verifier, parse_auth_providers

            _provs = auth_providers
            if isinstance(_provs, dict):  # the whole {"providers": [...]} mapping
                _provs = parse_auth_providers(_provs)
            elif _provs and isinstance(_provs[0], dict):  # a list of provider mappings
                _provs = parse_auth_providers({"providers": list(_provs)})
            # else: already a list[ProviderConfig]
            verifier = _multi_provider_verifier(list(_provs))

        _verifier_state: dict[str, Any] = {"v": verifier}

        def _get_verifier() -> Any:
            return _verifier_state["v"]

        @app.middleware("http")
        async def _config_auth(request: Request, call_next):  # type: ignore[no-untyped-def]
            path = request.url.path
            if _e_publico(path):
                return await call_next(request)

            authz = request.headers.get("authorization")
            if not authz or not authz.startswith("Bearer "):
                return JSONResponse({"detail": "missing bearer token"}, status_code=401)
            bearer = authz[len("Bearer "):].strip()
            try:
                access = await _get_verifier().verify_token(bearer)
            except Exception:  # noqa: BLE001 — a verifier error is an auth failure.
                access = None
            if access is None:
                return JSONResponse({"detail": "invalid bearer token"}, status_code=401)

            claims = dict(getattr(access, "claims", None) or {})
            request.state.claims = claims
            request.state.identity = identity_from_token(claims)

            # The boundary routes manage membership themselves (path names the
            # workspace; they RBAC on request.state.identity) — never bind here.
            if path.startswith("/v1/workspaces"):
                return await call_next(request)
            # POST /v1/projects names its workspace in the BODY (decision A1) and
            # re-checks ACTIVE membership in the core impl, which is the same gate
            # this bind performs. Exempting it is not a hole — it is the only way a
            # caller who belongs to SEVERAL workspaces can create a project at all:
            # `resolve_workspace` fails closed on an ambiguous multi-membership
            # request that names no `tenant`, and this route names none by design.
            if path == "/v1/projects" and request.method == "POST":
                return await call_next(request)
            # POST /v1/memories/import targets the caller's PERSONAL partition,
            # which is ORTHOGONAL to any workspace (decision B1 — personal memory
            # follows the person, not the workspace). Binding a workspace here
            # would be worse than useless: `resolve_workspace` fails closed for a
            # caller with NO membership, which would block exactly the signed-up
            # user with no workspace yet from importing their own memory — the
            # product wedge. Exempting it is not a hole: the route derives its
            # identity from `request.state.claims` (set just above, on the
            # VERIFIED token) and never reads `tenant` at all.
            if path == "/v1/memories/import" and request.method == "POST":
                return await call_next(request)
            # GET /v1/memories/personal is the READ face of the same partition
            # (i-046 unblock): identical reasoning — identity-scoped, workspace-
            # orthogonal, and a signed-up user with NO membership yet must be
            # able to read the memory they just imported. The route derives its
            # identity from `request.state.claims` (the VERIFIED token) and
            # never reads `tenant`; binding a workspace here would 403 exactly
            # that no-workspace caller.
            if path == "/v1/memories/personal" and request.method == "GET":
                return await call_next(request)

            grants_raw = await (await _live()).kernel.workspace_memberships()
            if not grants_raw:
                # No workspaces configured → Model B not engaged (legacy passthrough).
                # The TENANCY passthrough stays (a pre-Model-B deployment keeps
                # working), but it is not a scope grant: this caller IS
                # authenticated and resolves no workspace, so i-034's rule applies
                # — only an explicitly granted scope is reachable.
                live = await _live()
                req_scope = request.query_params.get("scope")
                if req_scope is not None and not live.scope_is_bound(
                    req_scope, None, authenticated=True, granted_scopes=_token_scopes
                ):
                    return _scope_denied(req_scope, live)
                return await call_next(request)

            memberships = [Membership.from_spec(g.get("spec") or {}) for g in grants_raw]
            requested = request.query_params.get("tenant")
            try:
                workspace = resolve_workspace(
                    token_present=True,
                    identity=request.state.identity,
                    requested=requested,
                    memberships=memberships,
                )
            except CrossWorkspaceError as exc:
                # The opt-out (i-074). This face shares the seam with MCP and must
                # share the switch: an operator whose MCP works but whose read-API
                # 403s has an opt-out they cannot trust. Default (and any
                # unrecognised value) → the 403 stands.
                if not enforcement_is_open():
                    return JSONResponse({"detail": str(exc)}, status_code=403)
                # Serve it — but only once the call can be ATTRIBUTED. The
                # membership-less caller resolves no workspace, so the plan gate
                # below would otherwise meter every such identity into one shared
                # bucket; stash the identity key it must use instead. A token with
                # no durable subject cannot be attributed and keeps the denial.
                try:
                    request.state.unenforced_metering_key = unenforced_metering_key(
                        claims
                    )
                except UnmeterableIdentityError as unmeterable:
                    return JSONResponse(
                        {"detail": str(unmeterable)}, status_code=403
                    )
                workspace = requested  # the unverified selector, at face value.

            # Bind the physical scope too (defense-in-depth, mirror the MCP guard):
            # an explicit `scope=` naming another workspace's scope is denied.
            # Bind the physical scope. NOTE the missing `workspace and` guard that
            # used to be here (i-034): gating the check on a resolved workspace made
            # the workspace-less caller — the one with the LEAST proven right to any
            # scope — the only one that skipped the check entirely. `scope_is_bound`
            # now takes `authenticated` and fails closed on that branch itself.
            live = await _live()
            req_scope = request.query_params.get("scope")
            if not live.scope_is_bound(
                req_scope, workspace, authenticated=True, granted_scopes=_token_scopes
            ):
                if workspace:
                    return JSONResponse(
                        {"detail": f"request is bound to workspace {workspace!r}; "
                                   f"cross-workspace access to scope {req_scope!r} "
                                   f"is denied"},
                        status_code=403,
                    )
                return _scope_denied(req_scope, live)

            # Adopt-on-access (i-058 hardening): the middleware just RESOLVED
            # the caller's workspace from its verified membership — the moment
            # no navigation path can skip. Declare the scope's parent (the
            # configured definitions base) before the route impl reads, so
            # THIS request already inherits the base's definitions. Cached +
            # single-flighted; NO-OP without the env; fail-soft.
            await adopt_workspace_scope_on_access(live, workspace)

            # OVERWRITE the tenant query param with the membership-bound workspace.
            # ⚠️ This line is why `tenant` is in `_FACE_WIDE_QUERY_PARAMS`: from
            # here on `query_params` carries a key the SERVER put there, on
            # routes that may never declare it.
            qs = parse_qs(request.scope.get("query_string", b"").decode())
            if workspace is not None:
                qs["tenant"] = [workspace]
            request.scope["query_string"] = urlencode(qs, doseq=True).encode()
            return await call_next(request)

    def _actor_claims_from_state(request: Request) -> dict[str, Any] | None:
        """The verified token claims stashed by the config-auth middleware (the
        actor for a `/v1/workspaces/*` write), or ``None`` under none/token auth."""
        return getattr(request.state, "claims", None)

    def _actor_from_state(request: Request) -> str:
        """WHO this request is, as an AUDIT field records it — a single string.

        Resolved SERVER-SIDE from the verified token, in the same preference
        order the MCP board writes use (``dna_cli._mcp_auth.actor_from_context``):
        the verified email → the durable subject (``oid``) → the token's raw
        ``sub``. Never a body or query value: attribution a caller can forge is
        not attribution, which is the whole reason the approval gate exists.

        Absence is honest rather than fatal, mirroring ``actor_from_context``
        (an unattributable write is still a write worth recording, and failing it
        turns attribution into a new way to lose work):

        * a request that carries no claims at all → the sentinel
          :func:`_unidentified_actor` picks for this lane. ``--auth token`` — a
          REMOTE deployment behind a shared secret — is the verified-and-nameless
          case, not the local one: the bearer IS verified (against
          ``DNA_API_TOKEN``), it simply names nobody. Calling that caller
          ``rest:local`` was a mislabel inherited from the MCP precedent, where
          the two lanes were lumped together as "no token at all";
          ``DNA_PERSONAL_ID`` still outranks either sentinel, because an
          operator who declared a name has said more than a sentinel can.
        * no token at all (``--auth none``, i.e. local or OSS self-host) →
          ``DNA_PERSONAL_ID`` if the operator declared one — the env var that
          already names an offline caller for personal memory — and
          :data:`_UNIDENTIFIED_LOCAL_ACTOR` otherwise. That lane is the ONLY one
          the local sentinel belongs to, which is the whole content of
          :func:`_unidentified_actor`.

        The two labels name the CHANNEL this face is (``rest:``), not the
        identity: recording a channel as an identity is the conflation the MCP
        constants exist to end, and reusing ``mcp:local`` here would re-make it
        one layer over.
        """
        from dna.tenancy import identity_from_token as _identity_from_token
        from dna_cli._mcp_auth import personal_id_from_env

        claims = _actor_claims_from_state(request)
        if claims is None:
            # ``--auth token`` stashes no claims (there are none to stash), but
            # it is not the local lane — see :func:`_unidentified_actor` for why
            # the choice keys on "did this lane verify anything at all" rather
            # than on one lane's configuration name.
            return personal_id_from_env() or _unidentified_actor(auth)
        identity = _identity_from_token(claims)
        for candidate in (identity.email, identity.oid, claims.get("sub")):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return _UNIDENTIFIED_TOKEN_ACTOR

    # -- plan gates on the WRITE path (i-042) ---------------------------------
    # Before this, the REST face had ZERO metering: the axes the Pro plan sells
    # (memory_mode write, calls_per_day) were enforced ONLY on the MCP channel —
    # a Free workspace writing through the web surface was never gated. The
    # policy is NOT re-implemented here: `_plan_gate` calls the SAME shared core
    # (`dna_cli._mcp_quota.enforce_plan`) the MCP `_guard` runs — same tier
    # resolution (claim → workspace → account → AccountPlan → Free floor), same
    # pre-counter mode
    # gates, same i-050 honesty (a denied call is never counted), same i-051
    # fail-closed switch (DNA_QUOTA_REQUIRE_TIERS). This face only maps the
    # exceptions to HTTP.
    #
    # Channel policy (deliberate, documented):
    #   * READS are NOT metered on REST. On MCP every tool call is an agent
    #     action and counts; a web dashboard fans a single page render out into
    #     several GETs, so counting reads would let navigation burn the
    #     customer's cap. calls_per_day on REST counts gated WRITES only.
    #   * `--auth none` (local / OSS self-host) is NEVER gated — the open-core
    #     hard rule, structurally enforced by the early return below.
    #   * Under `--auth token` (the portal's TRUSTED service bearer) the gate
    #     applies to tenant-attributed writes (the portal passes the session's
    #     workspace as `tenant`). A tenant-less call under the shared bearer is
    #     the operator's own service op (e.g. PUT /v1/account-plan, the
    #     billing bridge itself) and is not plan-gated — the same credential
    #     could rewrite the plan anyway, so gating it would add no security,
    #     only a bootstrap deadlock.
    from dna.memory.personal import personal_tenant
    from dna_cli import _mcp_quota as _quota_mod
    from dna_cli._mcp_auth import tier_from_token
    from dna_cli._mcp_quota import (
        FeatureNotInPlanError,
        # ⚠️ REST reaches this one through `_gate_kind_write`'s `family_op`,
        # exactly as MCP does — and it was simply never named here, so a plan
        # that omits `definitions_mode` refused a REST generic write with a
        # 500 instead of the 403 whose message names the missing cap. Found by
        # `tests/test_quota_refusals_reach_both_faces.py`, which is the actual
        # fix: this hand-written tuple can no longer go stale in silence.
        InstanceModeError,
        MemoryModeError,
        OverQuotaError,
        SdlcModeError,
        TierRegistryUnavailableError,
        store_from_env,
    )

    # The metering counter for THIS app — never touched under --auth none, and
    # not even constructed there (a local `dna api serve` against Postgres must
    # not demand the [quota] extra it will never use).
    _quota = (
        quota_store if quota_store is not None
        else (store_from_env() if auth != "none" else None)
    )

    async def _plan_gate(
        request: Request, *, tenant: str | None, family: str,
        memory_op: str | None = None, sdlc_op: str | None = None,
        family_op: str | None = None,
        quota_tenant: str | None = None,
    ) -> None:
        """Enforce the caller's plan on ONE write — the REST twin of the MCP
        ``_guard``'s metered branch. Maps the shared core's exceptions to HTTP:
        403 (mode/family — the plan does not include it), 429 (rate/daily cap,
        and the operator's margin breaker, which subclasses it), 503 (Tier
        registry unavailable under the fail-closed flag, and the breaker's own
        fail-safe when its counter cannot be read)."""
        if auth == "none":
            return  # local / OSS self-host: the plan gate does not exist.
        if auth == "token" and tenant is None and quota_tenant is None:
            return  # the shared bearer's own service op — see the note above.
        if tenant is None and quota_tenant is None:
            # An authenticated call that resolved NO workspace — which happens
            # only once the workspace boundary was explicitly opened (i-074).
            # It still counts, against the caller's own identity: the middleware
            # already derived that key from the verified claims. Without it the
            # metering key would be `None`, i.e. ONE bucket shared by every
            # membership-less identity.
            quota_tenant = getattr(request.state, "unenforced_metering_key", None)
        claims = _actor_claims_from_state(request)
        try:
            # Resolved through the MODULE (not a from-import) so the shared
            # symbol stays one seam for both faces (and monkeypatchable — the
            # parity test's hook).
            await _quota_mod.enforce_plan(
                (await _live()).kernel,
                tenant=tenant, family=family, store=_quota,
                # An explicit plan claim on the VERIFIED token wins, exactly as
                # on MCP; a claim-less token falls to AccountPlan → Free.
                claimed_tier=tier_from_token(claims) if claims else None,
                memory_op=memory_op, sdlc_op=sdlc_op, family_op=family_op,
                quota_tenant=quota_tenant,
            )
        except TierRegistryUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
        except (FeatureNotInPlanError, MemoryModeError, SdlcModeError,
                InstanceModeError) as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        except OverQuotaError as exc:
            # Includes `MarginBreakerTripped` (i-134), which subclasses this on
            # purpose so the operator's cost cutout is relayed by a mapping
            # written years before it — 429, with the refusal's own sentence.
            raise HTTPException(status_code=429, detail=str(exc)) from None

    async def _gate_kind_write(
        request: Request, *, kind: str, api_version: str | None,
        tenant: str | None,
    ) -> None:
        """i-042 — o gate de plano do WRITE genérico, kind-aware: a família do
        Kind ALVO decide o eixo (``sdlc_mode`` para o board, ``memory_mode``
        para memória, ``definitions_mode`` para o resto) — o espelho exato do
        ``_guard_for`` que o MCP sempre teve. Antes disto, os DOIS eixos que o
        Pro desbloqueia valiam só no canal MCP: um Free escrevendo Story pela
        REST não era barrado por nada. Resolução de família em pré-passe
        (métrica), fail-soft para ``definitions`` como no MCP (i-090); a
        recusa acontece ANTES do write — negado nunca escreve."""
        from dna.application import family_for_kind, resolve_kind_port_live

        familia = "definitions"
        try:
            live = await _live()
            port = await resolve_kind_port_live(
                live, kind, api_version, scope=live.default_scope(tenant),
            )
            familia = family_for_kind(port)
        except Exception:  # noqa: BLE001 — resolução falhou: família default
            familia = "definitions"
        await _plan_gate(
            request, tenant=tenant, family=familia,
            memory_op="write" if familia == "memory" else None,
            sdlc_op="write" if familia == "sdlc" else None,
            family_op="write" if familia not in ("memory", "sdlc") else None,
        )

    # -- health (unguarded) --------------------------------------------------

    @app.get("/health", response_model=m.HealthResponse)
    async def health() -> dict[str, Any]:
        return {"ok": True}

    # -- definitions (reuse the MCP impls verbatim — zero duplication) -------

    @app.get("/v1/agents", dependencies=guarded, response_model=m.AgentsResponse)
    async def agents(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List a scope's prompt-target agents, tenant-aware."""
        return await list_agents_impl(await _live(), scope, tenant)

    # response_model_exclude_unset: the explain-only fields (sections /
    # attribution) are OMITTED from the plain compose response — the historical
    # five-key JSON shape is preserved byte-for-byte for every caller that does
    # not opt in (guarded by tests/test_compose_explain.py).
    @app.get("/v1/agents/{name}/prompt", dependencies=guarded,
             response_model=m.AgentPromptResponse,
             response_model_exclude_unset=True)
    async def agent_prompt(
        name: str,
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
        explain: bool = Query(default=False, description=(
            "Opt-in per-section provenance (i-045). When true, the response "
            "additionally carries 'sections' (source artifact, content hash, "
            "version, layer origin and tenant-overlay marker per composed "
            "section) and 'attribution' (declared|heuristic — how trustworthy "
            "the section map is; see the response model). The composed "
            "'prompt' is byte-identical with or without the flag — explain "
            "never re-renders."
        )),
    ) -> dict[str, Any]:
        """Compose one agent's system prompt LIVE (Soul + Guardrails +
        instruction), tenant-aware — the per-tenant overlay a static emit
        artifact cannot express. ``?explain=true`` adds per-section
        provenance (the ``dna explain`` map) to the same response."""
        try:
            return await compose_prompt_impl(
                await _live(), name, scope, tenant, explain=explain
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    @app.get("/v1/tools", dependencies=guarded, response_model=m.ToolsResponse)
    async def tools(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List a scope's Tool Kind surfaces (name + description), tenant-aware."""
        return await list_tools_impl(await _live(), scope, tenant)

    @app.get("/v1/genome", dependencies=guarded, response_model=m.GenomeViewResponse)
    async def genome(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """The DERIVED Genome view of a scope: identity + ships (the scope's own
        contents, enumerated live = no drift) + the tenant LayerPolicy. One call
        composes what the portal's /console/genome panel renders."""
        return await genome_view_impl(await _live(), scope, tenant)

    # -- definitions (read/apply/revert a tenant-layer override) -------------
    # The strain-customization write path (s-strain-customization-ui): a
    # tenant-layer write is the ONE mechanism that gets LayerPolicy
    # enforcement for free (a LOCKED Kind/field vetoes the write at the
    # kernel, not here). These three thin routes reuse the SAME core
    # ``*_definition_impl`` use-cases Task 1 added — zero business logic here.

    @app.get("/v1/definitions/{kind}/{name}", dependencies=guarded,
             response_model=m.DefinitionView)
    async def get_definition(
        kind: str, name: str,
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Read a definition as the tenant sees it: the effective (composed)
        spec, the inherited base spec, whether the tenant has an override, and
        the Kind's edit schema (ui_schema + overlayable fields) — what the
        portal's customization editor renders. 404 for an unknown (kind, name)."""
        live = await _live()
        try:
            return await read_definition_impl(
                live, scope=scope or live.base_scope, tenant=tenant,
                kind=kind, name=name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    @app.put("/v1/definitions/{kind}/{name}", dependencies=guarded,
             response_model=m.DefinitionWriteResponse)
    async def put_definition(
        kind: str, name: str,
        spec: dict[str, Any] = Body(..., embed=True),
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Persist a tenant override of a definition (the editor's Save) — a
        tenant-layer write via the SAME core ``apply_definition_impl`` the CLI
        uses. A LOCKED Kind/field is vetoed by the kernel's LayerPolicy check,
        surfaced here as 403 (never silently dropped)."""
        live = await _live()
        try:
            return await apply_definition_impl(
                live, scope=scope or live.base_scope, tenant=tenant,
                kind=kind, name=name, spec=spec,
            )
        except LayerPolicyViolationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.delete("/v1/definitions/{kind}/{name}", dependencies=guarded,
                response_model=m.DefinitionWriteResponse)
    async def delete_definition(
        kind: str, name: str,
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Revert a tenant override — deletes the tenant-layer doc so reads
        fall back to the inherited base (the editor's "Reset to default")."""
        live = await _live()
        try:
            return await revert_definition_impl(
                live, scope=scope or live.base_scope, tenant=tenant,
                kind=kind, name=name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    # -- Kind authoring (a tenant declares its OWN Kind, inert until approved) -
    # A DEDICATED door, deliberately not a relaxation of the generic one. The
    # generic write (``write_instance_impl``) refuses every BOOTSTRAP Kind —
    # KindDefinition and Genome among them — because a tool that can write any
    # instance must not be the tool that rewrites the frame every other instance
    # is validated against; that refusal is untouched here and is pinned by
    # tests/test_kind_authoring_route.py.
    #
    # What this door writes is INERT: the spec is built field by field and never
    # merged from the request body, so it carries no ``approved_by`` and there is
    # no key an author can smuggle one through. Registration is what confers
    # schema validation and storage routing, and the registry's approval gate
    # withholds it until a DIFFERENT actor approves — so "not approved has no
    # effect" is the absence of a mechanism, not a promise. Approval is the
    # SECOND route below, and it is the act that confers effect.
    #
    # ── THE LANE — all four routes mount on EVERY auth mode ────────────────
    # ``config``, ``none`` and ``token`` alike. For one release they did not:
    # 0.31.0 wrapped these four decorators in ``if auth != "token":``, and the
    # argument was that on the shared-secret lane there is no identity, so
    # ``tenant`` is a raw query param a caller can forge and anyone holding the
    # secret could read and approve any workspace's Kinds.
    #
    # That argument left out WHO holds the secret. The shared-secret lane is a
    # TRUSTED SERVER-TO-SERVER lane: the credential belongs to the operator of
    # the deployment, not to its tenants. The caller holding it resolves the
    # tenant from a verified session BEFORE it calls and passes it as ``tenant``
    # — the identity check happens one layer up, in the caller. The breach the
    # exclusion imagined requires the operator's secret in a tenant's hands,
    # which is not the deployment. The cost of the exclusion, by contrast, was
    # concrete: the caller's audit screen asked a door that no longer existed and
    # rendered an empty roster while the Kind sat in the store, authored and
    # inert.
    #
    # All four routes enforce namespace ownership — a caller may touch only Kinds
    # in namespaces its ``tenant`` owns, resolved through ``owner_of`` against the
    # same ``KindNamespace`` claims the write gate decides with. That property
    # rests entirely on ``tenant``, and where ``tenant`` comes from differs per
    # lane. Stated plainly, because the difference is real:
    #
    #   * ``--auth config`` — IDENTITY-BOUND. The middleware above resolves the
    #     workspace from the verified token's membership and OVERWRITES the query
    #     param with it (``CrossWorkspaceError`` on a mismatch). ``tenant`` is a
    #     fact about the request, and the ownership filter keys on that fact.
    #   * ``--auth none`` — LOCAL / OSS SELF-HOST, and the Dockerfile default. No
    #     credential, no second tenant: the caller is the operator of their own
    #     store, and the unattributed lane (no resolved tenant ⇒ the ownership
    #     filter does not apply) is the DOCUMENTED, correct behaviour there — the
    #     same hinge ``NamespaceOwnershipGate`` uses for an unattributed write.
    #   * ``--auth token`` — TRUSTED SERVER-TO-SERVER. There is NO identity at
    #     the HTTP layer, ``tenant`` is CALLER-SUPPLIED, and THE CALLER IS
    #     RESPONSIBLE FOR HAVING RESOLVED AND VERIFIED IT — a trusted caller
    #     resolves the tenant itself, from its own verified session, before it
    #     reaches this door.
    #
    # So the ownership property the handlers below enforce is, on that last lane,
    # only as strong as the caller. That is a DELIBERATE, DOCUMENTED TRUST
    # BOUNDARY rather than an oversight, and it is where the boundary belongs
    # while the lane's credential is a single shared secret: a door cannot
    # re-derive an identity nobody sent it. The standing ``TODO(hosted)`` above
    # (swap the shared-token gate for a verified-token → tenant bridge, the same
    # tenancy model ``dna_cli._mcp_auth`` uses, so ``tenant`` becomes bound to
    # the verified token instead of supplied alongside it) is exactly the work
    # that would remove the caveat — after it lands, this lane reads like the
    # config one and this paragraph goes away.
    #
    # The audit records the lane honestly in the meantime. A ``--auth token``
    # caller with no identity claim is stamped ``rest:unidentified`` — VERIFIED
    # (against the configured secret) yet naming nobody, a different fact from
    # ``--auth none``'s ``rest:local`` — so a later reader of the store can see
    # that WHO was decided by the caller and not by this door.
    #
    # Pinned by tests/test_kind_authoring_route.py §0, which asserts on the ROUTE
    # TABLE in all three modes (a status-only assertion cannot tell an unrouted
    # path from a handler's own 404: Starlette answers both with ``{"detail":
    # "Not Found"}``).

    @app.post("/v1/kinds", dependencies=guarded, status_code=201,
              response_model=m.AuthorKindResponse)
    async def author_kind(
        request: Request,
        kind: str = Body(..., embed=True),
        schema: dict[str, Any] = Body(..., embed=True),
        traits: list[str] | None = Body(default=None, embed=True),
        presentation: dict[str, Any] | list[str] | None = Body(
            default=None, embed=True),
        relations: dict[str, Any] | None = Body(default=None, embed=True),
        plane: str | None = Body(default=None, embed=True),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Author a Kind for the calling workspace — a ``KindDefinition``
        instance written WITHOUT an approval marker, under the workspace's own
        assigned apiVersion namespace (minted on first use, then stable).

        ``relations`` (optional) declares what the Kind POINTS AT — the
        ``{field: {to, cardinality, inverse_of, by}}`` block
        ``dna.kernel.kinds.relations`` defines, normalized by the same validator
        a builtin descriptor goes through and checked against ``schema`` in the
        same call. Without it a tenant-authored Kind could not declare a single
        link, so every one of them was an island BY CONSTRUCTION — a product
        that says "model your domain" and then refuses the half of a model that
        is the edges. A malformed or self-contradicting declaration is a 400
        naming the relation.

        **Declaring a relation does not create an edge.** Relations are
        resolved, validated and drawn only for REGISTERED Kinds, and
        registration is what HUMAN approval turns on. An edit clears the
        approval marker, so adding a relation to an already-approved Kind sends
        it back to a person rather than past one. Nothing on this door can
        confer effect, and that is the property to keep.

        ``plane`` (optional) is ``composition`` or ``record``, stored only when
        DECLARED: ``KindDefinitionSpec`` defaults it to ``composition``, and
        whether that default is right for tenant Kinds is an open question with
        a named owner — writing the default into every instance would settle it
        silently and leave it unsettleable.

        ``presentation`` (optional) declares how instances of this Kind READ —
        the ordered fields, their human labels, their semantic roles, and what
        to hide from a human. It is the SAME block a builtin Kind descriptor
        declares, through the same normalizer, and it is what keeps a
        tenant-authored Kind from being second-class: without it, only Kinds
        shipped inside the SDK could tell a surface how to render them. A
        malformed declaration is a 400 naming the offending key — never a card
        that breaks later, in front of a user, with nothing to say.

        The response's ``approved`` is always ``false``. An ``approved_by`` in
        the body is ignored, not honoured and not rejected: a caller that could
        approve its own proposal would make the gate decorative. The instance
        records ``proposed_by`` — the caller's VERIFIED identity, resolved
        server-side (``_actor_from_state``) and never read from the body, and
        stamped here because a proposer cannot be back-filled onto an instance
        that never recorded one. 400 for a missing tenant / a Kind name that is
        not a CamelCase identifier, 403 when the namespace gate refuses the
        write (the workspace does not own the target namespace), 503 when the
        namespace registry scope has not been provisioned in this store.

        **Mounted on every auth mode.** The namespace gate decides from
        ``tenant``: under ``--auth config`` that is bound to the caller's
        VERIFIED identity, under ``--auth none`` there is no second tenant to
        take it from, and under ``--auth token`` — a trusted server-to-server
        lane — it is caller-supplied and the CALLER is responsible for having
        resolved and verified it. See the section comment above for that
        boundary in full."""
        from dna.application.sdlc import now_iso

        live = await _live()
        try:
            return await author_kind_impl(
                live, kind=kind, schema=schema, tenant=tenant or "",
                now=now_iso(), actor=_actor_from_state(request), traits=traits,
                presentation=presentation, relations=relations, plane=plane,
            )
        except LayerPolicyViolationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except FileNotFoundError as exc:
            # A FIRST author on a store whose namespace-registry scope was never
            # provisioned — see _no_registry_scope_detail.
            #
            # This is the face's half only. The deeper fix — reading a missing
            # registry scope as "no claims yet" rather than raising — belongs to
            # dna.application.namespace_assignment, and until it lands this
            # mapping is what stands between the operator and a 500.
            raise HTTPException(
                status_code=503,
                detail=_no_registry_scope_detail(
                    "authored yet: authoring reads the KindNamespace registry "
                    "before it mints a namespace",
                    exc,
                ),
            ) from exc

    # THE ACT THAT CONFERS EFFECT. Registration is what gives a Kind schema
    # validation and storage routing, and the registry's gate withholds it until
    # ``approved_by`` names someone — so this route is not a flag flip with a
    # promise attached, it is the only thing that lets the next load take the
    # Kind at all. A SEPARATE route from authoring by construction: the authoring
    # door builds its spec field by field and cannot write ``approved_by``, so
    # approval necessarily costs a second call, made with whatever identity the
    # second caller holds. Whether that identity must DIFFER from the proposer's
    # is a workspace policy (four-eyes), not a kernel rule — see the impl.

    @app.post("/v1/kinds/{kind}/approve", dependencies=guarded,
              response_model=m.ApproveKindResponse)
    async def approve_kind(
        request: Request,
        kind: str,
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Approve an authored Kind — the act that puts it INTO EFFECT.

        The approver is the caller's VERIFIED identity, resolved server-side
        (``_actor_from_state``: email → durable oid → ``sub``). An
        ``approved_by`` in the body reaches nothing: attribution a caller can
        forge is not attribution. The instance's ``proposed_by`` is preserved
        untouched, so the audit names both acts and neither wears the other's
        name. 404 when no such Kind was authored in this scope (approval acts on
        an existing instance and creates none — and a Kind authored by ANOTHER
        workspace in a shared scope is a 404 too: it is not the caller's to
        approve, and saying "it exists but is not yours" would hand a stranger
        a probe for what its neighbours are authoring), 400 for a missing
        tenant / a malformed Kind name / a Kind the caller declared under two
        of its own namespaces at once, 403 when the namespace gate refuses the
        write, 503 when the namespace registry scope has not been provisioned
        in this store.

        **Mounted on every auth mode**, this one included, and it is the route
        where the ``--auth token`` boundary is worth naming: the whole value of
        the record this act writes is naming WHO made it, and on that lane the
        HTTP layer knows nobody. It records ``rest:unidentified`` — verified
        against the configured secret, naming no person — and the 404 that hides
        a neighbour's Kind rests on the ``tenant`` the caller supplied. That is
        sound exactly insofar as the caller is trusted and resolved the tenant
        from its own verified session first, which is what that lane is for; it
        is the documented trust boundary in the section comment above, and the
        ``TODO(hosted)`` bridge is what would move the check into this door."""
        from dna.application.sdlc import now_iso

        try:
            return await approve_kind_impl(
                await _live(), kind=kind, tenant=tenant or "",
                actor=_actor_from_state(request), now=now_iso(),
            )
        except AuthoredKindNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except StaleInstanceWrite as exc:
            # i-083 — the Kind was edited between the reviewer's read and this
            # approval, so the write was REFUSED rather than allowed to stamp an
            # approval onto a shape nobody saw. 409 and not 400: the request was
            # perfectly well formed and it is the STATE that moved, which is also
            # what tells the client that retrying the identical call is the wrong
            # move and re-reading first is the right one.
            #
            # BEFORE the ``ValueError`` arm below, which it would otherwise fall
            # into — ``StaleInstanceWrite`` is deliberately a ``ValueError`` so
            # that faces which already relay write-path vetoes surface it at all
            # — and be reported as the caller's own malformed request.
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except LayerPolicyViolationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except (NamespaceRegistryUnreadable, FileNotFoundError) as exc:
            # The sibling door has mapped this since it shipped; this one did
            # not, so the same missing directory answered 503 on one route and
            # an unmapped 500 on the other. Approval resolves the KindNamespace
            # registry to check the caller owns the namespace the Kind was
            # authored under — same read, same precondition, same honest answer.
            #
            # BOTH exceptions, because ``FileNotFoundError`` alone was only the
            # filesystem store's spelling of the failure: the core now refuses
            # broadly (``NamespaceRegistryUnreadable``, mirroring the write
            # gate's broad catch), so a transient Postgres registry error
            # refuses here as honestly as a missing `_lib` directory does —
            # instead of 500ing on this door while the write path answered
            # properly.
            raise HTTPException(
                status_code=503,
                detail=_no_registry_scope_detail(
                    "approved: approval resolves the KindNamespace registry to "
                    "check that the caller owns the namespace the Kind was "
                    "authored under, and an unreadable authorization record is "
                    "not a granted one",
                    exc,
                ),
            ) from exc

    # THE ACT THAT WITHDRAWS EFFECT (i-085), and deliberately not the inverse of
    # the one above. Un-approving would return the Kind to *never approved*, and
    # an unregistered Kind is the PERMISSIVE state — its instances are accepted
    # with no validation at all — so revoking by clearing the approval would
    # switch the gate off instead of closing it. Revoked is a THIRD state:
    # existing instances stay readable and are MARKED invalid, new ones are
    # refused, and approving again restores validity with nothing to migrate.
    #
    # It exists BEFORE any approve button reaches a conversational surface, and
    # that order is the point: approving where consent can be misread is only
    # defensible if undoing works.

    @app.post("/v1/kinds/{kind}/revoke", dependencies=guarded,
              response_model=m.RevokeKindResponse)
    async def revoke_kind(
        request: Request,
        kind: str,
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Revoke an authored Kind — the act that WITHDRAWS its effect.

        Every existing instance of the Kind becomes invalid: it is NOT deleted
        and NOT made unreadable, it reads back MARKED (``status.valid ==
        false``), and in a listing it appears marked rather than vanishing — so
        revocation can never be used to hide data without deleting it. New
        instances of the Kind are refused outright, conforming ones included:
        what was withdrawn is the Kind, not a schema.

        The revoker is the caller's VERIFIED identity, resolved server-side, on
        exactly the terms the approval route documents above — including the
        ``--auth token`` caveat, which matters here for the same reason: the
        value of the record this act writes is naming WHO made it.

        ``approved_by`` survives untouched, because revoking is a third act and
        not an erasure of the second. To undo, call the approve route — it is
        the only thing that clears a revocation, and an EDIT deliberately does
        not (an edit that un-revoked would be the loosening through a third
        door).

        Same refusals as its sibling and for the same reasons: 404 when no such
        Kind was authored in this scope — or when it belongs to a neighbour,
        because "it exists but is not yours" would hand a stranger a probe; 400
        for a missing tenant / a malformed Kind name / a Kind the caller
        declared under two of its own namespaces; 409 when the instance moved
        since it was read (i-083 — a revocation is a read-modify-write too, and
        unguarded it would resurrect a stale replica's shape AND mark it
        revoked); 403 from the namespace gate; 503 when the namespace registry
        scope has not been provisioned in this store."""
        from dna.application.sdlc import now_iso

        try:
            return await revoke_kind_impl(
                await _live(), kind=kind, tenant=tenant or "",
                actor=_actor_from_state(request), now=now_iso(),
            )
        except AuthoredKindNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except StaleInstanceWrite as exc:
            # BEFORE the ``ValueError`` arm — see the approval route: it is
            # deliberately a ``ValueError`` so faces that predate the refusal
            # base surface it at all, and 409 rather than 400 is what tells the
            # client to re-read instead of retrying the identical call.
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except LayerPolicyViolationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except (NamespaceRegistryUnreadable, FileNotFoundError) as exc:
            raise HTTPException(
                status_code=503,
                detail=_no_registry_scope_detail(
                    "revoked: revocation resolves the KindNamespace registry to "
                    "check that the caller owns the namespace the Kind was "
                    "authored under, and an unreadable authorization record is "
                    "not a granted one",
                    exc,
                ),
            ) from exc

    @app.get("/v1/kinds", dependencies=guarded,
             response_model=m.AuthoredKindsResponse)
    async def list_authored_kinds(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List the CALLER's authored Kinds with their approval state — the
        audit view. Reads INSTANCES, not the registry: an unapproved Kind is
        precisely the one the registry does not have, and it is the one a
        reviewer came here for.

        FILTERED to what the caller owns (plus inherited and non-namespaced
        rows), because a scope is shared by default and this route otherwise
        handed a caller its neighbours' Kind names, namespaces and
        ``proposed_by``/``approved_by`` — identity strings, i.e. the very fact
        the approval door's 404 exists to withhold. A request that resolves NO
        workspace (``--auth none`` self-host, an explicit operator ``scope=``)
        is not filtered — the same hinge the namespace gate uses for an
        unattributed write. 403 for a namespace two claims give to different
        owners, 503 when the claim registry cannot be read: neither degrades to
        the unfiltered list.

        **Mounted on every auth mode.** The filter is what makes this route the
        CALLER's roster rather than the scope's, and it is computed from
        ``tenant``. Under ``--auth config`` that is the verified identity's
        workspace; under ``--auth token`` it is whatever the trusted caller
        supplied, having resolved it from its own verified session first — so
        the roster is the caller's to the exact extent the caller is. See the
        section comment above."""
        try:
            return await list_authored_kinds_impl(
                await _live(), tenant=tenant, scope=scope,
            )
        except LayerPolicyViolationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (NamespaceRegistryUnreadable, FileNotFoundError) as exc:
            raise HTTPException(
                status_code=503,
                detail=_no_registry_scope_detail(
                    "listed: the listing resolves the KindNamespace registry to "
                    "decide which authored Kinds belong to the caller, and an "
                    "unreadable authorization record is not a granted one",
                    exc,
                ),
            ) from exc

    # -- the Kind CATALOG ------------------------------------------------------
    #
    # Declared HERE, above ``/v1/kinds/{kind}``, for the reason the singular
    # ``/v1/kinds/registry/{kind}`` is declared above ``/{kind}/instances``:
    # FastAPI matches in declaration order, and ``registry`` is a literal
    # segment a Kind can never collide with (a Kind name is CamelCase).

    @app.get("/v1/kinds/registry", dependencies=guarded,
             response_model=m.RegisteredKindsResponse)
    async def list_registered_kinds(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """The Kind CATALOG of a scope — every Kind the registry actually
        serves here, with the facts a caller needs before acting on one.

        The gap this closes is the enumeration itself. ``list_kinds_impl`` has
        answered "what can I act on here?" for the MCP face since the catalog
        existed, and the read-API had only the SINGULAR
        ``/v1/kinds/registry/{kind}`` — so every REST consumer that wanted the
        list had to hardcode one. A hardcoded list is precisely how a Kind that
        gets registered tomorrow stays invisible: the enumeration is the whole
        point, and it belongs to the registry, not to each caller.

        Not the same question as ``GET /v1/kinds``, and the two must not be
        confused. That one lists the caller's AUTHORED KindDefinition instances
        including the unapproved ones — the audit roster, whose subject is an
        approval decision. This one lists what is REGISTERED and therefore in
        force, built-ins included; an unapproved Kind is by definition absent.

        Like its singular sibling, it does NOT filter by caller: a registered
        Kind is the product's data model, identical for every tenant and
        holding nobody's content. It also does not filter by PLAN — the MCP
        catalog shortens itself to a caller's unlocked feature families, and
        this face has no per-request plan the way that one does, so
        ``filtered_by_plan`` is always false here rather than quietly meaning
        something different from the same field on the other face.

        ``tenant`` resolves the scope the way every instance route does
        (``live.default_scope``), so a portal that only knows a workspace id
        reaches that workspace's own registered Kinds without hardcoding the
        scope-prefix convention. An explicit ``scope`` still wins."""
        return await list_kinds_impl(await _live(), scope=scope, tenant=tenant)

    # ONE authored Kind, IN FULL — the audit screen's read. The listing above
    # projects ten summary fields and deliberately not ``spec.schema`` (a roster
    # that inlined every JSON Schema would be unreadable), which left a reviewer
    # unable to see what they would be conferring effect ON. Registration is what
    # gives a Kind schema validation and storage routing, so "should this take
    # effect?" is a question about the schema; this route is the answer.
    #
    # It therefore hands over strictly MORE than the listing, and inherits every
    # decision the listing and the approval door already made: the same
    # ``owner_of`` ownership walk, the same 404-not-403 for a neighbour's Kind,
    # the same shared Kind-name validator on the path segment, and the same
    # refusal to degrade to an unfiltered answer.

    @app.get("/v1/kinds/{kind}", dependencies=guarded,
             response_model=m.AuthoredKindDetail)
    async def get_authored_kind(
        kind: str,
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Read ONE authored Kind in full — the listing's row PLUS the
        ``schema`` and the ``traits``, i.e. everything a human needs to answer
        "should this take effect?".

        Filtered to the CALLER exactly as the listing is, and harder-edged
        because it carries more: a Kind authored by another workspace in a
        shared scope is a **404**, the same answer a Kind nobody ever authored
        gets — "it exists but is not yours" would hand a stranger a probe for
        what its neighbours are authoring, and this door would answer that probe
        with their data model. A request that resolves NO workspace
        (``--auth none`` self-host, an explicit operator ``scope=``) is not
        filtered, the same hinge the namespace gate uses for an unattributed
        write.

        400 for a ``kind`` that is not a CamelCase identifier (the same shared
        guard the authoring and approval doors use — it is a path segment here)
        or for a Kind the caller declared under two of its own namespaces at
        once; 403 for a namespace two claims give to different owners; 503 when
        the claim registry cannot be read. None of them degrades to answering
        with the instance.

        **Mounted on every auth mode**, and this route carries the most: the
        workspace's JSON Schema, i.e. its data model. The 404 that keeps a
        neighbour's Kind invisible is decided from ``tenant``, so under
        ``--auth config`` it is enforced against a verified identity and under
        ``--auth token`` it is enforced against what the trusted caller
        resolved and supplied. See the section comment above for that
        boundary."""
        try:
            return await get_authored_kind_impl(
                await _live(), kind=kind, tenant=tenant, scope=scope,
            )
        except AuthoredKindNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except LayerPolicyViolationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except (NamespaceRegistryUnreadable, FileNotFoundError) as exc:
            raise HTTPException(
                status_code=503,
                detail=_no_registry_scope_detail(
                    "read: the read resolves the KindNamespace registry to "
                    "decide whether the authored Kind belongs to the caller, "
                    "and an unreadable authorization record is not a granted "
                    "one",
                    exc,
                ),
            ) from exc

    @app.get("/v1/kinds/registry/{kind}", dependencies=guarded,
             response_model=m.RegisteredKindView)
    async def get_registered_kind(
        kind: str,
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """The descriptor of a REGISTERED Kind — its JSON ``schema`` plus the
        ``ui_schema`` widget hints, so a form can DERIVE validation (min/max,
        enums, required) instead of hand-copying it and drifting.

        The registry sibling of ``GET /v1/kinds/{kind}`` (which reads an
        AUTHORED Kind and filters by caller): a registered Kind is the
        PRODUCT's data model, identical for every tenant and holding nobody's
        content, so this door does not filter. Declared BEFORE the
        ``/{kind}/instances`` routes so ``registry`` is matched as the literal
        segment it is (a Kind is CamelCase and can never be named
        ``registry``). 404 for a Kind the runtime does not register.

        ``tenant`` (i-094) resolves the scope the way EVERY instance route
        does (``live.default_scope`` — under multi-workspace, ``tenant-<ws>``
        for an outside workspace), so a portal that only knows the workspace
        id reaches the workspace's OWN registered Kinds without hardcoding
        the scope-prefix convention. An explicit ``scope`` still wins — it is
        the older, narrower contract and existing callers keep it."""
        live = await _live()
        if not (scope and scope.strip()) and tenant and tenant.strip():
            scope = live.default_scope(tenant.strip())
        try:
            return await read_registered_kind_impl(live, kind=kind, scope=scope)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    # -- the SCHEMA graph: the registry's SET answer, in ONE call --------------
    #
    # The registry sibling above answers "what does THIS Kind look like?". The
    # question it could not answer is the SET one — "which Kinds reference
    # which here?" — and the portal was paying for the gap: N calls to
    # ``/v1/kinds/registry/{kind}``, a queue with concurrency 4, on EVERY
    # render of the Kind catalogue, to rebuild in memory a graph the registry
    # already holds whole. Latency that grew with the workspace, for a fact
    # that is one projection away.
    #
    # NOT under /v1/kinds/**: this is not a Kind resource, and mounting it
    # there would collide with the CamelCase ``{kind}`` segment the routes
    # above own. ``/v1/graph/`` is its own noun — and it is the noun the DATA
    # graph will land under too (an instance's inbound/outbound references),
    # which is a different question with the same shape.
    #
    # NOT FILTERED BY CALLER, like its registry sibling and for the same
    # reason: a registered Kind is the PRODUCT's data model — identical for
    # every tenant, holding nobody's content. What IS caller-visible is the
    # scope, and it is resolved exactly as the registry route resolves it.
    #
    # THE ANSWER CARRIES ITS OWN CAVEATS. ``coverage`` states how many edges
    # each tier contributed, which tiers the runtime enforces, and — in
    # ``limits`` — the four things this graph structurally cannot see. That is
    # not decoration: 16 of the model's 109 schema edges are declared, and a
    # screen rendering the list as "the relations" would be asserting a
    # completeness this repo does not have. Shipping the qualifier ON the wire
    # is what stops each consumer from having to remember it.

    @app.get("/v1/graph/kinds", dependencies=guarded,
             response_model=m.KindGraphResponse)
    async def kind_graph(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """The SCHEMA graph of the registered Kinds — which Kind may point at
        which, through which field, in ONE call.

        Replaces "read every Kind's descriptor and derive the graph in the
        client", which cost one request per Kind and got slower as a workspace
        grew. Same projection that generates ``docs/reference/data-model.md``:
        the tiering, the ``spec.relations`` reading (the SAME one the write path
        validates with) and the gap tables live in the SDK, so the page and
        this route cannot disagree about what the model says.

        **SCHEMA, not data.** The edges say which Kinds MAY reference which.
        Which INSTANCES reference which is a different graph and this route
        does not answer it — ``coverage.limits`` says so on the wire.

        ``tenant`` resolves the scope the way the registry route does
        (``live.default_scope``); an explicit ``scope`` still wins. No 404:
        a scope with no Kinds is an empty graph with a coverage block that
        says ``kinds: 0``, which is an answer — conflating it with "no such
        scope" would make a screen say *error* where it should say *nothing
        registered yet*."""
        live = await _live()
        if not (scope and scope.strip()) and tenant and tenant.strip():
            scope = live.default_scope(tenant.strip())
        return await kind_graph_impl(live, scope=scope)

    # -- the generic, kubernetes-shaped instance write ------------------------
    #
    # POST /v1/kinds/{kind}/instances. The gap this closes: every write route
    # above is PER-KIND (memories, artifacts, the Kind-authoring doors,
    # projects, workspaces, tenants) — an instance of an ARBITRARY Kind,
    # including one a tenant just authored and had approved, had no REST door
    # at all. Without it, a proposer (e.g. an instance-converter agent) that
    # authors a Kind and matches a typed instance to it has nowhere to write
    # the instance through the shared REST lane the portal calls.
    #
    # THE SHAPE IS KUBERNETES', DELIBERATELY (the plan cites it verbatim):
    # applying a CRD CREATES an endpoint that serves that type; "kind is a
    # string representing the REST resource — servers can infer it from the
    # endpoint the client submits to"; and since 1.25 the API server VALIDATES
    # every create/update against the registered schema before persisting.
    # Hence the route: the PATH carries the Kind (the k8s convention), the
    # body carries only what k8s calls ``metadata``/``spec``, and the SERVER
    # validates — never a portal-side schema check reasoning from a belief
    # formed turns earlier.
    #
    # ZERO business logic here: this is a thin delegate to the SAME
    # ``write_instance_impl`` the MCP ``write_instance`` tool already calls —
    # the bootstrap refusal, the LayerPolicy gate, the schema validation and
    # the merge semantics are the kernel's, inherited for free.
    #
    # THE KIND COMES FROM THE PATH, NEVER THE BODY. A body that names a
    # DIFFERENT kind is refused (400) below, explicitly — neither "the path
    # wins silently" nor "the body wins": two sources stating one fact is the
    # exact defect this project spent a day fixing elsewhere, and this route
    # does not reintroduce it.
    #
    # IDENTITY AND SCOPE ARE NOT CALLER INPUT. Unlike the Model-B routes above
    # (``register_artifact`` / ``create_project``, which take a ``claims``
    # body field because a TRUSTED portal vouches an already-verified session
    # under none/token auth), this route takes NEITHER a ``claims`` field NOR
    # a ``scope`` query param — it follows the Kind-authoring doors' shape
    # instead: only ``tenant`` as a query param, on the SAME trust boundary
    # those doors instance at length (config-bound / no second tenant under
    # none / a trusted caller's own resolved value under token). The write
    # scope is always DERIVED from ``tenant`` (``live.default_scope``),
    # exactly as the artifact/project routes derive theirs — there is simply
    # no second field here a caller could use to name a scope directly.
    # Pinned against the PUBLISHED OpenAPI schema by
    # ``tests/test_rest_documents.py`` (the REST analogue of
    # ``test_tools_bind_their_scope.py``'s source-pattern guard for the MCP
    # tools), not against this function's Python signature.
    #
    # MOUNTED ON EVERY AUTH MODE, like the Kind-authoring doors it depends on
    # (an instance under a freshly-approved Kind is unreachable if this route
    # were lane-conditional while authoring/approval are not).

    @app.get("/v1/kinds/{kind}/instances", dependencies=guarded,
             response_model=m.ListKindInstancesResponse)
    async def list_kind_instances(
        kind: str,
        tenant: str | None = Query(default=None),
        api_version: str | None = Query(default=None),
        # E3: sem default nem teto FIXOS — a CognitivePolicy do workspace
        # decide (default_limit quando omitido; max_limit clampa o explícito).
        limit: int | None = Query(default=None, ge=1),
        offset: int = Query(default=0, ge=0),
        fields: str | None = Query(default=None),
        order_by: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Listar as instâncias de ``{kind}`` — a LEITURA da porta genérica.

        A face escrevia qualquer instância por ``POST
        /v1/kinds/{kind}/instances`` e só lia os Kinds para os quais alguém
        escrevera uma rota à mão (``/v1/memories``, ``/v1/projects``, …). O
        ``list_instances_impl`` já existia no SDK, completo, e não tinha porta:
        quem gravava por aqui não conseguia ler de volta por lugar nenhum, e
        descobria isso depois de gravar.

        ``fields`` (CSV, caminhos pontuados; sem prefixo resolve sob ``spec.``)
        empurra a PROJEÇÃO para o kernel. Sem ela, responder "quais estão
        abertos" custa 1 + N chamadas — listar os nomes e ler cada um. No
        Postgres a projeção vira SELECT e a linha viaja aparada.

        Um Kind desconhecido é 404 **nomeando o Kind**, a mesma resposta que a
        escrita dá. Uma lista vazia de um Kind que existe é 200 com
        ``instances: []`` — "existe e não tem nada" é uma resposta, e confundi-la
        com "não existe" faria uma tela dizer *erro* onde devia dizer *nenhum
        ainda*.
        """
        live = await _live()
        try:
            return await list_instances_impl(
                live, kind=kind, tenant=tenant,
                api_version=api_version, limit=limit, offset=offset,
                fields=[f.strip() for f in fields.split(",") if f.strip()] if fields else None,
                order_by=[o.strip() for o in order_by.split(",") if o.strip()] if order_by else None,
            )
        except UnknownKindError as exc:
            # 404 NOMEANDO o Kind — a mesma resposta que a escrita dá. Um leitor
            # não pode descobrir que o Kind não existe por uma lista vazia, que é
            # indistinguível de "existe e está vazio".
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.get("/v1/kinds/{kind}/instances/{name}", dependencies=guarded,
             response_model=m.GetKindInstanceResponse)
    async def get_kind_instance(
        kind: str,
        name: str,
        tenant: str | None = Query(default=None),
        api_version: str | None = Query(default=None),
        as_of: str | None = Query(
            default=None,
            description=(
                "ISO-8601 instant. Return the instance AS THIS STORE RECORDED "
                "IT at that moment (transaction time) instead of its current "
                "state. Refuses rather than approximates: 501 if the store "
                "keeps no version history, 410 if this instance's history was "
                "pruned past the instant, 404 if it did not exist yet."
            ),
        ),
    ) -> dict[str, Any]:
        """Ler UMA instância de ``{kind}``, VERBATIM — o que a lista não dá.

        A lista com ``fields`` projeta pela VISTA quando o Kind é produzível
        por readers (Agent, Skill…), e a vista normaliza — campos reais do
        spec gravado (``description``, ``tools_requiring_confirmation`` de um
        Agent) não viajam por ela. Quem gravou pelo POST genérico precisa
        conseguir ler DE VOLTA o que gravou: esta rota é o
        ``get_instance_impl`` de sempre, na mesma fronteira de confiança do
        POST (só ``tenant``; o scope é derivado, nunca nomeado).

        404 nomeia o que faltou — o Kind desconhecido ou a instância.

        ``as_of`` (i-106) é a leitura no TEMPO, e chegou aqui por um defeito, não
        por um pedido: esta rota já **aceitava** ``?as_of=`` — o FastAPI descarta
        em silêncio um query param não declarado — e devolvia 200 com o presente.
        Medido em 06/08/2026: um Issue de 18 versões respondia `resolved` com 6
        eventos tanto agora quanto "às 14:00 do dia anterior", quando às 14:00 do
        dia anterior ele não era nem uma coisa nem outra. Aceitar e ignorar é
        pior que recusar: o chamador acredita ter visto o passado e nada na
        resposta o desmente.

        As QUATRO saídas são distintas de propósito, porque colapsar duas
        quaisquer delas reintroduz o mesmo defeito uma casa adiante:

        * **200** — o estado de crença naquele instante, com ``as_of``,
          ``as_of_version`` e ``as_of_recorded_at`` no corpo.
        * **404** — não existia ainda. Isto é uma RESPOSTA.
        * **410** — existia história, mas não tão atrás: as versões daquela época
          foram podadas (``VERSION_CHURN_RETENTION``). O store não sabe, e dizer
          404 aqui seria afirmar "não existia" a partir de "não há registro".
        * **501** — este deployment não guarda histórico nenhum (o adapter de
          filesystem declara ``versions=True`` e não retém nada).

        e **422** quando o instante não é ISO-8601 — erro do chamador, não do
        servidor."""
        from dna.memory.as_of import AsOfTruncated, AsOfUnsupported

        live = await _live()
        try:
            return await get_instance_impl(
                live, kind=kind, name=name, tenant=tenant,
                api_version=api_version, as_of=as_of,
            )
        except UnknownKindError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except AsOfUnsupported as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from None
        except AsOfTruncated as exc:
            # 410 Gone, and it must NOT be the 404 the sibling branch gives: the
            # pruning is deliberate and permanent, and "no record" is not
            # "no instance". LookupError's subclass, so this except comes FIRST.
            raise HTTPException(status_code=410, detail=str(exc)) from None
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except AmbiguousKindError as exc:
            # 400 like the sibling list route — the ambiguity is about the KIND,
            # not about `as_of`, and the two must not answer with one code.
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @app.get("/v1/instances/{id}", dependencies=guarded,
             response_model=m.ResolveInstanceResponse)
    async def resolve_instance(
        id: str,
        tenant: str | None = Query(default=None),
        scope: str | None = Query(
            default=None,
            description=(
                "Narrow the search to one scope. Normally unnecessary — ids "
                "are unique across the store, and not needing to know the "
                "scope is most of what an id buys."
            ),
        ),
    ) -> dict[str, Any]:
        """Expand a short ``metadata.id`` PREFIX to the one instance it names.

        The id lane (i-114). The ``{kind}/{name}`` routes are the NAME lane and
        stay exactly as they were: a name is the address a human authors and
        reviews in a diff, and it is what a ``.dna/`` reference keeps. An id is
        the identity underneath it — stable across a rename, and the value
        ``dna_edges.to_id`` records beside every target name.

        Resolution is by unique prefix, the way ``git`` expands a short commit
        hash. Four to twelve characters; the response echoes the FULL id.

        The status codes are the whole contract:

        * **200** — exactly one instance matches.
        * **409** — MORE THAN ONE matches, and this is the refusal the feature
          exists for. Answering with the first match would be indistinguishable
          from answering correctly: same shape, same 200, nothing in the body
          to say a coin was flipped. The detail names the candidates so the
          caller can lengthen the prefix.
        * **404** — nothing matches.
        * **422** — the prefix is shorter than four characters, or is not an
          id at all. A one-character prefix is a typo, not a question, and
          calling it "ambiguous" would hide that the query is the problem.
        * **501** — this deployment's store cannot search by id.
        """
        from dna.kernel.errors import InstanceIdLookupUnsupported
        from dna.kernel.identity import (
            AmbiguousInstanceId, PrefixTooShort, UnknownInstanceId,
        )

        live = await _live()
        try:
            return await resolve_instance_impl(
                live, id=id, scope=scope, tenant=tenant,
            )
        except InstanceIdLookupUnsupported as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from None
        except AmbiguousInstanceId as exc:
            # 409 and NOT 300/400: the request was well formed and the store
            # answered — the conflict is in the data the caller is pointing at.
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except PrefixTooShort as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except UnknownInstanceId as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    @app.get("/v1/kinds/{kind}/instances/{name}/refs", dependencies=guarded,
             response_model=m.GraphRefsResponse)
    async def graph_refs(
        kind: str,
        name: str,
        tenant: str | None = Query(default=None),
        api_version: str | None = Query(default=None),
        direction: str = Query(default="in"),
        depth: int = Query(default=1, ge=1),
        as_of: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """"O que depende desta instância?" — o grafo de DADO, com profundidade.

        A tela do Kind sempre soube dizer que ``Story.feature → Feature``
        existe como REGRA, e nunca soube dizer que ESTAS 47 Stories apontam
        para ESTA Feature. Esta rota responde a segunda pergunta, lendo as
        arestas que o próprio write path produziu ao validar as referências —
        nada aqui deriva, adivinha ou lê slug.

        ``direction=in`` (o default, e a pergunta do produto) traz quem aponta
        para cá; ``out`` o que esta instância aponta; ``both`` a união.
        ``depth`` é OBRIGATÓRIO ter teto: ``Spec.supersedes`` e
        ``Story.dependencies`` são auto-referentes por desenho, e uma travessia
        sem limite aqui é incidente de produção, não risco teórico. O valor é
        clampado ao teto do kernel (``DNA_GRAPH_MAX_DEPTH``).

        ``as_of`` (ISO-8601) devolve **o grafo como ele era naquele instante de
        TRANSAÇÃO** — a quarta coordenada da mesma pergunta. Ele é re-derivado
        das versões, não filtrado das arestas: ``dna_edges`` é substituída a
        cada escrita e não guarda história nenhuma.

        **501, nunca lista vazia**, quando o adapter ativo não guarda arestas
        (o filesystem não tem transação nem tabela para guardá-las). ``[]``
        se lê como "nada aponta para esta instância", e essa é uma afirmação
        que só um store que de fato registra arestas pode fazer. Também **501**
        quando o store não retém história e o pedido tem ``as_of`` — o grafo de
        hoje sob um carimbo do passado é a mesma mentira, mais confiante.

        **410** quando a instância TEM história e nenhuma alcança ``as_of``: as
        versões daquela época foram podadas, e "não dá para saber" não é 404.
        **404** quando ela não existia ainda naquele instante — aí é resposta.
        """
        from dna.kernel.query.graph import GraphUnsupported
        from dna.memory.as_of import AsOfTruncated, AsOfUnsupported

        live = await _live()
        try:
            return await graph_refs_impl(
                live, kind=kind, name=name, tenant=tenant,
                api_version=api_version, direction=direction, depth=depth,
                as_of=as_of,
            )
        except UnknownKindError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except GraphUnsupported as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from None
        except AsOfUnsupported as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from None
        except AsOfTruncated as exc:
            # 410 Gone, and it must NOT be the 404 the next arm gives: "the
            # record of that era is gone" and "it did not exist yet" are
            # opposite facts about the same silence, and a caller acting on the
            # wrong one acts on a graph that never existed. ⚠️ BEFORE the bare
            # ``LookupError`` arm — ``AsOfTruncated`` IS one, and being caught
            # there is exactly how the distinction dies.
            raise HTTPException(status_code=410, detail=str(exc)) from None
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.post("/v1/kinds/{kind}/instances", dependencies=guarded, status_code=201,
              response_model=m.WriteKindInstanceResponse)
    async def write_kind_instance(
        request: Request,
        kind: str,
        body: m.WriteKindInstanceRequest,
        api_version: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
        merge: bool = Query(default=True),
        if_match: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Write one instance of ``{kind}`` — the generic door, kubernetes-shaped.

        The body is exactly ``{metadata, spec}`` (plus the optional
        ``source_sha256`` provenance citation). ``metadata.name`` is
        REQUIRED — 400 when blank or absent. A ``kind`` in the body that
        DIFFERS from the path is refused (400); one that matches is a no-op
        (redundant, not wrong).

        The write goes through the kernel's own pipeline exactly as the MCP
        ``write_instance`` tool's does: the Kind's JSON Schema validates
        ``spec`` and names the offending field on refusal (400), a BOOTSTRAP
        Kind (Genome / LayerPolicy / KindDefinition) is refused (403, the
        generic write's own gate — untouched, not relaxed here), an authored
        Kind nobody has approved yet resolves to nothing in the registry and
        is a 404 naming it (the SAME answer a Kind that was never authored at
        all gets — there is no third state visible from here), an unknown
        Kind is a 404 naming it, and a stale ``if_match`` is a 409.

        ``source_sha256`` (optional) cites the ``SourceArtifact`` this
        instance was extracted from (by content address); the runtime closes
        the ``derived_refs`` provenance edge server-side, preserving every
        OTHER instance already recorded there and updating THIS instance's
        own entry in place on a re-write — never accreting a duplicate. A
        ``source_sha256`` that names no registered artifact under ``tenant``
        is refused (400)."""
        if body.kind is not None and body.kind != kind:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"the body names kind {body.kind!r}, the path names "
                    f"{kind!r} — refusing rather than picking one silently. "
                    f"The path is the single source of truth for which Kind "
                    f"is written here: omit `kind` from the body, or make it "
                    f"match the path."
                ),
            )
        name = (body.metadata or {}).get("name")
        name = name.strip() if isinstance(name, str) else ""
        if not name:
            raise HTTPException(
                status_code=400, detail="metadata.name is required",
            )
        await _gate_kind_write(
            request, kind=kind, api_version=api_version, tenant=tenant,
        )
        try:
            return await write_instance_impl(
                await _live(), kind=kind, name=name, spec=body.spec,
                tenant=tenant, api_version=api_version, merge=merge,
                if_match=if_match, source_sha256=body.source_sha256,
            )
        except BootstrapKindWriteRefused as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LayerPolicyViolationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except UnknownKindError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except ConcurrentWriteError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except (AmbiguousKindError, ValueError, LookupError) as exc:
            raise HTTPException(
                status_code=400, detail=f"{type(exc).__name__}: {exc}"
            ) from None

    # -- bundle entries (list/read/write/revert a bundle-file fork, plane B) -
    # A bundle-pattern Kind (Skill, and any future bundle Kind) stores MULTIPLE
    # files per instance, not a single spec — these routes are the file-grained
    # twin of the three definition routes above, generic over any bundle Kind
    # (routed by the Kind's StorageDescriptor pattern, never Skill-specific),
    # with the SAME LayerPolicy governance: a fork on a LOCKED Kind is vetoed
    # (403). Zero business logic here — thin delegates to the SAME core
    # ``*_bundle_entry(ies)_impl`` use-cases Task 2 added. ``{entry:path}``
    # captures the entry's own ``/`` (e.g. ``scripts/hello.py``).

    @app.get("/v1/definitions/{kind}/{name}/entries", dependencies=guarded,
             response_model=m.BundleEntriesView)
    async def list_bundle_entries(
        kind: str, name: str,
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List a bundle instance's entry files (base ∪ tenant overlay), each
        flagged ``overridden`` — whether THIS tenant forked that specific
        file. 404 for a non-bundle Kind or an unknown (kind, name)."""
        live = await _live()
        try:
            return await list_bundle_entries_impl(
                live, scope=scope or live.base_scope, tenant=tenant,
                kind=kind, name=name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    @app.get("/v1/definitions/{kind}/{name}/entries/{entry:path}",
             dependencies=guarded, response_model=m.BundleEntryView)
    async def get_bundle_entry(
        kind: str, name: str, entry: str,
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Read one bundle entry's effective content (tenant overlay wins over
        base), plus whether THIS tenant forked it and whether it's binary
        (reported honestly rather than mangling bytes into ``content``). 404
        for a non-bundle Kind or an unknown entry (the kernel's fetch raises
        ``FileNotFoundError`` for a missing file, ``ValueError`` for a
        non-bundle Kind — both map to the same 404 the caller sees)."""
        live = await _live()
        try:
            return await read_bundle_entry_impl(
                live, scope=scope or live.base_scope, tenant=tenant,
                kind=kind, name=name, entry=entry,
            )
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    @app.put("/v1/definitions/{kind}/{name}/entries/{entry:path}",
             dependencies=guarded, response_model=m.BundleEntryWriteResponse)
    async def put_bundle_entry(
        kind: str, name: str, entry: str,
        body: m.WriteBundleEntryRequest,
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Fork one bundle entry into the tenant layer (the editor's
        file-level Save) — a tenant-layer write via the SAME core
        ``write_bundle_entry_impl`` the CLI uses. A LOCKED Kind is vetoed by
        the kernel's LayerPolicy check, surfaced here as 403 (never silently
        dropped)."""
        live = await _live()
        try:
            return await write_bundle_entry_impl(
                live, scope=scope or live.base_scope, tenant=tenant,
                kind=kind, name=name, entry=entry, content=body.content,
            )
        except LayerPolicyViolationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.delete("/v1/definitions/{kind}/{name}/entries/{entry:path}",
                dependencies=guarded, response_model=m.BundleEntryWriteResponse)
    async def delete_bundle_entry(
        kind: str, name: str, entry: str,
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Revert a tenant's fork of one bundle entry — deletes the
        tenant-layer file so reads fall back to the inherited base (the
        editor's "Reset to default", file-grained)."""
        live = await _live()
        try:
            return await revert_bundle_entry_impl(
                live, scope=scope or live.base_scope, tenant=tenant,
                kind=kind, name=name, entry=entry,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    # -- reconcile (2-way diff of a tenant's forks vs base-NOW, plane B2) ----
    # READ-only — no new write route. A tenant's fork can drift because the
    # BASE moved on (an upstream release), not because the tenant changed
    # anything; this is the file-grained "what changed under me" view. The
    # three resolutions an editor offers over this are all EXISTING B1
    # routes: keep = no-op, take-base = the DELETE above, edit = the PUT
    # above. Thin delegate to the SAME core ``reconcile_forks_impl``.

    @app.get("/v1/definitions/{kind}/{name}/reconcile", dependencies=guarded,
             response_model=m.ReconcileView)
    async def reconcile_forks(
        kind: str, name: str,
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """For each of the tenant's forked bundle-entry files, diff the
        fork's content (``mine``) against the base's CURRENT content
        (``base``) — ``identical`` only when a base exists and its bytes
        match; a tenant-added file (no base at all) is always
        ``diverged`` with ``base: None``. 404 for a non-bundle Kind."""
        live = await _live()
        try:
            return await reconcile_forks_impl(
                live, scope=scope or live.base_scope, tenant=tenant,
                kind=kind, name=name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    # -- memory (list + search + the two guarded writes: remember + delete) --

    async def _as_of_guarded(coro):
        """Map the two transaction-time refusals onto HTTP, honestly.

        The whole point of ``as_of`` is that it never guesses, so neither may
        this face: a bad timestamp is the CALLER's error (422) and a store with
        no version history is THIS DEPLOYMENT's limit (501, `Not Implemented` —
        the request was well-formed and the server cannot fulfil it). Returning
        200 with the current state under either would hand back a fabricated
        past wearing a real answer's shape."""
        from dna.memory.as_of import AsOfUnsupported
        try:
            return await coro
        except AsOfUnsupported as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @app.get("/v1/memories", dependencies=guarded, response_model=m.MemoriesResponse)
    async def memories(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
        as_of: str | None = Query(
            default=None,
            description=(
                "ISO-8601 instant. List the BELIEF STATE at that moment "
                "(transaction time) instead of the current one."
            ),
        ),
    ) -> dict[str, Any]:
        """List the tenant's memory — base + the tenant's OWN overlay (per the #83
        isolation), never another tenant's.

        Delegates to the CORE ``list_memories_impl`` (i-079). This route used to
        carry its own copy, which had drifted into answering a different
        question: it hid a memory carrying ANY ``valid_to``, where the core and
        ``recall`` both use ``currently_valid`` and keep one whose expiry has not
        arrived. The sibling ``/v1/memories/personal`` already delegated, so the
        same memory was listed there and missing here — on one screen.

        Delegating also changes WHICH SCOPE is read, and that is the least
        visible half of the same bug. The copy resolved ``scope or
        live.base_scope``; ``remember``, ``recall`` and ``forget`` all resolve
        ``default_scope(tenant)`` — under multi-workspace, ``tenant-<ws>`` for a
        non-vendor workspace. The list was therefore reading a scope that
        workspace never writes to, so a memory it had just stored and could
        still recall was missing from its own list. It now reads the same home
        its writes land in, like every sibling route on this face.

        ``tenant`` is echoed back from the REQUEST rather than taken from the
        core's result, which does not return it. Dropping it would have silently
        removed a field from a published response shape while fixing a different
        bug, and a caller cannot tell "the field is gone" from "the value is
        null"."""
        from dna.application import list_memories_impl

        async def _run() -> dict[str, Any]:
            return await list_memories_impl(
                await _live(), scope, tenant=tenant, as_of=as_of,
            )
        out = await _as_of_guarded(_run())
        return {**out, "tenant": tenant}

    @app.get("/v1/memories/personal", dependencies=guarded,
             response_model=m.PersonalMemoriesResponse)
    async def personal_memories(
        request: Request,
        scope: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List the CALLER'S OWN personal memories — the READ face of the
        partition ``POST /v1/memories/import`` writes (i-046: the founder
        imported a memory and no portal surface could show it).

        Same identity contract as the import, MIRRORED not re-derived: the
        ``personal:<oid>`` partition is resolved SERVER-SIDE from the verified
        token's claims (``--auth config``), and is never accepted from the
        query or body — a ``tenant``/``oid``/``personal_id`` a client sends is
        IGNORED (INV-PERSONAL layer 1). A SHARED bearer (``--auth token``) is
        not an identity, so that mode is always 403; ``--auth none`` (the
        single-user local deployment) may read ``DNA_PERSONAL_ID``, and there
        is no such fallback on an authenticated deployment. No resolvable
        identity ⇒ 403, nothing read.

        The result unions the personal partition with the shared base scope
        (never any workspace's memory); each item is the ``list_memories``
        shape enriched with the per-ITEM ``personal`` flag (i-068), so a UI
        can chip the caller's own memories apart from the shared riders.

        ``scope`` is accepted for back-compat but the read is PINNED to the
        server's base scope (i-069): every personal write lands there, so a
        forwarded workspace scope (``tenant-<ws>``) would target a partition
        nothing ever writes to and return an honest-looking EMPTY list while
        the caller's memories exist — personal reads and writes must resolve
        the SAME home. The response's ``scope`` reports the pinned home."""
        from dna.application import list_memories_impl as core_list_memories_impl
        from dna.memory.personal import (
            PersonalIdentityRequired,
            PersonalOverrideRejected,
        )
        from dna_cli._mcp_auth import personal_identity_from_claims

        claims = _actor_claims_from_state(request) if auth == "config" else None
        try:
            oid, family = personal_identity_from_claims(
                claims,
                token_present=(auth == "config"),
                allow_env_fallback=(auth == "none"),
            )
        except (PersonalIdentityRequired, PersonalOverrideRejected) as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None

        try:
            out = await core_list_memories_impl(
                await _live(), scope,
                memory_scope="personal", oid=oid, family=family,
            )
        except PersonalIdentityRequired as exc:  # defense in depth (core re-checks)
            raise HTTPException(status_code=403, detail=str(exc)) from None
        # `partition` echoes the SCHEME only — the concrete personal:<oid>
        # value never goes back onto the wire (mirrors the import response).
        return {
            "scope": out["scope"],
            "partition": "personal",
            "memories": out["memories"],
        }

    @app.post("/v1/memories", dependencies=guarded, status_code=201,
              response_model=m.RememberResponse)
    async def remember_memory(
        request: Request,
        summary: str = Body(..., embed=True),
        area: str = Body(default="general", embed=True),
        tags: list[str] | None = Body(default=None, embed=True),
        affect: str = Body(default="triumph", embed=True),
        owner: str = Body(default="portal", embed=True),
        claims: list[dict[str, Any]] | None = Body(
            default=None, embed=True,
            # The ONE instruction, from `dna.memory.contradiction`, on the FIELD
            # rather than in the route summary: whoever decides what to send in
            # `claims` is reading this schema (Swagger, and the generated
            # client's own type), and a rule kept one paragraph away is a rule
            # read by nobody. Same text the MCP tool announces and `dna memory
            # remember --help` prints — three faces, one sentence.
            description=(
                "Structured assertions — `[{subject?, predicate, object?, "
                "polarity?}]` — that make this memory comparable to another for "
                "CONTRADICTION (s-grafo-2-contradicao) instead of only for "
                "lexical repetition. A malformed claim is a 400 naming the "
                "offending index and field; nothing is written.\n\n"
                + WHEN_TO_CLAIM
            ),
        ),
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Persist ONE memory (an ``Engram``) into the tenant's OWN overlay
        — the portal's ``remember`` / add affordance, tenant-scoped from the
        session (never base, never another tenant). Reuses the SAME CORE
        ``remember_impl`` the MCP ``remember`` tool delegates to (one core, three
        faces), so a memory added here is recalled identically by MCP/CLI. The
        deterministic ``_slug(summary)`` name it returns is the id the portal's
        ``DELETE /v1/memories/{name}`` targets to undo it.

        ``claims`` — ``[{subject?, predicate, object?, polarity?}]`` — are the
        memory's structured assertions, what makes it comparable to another
        memory for CONTRADICTION (s-grafo-2-contradicao) rather than only for
        lexical repetition. **WHEN one is worth declaring is on the ``claims``
        field's own description** (``dna.memory.contradiction.WHEN_TO_CLAIM``),
        where the caller choosing what to send is already looking — declaring
        one for everything is the failure this API must not invite. A malformed
        claim is a **400** naming the offending index and field; nothing is
        written.

        PLAN-GATED (i-042): the same axes the MCP ``remember`` tool enforces —
        ``memory`` family, ``memory_mode='write'``, rate + daily cap — via the
        SAME shared core. 403 for a read-only tier, 429 over quota."""
        text = (summary or "").strip()
        if not text:
            raise HTTPException(
                status_code=400, detail="summary is required and cannot be empty"
            )
        await _plan_gate(request, tenant=tenant, family="memory", memory_op="write")
        try:
            return await remember_impl(
                await _live(), text, scope, area=area, affect=affect,
                tags=tags, owner=owner, claims=claims, tenant=tenant,
            )
        except ValueError as exc:
            # A malformed claim is the CALLER's mistake, so it must read as one:
            # 400 with the verb's own message (which names claims[i].field),
            # never a 500 that tells the caller nothing to fix.
            raise HTTPException(status_code=400, detail=str(exc)) from None

    # The body is read RAW (see the handler) so the byte bound is enforced before
    # anything is buffered into a model — which would otherwise leave the request
    # body undocumented (``requestBody: never``) and untypeable by the generated
    # clients. So the schema is declared explicitly here: the OpenAPI contract
    # and the hand-parsed body are kept in lockstep by the route's own tests.
    _IMPORT_BODY_SCHEMA = {
        "title": "ImportMemoriesRequest",
        "type": "object",
        "required": ["bundle"],
        "properties": {
            "bundle": {
                "title": "Bundle",
                "description": (
                    "The MIF payload: a JSON-LD {'@graph': [...]} bundle, a bare "
                    "list of Memory Units, or a single Memory Unit."
                ),
            },
            "as": {
                "title": "As",
                "type": "string",
                "enum": ["passthrough", "native", "both"],
                "default": "both",
                "description": (
                    "passthrough = store the MIF verbatim only; native = project "
                    "to a recallable Engram only; both = verbatim AND projected."
                ),
            },
            "dedupe": {
                "title": "Dedupe",
                "type": "string",
                "enum": ["id", "content-hash", "off"],
                "default": "id",
                "description": (
                    "id = skip a doc whose MIF id was already imported "
                    "(idempotent re-import); content-hash = skip by exact "
                    "content match; off = no pre-check."
                ),
            },
        },
    }

    @app.post("/v1/memories/import", dependencies=guarded, status_code=201,
              response_model=m.ImportMemoriesResponse,
              openapi_extra={
                  "requestBody": {
                      "required": True,
                      "content": {
                          "application/json": {"schema": _IMPORT_BODY_SCHEMA}
                      },
                  }
              })
    async def import_memories(
        request: Request,
        scope: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Import a MIF bundle into the CALLER'S OWN personal memory.

        The remote face of ``dna memory import --personal``: it wraps the SAME
        core pipeline (``dna.memory.verbs.import_mif_docs`` →
        ``dna.memory.interchange.from_mif``), so MIF is stored verbatim as a
        passthrough ``Memory`` AND/OR projected to a recallable ``Engram`` with
        no format logic re-implemented anywhere else.

        Body: ``{"bundle": <MIF>, "as": "both"|"passthrough"|"native",
        "dedupe": "id"|"content-hash"|"off"}``. ``bundle`` accepts the shapes the
        export side emits — a JSON-LD ``{"@graph": [...]}``, a bare list of
        Memory Units, or one Memory Unit.

        **The write ALWAYS lands in the caller's personal partition**
        (``personal:<oid>``), never a workspace: personal memory follows the
        PERSON, not the workspace (decision B1 / ADR-personal-memory). The
        identity is derived SERVER-SIDE from the verified token's claims and is
        never accepted from the body or the query — a ``tenant``/``oid``/
        ``personal_id`` sent by a client is IGNORED here (INV-PERSONAL layer 1),
        and there is no fallback to a workspace or to ``DNA_PERSONAL_ID`` on an
        authenticated deployment. No resolvable identity ⇒ 403, nothing written.
        """
        from dna.memory.interchange import MifFormatError, parse_mif_bundle
        from dna.memory.personal import (
            PersonalIdentityRequired,
            PersonalOverrideRejected,
        )
        from dna_cli._mcp_auth import personal_identity_from_claims

        # 1. Identity FIRST — resolve (and fail closed) before reading a byte of
        #    body, so an unidentified caller can never even stage an import.
        #    `auth == "config"` is the only mode with a per-request VERIFIED
        #    identity; `--auth token` is a SHARED secret (not an identity) and
        #    `--auth none` is the single-user local deployment, the stdio
        #    equivalent, which is the only mode allowed to read DNA_PERSONAL_ID.
        claims = _actor_claims_from_state(request) if auth == "config" else None
        try:
            oid, family = personal_identity_from_claims(
                claims,
                token_present=(auth == "config"),
                allow_env_fallback=(auth == "none"),
            )
        except (PersonalIdentityRequired, PersonalOverrideRejected) as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None

        # 1b. PLAN gate (i-042) — the REST twin of the MCP `_personal_guard`:
        #    a personal import is a memory WRITE, metered per the caller's
        #    IDENTITY partition (never a workspace — there may not be one). The
        #    tier comes from the verified token's plan claim (Free floor
        #    default), exactly as on MCP; a read-only tier is refused BEFORE a
        #    byte of body is buffered, and the denial costs no quota.
        await _plan_gate(
            request, tenant=None, family="memory", memory_op="write",
            quota_tenant=personal_tenant(oid, family=family),
        )

        # 2. Size gate BEFORE parsing — a bounded read, so an oversized upload is
        #    refused (413) instead of being buffered/parsed into memory.
        raw = await request.body()
        if len(raw) > _MAX_IMPORT_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"MIF bundle is {len(raw)} bytes; the import limit is "
                    f"{_MAX_IMPORT_BYTES} bytes "
                    f"({_MAX_IMPORT_BYTES // (1024 * 1024)} MiB). Split the "
                    "export into smaller bundles (import is idempotent by MIF "
                    "id, so the parts can be sent independently)."
                ),
            )
        try:
            payload = json.loads(raw or b"")
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"body is not valid JSON: {exc}"
            ) from None
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=400,
                detail="body must be a JSON object with a 'bundle' field",
            )

        as_mode = payload.get("as", "both")
        dedupe = payload.get("dedupe", "id")
        if as_mode not in ("passthrough", "native", "both"):
            raise HTTPException(
                status_code=400,
                detail=f"'as' must be passthrough/native/both, got {as_mode!r}",
            )
        if dedupe not in ("id", "content-hash", "off"):
            raise HTTPException(
                status_code=400,
                detail=f"'dedupe' must be id/content-hash/off, got {dedupe!r}",
            )
        if "bundle" not in payload:
            raise HTTPException(
                status_code=400, detail="body must carry a 'bundle' field (the MIF)"
            )

        # 3. Parse + validate the WHOLE bundle before any write — a malformed
        #    bundle is a 400 with nothing written, never a partial import.
        try:
            docs = parse_mif_bundle(payload["bundle"], source="bundle")
        except MifFormatError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        if len(docs) > _MAX_IMPORT_DOCS:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"bundle carries {len(docs)} memories; the import limit is "
                    f"{_MAX_IMPORT_DOCS} per request."
                ),
            )

        try:
            out = await import_memories_impl(
                await _live(), docs,
                as_mode=as_mode, dedupe=dedupe, scope=scope,
                memory_scope="personal", oid=oid, family=family,
            )
        except PersonalIdentityRequired as exc:  # defense in depth (core re-checks)
            raise HTTPException(status_code=403, detail=str(exc)) from None

        return {
            "imported": out["imported"],
            "skipped": out["skipped"],
            "failed": out["failed"],
            "received": len(docs),
            "partition": "personal",
            "as_mode": out["as"],
            "dedupe": out["dedupe"],
            "ids": out["ids"],
            "errors": out["errors"],
        }

    @app.get("/v1/memories/search", dependencies=guarded,
             response_model=m.RecallResponse)
    async def memories_search(
        q: str = Query(...),
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
        k: int = Query(default=5, ge=1, le=50),
        as_of: str | None = Query(
            default=None,
            description=(
                "ISO-8601 instant. Recall the BELIEF STATE at that moment — "
                "what this deployment believed then (transaction time), not "
                "what it believes now. Omit for the live read."
            ),
        ),
    ) -> dict[str, Any]:
        """Recall the tenant's memory for ``q`` (hybrid/bi-temporal when the
        search extra is present, honest lexical otherwise), tenant-scoped.

        ``as_of`` adds the second time axis (s-memory-as-of): every hit is
        resolved from the version the store RECORDED at or before that instant.
        A malformed timestamp is a 422 and a store with no version history is a
        501 — never a silent fallback to the current state, which would answer a
        question about the past with a fact about the present."""
        async def _run() -> dict[str, Any]:
            return await recall_impl(
                await _live(), q, scope, k, tenant, as_of=as_of,
            )
        return await _as_of_guarded(_run())

    @app.delete("/v1/memories/{name}", dependencies=guarded,
                response_model=m.DeleteMemoryResponse)
    async def delete_memory(
        request: Request,
        name: str,
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """⚠️ **REFUSED (403) since i-130** — a memory is never hard-deleted.

        This route called itself *"the MCP twin (``forget``)"* and was not one:
        ``forget`` stamps ``valid_to`` and leaves the row in place, while this
        removed the row and its ``dna_versions`` history with it (measured, both
        dialects: 3 versions → 0, and ``forget`` afterwards raised "not found").
        The founder's decision on i-130 kept the descriptor's promise — the
        memory is immortal — so the kernel now refuses the hard delete at the
        chokepoint every door crosses, and this route relays the refusal with
        the way out in it rather than pretending to delete.

        It stays a route, and returns 403 rather than 404/405, because all three
        alternatives lie in a different direction: removing it would 404 as
        *"there is no such endpoint"*, 405 would say the METHOD is wrong for the
        collection, and both hide that there is a policy and a remedy. 403 with
        the reason is the only answer a portal can act on.

        Tenant isolation is unchanged and now holds a fortiori: nobody deletes
        any memory, base or overlay, their own or another tenant's.

        PLAN-GATED (i-042) still, and BEFORE the refusal: a refusal is not a
        reason to stop metering a write attempt on the memory surface.

        The way out **in this lane** is ``POST /v1/memories/{name}/forget``
        (i-136), appended to the kernel's message by this route rather than
        carried inside it: the kernel names the verb, the command and the tool,
        and it must not learn what an HTTP path looks like. Until that route
        existed the refusal named a remedy the caller could not reach from here,
        which is a wall wearing a signpost."""
        await _plan_gate(request, tenant=tenant, family="memory", memory_op="write")
        try:
            return await delete_memory_impl(await _live(), name, scope, tenant)
        except DeleteRefused as exc:
            raise HTTPException(
                status_code=403, detail=f"{exc} {_FORGET_LANE_HINT}",
            ) from None
        except MemoryNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    @app.post("/v1/memories/{name}/forget", dependencies=guarded,
              response_model=m.ForgetMemoryResponse)
    async def forget_memory(
        request: Request,
        name: str,
        superseded_by: str | None = Body(
            default=None, embed=True,
            description=(
                "The memory that REPLACES this one, recorded on the tombstone "
                "as `spec.superseded_by_memory`. Send it when the retirement is "
                "part of an EDIT (write the new memory, then forget the old one "
                "naming it) — that is what turns two writes into one declared "
                "intent, and it is what a later reader follows to find where "
                "the thought went. Omit it for a plain retirement: the memory "
                "stopped being true and nothing took its place. NOT resolved — "
                "the name is recorded as declared, never checked against the "
                "store."
            ),
        ),
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Retire ONE memory — the REST face of the memory verb ``forget``, and
        since i-136 the ONLY way a portal retires a memory in this lane.

        A **bi-temporal demotion**, not a delete: it stamps ``valid_to``, the
        memory drops out of ``recall`` and ``list_memories``, and the instance
        plus its whole version history stay exactly where they were — auditable,
        readable at an earlier ``?as_of=``, revivable. That is the same verb
        ``dna memory forget`` and the MCP ``forget`` tool call; this is the third
        face of one core (``dna.application.forget_impl``), never a fourth
        implementation.

        **Why this route had to exist.** i-130 made ``DELETE /v1/memories/{name}``
        refuse — correctly, the row is immortal — and the refusal named ``forget``.
        But ``forget`` had no REST door, so the refusal named a remedy this lane
        could not perform, and the DELETE it replaced was the ONLY retire
        affordance the portal had. Two flows broke, and the worse one broke
        quietly: the portal's memory EDIT is a replace (write the new, retire the
        old), so a refused second half left BOTH copies live and recall answering
        with both. A door that refuses is only honest if the door it names is open.

        **Idempotent, which is what makes a retry safe.** Forgetting an already
        forgotten memory keeps the original ``valid_to`` and answers 200 with
        ``outcome: "already_forgotten"`` — so a client whose first attempt died
        in flight can simply repeat it. Repeating it WITH ``superseded_by``
        records the pointer on the existing tombstone, which is exactly what a
        half-finished edit needs to finish.

        **404 only for a name this layer does not hold** (``outcome: not_found``
        from the core): most often the PARTITION rather than the name — a
        personal Engram is invisible from the workspace lane. Reported as a 404
        instead of a 200 that says nothing happened, because "I could not find
        what you named" is a different fact from "I retired it".

        PLAN-GATED (i-042), ``memory`` family, ``memory_op='write'`` — the same
        axes the MCP ``forget`` tool crosses, through the same shared gate. A
        demotion is a write."""
        await _plan_gate(request, tenant=tenant, family="memory", memory_op="write")
        out = await forget_impl(
            await _live(), name, scope, tenant=tenant, superseded_by=superseded_by,
        )
        if out.get("outcome") == "not_found":
            raise HTTPException(
                status_code=404,
                detail=(
                    f"memory {name!r} not found in tenant {tenant!r}'s memory "
                    f"(scope {scope or 'default'!r}) — nothing to forget. If it "
                    f"is one of YOUR personal memories it lives in another "
                    f"partition and is not reachable from this workspace lane."
                ),
            )
        return out

    # -- intel (sources + insights + the feedback state transition) ----------
    # Thin delegates to dna.extensions.intel.engine — the portal's intelligence
    # surface. ZERO business logic here (adr-faces-reorg).

    @app.get("/v1/sources", dependencies=guarded, response_model=m.SourcesResponse)
    async def sources(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List the tenant's watched IntelSource docs (the Direction stage)."""
        live = await _live()
        sc = scope or live.base_scope
        items = await intel_engine.list_sources(live.kernel, scope=sc, tenant=tenant)
        return {"scope": sc, "tenant": tenant, "sources": items}

    @app.get("/v1/insights", dependencies=guarded, response_model=m.InsightsResponse)
    async def insights(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
        state: str | None = Query(default=None),
        source: str | None = Query(
            default=None,
            description="Filter to one IntelSource's insights (a project shows "
            "only its own). Alias of source_ref; source_ref wins if both are set.",
        ),
        source_ref: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List the tenant's IntelInsight docs (ranked), optionally filtered by
        ``state`` and/or originating source. The console's per-project view
        passes ``?source=<name>`` so a project shows only its own insights."""
        live = await _live()
        sc = scope or live.base_scope
        items = await intel_engine.list_insights(
            live.kernel, scope=sc, tenant=tenant, state=state,
            source_ref=source_ref or source,
        )
        return {"scope": sc, "tenant": tenant, "insights": items}

    @app.get("/v1/insights/metrics", dependencies=guarded,
             response_model=m.InsightMetricsResponse)
    async def insight_metrics(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
        source_ref: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """The feedback KPIs (precision + noise rate) over the tenant's insight
        stream, optionally for one ``source_ref``. Read-only; the arithmetic is
        the core ``feedback_metrics``."""
        live = await _live()
        sc = scope or live.base_scope
        return await intel_engine.feedback_metrics(
            live.kernel, scope=sc, tenant=tenant, source_ref=source_ref,
        )

    @app.patch("/v1/insights/{name}/state", dependencies=guarded,
               response_model=m.InsightStateResponse)
    async def set_insight_state(
        name: str,
        state: str = Body(..., embed=True),
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Set an insight's feedback state (new|actioned|dismissed|snoozed) —
        the reader's disposition. Delegates the read-modify-write to the core."""
        live = await _live()
        sc = scope or live.base_scope
        try:
            return await intel_engine.set_insight_state(
                live.kernel, name, state, scope=sc, tenant=tenant,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except intel_engine.InsightNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    # -- portfolio (the console's org / project / repo / board read model) ----
    # Thin delegates to the CORE application impls (dna.application) — the SAME
    # pattern as the definitions/intel handlers. ZERO business logic here.

    @app.get("/v1/orgs", dependencies=guarded, response_model=m.OrgsResponse)
    async def orgs(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List the tenant's Organization docs (the console's top-level container)."""
        return await list_orgs_impl(await _live(), scope, tenant)

    @app.get("/v1/projects", dependencies=guarded, response_model=m.ProjectsResponse)
    async def projects(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List the tenant's Project docs (the multi-repo development-space
        containers the portfolio console aggregates)."""
        return await list_projects_impl(await _live(), scope, tenant)

    @app.get("/v1/projects/{slug}", dependencies=guarded,
             response_model=m.ProjectDetailResponse)
    async def project_detail(
        slug: str,
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """One project's detail + its RESOLVED repos (``repo_refs`` → the Repo
        docs). 404 when the slug is unknown for this (scope, tenant)."""
        try:
            return await get_project_impl(await _live(), slug, scope, tenant)
        except ProjectNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    @app.get("/v1/projects/{slug}/members", dependencies=guarded,
             response_model=m.ProjectMembersResponse)
    async def project_members(
        slug: str,
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
        viewer: str | None = Query(
            default=None,
            description="The signed-in user (email/id) — flags their own row and "
            "whether they may manage membership (Owner/Admin).",
        ),
    ) -> dict[str, Any]:
        """List a project's members with their RESOLVED role (highest-role-wins
        across org + project grants; org-owner a superuser), tenant-scoped. When
        ``viewer`` is set, reports ``viewer.can_manage`` so the portal gates its
        write controls. 404 when the slug is unknown for this (scope, tenant)."""
        try:
            return await list_members_impl(await _live(), slug, scope, tenant, viewer)
        except ProjectNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    @app.post("/v1/projects/{slug}/members", dependencies=guarded, status_code=201,
              response_model=m.SetMemberResponse)
    async def set_project_member(
        slug: str,
        user: str = Body(..., embed=True),
        role: str = Body(..., embed=True),
        actor: str | None = Body(default=None, embed=True),
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Invite / set a user's PROJECT-scope role — the Membros panel's write.
        RBAC-guarded: ``actor`` (the acting user) must be Owner/Admin of the
        project/org, and only an Owner may grant Owner (403 otherwise). Upserts the
        same Membership doc, tenant-scoped to the caller's overlay. 404 for an
        unknown project; 422 for an unknown role."""
        try:
            return await set_member_impl(
                await _live(), slug, user, role, scope, tenant, actor
            )
        except ProjectNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except MemberForbidden as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @app.delete("/v1/projects/{slug}/members/{user}", dependencies=guarded,
                response_model=m.RemoveMemberResponse)
    async def remove_project_member(
        slug: str,
        user: str,
        actor: str | None = Query(default=None),
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Remove a user's PROJECT-scope grant — the Membros panel's remove.
        RBAC-guarded: ``actor`` must be Owner/Admin (removing an Owner needs
        Owner). Deletes only the project-scope Membership (an inherited org grant
        is untouched), tenant-scoped. 403 without permission, 404 when the user has
        no project grant here."""
        try:
            return await remove_member_impl(
                await _live(), slug, user, scope, tenant, actor
            )
        except ProjectNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except MemberForbidden as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        except MemberNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    # -- first-owner provisioning (audit finding C3) -------------------------
    # A brand-new tenant has ZERO Membership docs, so its first user could not
    # manage members (every membership write 403'd — nothing made the sole user
    # the Owner of their own tenant). The DNA Cloud portal calls this on first
    # authenticated access (server-side, with the shared bearer it already holds —
    # never opening the DNA source directly, same pattern as PUT /v1/account-plan)
    # so the signed-in user becomes Owner of their OWN tenant (== the `tid` path
    # segment). Idempotent + first-owner-only: a NO-OP once any Owner exists, so a
    # LATER user does not auto-escalate. Delegates to the CORE impl (zero logic
    # here). 400 on a missing tenant/user.
    @app.post("/v1/tenants/{tid}/provision-owner", dependencies=guarded, status_code=201,
              response_model=m.ProvisionTenantOwnerResponse)
    async def provision_tenant_owner(
        tid: str,
        user: str = Body(..., embed=True),
        scope: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Ensure ``user`` is Owner of tenant ``tid`` when it has no Owner yet — the
        first-owner bootstrap. Idempotent (no-op if an Owner already exists).
        Returns the grants created (org-scope per referenced org + project-scope per
        orgless project). 400 on a missing tenant/user."""
        try:
            return await provision_tenant_owner_impl(await _live(), tid, user, scope)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.get("/v1/repos", dependencies=guarded, response_model=m.ReposResponse)
    async def repos(
        scope: str | None = Query(default=None),
        tenant: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List the tenant's Repo docs (code repositories the portfolio references)."""
        return await list_repos_impl(await _live(), scope, tenant)

    @app.get("/v1/board", dependencies=guarded, response_model=m.BoardResponse)
    async def board(
        scope: str = Query(..., description="A project's board_scope (e.g. my-board)."),
        tenant: str | None = Query(default=None),
        recent: int = Query(default=6, ge=0, le=50),
    ) -> dict[str, Any]:
        """A compact SDLC summary for a project's ``board_scope``: Story + Feature
        counts by status, totals, and the newest work items — the console's board
        card. Reuses the shared SDLC read impl (``list_stories_impl``)."""
        return await board_summary_impl(await _live(), scope, tenant, recent)

    @app.get("/v1/board/item", dependencies=guarded, response_model=m.BoardItemResponse)
    async def board_item(
        scope: str = Query(..., description="The project's board_scope."),
        name: str = Query(..., description="The work-item doc name (e.g. s-foo)."),
        tenant: str | None = Query(default=None),
        kind: str | None = Query(
            default=None,
            description="Optional Kind hint (Story/Feature/…); probed if omitted.",
        ),
    ) -> dict[str, Any]:
        """One board work-item's FULL doc — the console's item-detail drawer:
        title, status, description, acceptance_criteria, definition_of_done,
        timeline, feature/epic refs, and produces. Delegates to the CORE
        ``board_item_impl`` (zero logic here). 404s an unknown name (for this
        scope/tenant, or under an explicit ``kind`` hint)."""
        try:
            return await board_item_impl(await _live(), scope, name, tenant, kind)
        except BoardItemNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None

    # -- cloud billing → enforcement bridge (AccountPlan write) --------------
    # The ONE write that closes the billing→runtime gap: dna-cloud's Stripe
    # webhook calls this (server-side, with the shared DNA_API_TOKEN bearer it
    # already holds) on the Pro-activate / downgrade / cancel transitions, so
    # runtime quota follows billing state.
    #
    # KEYED ON THE BILLING ACCOUNT, NOT A WORKSPACE. One call covers every
    # workspace the account owns — creating a second workspace is not a second
    # charge and requires no billing write at all. This replaces the retired
    # `PUT /v1/workspace-plan`, whose per-workspace key forced the caller to FAN
    # OUT one write per workspace; that fan-out could not be made safe, because
    # `GET /v1/workspaces` enumerates by MEMBERSHIP, not ownership — a workspace
    # somebody else founded and invited the payer into would have been swept in
    # and handed a tier its own account never bought.
    #
    # GLOBAL / _lib-direct: the doc's name == the account_id, so there is no query
    # param — `account_id` is the body key being assigned. Delegates to the CORE
    # set_account_plan_impl (zero logic here); idempotent under Stripe retries
    # (write_instance upserts on name).
    @app.put("/v1/account-plan", dependencies=guarded,
             response_model=m.AccountPlanResponse)
    async def put_account_plan(
        account_id: str = Body(..., embed=True),
        tier_id: str = Body(..., embed=True),
        source: str = Body(default="stripe", embed=True),
        stripe_customer_id: str | None = Body(default=None, embed=True),
        stripe_subscription_id: str | None = Body(default=None, embed=True),
        status: str | None = Body(default=None, embed=True),
    ) -> dict[str, Any]:
        """Upsert the AccountPlan Kind assigning ``account_id`` → ``tier_id`` (the
        billing→enforcement bridge). The assignment covers EVERY workspace whose
        ``account_id`` matches. 400 on a missing account_id/tier_id."""
        try:
            return await set_account_plan_impl(
                await _live(),
                account_id,
                tier_id,
                source=source,
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
                status=status,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    # -- workspace + project CREATION (decisions D5 / A1) ---------------------
    # THE ACT OF CREATION that DNA Cloud was missing: before these routes a
    # Workspace could only be born from a seed script and its id WAS the Azure
    # `tid`, so there was no way to create the thing the product sells. All three
    # live in the CORE impls; these handlers only shape HTTP + source the actor.
    #
    # The id of a workspace is MINTED SERVER-SIDE. Note there is deliberately NO
    # `workspace_id` field on the create body: the route cannot accept one, so a
    # caller cannot name a workspace into existence and race its owner for it.
    # That is the replacement for the old `tid == workspace_id` takeover guard.
    #
    # The two /v1/workspaces routes are EXEMPT from the config-auth membership
    # bind (a caller creating their FIRST workspace holds no membership anywhere
    # yet — that is the whole point) and do their own check on the verified
    # identity. POST /v1/projects is exempted too, for a different reason: it names
    # its workspace in the BODY, so the bind (which reads a `tenant` query param and
    # fails closed on an ambiguous multi-membership caller) would refuse a request
    # the core impl is perfectly able to authorize. See the exemption's own comment.

    @app.post("/v1/workspaces", dependencies=guarded, status_code=201,
              response_model=m.CreateWorkspaceResponse)
    async def create_workspace(
        request: Request,
        name: str = Body(..., embed=True),
        slug: str | None = Body(default=None, embed=True),
        claims: dict[str, Any] | None = Body(default=None, embed=True),
    ) -> dict[str, Any]:
        """Create a workspace and its first OWNER, in one call. The
        ``workspace_id`` is generated by the server (opaque + unguessable) — it is
        NOT accepted from the client, which is what makes takeover structurally
        impossible. ``slug`` defaults to a slugified ``name`` and is made unique.
        The caller's verified identity (oid + email; ``tid`` stored as provenance
        only) becomes the active owner. 400 on a blank name or a missing
        oid/email claim."""
        effective = _actor_claims_from_state(request) or claims or {}
        try:
            return await create_workspace_impl(
                await _live(), name, effective, slug=slug
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.get("/v1/workspaces", dependencies=guarded,
             response_model=m.WorkspacesResponse)
    async def list_workspaces(
        request: Request,
        actor_oid: str | None = Query(default=None),
        actor_email: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List the workspaces the caller holds an ACTIVE membership in — the
        workspace switcher's data source. Membership is the enumeration key, never
        the ``tid``; a pending invite is not listed. Under config auth the caller
        is the verified token identity; under none/token a trusted portal passes
        ``actor_oid``/``actor_email``. Never returns a workspace the identity does
        not belong to (an unmatched identity gets an empty list, not an error)."""
        effective = _actor_claims_from_state(request)
        if effective is None:
            effective = {"oid": actor_oid, "email": actor_email}
        return await list_workspaces_impl(await _live(), effective)

    @app.post("/v1/projects", dependencies=guarded, status_code=201,
              response_model=m.CreateProjectResponse)
    async def create_project(
        request: Request,
        workspace_id: str = Body(..., embed=True),
        name: str = Body(..., embed=True),
        slug: str | None = Body(default=None, embed=True),
        claims: dict[str, Any] | None = Body(default=None, embed=True),
    ) -> dict[str, Any]:
        """Create a Project inside ``workspace_id`` (decision A1 — the owning
        workspace is an explicit field on the Project). The caller must hold an
        ACTIVE WorkspaceMembership there, else **403**. The write scope and the
        project's ``board_scope`` are DERIVED from the workspace + slug and are
        deliberately not accepted from the caller. 400 on a blank
        workspace_id/name."""
        effective = _actor_claims_from_state(request) or claims or {}
        try:
            return await create_project_impl(
                await _live(), workspace_id, name, effective, slug=slug
            )
        except WorkspaceForbidden as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.post("/v1/artifacts", dependencies=guarded, status_code=201,
              response_model=m.RegisterArtifactResponse)
    async def register_artifact(
        request: Request,
        workspace_id: str = Body(..., embed=True),
        sha256: str = Body(..., embed=True),
        uri: str = Body(..., embed=True),
        filename: str | None = Body(default=None, embed=True),
        mime: str | None = Body(default=None, embed=True),
        size_bytes: int | None = Body(default=None, embed=True),
        detected_mime: str | None = Body(default=None, embed=True),
        mime_mismatch: bool | None = Body(default=None, embed=True),
        origin: str | None = Body(default=None, embed=True),
        claims: dict[str, Any] | None = Body(default=None, embed=True),
    ) -> dict[str, Any]:
        """Record the ORIGINAL a projection will be derived from.

        The caller must hold an ACTIVE WorkspaceMembership in ``workspace_id``,
        else **403**. The write scope is DERIVED from the workspace and is
        deliberately not accepted from the caller.

        IDEMPOTENT by content address: the same ``sha256`` updates the same
        instance, so a retried upload leaves no second artifact behind — and an
        existing ``derived_refs`` survives the retry rather than being blanked.

        ``uri`` names where the bytes live and must NOT be a signed URL: a
        stored credential would make the instance itself the access to its own
        original. 400 on a blank workspace_id / sha256 / uri."""
        effective = _actor_claims_from_state(request) or claims or {}
        try:
            return await register_artifact_impl(
                await _live(), workspace_id, sha256, uri, effective,
                filename=filename, mime=mime, size_bytes=size_bytes,
                detected_mime=detected_mime, mime_mismatch=mime_mismatch,
                origin=origin,
            )
        except WorkspaceForbidden as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    # -- workspace invites (ADR "Model B", F3 — the cross-org join) -----------
    # The identity→workspace boundary REST surface (story s-ws-invite-rest). Auth
    # is BY MEMBERSHIP: Owner/Admin of the workspace to invite/list; the invitee
    # (a verified email claim) to accept. The RBAC + the anti-impersonation accept
    # rule live in the CORE impls (invite_member_impl / list_workspace_members_impl
    # / accept_invites_impl) — these handlers only shape HTTP + source the actor.
    #
    # Actor sourcing: under `--auth config` the actor's VERIFIED token claims are
    # stashed on request.state by the middleware (the hardened path). Under
    # none/token (a TRUSTED portal server-side call holding the shared bearer) the
    # actor's Entra-session claims are passed explicitly — the config-auth claims,
    # when present, always WIN over a body/query value.

    @app.post("/v1/workspaces/{workspace_id}/invites", dependencies=guarded,
              status_code=201, response_model=m.InviteResponse)
    async def create_invite(
        request: Request,
        workspace_id: str,
        email: str = Body(..., embed=True),
        role: str = Body(default="member", embed=True),
        actor: dict[str, Any] | None = Body(default=None, embed=True),
    ) -> dict[str, Any]:
        """Invite an identity (by email) into a workspace — a ``pending``
        WorkspaceMembership. RBAC: the actor must be Owner/Admin (only an Owner may
        invite an Owner). 403 without permission; 422 on an unknown role."""
        actor_claims = _actor_claims_from_state(request) or actor
        try:
            return await invite_member_impl(
                await _live(), workspace_id, email, role, actor_claims=actor_claims
            )
        except WorkspaceForbidden as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @app.get("/v1/workspaces/{workspace_id}/members", dependencies=guarded,
             response_model=m.WorkspaceMembersResponse)
    async def workspace_members(
        request: Request,
        workspace_id: str,
        actor_oid: str | None = Query(default=None),
        actor_email: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List a workspace's members (grants). RBAC: the actor must be
        Owner/Admin. Under config auth the actor is the verified token identity;
        under none/token pass ``actor_oid``/``actor_email`` (the trusted portal
        vouches the session). 403 without permission."""
        actor_claims = _actor_claims_from_state(request)
        kwargs: dict[str, Any] = {}
        if actor_claims is not None:
            kwargs["actor_claims"] = actor_claims
        else:
            kwargs["actor"] = Identity(oid=actor_oid, email=actor_email)
        try:
            return await list_workspace_members_impl(await _live(), workspace_id, **kwargs)
        except WorkspaceForbidden as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None

    @app.post("/v1/workspaces/accept", dependencies=guarded,
              response_model=m.AcceptInvitesResponse)
    async def accept_invites(
        request: Request,
        claims: dict[str, Any] | None = Body(default=None, embed=True),
    ) -> dict[str, Any]:
        """Accept every pending invite the caller's VERIFIED sign-in claims — binds
        the durable ``oid`` + flips ``pending→active``. Under config auth the
        claims come from the verified token (the invitee is still pending, so this
        route is exempt from the membership bind); under none/token a trusted portal
        passes the verified Entra claims. The SECURITY gate (verified email only, no
        hijack of a bound grant) is enforced in the core impl — never here."""
        effective = _actor_claims_from_state(request) or claims or {}
        return await accept_invites_impl(await _live(), effective)

    # -- workspace owner reconcile + revoke (Model B, f-ws-owner-provision) ----
    # provision-owner is the portal's every-sign-in reconcile. Since decision D5 it
    # CREATES NOTHING: workspaces are born from POST /v1/workspaces (server-minted
    # id), and this route degraded to the idempotent no-op that requires an
    # existing ACTIVE membership — a caller without one is 403'd. Revoke removes a
    # member (Owner/Admin only, last-owner protected). The name is kept for wire
    # compatibility with the deployed portal.
    #
    # Both live UNDER /v1/workspaces/* so they are EXEMPT from the config-auth
    # membership bind (the caller may hold no active membership yet — that is the
    # whole point of the bootstrap) and do their OWN check on the verified identity:
    # under --auth config the verified token claims (stashed on request.state) WIN
    # over the body; under none/token a trusted portal passes the verified claims.

    @app.post("/v1/workspaces/{workspace_id}/provision-owner",
              dependencies=guarded, status_code=201,
              response_model=m.ProvisionWorkspaceOwnerResponse)
    async def provision_workspace_owner(
        request: Request,
        workspace_id: str,
        claims: dict[str, Any] | None = Body(default=None, embed=True),
    ) -> dict[str, Any]:
        """Reconcile the verified identity's membership in ``{workspace_id}`` — the
        every-sign-in idempotent no-op. Since decision **D5** this CREATES NOTHING:
        it requires an ACTIVE WorkspaceMembership and returns it (back-filling the
        Workspace identity doc only for an owner whose doc is missing). A caller
        holding no active membership here is **403** — including a stranger, so the
        anti-takeover answer is unchanged; workspaces are created by
        ``POST /v1/workspaces``, which mints its own id. 400 on a missing
        oid/email claim."""
        effective = _actor_claims_from_state(request) or claims or {}
        try:
            return await provision_workspace_owner_impl(
                await _live(), workspace_id, effective
            )
        except WorkspaceForbidden as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.post("/v1/workspaces/{workspace_id}/members/revoke", dependencies=guarded,
              response_model=m.RevokeWorkspaceMemberResponse)
    async def revoke_workspace_member(
        request: Request,
        workspace_id: str,
        target_email: str | None = Body(default=None, embed=True),
        target_oid: str | None = Body(default=None, embed=True),
        actor: dict[str, Any] | None = Body(default=None, embed=True),
    ) -> dict[str, Any]:
        """Revoke (remove) a member's WorkspaceMembership — the Members panel remove
        (issue ``i-033``). RBAC: the actor must be Owner/Admin (403 else). The LAST
        remaining owner can NEVER be revoked (409, fail-closed). A target holding no
        grant here is 404 (clear no-op). Target named by ``target_email`` or
        ``target_oid`` (oid wins). Under ``--auth config`` the actor is the verified
        token identity; under none/token the trusted portal passes ``actor`` claims."""
        actor_claims = _actor_claims_from_state(request) or actor
        try:
            return await revoke_workspace_member_impl(
                await _live(), workspace_id,
                actor_claims=actor_claims,
                target_email=target_email, target_oid=target_oid,
            )
        except WorkspaceForbidden as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from None
        except WorkspaceLastOwner as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except WorkspaceMemberNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    # O kernel vivo, alcançável por quem MONTA outra face sobre este app.
    #
    # `_live` já existia e era um closure — perfeito para as rotas daqui, e
    # invisível para um host que monta mais coisa no mesmo `app`. O caso real: a
    # porta A2A do dna-cloud faz `attach_a2a(app, …)` e precisa de um kernel
    # para `enforce_plan` resolver plano e caps; sem este handle ela abria um
    # SEGUNDO `boot_live`.
    #
    # Dois kernels sobre a mesma fonte não são só um pool de conexões a mais:
    # são duas caches de Kind e duas janelas de refresh. Uma instância reescrito
    # fica visível numa e não na outra, e o sintoma aparece longe da causa.
    #
    # É a MESMA corrotina memoizada que as rotas usam — não um segundo boot com
    # outro nome.
    app.state.live = _live

    return app
