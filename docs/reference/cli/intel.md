# `dna intel`

Portfolio intelligence — run passes, inspect sources + insights.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna intel --help`.

## `dna intel list`

List produced IntelInsight docs (ranked, feedback state).

```text
dna intel list [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--scope` | _(default: `dna-development`)_ |
| `--source` | Filter by originating IntelSource. |
| `--state` |  |
| `--tenant` | Tenant (default: $DNA_TENANT or 'demo'). |

## `dna intel run`

Run one intel pass over SOURCE: pass → rank → suppress → deliver.

Writes the surviving insights as IntelInsight docs (state=new) and prints
what was KEPT vs SUPPRESSED (below the source threshold — the anti-noise
core). Uses the SeedAnalyzer (real experiment insights, no LLM creds needed).

```text
dna intel run [OPTIONS] SOURCE
```

**Arguments**

| Argument | Required |
| --- | --- |
| `SOURCE` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--scope` | _(default: `dna-development`)_ |
| `--tenant` | Tenant (default: $DNA_TENANT or 'demo'). |

## `dna intel sources`

List the watched IntelSource docs (the Direction stage).

```text
dna intel sources [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--scope` | _(default: `dna-development`)_ |
| `--tenant` | Tenant (default: $DNA_TENANT or 'demo'). |

