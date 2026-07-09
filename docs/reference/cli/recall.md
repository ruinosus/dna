# `dna recall`

Hybrid semantic search (dense + lexical + RRF) over the scope's records.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna recall --help`.

## `dna recall`

Hybrid semantic search (dense + lexical + RRF) over the scope's records.

```text
dna recall [OPTIONS] QUERY
```

**Arguments**

| Argument | Required |
| --- | --- |
| `QUERY` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--kind` | Restrict to a record kind (repeatable). Default: every kind in the scope. |
| `--scope` | Scope to search (default: first/only scope). |
| `--tenant` | Tenant overlay (base ∪ overlay; overlay shadows base). |
| `-k`, `--limit` | Max hits. _(default: `10`)_ |

