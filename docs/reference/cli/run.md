# `dna run`

Execute a resolved DNA Agent through a provider-owned consumer harness. DNA
resolves declarative state and normalizes lifecycle events; the provider keeps
ownership of its model/tool loop and service session.

## Install

The GitHub Copilot provider is optional:

```bash
pip install "dna-cli[harness]"
```

## Agent

```bash
dna run architect --prompt "Analyze this repository"
```

The command auto-detects the scope from `DNA_SCOPE_DEFAULT` or the configured
source. Use `--scope` or `--base-dir` to select it explicitly.

## RuntimeBinding

```bash
dna run --binding local-copilot --prompt "Continue the analysis"
```

The binding selects its Agent and provider. `spec.host.ref` remains a
deployment reference; the local command does not treat it as an endpoint.

## Resume

A completed human-readable run prints its local and provider session IDs:

```text
Session: local-id (service: provider-id)
```

Pass both values to continue the provider conversation:

```bash
dna run architect --prompt "Continue" \
  --session-id local-id \
  --service-session-id provider-id
```

## JSON Lines

`--json` emits one object per lifecycle event. Stable event types include
`run.started`, `session.started`, `session.resumed`, `message.delta`,
`message.completed`, `run.completed`, `run.failed`, and `run.cancelled`.

```bash
dna run architect --prompt "Analyze" --json
```

Ctrl+C cancels the active provider run and exits with status 130.

## Options

```text
Usage: dna run [OPTIONS] [AGENT_NAME]

Options:
  --binding TEXT             RuntimeBinding to resolve.
  --prompt TEXT              Prompt sent to the resolved Agent.  [required]
  --scope TEXT               DNA scope (auto-detected when omitted).
  --base-dir DIRECTORY       DNA source directory.
  --provider TEXT            Harness provider (default: github-copilot).
  --session-id TEXT          Stable local session identifier.
  --service-session-id TEXT  Provider session identifier to resume.
  --json                     Emit JSON Lines events.
  -h, --help                 Show this message and exit.
```