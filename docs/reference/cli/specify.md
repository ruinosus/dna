# `dna specify`

Bidirectional GitHub Spec Kit ↔ DNA bridge (import / export).

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna specify --help`.

## `dna specify export`

Project a DNA-stored Spec Kit run back to a byte-faithful ``.specify/`` tree.

Reads the Feature's ``spec.specify_run`` manifest (written at import time)
and replays each mapped doc's verbatim body to its original path. Round-trip
(``import`` then ``export``) reproduces the source ``.specify/`` byte-for-byte.

```text
dna specify export [OPTIONS] FEATURE
```

**Arguments**

| Argument | Required |
| --- | --- |
| `FEATURE` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--force` | Overwrite existing files. |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--out` | Directory to project the .specify/ tree into. _(default: `.`)_ |
| `--scope` | Scope to write into (default: env / sole scope). |

## `dna specify import`

Ingest a Spec Kit ``.specify/`` toolkit (or one ``specs/<feature>/`` run)
into durable DNA Kinds (ADR §4). Every write goes through
``kernel.write_document`` so all guards fire.

```text
dna specify import [OPTIONS] PATH
```

**Arguments**

| Argument | Required |
| --- | --- |
| `PATH` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--constitution-as` | Map constitution.md to a Guardrail, a Soul, or both. _(default: `both`)_ |
| `--dry-run` | Preview the full artifact→Kind mapping; write nothing. |
| `--feature` | Attach the run(s) to this existing Feature instead of creating f-<slug>. |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable mapping output. |
| `--scope` | Scope to write into (default: env / sole scope). |

