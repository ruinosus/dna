"""dna_cli.serving — the PUBLIC, stable surface for composing DNA endpoints.

The DNA SDK is a library of primitives, not a set of production endpoints
(the `dna mcp serve` / `dna api serve` commands are dev/self-host conveniences
and are deprecated for production use). A HOST — e.g. DNA Cloud's `apps/mcp` and
`apps/api` — composes its OWN server from these primitives: build the app with
the host's auth provider + quota store, then run it under the host's ASGI server.

This module is the stable boundary. The underlying `_mcp_server` / `_rest_api`
/ `_mcp_auth` / `_mcp_quota` modules stay PRIVATE (implementation); import from
here, not from those, so the host is insulated from internal refactors.

Example (a host's MCP endpoint):

    from dna_cli.serving import build_mcp_server, jwt_provider_from_env, quota_store_from_env
    server = build_mcp_server(auth=jwt_provider_from_env(), quota_store=quota_store_from_env())
    # run server under the host's own ASGI server (uvicorn/hypercorn/…)

Example (a host's REST read-API):

    from dna_cli.serving import build_rest_app
    app = build_rest_app(auth="config", verifier=my_verifier)
"""

from __future__ import annotations

# The app FACTORIES — the primitives a host runs.
from dna_cli._mcp_server import build_server as build_mcp_server
from dna_cli._rest_api import build_app as build_rest_app

# The MCP HTTP wrapper: a Starlette ASGI app over the FastMCP server that ALSO
# accepts the per-workspace URL `/w/<id>/mcp` (ADR Model B) beside the bare
# `/mcp`. A host that serves the MCP endpoint over HTTP itself (apps/mcp) needs
# this to keep multi-workspace routing — `build_mcp_server` alone is just /mcp.
from dna_cli._mcp_server import build_http_app

# The auth layer — TWO tiers a host composes with:
#   • the FACTORIES that build a provider/auth object from env/config
#     (`*_from_env`, `build_auth_from_config`), passed to the `auth=` PORT; and
#   • `parse_auth_providers`, the pure-core dict→ProviderConfig parser, so a host
#     can turn its OWN env into providers WITHOUT a dna.config.yaml — the same
#     providers the `auth_providers=` sugar on build_mcp_server/build_rest_app takes.
from dna_cli._mcp_auth import (
    build_auth_from_config,
    parse_auth_providers,
    azure_provider_from_env,
    jwt_provider_from_env,
)

# The metering counter a host spends quota against (durable when a Postgres DSN
# is present; in-process otherwise).
from dna_cli._mcp_quota import store_from_env as quota_store_from_env

__all__ = [
    "build_mcp_server",
    "build_rest_app",
    "build_http_app",
    "build_auth_from_config",
    "parse_auth_providers",
    "azure_provider_from_env",
    "jwt_provider_from_env",
    "quota_store_from_env",
]
