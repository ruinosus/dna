# `dna rename`

Rename an instance and repoint the AUTHORED references to it.

The declared relations that name it are rewritten field-by-field — never by
text substitution, so a longer name that merely CONTAINS the old one is
untouched. References from another scope are listed and left alone; prose
is neither rewritten nor searched. ``--dry-run`` prints the same plan
without writing, because what this operation promises is that the result
shows up in the diff of a pull request.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna rename --help`.

## `dna rename`

Rename an instance and repoint the AUTHORED references to it.

The declared relations that name it are rewritten field-by-field — never by
text substitution, so a longer name that merely CONTAINS the old one is
untouched. References from another scope are listed and left alone; prose
is neither rewritten nor searched. ``--dry-run`` prints the same plan
without writing, because what this operation promises is that the result
shows up in the diff of a pull request.

```text
dna rename [OPTIONS] KIND_NAME OLD_NAME NEW_NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND_NAME` | yes |
| `OLD_NAME` | yes |
| `NEW_NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--dry-run` | Show exactly what would change; write nothing. |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--scope` | Scope holding the instance (default: env / sole scope). |
| `--tenant` | Bind to this tenant. |

