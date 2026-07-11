#!/usr/bin/env sh
# Entrypoint for the hosted DNA MCP server.
#
# Turns the container's env into a `dna mcp serve` invocation, so the SAME image
# runs authenticated (--auth jwt, the hosted default) or open (--auth none, for a
# throwaway local run) by flipping one env var — no rebuild. Every knob has a
# sane default (the Dockerfile ENV block sets them); the Container App overrides
# the auth + source vars (see resources.bicep).
set -eu

TRANSPORT="${DNA_MCP_TRANSPORT:-http}"
HOST="${DNA_MCP_HOST:-0.0.0.0}"
PORT="${DNA_MCP_PORT:-8080}"
AUTH="${DNA_MCP_AUTH:-jwt}"

echo "[dna-mcp] starting: transport=${TRANSPORT} host=${HOST} port=${PORT} auth=${AUTH}"
echo "[dna-mcp] source: DNA_SOURCE_URL=${DNA_SOURCE_URL:-<unset>} DNA_BASE_DIR=${DNA_BASE_DIR:-<unset>}"

# exec so `dna` is PID 1 and receives SIGTERM directly (clean Container App
# scale-down / revision restart).
exec dna mcp serve \
  --transport "${TRANSPORT}" \
  --host "${HOST}" \
  --port "${PORT}" \
  --auth "${AUTH}"
