# `dna kind`

List + inspect registered Kinds.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna kind --help`.

## `dna kind describe`

Show the JSON Schema + storage descriptor for a Kind.

```text
dna kind describe [OPTIONS] KIND_NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND_NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | _(default: `dna-development`)_ |
| `--tenant` | Route as this tenant. |

## `dna kind list`

List all Kinds registered on the kernel (in the given scope).

```text
dna kind list [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | JSON output. |
| `--scope` | Scope to enumerate kinds from. _(default: `dna-development`)_ |
| `--tenant` | Route as this tenant. |

