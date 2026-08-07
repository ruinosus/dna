# mcp-entra — built from THIS app's own package, never from a shared
# infra Dockerfile: the version floor lives in pyproject.toml, and a build that
# installed it anywhere else would make the declared floor a lie.
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
