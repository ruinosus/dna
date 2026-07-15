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

## `dna specify export-templates`

Project the DNA-stored Spec Kit toolkit back to a byte-faithful
``.specify/`` tree — the inverse of ``install-templates``. Reads every
``speckit-*`` PromptTemplate/Skill/Guardrail carrying a ``spec.origin`` and
replays its verbatim body to that path (round-trips byte-for-byte).

```text
dna specify export-templates [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--force` | Overwrite existing files. |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--out` | Directory to project the .specify/ toolkit into. _(default: `.`)_ |
| `--scope` | Scope to read from (default: env / sole scope). |

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

## `dna specify install-templates`

Ingest a Spec Kit **toolkit** (``.specify/templates/`` + slash-commands +
``.specify/scripts/`` + constitution) into durable, servable DNA Kinds
(ADR §5, Layer 3). Served live over ``dna mcp serve`` and overridable per
scope/tenant. Every write goes through ``kernel.write_document``.

```text
dna specify install-templates [OPTIONS] PATH
```

**Arguments**

| Argument | Required |
| --- | --- |
| `PATH` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--commands-from` | Directory of slash-command markdown (default: auto-detect .specify/templates/commands or a projected agent dir). |
| `--constitution-as` | Map constitution.md to a Guardrail, a Soul, or both. _(default: `both`)_ |
| `--dry-run` | Preview the toolkit→Kind mapping; write nothing. |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable mapping output. |
| `--scope` | Scope to write into (default: env / sole scope). |

## `dna specify wire`

Project the DNA MCP server into each agent's MCP config (ADR Layer 2).

Spec Kit drives whichever agent you chose at ``specify init``; this points
that agent at the LIVE DNA over MCP, so mid-run it has DNA's **memory**
(recall/remember), **soul** (compose_prompt = Soul + Guardrails, composed
live + tenant-aware) and the **board** (sdlc_digest/list_stories) — the SAME
context whether Spec Kit drives Copilot or Claude. One DNA endpoint, N
per-agent projections (the same philosophy as ``dna init``'s skill
projection). Skills themselves travel via ``dna init`` (byte-faithful into
the agent's skill dir); run both to fully ground a Spec Kit run in DNA.


  dna specify wire                         # here, claude+copilot, stdio
  dna specify wire --tools all             # every supported agent
  dna specify wire --http `https://h/mcp/`   # a hosted remote DNA MCP
  dna specify wire --dry-run --json        # preview; write nothing

Non-destructive + idempotent: other MCP servers are preserved, and a
re-run leaves an existing `dna` entry untouched unless --force is given.

```text
dna specify wire [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--dir` | Project directory to wire (default: current directory). _(default: `.`)_ |
| `--dry-run` | Preview the projections; write nothing. |
| `--force` | Replace an existing `dna` server entry (default: leave it and report 'skipped'). Other servers are always preserved. |
| `--help` | Show this message and exit. |
| `--http` | Wire a REMOTE Streamable-HTTP endpoint (a hosted `dna mcp serve --transport http`) instead of spawning a local stdio server. Mutually exclusive with --source-url. |
| `--json` | Machine-readable output. |
| `--source-url` | DNA_SOURCE_URL to pin in the stdio block (default: the ambient DNA_SOURCE_URL / DNA_BASE_DIR the `dna` CLI reads, so the wired agent sees the SAME DNA). |
| `--tools` | Comma-separated agents to project the DNA MCP config for (claude, cursor, copilot, opencode — or 'all'). Default: claude,copilot. |

