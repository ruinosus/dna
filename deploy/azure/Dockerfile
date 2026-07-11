# DNA MCP server — container image for Azure Container Apps (Phase A of DNA-hosted).
#
# Containerizes `dna mcp serve --transport http` so a remote/web MCP client
# (Claude web, ChatGPT, any hosted client) can reach the LIVE DNA over HTTPS,
# authenticated with a Microsoft Entra bearer token (--auth jwt; see the runbook
# deploy/azure/README.md).
#
# BUILD CONTEXT = the repository root (not this directory), so the image can
# install the workspace packages from source. azd wires this automatically
# (azure.yaml sets the service `project` to the repo root). To build by hand:
#
#   docker build -f deploy/azure/Dockerfile -t dna-mcp .
#
# The `mcp` extra (FastMCP) is imported lazily by the CLI, so it is pulled in
# here explicitly — the base `dna` install never carries it.
#
# Published alternative: instead of the two COPY+install lines below you can
# `RUN pip install --no-cache-dir "dna-cli[mcp]"` once dna-cli is on PyPI. The
# from-source install keeps this recipe reproducible directly from a checkout.

FROM python:3.12-slim AS base

# uvicorn/anyio behave better with an explicit UTF-8 locale; no .pyc noise; no
# stdout buffering (logs stream to the Container App log stream immediately).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install the SDK first (satisfies dna-cli's `dna-sdk>=0.9,<0.10` constraint from
# the local checkout, so pip never reaches out to PyPI for it), then the CLI with
# the `mcp` extra (FastMCP). --no-deps is NOT used: fastmcp + the sdk runtime deps
# resolve from wheels on slim without a compiler.
COPY packages/sdk-py /src/packages/sdk-py
COPY packages/cli /src/packages/cli
RUN pip install /src/packages/sdk-py \
 && pip install "/src/packages/cli[mcp]"

# Seed DNA scope baked into the image (a minimal, queryable demo). At runtime the
# server reads whatever DNA_SOURCE_URL / DNA_BASE_DIR points at — the Container App
# defaults DNA_BASE_DIR to the mounted Azure Files share (/mnt/dna) and falls back
# to this baked scope only when the source env is unset. Replace/seed the share
# with your real scope via deploy/azure/scripts/push-scope.sh.
COPY deploy/azure/dna-scope /app/dna-scope

COPY deploy/azure/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Run as an unprivileged user (Container Apps does not require root).
RUN useradd --create-home --uid 10001 dna \
 && chown -R dna:dna /app
USER dna

# Streamable HTTP endpoint. Container Apps terminates TLS at the ingress and
# forwards plain HTTP to this port; keep it in lockstep with targetPort in the
# bicep (resources.bicep) and DNA_MCP_PORT below.
ENV DNA_MCP_TRANSPORT=http \
    DNA_MCP_HOST=0.0.0.0 \
    DNA_MCP_PORT=8080 \
    DNA_MCP_AUTH=jwt \
    DNA_BASE_DIR=/app/dna-scope
EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
