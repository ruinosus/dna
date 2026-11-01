#!/usr/bin/env bash
# The review as in a cloud sandbox: Linux, as root, with Playwright's Chromium and no other browser. The coffee chain
# with the balloon on the café must be found (exit 3) and the clean one must pass with its snapshots (exit 0) — never
# «not checked». Needs Docker; downloads node:22-slim and Playwright's Chromium (~150 MB). Run after npm run assets.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
skill="$here/../skills/chalk-talk"
name="chalk-talk-linux-check-$$"
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
docker run -d --name "$name" node:22-slim sleep 1800 >/dev/null
docker exec "$name" mkdir -p /work/skill
docker cp "$skill/scripts" "$name:/work/skill/"
docker cp "$skill/assets" "$name:/work/skill/"
docker cp "$here/fixtures" "$name:/work/"
docker exec "$name" bash -c 'cd /work && npm init -y >/dev/null && npm i playwright >/dev/null 2>&1 && npx playwright install --with-deps chromium >/dev/null 2>&1'
docker exec "$name" bash -c '
  set -uo pipefail
  cd /work
  node skill/scripts/build.mjs fixtures/coffee-chain-left.chalk /tmp/left.html; left=$?
  start=$(date +%s%N)
  node skill/scripts/build.mjs fixtures/coffee-chain.chalk /tmp/clean.html --snapshots; clean=$?
  ms=$(( ($(date +%s%N) - start) / 1000000 ))
  shots=$(ls /tmp/cadeia-cafe.snapshots 2>/dev/null | wc -l)
  echo "left exit $left, clean exit $clean in ${ms} ms, $shots files"
  [ "$left" = 3 ] && [ "$clean" = 0 ] && [ "$shots" = 17 ] && echo "✓ linux as root: found, clean, 16 snapshots and a sheet" || { echo "✗ linux check failed"; exit 1; }
'
