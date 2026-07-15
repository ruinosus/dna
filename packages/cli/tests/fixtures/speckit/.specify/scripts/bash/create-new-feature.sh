#!/usr/bin/env bash
set -e
source "$(dirname "$0")/common.sh"

REPO_ROOT=$(get_repo_root)
FEATURE_DESC="$*"
SHORT_NAME=$(echo "$FEATURE_DESC" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | cut -c1-40)
NEXT=$(printf "%03d" "$(( $(ls -1 "$REPO_ROOT/specs" 2>/dev/null | wc -l) + 1 ))")
BRANCH_NAME="${NEXT}-${SHORT_NAME}"
SPEC_DIR="$REPO_ROOT/specs/$BRANCH_NAME"
mkdir -p "$SPEC_DIR"
cp "$REPO_ROOT/.specify/templates/spec-template.md" "$SPEC_DIR/spec.md"
echo "{\"BRANCH_NAME\":\"$BRANCH_NAME\",\"SPEC_FILE\":\"$SPEC_DIR/spec.md\"}"
