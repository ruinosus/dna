# `dna genome`

The Genome view — a module's identity, contents (ships), and Strain policy.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna genome --help`.

## `dna genome view`

Derived view of SCOPE's Genome: identity + ships (the scope's contents) +
the tenant LayerPolicy. Reads the scope live — no stored list, no drift.

```text
dna genome view [OPTIONS] SCOPE
```

**Arguments**

| Argument | Required |
| --- | --- |
| `SCOPE` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable JSON. |

