# `dna source`

Source-level operations: declarative replicas, introspection.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna source --help`.

## `dna source diff`

s-sync-s4 — semantic diff of a scope between the CURRENT source
(DNA_SOURCE_URL) and OTHER_URL (e.g. `file://./scopes` or a postgres URL).

Compares Kind-aware content digests (not raw text), so formatting,
frontmatter re-serialization and volatile stamps never show as drift.
Reports added (in current, missing in other), removed (in other only),
and changed (digest drifted).

```text
dna source diff [OPTIONS] OTHER_URL
```

**Arguments**

| Argument | Required |
| --- | --- |
| `OTHER_URL` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--authored-only` | Skip runtime-generated Kinds (EvalRun, Narrative, …) — compare only authored docs (the FS git source-of-truth class). |
| `--help` | Show this message and exit. |
| `--json` | Emit JSON. |
| `--scope` | Scope to compare. |
| `--tenant` | Tenant layer (default: base). |

## `dna source push`

s-sync-s5 — reconcile TO_URL to match the CURRENT source (DNA_SOURCE_URL,
the source-of-truth) for a scope. Writes added/changed docs atomically
(doc + bundle via the s-sync-s3 net). Dry-run by default — pass --apply to
write. --prune also removes docs that exist only in the target.

```text
dna source push [OPTIONS] TO_URL
```

**Arguments**

| Argument | Required |
| --- | --- |
| `TO_URL` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--apply` | Actually write to the target (default: dry-run preview only). |
| `--authored-only` | Skip runtime-generated Kinds — push only authored docs. |
| `--help` | Show this message and exit. |
| `--json` | Emit JSON. |
| `--prune` | Delete docs that exist ONLY in the target (off by default). |
| `--scope` | Scope to reconcile. |
| `--tenant` | Tenant layer (default: base). |

## `dna source replica`

Manage source replicas (.dna-replicas.yaml).

```text
dna source replica [OPTIONS] COMMAND [ARGS]...
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |

### `dna source replica add`

Add a new replica entry. Errors on duplicate id.

```text
dna source replica add [OPTIONS] REPLICA_ID
```

**Arguments**

| Argument | Required |
| --- | --- |
| `REPLICA_ID` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--config` | Path to .dna-replicas.yaml (default: walk up from cwd, then cwd). |
| `--help` | Show this message and exit. |
| `--kinds` | Comma-separated Kind allowlist. Omit = all kinds. |
| `--replica` | Destination URL (`fs://path` or `file://path`). |
| `--scopes` | Comma-separated scope allowlist (e.g. dna-development). |

### `dna source replica disable`

Set enabled=false for a replica (soft-mute without losing config).

```text
dna source replica disable [OPTIONS] REPLICA_ID
```

**Arguments**

| Argument | Required |
| --- | --- |
| `REPLICA_ID` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--config` |  |
| `--help` | Show this message and exit. |

### `dna source replica drop`

Remove a replica entry.

```text
dna source replica drop [OPTIONS] REPLICA_ID
```

**Arguments**

| Argument | Required |
| --- | --- |
| `REPLICA_ID` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--config` |  |
| `--help` | Show this message and exit. |

### `dna source replica enable`

Set enabled=true for a replica.

```text
dna source replica enable [OPTIONS] REPLICA_ID
```

**Arguments**

| Argument | Required |
| --- | --- |
| `REPLICA_ID` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--config` |  |
| `--help` | Show this message and exit. |

### `dna source replica list`

List replicas declared in the config file.

```text
dna source replica list [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--config` |  |
| `--help` | Show this message and exit. |
| `--json` |  |

### `dna source replica show`

Show full entry for one replica id.

```text
dna source replica show [OPTIONS] REPLICA_ID
```

**Arguments**

| Argument | Required |
| --- | --- |
| `REPLICA_ID` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--config` |  |
| `--help` | Show this message and exit. |

