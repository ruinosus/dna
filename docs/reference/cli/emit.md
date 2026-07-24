# `dna emit`

Emit a DNA agent as a target runtime's native artifact (the de-para).

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna emit --help`.

## `dna emit`

Emit a DNA agent as a target runtime's native artifact (the de-para).

```text
dna emit [OPTIONS] [AGENT]
```

**Arguments**

| Argument | Required |
| --- | --- |
| `AGENT` | no |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--hosting` | Treat AGENT as a Copilot and emit its HOSTED variant (hosting.mode=hosted) — Foundry Dockerfile/main.py/requirements/azure.yaml (first-class), langgraph/agentos documented (f-copilot-hosting). Writes N files; needs --out DIR. |
| `--infra` | Treat AGENT as a Copilot and emit its Terraform infra inputs (<agent>.tfvars.json) — the persistence/knowledge.store/hosting → TF module inputs (f-copilot-infra-binding). |
| `--json` | Machine-readable output (artifact + de-para). |
| `--list-targets` | List the registered emit targets and exit. |
| `--model` | Override the model coordinate (else agent.spec.model / Genome default_llm). |
| `--out`, `-o` | Write the artifact to this file instead of stdout. |
| `--provider` | Override the provider the target binds (e.g. AzureOpenAI, OpenAI). |
| `--scope` | Scope holding the agent (default: env / sole scope). |
| `--target`, `-t` | Runtime to emit for (e.g. agent-framework). See --list-targets. When AGENT is a Copilot, picks the servable runtime (agno default; agent-framework). The langgraph copilot scaffold is retired — use dna.runtime.build_copilot instead. |

