"""Entry point for `mcp-entra`.

⚠️ This file is a SKELETON, on purpose. The template owns the wiring — the
container, the bicep module, the compose fragment, the version floor — and
stops here, where your reasoning starts. Grow it freely.

The trade you accepted by generating this: a future `dna solution update` that
touches a line you also touched produces a merge conflict, and adjacent edits
collapse into one coarse block. That is the price of owning real code instead
of depending on a library. The wiring files below `wiring/` are the part you
are NOT expected to edit, and they are the part that merges clean.
"""
from __future__ import annotations

import os


HOST = os.environ.get("DNA_MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("DNA_MCP_PORT", "8000"))

# The NAME of the identity authority, decided at generation time. What it means
# operationally — issuer, audience, JWKS — is configuration this process reads
# at boot, never a literal baked in here.
IDENTITY = "entra"
# This door carries the Microsoft Graph on-behalf-of pack: it is the lane that
# can exchange the verified inbound token for a downstream Graph token.
GRAPH_OBO = True


def build_app():
    """Return the ASGI app this container serves.

    Replace the body. Nothing below this line is template-owned.
    """
    raise NotImplementedError("mcp-entra: build_app() is yours to write")


def main() -> None:
    import uvicorn

    uvicorn.run(build_app(), host=HOST, port=PORT)


if __name__ == "__main__":
    main()
