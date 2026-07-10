# `dna scope`

List + inspect scopes (manifest modules).

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna scope --help`.

## `dna scope detect`

Walk upward from cwd looking for the nearest .dna/<scope>/Genome.yaml.

Phase 14u — used by the Claude Code PreToolUse hook to auto-inject
scope context. Prints the scope name to stdout (no decorations) so
shell scripts can capture it via $(dna scope detect).

Genome.yaml is the canonical scope-root marker (Phase 16); the legacy
pre-Genome manifest.yaml is still accepted (i-007) — same dual-marker
contract as `dna install` and the composite source.

```text
dna scope detect [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--cwd` | Override starting directory (default: CWD). |
| `--help` | Show this message and exit. |

## `dna scope list`

List discoverable scopes from the configured source.

Uses dna-client (HTTP to kinds-api) instead of building a local
kernel — avoids the asyncpg "task attached to different loop"
error that happens when a click-sync entrypoint calls
kernel.list_scopes_async() against a holder built in a different
event loop.

```text
dna scope list [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--tenant` | Route as this tenant (overrides DNA_TENANT). |

## `dna scope tree`

Inventory all documents in a scope, grouped by Kind.

Migrated to dna-client (HTTP /scopes/{X}/tree) so it doesn't need
DNA_SOURCE_URL set in the CLI's own env — the kinds-api already
has the kernel and serves the snapshot.

```text
dna scope tree [OPTIONS] [SCOPE_NAME]
```

**Arguments**

| Argument | Required |
| --- | --- |
| `SCOPE_NAME` | no |

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` |  |
| `--tenant` | Route as this tenant (overrides DNA_TENANT). |

