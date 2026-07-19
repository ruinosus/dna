# `dna memory`

Declarative memory over existing Kinds (remember/recall/forget/consolidate).

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna memory --help`.

## `dna memory consolidate`

Deterministic consolidation pass — recompute decay, report/soft-forget
stale memories. NO LLM (that scribe is external + optional).

```text
dna memory consolidate [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--apply` | Soft-forget stale memories (bi-temporal, never delete). |
| `--floor` | Retention floor below which a memory is stale. _(default: `0.15`)_ |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--kind` | _(default: `Engram`)_ |
| `--scope` |  |
| `--tenant` |  |

## `dna memory export`

Project Engrams to a portable MIF bundle. Deterministic, no LLM, no network.

```text
dna memory export [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--bundle` | Emit a single JSON-LD file instead of N .md files. |
| `--format` | Interchange format. Only 'mif' is implemented; --format omp/pam are a documented future switch (design §2/§9). _(default: `mif`)_ |
| `--help` | Show this message and exit. |
| `--include-forgotten` | Include bi-temporally invalidated memories (valid_to<now), temporal preserved — otherwise supersession looks like a silent delete on export. |
| `--json` |  |
| `--kind` | Source memory kind. Only Engram has a MIF field mapping today. _(default: `Engram`)_ |
| `--out` | Output path — a directory (one <id>.md per memory) or, with --bundle, a single JSON-LD file. Default: ./mif-export/ (or ./mif-export.json with --bundle). |
| `--personal` | Export YOUR OWN private partition (DNA_PERSONAL_ID) — never workspace memory (INV-PERSONAL). |
| `--scope` |  |
| `--tenant` |  |

## `dna memory forget`

Bi-temporal DEMOTION — set valid_to (never hard-delete).

```text
dna memory forget [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--kind` | _(default: `Engram`)_ |
| `--scope` |  |
| `--superseded-by` | Name of the memory that supersedes this one. |
| `--tenant` |  |

## `dna memory import`

Ingest a MIF bundle (PATH: a .md/.json file or a directory of them).

``--as both`` (default) stores the original MIF doc byte-for-byte as
``mif-spec.dev/v1 · Memory`` (passthrough — auditable, stable re-export)
AND projects an ``Engram`` (indexable/recallable by ``dna memory
recall``). Deterministic, no LLM, no network.

```text
dna memory import [OPTIONS] PATH
```

**Arguments**

| Argument | Required |
| --- | --- |
| `PATH` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--as` | passthrough = store the MIF doc verbatim only; native = project to Engram only; both = store verbatim AND project (default — auditable + recallable). _(default: `both`)_ |
| `--dedupe` | id = skip a doc whose MIF id was already imported (idempotent re-import, the §6 contract); content-hash = skip by exact content match; off = no pre-check. _(default: `id`)_ |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--personal` | Import into YOUR OWN private partition (DNA_PERSONAL_ID) — never a shared partition (INV-PERSONAL). |
| `--scope` |  |
| `--tenant` |  |

## `dna memory list`

List memories in the scope (current by default; ``--all`` includes forgotten).

```text
dna memory list [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--all` | Include bi-temporally-invalidated (forgotten) memories. |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--kind` | _(default: `Engram`)_ |
| `--scope` |  |
| `--tenant` |  |

## `dna memory recall`

Hybrid, bi-temporal, retention-re-scored recall over the memory Kinds.

```text
dna memory recall [OPTIONS] QUERY
```

**Arguments**

| Argument | Required |
| --- | --- |
| `QUERY` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--actor` | Who is recalling (stamped in cues_history). _(default: `cli`)_ |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--kind` | Restrict to memory kind(s). Default: all. |
| `--no-reconsolidate` | Skip the cue/confidence bump side-effect. |
| `--personal` | Recall YOUR OWN private memory (DNA_PERSONAL_ID), unioned with the base defaults — never any workspace's memory. |
| `--scope` |  |
| `--semantic`, `--no-semantic` | Blend embedding similarity into the ecphory ranking (RRF fusion). Default: auto — on when the search provider is available. |
| `--tenant` |  |
| `-k`, `--limit` | _(default: `5`)_ |

## `dna memory remember`

Write a memory Kind + deterministic encoding-context + index it.

```text
dna memory remember [OPTIONS] SUMMARY
```

**Arguments**

| Argument | Required |
| --- | --- |
| `SUMMARY` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--affect` | _(default: `triumph`)_ |
| `--area` | Scoped target area (Feature/X, Epic/Y, …). _(default: `general`)_ |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--kind` | _(default: `Engram`)_ |
| `--name` | Doc name (default: rem-<hash> of summary). |
| `--owner` | Authoring agent (claude-code, jarvis, …). |
| `--personal` | Remember PRIVATELY — into your own per-user partition (DNA_PERSONAL_ID), portable across workspaces, not shared. |
| `--reason` | Concrete justification for the affect (≥20 chars). |
| `--scope` | Scope (default: first/only scope). |
| `--source-ref` | Source artifact ref (repeatable). |
| `--tag` | Tag (repeatable) — also seeds encoding_context co_topics. |
| `--tenant` | Tenant overlay. |

