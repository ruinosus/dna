# `dna run`

Run AGENT_NAME or a RuntimeBinding through a consumer harness.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna run --help`.

## `dna run`

Run AGENT_NAME or a RuntimeBinding through a consumer harness.

```text
dna run [OPTIONS] [AGENT_NAME]
```

**Arguments**

| Argument | Required |
| --- | --- |
| `AGENT_NAME` | no |

**Options**

| Option | Description |
| --- | --- |
| `--base-dir` | DNA source directory. |
| `--binding` | RuntimeBinding to resolve. |
| `--help` | Show this message and exit. |
| `--json` | Emit JSON Lines events. |
| `--prompt` | Prompt sent to the resolved Agent. |
| `--provider` | Harness provider (default: github-copilot). |
| `--scope` | DNA scope (auto-detected when omitted). |
| `--service-session-id` | Provider session identifier to resume. |
| `--session-id` | Stable local session identifier. |

