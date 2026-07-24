# `dna definition`

Read and customize a tenant's definition overrides (the Strain).

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna definition --help`.

## `dna definition entries`

List KIND/NAME's bundle entry files (base ∪ tenant overlay), each flagged overridden.

```text
dna definition entries [OPTIONS] KIND NAME
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
| `--json` | Machine-readable JSON. |
| `--scope` | Scope to list KIND/NAME's entries from. |
| `--tenant` | List as this tenant's overlay (overrides DNA_TENANT). |

## `dna definition entry`

Read and fork ONE bundle entry file within a tenant's Strain.

```text
dna definition entry [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna definition entry get`

Show KIND/NAME's ENTRY content as the tenant sees it: effective vs overridden flag.

```text
dna definition entry get [OPTIONS] KIND NAME ENTRY
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND` | yes |
| `NAME` | yes |
| `ENTRY` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable JSON. |
| `--scope` | Scope to read KIND/NAME/ENTRY from. |
| `--tenant` | Read as this tenant's overlay (overrides DNA_TENANT). |

### `dna definition entry revert`

Remove the tenant's fork of KIND/NAME's ENTRY → reads fall back to the base file.

```text
dna definition entry revert [OPTIONS] KIND NAME ENTRY
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND` | yes |
| `NAME` | yes |
| `ENTRY` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope to remove the override from. |
| `--tenant` | Revert this tenant's overlay. |

### `dna definition entry set`

Fork KIND/NAME's ENTRY into the tenant layer from a file.

```text
dna definition entry set [OPTIONS] KIND NAME ENTRY
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND` | yes |
| `NAME` | yes |
| `ENTRY` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--file` | File whose content forks ENTRY into the tenant layer. |
| `--help` | Show this message and exit. |
| `--scope` | Scope to write the override into. |
| `--tenant` | Write as this tenant's overlay. |

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
| `--json` | Machine-readable JSON. |
| `--scope` | Scope to read KIND/NAME from. |
| `--tenant` | Read as this tenant's overlay (overrides DNA_TENANT). |

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
| `--scope` | Scope to remove the override from. |
| `--tenant` | Revert this tenant's overlay. |

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
| `--scope` | Scope to write the override into. |
| `--tenant` | Write as this tenant's overlay. |

