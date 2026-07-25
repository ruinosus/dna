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
| `--scope` | Scope to write the Research doc into (default: env / sole scope). |
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
| `--scope` | Scope to list Research docs from (default: env / sole scope). |
| `--status` |  |
| `--tenant` | Optional tenant (Research is PERMISSIVE — omit for base docs). |

## `dna research recall`

Semantic recall over the Research catalog (resolves i-004).

Previously lexical-only (no embeddings server travelled to this repo).
Now routes through ``kernel.search()``: when the ``search-sqlite`` extra is
installed it uses the registered RecordSearchProvider (dense sqlite-vec +
lexical FTS5 fused with RRF — real semantic recall); otherwise it degrades
HONESTLY to the kernel's lexical scan. Thin wrapper over ``dna recall
--kind Research`` so the two share one code path.

```text
dna research recall [OPTIONS] QUERY
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
| `--scope` | Scope to search (default: env / sole scope). |
| `--tenant` | Tenant overlay (base ∪ overlay). |
| `-k`, `--limit` | Max hits. _(default: `10`)_ |

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
| `--scope` | Scope to read the Research doc from (default: env / sole scope). |
| `--tenant` | Optional tenant (Research is PERMISSIVE). |

