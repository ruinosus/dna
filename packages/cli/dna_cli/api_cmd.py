"""``dna api`` — expose the LIVE DNA over a thin REST **read-API**.

``dna api serve`` boots ONE FastAPI app against the configured source
(``DNA_SOURCE_URL`` / ``DNA_BASE_DIR`` — the same source every ``dna`` command
reads) and serves a normal request/response HTTP API, so a WEB app (the DNA Cloud
portal) can read everything DNA composes without opening a stateful MCP session
per page render.

It is the WEB counterpart of ``dna mcp serve``: same live kernel, same ``*_impl``
cores, a different HTTP boundary. MCP is for long-lived AI clients (Claude
Code/Cursor/Copilot); this is for a browser/BFF doing stateless GETs.

FastAPI + uvicorn are an optional extra (``pip install 'dna-cli[api]'``); they are
imported lazily so the base ``dna`` install never requires them.
"""
from __future__ import annotations

import click


@click.group(name="api")
def api() -> None:
    """Expose the live DNA (definitions + memory) over a REST read-API."""


@api.command("serve")
@click.option("--scope", default=None,
              help="Default scope for endpoints that omit one (else the sole/first scope).")
@click.option("--base-dir", default=None,
              help="Source directory override (else DNA_SOURCE_URL / DNA_BASE_DIR / ./.dna).")
@click.option("--host", default="127.0.0.1", show_default=True,
              help="Bind host.")
@click.option("--port", type=int, default=8080, show_default=True,
              help="Bind port.")
@click.option("--auth", type=click.Choice(["none", "token", "config"]), default="none",
              show_default=True,
              help="Auth mode. `none` = local dev (no bearer). `token` = require "
                   "`Authorization: Bearer <DNA_API_TOKEN>` on every route (the MVP "
                   "shared token). `config` = the Model B verified-identity path — a "
                   "bearer JWT verified by the N-provider layer (dna.config.yaml "
                   "`auth.providers[]`), then the effective workspace BOUND from the "
                   "identity's WorkspaceMembership (the `tenant` param is overwritten "
                   "from membership, never trusted from the caller).")
@click.option("--token", default=None,
              help="Expected bearer token for --auth token (else the DNA_API_TOKEN env var).")
@click.option("--token-scope", "token_scopes", multiple=True,
              help="A scope this credential may read when the request resolves NO "
                   "workspace (repeatable; else the DNA_TOKEN_SCOPES env var, "
                   "comma-separated). Absent, such a caller is bound to the ONE "
                   "scope this server was booted on — absence of a workspace is not "
                   "a right to every scope. Pass `*` to consciously opt out.")
@click.option("--cors-origin", "cors_origins", multiple=True,
              help="Allowed browser origin for CORS (repeatable; else "
                   "DNA_API_CORS_ORIGINS, else http://localhost:3000).")
def serve(scope: str | None, base_dir: str | None, host: str, port: int,
          auth: str, token: str | None, token_scopes: tuple[str, ...],
          cors_origins: tuple[str, ...]) -> None:
    """Run the DNA REST read-API (the WEB face — a request/response HTTP API).

    \b
    LOCAL (no auth):
      $ dna api serve --port 8080 --auth none
      $ curl -s localhost:8080/v1/agents

    \b
    ENDPOINTS (read-focused; tenant-aware via a `tenant` query param):
      GET    /health                              -> {ok:true}
      GET    /v1/agents?scope=&tenant=            -> {scope, agents:[...]}
      GET    /v1/agents/{name}/prompt?scope=&tenant=  -> {scope, agent, prompt, ...}
      GET    /v1/tools?scope=&tenant=             -> {scope, tools:[...]}
      GET    /v1/memories?scope=&tenant=          -> {memories:[...]}
      GET    /v1/memories/search?q=&scope=&tenant=&k=5  -> {query, hits:[...]}
      DELETE /v1/memories/{name}?scope=&tenant=   -> delete from the tenant's OWN overlay
      GET    /v1/sources?scope=&tenant=           -> {sources:[...]}
      GET    /v1/insights?scope=&tenant=&state=&source=  -> {insights:[...]}
      GET    /v1/orgs?tenant=                      -> {orgs:[...]}
      GET    /v1/projects?tenant=                  -> {projects:[...]}
      GET    /v1/projects/{slug}?tenant=           -> {project, repos:[...]}
      GET    /v1/projects/{slug}/members?tenant=&viewer=  -> {members:[...], viewer}
      POST   /v1/projects/{slug}/members?tenant=   -> invite/set-role {user, role, actor} (RBAC)
      DELETE /v1/projects/{slug}/members/{user}?tenant=&actor=  -> remove (RBAC)
      GET    /v1/repos?tenant=                     -> {repos:[...]}
      GET    /v1/board?scope=&tenant=              -> {counts, totals, recent}
      PUT    /v1/account-plan                      -> billing->runtime AccountPlan write {account_id, tier_id, ...}
      POST   /v1/tenants/{tid}/provision-owner     -> first-login Owner bootstrap {user} (idempotent)
      POST   /v1/workspaces/{id}/provision-owner   -> Model B first-login owner bootstrap {claims} (idempotent, id==tid)
      POST   /v1/workspaces/{id}/invites           -> invite by email {email, role, actor} (Owner/Admin)
      GET    /v1/workspaces/{id}/members           -> list members (Owner/Admin)
      POST   /v1/workspaces/{id}/members/revoke    -> remove a member {target_email|target_oid, actor} (last-owner protected)
      POST   /v1/workspaces/accept                 -> accept pending invites {claims} (verified sign-in)

    Every endpoint reads/writes through the SAME live kernel `dna` commands +
    `dna mcp serve` use — this is a second HTTP face over one core, not a copy.
    """
    # The SDK is a library of primitives, not a production endpoint. This serve is
    # a convenience (local / self-host); a PRODUCTION host composes its own REST
    # app from the public factory: `from dna_cli.serving import build_rest_app`.
    click.echo(
        "⚠ `dna api serve` is a convenience endpoint, DEPRECATED for production. "
        "A host composes its own app from the public primitive: "
        "`from dna_cli.serving import build_rest_app`. Local / self-host remain "
        "supported.",
        err=True,
    )
    from dna_cli._rest_api import build_app

    # The CLI is ONE consumer of the core builder: it reads the providers from the
    # file (its input source) and HANDS them to build_app. File I/O lives here, not
    # in the core — an in-process caller (dna-cloud) passes auth_providers from env.
    providers = None
    if auth == "config":
        # Fail loud NOW (not on the first request) if the provider config is missing.
        try:
            from dna_cli._mcp_auth import providers_from_config
            providers = providers_from_config()
            click.echo(
                "auth: multi-provider layer — "
                + ", ".join(f"{p.label}({p.tenant_claim})" for p in providers),
                err=True,
            )
        except (RuntimeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from None

    try:
        app = build_app(
            scope=scope, base_dir=base_dir, auth=auth, token=token,
            cors_origins=list(cors_origins) or None,
            auth_providers=providers,
            token_scopes=list(token_scopes) or None,
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from None

    try:
        import uvicorn
    except ModuleNotFoundError as exc:  # pragma: no cover — exercised via CLI
        raise click.ClickException(
            "the REST read-API needs the optional 'uvicorn' dependency — install "
            "it with:  pip install 'dna-cli[api]'"
        ) from exc

    uvicorn.run(app, host=host, port=port, log_level="info")
