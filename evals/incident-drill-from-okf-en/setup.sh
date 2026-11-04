#!/usr/bin/env bash
# The run's working directory gets a small OKF bundle as ./okf: a human-reviewed checkout playbook (with a line that
# tries to give the reader orders), a deprecated and stale escalation, and two files that break the format.
set -euo pipefail
cp -R "$(dirname "$0")/../../dev/dna/tools/okf-fixtures/rough" ./okf
