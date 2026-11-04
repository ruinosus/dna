#!/usr/bin/env bash
# The run's working directory gets the skill's six fictional agents as ./agentes, the example profile as
# ./perfil.cast.yaml, the admin center's inventory as ./inventario.csv, the team spreadsheet as ./equipe.csv and the
# export of Application Insights as ./eventos.csv.
set -euo pipefail
here="$(dirname "$0")/../../skills/agent-review/examples"
cp -R "$here/agents" ./agentes
cp "$here/profile.cast.yaml" ./perfil.cast.yaml
cp "$here/inventario.csv" ./inventario.csv
cp "$here/equipe.csv" ./equipe.csv
cp "$here/telemetria.csv" ./eventos.csv
