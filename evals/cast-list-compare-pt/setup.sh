#!/usr/bin/env bash
# The run's working directory gets the skill's six fictional agents as ./agentes (a cloned Copilot Studio folder).
set -euo pipefail
cp -R "$(dirname "$0")/../../skills/agent-review/examples/agents" ./agentes
