# `dna instance`

List, show, create, edit, delete instances.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna instance --help`.

## `dna instance apply`

Upsert instance(s) from a YAML/JSON file, a bundle marker, or a bundle directory.

YAML/JSON files may hold MULTIPLE documents separated by ``---`` (a YAML
stream); each is applied independently in order. Single-doc files behave
exactly as before.

NOTE: this command still uses the local kernel (via dna_session) because
bundle/marker → kind resolution requires walking registered Kinds. Other
`dna instance` commands run via dna-client and don't need DNA_SOURCE_URL set.

```text
dna instance apply [OPTIONS] PATH
```

**Arguments**

| Argument | Required |
| --- | --- |
| `PATH` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--dry-run` | Validate without writing. |
| `--help` | Show this message and exit. |
| `--scope` | Override scope (default from env or doc). |
| `--tenant` | Bind the apply to this tenant (overrides DNA_TENANT). |

## `dna instance create`

Create a new instance via the kernel WriterPort.

```text
dna instance create [OPTIONS] KIND_NAME DOC_NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND_NAME` | yes |
| `DOC_NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--dry-run` | Validate without writing. |
| `--help` | Show this message and exit. |
| `--scope` | Scope to write the instance into (default: env / sole scope). |
| `--spec` | Path to JSON file (or `-` for stdin). |
| `--tenant` | Bind the write to this tenant (overrides DNA_TENANT). |

## `dna instance delete`

Delete an instance from the scope. Asks for confirmation unless --yes.

```text
dna instance delete [OPTIONS] KIND_NAME DOC_NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND_NAME` | yes |
| `DOC_NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope to delete the instance from (default: env / sole scope). |
| `--tenant` | Bind the delete to this tenant (overrides DNA_TENANT). |
| `--yes` | Skip confirmation. |

## `dna instance fields`

List the fields a Kind accepts (with type + enum + required marker).

```text
dna instance fields [OPTIONS] KIND_NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND_NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope holding the Kind (default: env / sole scope). |
| `--tenant` |  |

## `dna instance list`

List instances of a Kind in the scope.

```text
dna instance list [OPTIONS] KIND_NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND_NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--scope` | Scope to list instances from (default: env / sole scope). |
| `--tenant` | Bind to this tenant (overrides DNA_TENANT). |

## `dna instance make`

Create a doc via schema-driven flags (no JSON file needed).

Syntax: dna instance make <Kind> <name> field1=value1 field2=value2 ...

Field types are coerced from the Kind's JSON Schema:
  severity=high                  → "high" (string)
  time_box_hours=8               → 8 (integer)
  repro_steps="step1;step2"      → ["step1", "step2"] (array)
  labels=                        → [] (empty array on empty value)

```text
dna instance make [OPTIONS] KIND_NAME DOC_NAME [FIELDS]...
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND_NAME` | yes |
| `DOC_NAME` | yes |
| `FIELDS...` | no |

**Options**

| Option | Description |
| --- | --- |
| `--dry-run` | Validate without writing. |
| `--help` | Show this message and exit. |
| `--scope` | Scope to write the instance into (default: env / sole scope). |
| `--tenant` | Bind the write to this tenant. |

## `dna instance show`

Print the full instance (raw frontmatter + spec) as JSON.

```text
dna instance show [OPTIONS] KIND_NAME DOC_NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND_NAME` | yes |
| `DOC_NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--scope` | Scope to read the instance from (default: env / sole scope). |
| `--tenant` | Bind to this tenant (overrides DNA_TENANT). |

## `dna instance transition`

Generic status transition for any Kind that declares ``status`` in schema.

Validates new_status against the Kind's status enum. Stamps updated_at,
optionally closed_at (if new_status is terminal — heuristic), commit_ref,
and a timeline entry.

```text
dna instance transition [OPTIONS] KIND_NAME DOC_NAME NEW_STATUS
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND_NAME` | yes |
| `DOC_NAME` | yes |
| `NEW_STATUS` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--commit-ref` | Git SHA to stamp on transition. |
| `--help` | Show this message and exit. |
| `--reason` | Optional reason string. |
| `--scope` | Scope holding the instance (default: env / sole scope). |
| `--tenant` |  |

