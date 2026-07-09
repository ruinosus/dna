# `dna doc`

List, show, create, edit, delete documents.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna doc --help`.

## `dna doc apply`

Upsert document(s) from a YAML/JSON file, a bundle marker, or a bundle directory.

YAML/JSON files may hold MULTIPLE documents separated by ``---`` (a YAML
stream); each is applied independently in order. Single-doc files behave
exactly as before.

NOTE: this command still uses the local kernel (via dna_session) because
bundle/marker → kind resolution requires walking registered Kinds. Other
`dna doc` commands run via dna-client and don't need DNA_SOURCE_URL set.

```text
dna doc apply [OPTIONS] PATH
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

## `dna doc create`

Create a new document via the kernel WriterPort.

```text
dna doc create [OPTIONS] KIND_NAME DOC_NAME
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
| `--scope` | _(default: `dna-development`)_ |
| `--spec` | Path to JSON file (or `-` for stdin). |
| `--tenant` | Bind the write to this tenant (overrides DNA_TENANT). |

## `dna doc delete`

Delete a document from the scope. Asks for confirmation unless --yes.

```text
dna doc delete [OPTIONS] KIND_NAME DOC_NAME
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
| `--scope` | _(default: `dna-development`)_ |
| `--tenant` | Bind the delete to this tenant (overrides DNA_TENANT). |
| `--yes` | Skip confirmation. |

## `dna doc fields`

List the fields a Kind accepts (with type + enum + required marker).

```text
dna doc fields [OPTIONS] KIND_NAME
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
| `--tenant` |  |

## `dna doc list`

List documents of a Kind in the scope.

```text
dna doc list [OPTIONS] KIND_NAME
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
| `--scope` | _(default: `dna-development`)_ |
| `--tenant` | Bind to this tenant (overrides DNA_TENANT). |

## `dna doc make`

Create a doc via schema-driven flags (no JSON file needed).

Syntax: dna doc make <Kind> <name> field1=value1 field2=value2 ...

Field types are coerced from the Kind's JSON Schema:
  severity=high                  → "high" (string)
  time_box_hours=8               → 8 (integer)
  repro_steps="step1;step2"      → ["step1", "step2"] (array)
  labels=                        → [] (empty array on empty value)

```text
dna doc make [OPTIONS] KIND_NAME DOC_NAME [FIELDS]...
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
| `--scope` | _(default: `dna-development`)_ |
| `--tenant` | Bind the write to this tenant. |

## `dna doc show`

Print the full document (raw frontmatter + spec) as JSON.

```text
dna doc show [OPTIONS] KIND_NAME DOC_NAME
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
| `--scope` | _(default: `dna-development`)_ |
| `--tenant` | Bind to this tenant (overrides DNA_TENANT). |

## `dna doc transition`

Generic status transition for any Kind that declares ``status`` in schema.

Validates new_status against the Kind's status enum. Stamps updated_at,
optionally closed_at (if new_status is terminal — heuristic), commit_ref,
and a timeline entry.

```text
dna doc transition [OPTIONS] KIND_NAME DOC_NAME NEW_STATUS
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
| `--scope` | _(default: `dna-development`)_ |
| `--tenant` |  |

