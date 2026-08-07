# mcp-entra — built from THIS app's own package, never from a shared
# infra Dockerfile: the version floor lives in pyproject.toml, and a build that
# installed it anywhere else would make the declared floor a lie.
#
# ⚠️ This file exists only because mcp-entra OWNS the code
# (`owns_code: true`). N services can run this ONE image — the identity doors
# are three services over one image — and each of them renders its own wiring
# with its own port and its own sleep answer. So the DNA_MCP_PORT
# baked in below is a DEFAULT for the image, not the truth about any service:
# the container app and the compose fragment set it per service, and they win.
FROM python:3.12-slim AS base

LABEL org.opencontainers.image.title="mcp-entra" \
      org.opencontainers.image.description="the delegated door"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DNA_MCP_HOST=0.0.0.0 \
    DNA_MCP_PORT=8000

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["mcp-entra"]
