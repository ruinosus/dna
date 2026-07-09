# `dna research`

Manage Research synthesis documents (curated syntheses of References).

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna research --help`.

## `dna research create`

Create/upsert a Research doc from a YAML/JSON file.

First-class research authoring (no ``dna doc apply`` needed). Validates
kind == Research and the spec schema BEFORE writing. Tenancy is
permissive: ``--tenant`` optional.

```text
dna research create [OPTIONS] PATH
```

**Arguments**

| Argument | Required |
| --- | --- |
| `PATH` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | _(default: `dna-development`)_ |
| `--status` | Override spec.status (else the file's value, else 'draft'). |
| `--tenant` | Optional tenant (Research is PERMISSIVE — omit for base docs). |

## `dna research list`

List Research docs in the scope, with key metadata.

```text
dna research list [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--methodology` |  |
| `--scope` | _(default: `dna-development`)_ |
| `--status` | _(default: `Sentinel.UNSET`)_ |
| `--tenant` | Optional tenant (Research is PERMISSIVE — omit for base docs). |

## `dna research show`

Show a Research doc + its citation graph.

```text
dna research show [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--full` | Print all findings + recommendations. |
| `--help` | Show this message and exit. |
| `--scope` | _(default: `dna-development`)_ |
| `--tenant` | Optional tenant (Research is PERMISSIVE). |

