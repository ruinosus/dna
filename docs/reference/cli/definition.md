# `dna definition`

Read and customize a tenant's definition overrides (the Strain).

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna definition --help`.

## `dna definition get`

Show KIND/NAME as the tenant sees it: effective vs base + overridden flag.

```text
dna definition get [OPTIONS] KIND NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND` | yes |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--scope` |  |
| `--tenant` |  |

## `dna definition revert`

Remove the tenant override for KIND/NAME → reads fall back to the base.

```text
dna definition revert [OPTIONS] KIND NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND` | yes |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` |  |
| `--tenant` |  |

## `dna definition set`

Write the tenant override for KIND/NAME from a spec file.

```text
dna definition set [OPTIONS] KIND NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND` | yes |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--file` | YAML/JSON file whose top-level `spec:` (or the whole doc) is the override spec. |
| `--help` | Show this message and exit. |
| `--scope` |  |
| `--tenant` |  |

