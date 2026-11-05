#!/usr/bin/env bash
# The run's working directory gets the synthetic examples as ./workday-files (the Operation Directory text and two
# WSDLs with made-up fields): what a person would have downloaded, for the skill to index.
set -euo pipefail
cp -R "$(dirname "$0")/../skills/workday-integration/examples" ./workday-files
