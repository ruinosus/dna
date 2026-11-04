#!/usr/bin/env bash
# The run's working directory gets the skill's six fictional agents as ./agentes, the example profile as
# ./perfil.cast.yaml and the example export of Application Insights (the query of references/telemetry.md) as
# ./eventos.csv.
set -euo pipefail
here="$(dirname "$0")/../../skills/agent-review/examples"
cp -R "$here/agents" ./agentes
cp "$here/profile.cast.yaml" ./perfil.cast.yaml
cp "$here/telemetria.csv" ./eventos.csv
