# `dna graph`

The derived reference graph (declared relations).

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna graph --help`.

## `dna graph backfill`

Compute edges for documents that predate the producer.

For each declared ``(Kind, field)`` pair, ask the store for the documents
whose ``spec`` HAS that field — on Postgres a JSONB key-existence query the
``dna_docs_spec_gin_idx`` index serves directly. That is a handful of
queries, not a walk over every document.

A document whose references cannot be resolved COMPLETELY (a read failed
part-way) is left alone and its scope is reported as pending: a partial
edge set stored as if it were whole is a graph that lies while looking
finished, and the screen can label an absent graph but not a lying one.

```text
dna graph backfill [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--dry-run` | Resolve everything, write nothing — same reads, real numbers. |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--scope` | Only this scope (default: every scope in the store). |

## `dna graph refs`

"What points at this document?" — the same walk the REST face serves.

```text
dna graph refs [OPTIONS] KIND_NAME NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND_NAME` | yes |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--depth` | Walk further; clamped by DNA_GRAPH_MAX_DEPTH. _(default: `1`)_ |
| `--direction` | 'in' = what points AT this document (the product question). _(default: `in`)_ |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--scope` |  |
| `--tenant` |  |

