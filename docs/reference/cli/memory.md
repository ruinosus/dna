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
| `--kind` | _(default: `LessonLearned`)_ |
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
| `--kind` | _(default: `LessonLearned`)_ |
| `--scope` |  |
| `--superseded-by` | Name of the memory that supersedes this one. |
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
| `--kind` | _(default: `LessonLearned`)_ |
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
| `--kind` | _(default: `LessonLearned`)_ |
| `--name` | Doc name (default: rem-<hash> of summary). |
| `--owner` | Authoring agent (claude-code, jarvis, …). |
| `--reason` | Concrete justification for the affect (≥20 chars). |
| `--scope` | Scope (default: first/only scope). |
| `--source-ref` | Source artifact ref (repeatable). |
| `--tag` | Tag (repeatable) — also seeds encoding_context co_topics. |
| `--tenant` | Tenant overlay. |

