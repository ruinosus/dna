#!/usr/bin/env bash
# The run's working directory gets the skill's six fictional agents as ./agentes and the example profile (markers, the
# official links block, types) as ./perfil.cast.yaml.
set -euo pipefail
here="$(dirname "$0")/../../skills/cast-list/examples"
cp -R "$here/agents" ./agentes
cp "$here/profile.cast.yaml" ./perfil.cast.yaml
