#!/usr/bin/env bash
# Seed / update the hosted DNA source — upload a local .dna scope to the Azure
# Files share the Container App mounts read-only at /mnt/dna, then restart the
# app's revision so it re-reads. The runtime never writes the source; publishing
# is always this out-of-band push (the same shape as the sibling Foundry app's
# prompt-publish leg).
#
# Usage (from deploy/azure/, after `azd up`):
#   ./scripts/push-scope.sh ../../.dna            # push a local .dna tree
#   ./scripts/push-scope.sh /path/to/your/.dna
#
# Reads the provisioned names from the azd environment (.azure/<env>/.env):
#   STORAGE_ACCOUNT_NAME, DNA_SOURCE_SHARE, plus AZURE_ENV_NAME for the app name.
# Requires: azd, az (Azure CLI) logged in to the same subscription.
set -euo pipefail

LOCAL_DNA="${1:?usage: push-scope.sh <path-to-.dna>}"

if [ ! -d "$LOCAL_DNA" ]; then
  echo "error: '$LOCAL_DNA' is not a directory" >&2
  exit 1
fi

# Pull the provisioned resource names from the azd environment.
eval "$(azd env get-values | sed 's/^/export /')"

: "${STORAGE_ACCOUNT_NAME:?not set — run azd up first}"
: "${DNA_SOURCE_SHARE:?not set — run azd up first}"

echo "[push-scope] uploading $LOCAL_DNA -> //${STORAGE_ACCOUNT_NAME}/${DNA_SOURCE_SHARE}"
az storage file upload-batch \
  --account-name "$STORAGE_ACCOUNT_NAME" \
  --destination "$DNA_SOURCE_SHARE" \
  --source "$LOCAL_DNA" \
  --auth-mode key \
  --output none

# Restart the running revision so the mounted source is re-read.
RG="rg-${AZURE_ENV_NAME}"
APP="$(az containerapp list --resource-group "$RG" --query "[?tags.\"azd-service-name\"=='mcp'].name | [0]" -o tsv)"
if [ -n "${APP:-}" ]; then
  echo "[push-scope] restarting Container App revision ($APP)"
  REV="$(az containerapp revision list --name "$APP" --resource-group "$RG" --query "[0].name" -o tsv)"
  az containerapp revision restart --name "$APP" --resource-group "$RG" --revision "$REV" --output none
fi

echo "[push-scope] done — the hosted MCP server now serves your scope from /mnt/dna"
