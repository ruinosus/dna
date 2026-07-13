# `dna explain`

Show per-section provenance for a composed agent prompt.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna explain --help`.

## `dna explain`

Show per-section provenance for a composed agent prompt.

```text
dna explain [OPTIONS] [AGENT]
```

**Arguments**

| Argument | Required |
| --- | --- |
| `AGENT` | no |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output (prompt + provenance). |
| `--scope` | Scope holding the agent (default: env / sole scope). |
| `--show-prompt` | Also print the composed prompt below the table. |
| `--tenant` | Resolve with this tenant's overlays (marks overridden sections). |

