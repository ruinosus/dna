# `dna mcp`

Expose the live DNA (definitions + SDLC + memory) over MCP.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna mcp --help`.

## `dna mcp serve`

Run the DNA MCP server (stdio).


Wire it into a client (e.g. Claude Code / Cursor mcp config):
  {
    "mcpServers": {
      "dna": {
        "command": "dna",
        "args": ["mcp", "serve"],
        "env": { "DNA_SOURCE_URL": "`file:///abs/path/to/.dna"` }
      }
    }
  }
Then the client can call compose_prompt / sdlc_digest / recall, and read the
`dna://{scope}/manifest` resource — all against your live DNA.

```text
dna mcp serve [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--base-dir` | Source directory override (else DNA_SOURCE_URL / DNA_BASE_DIR / ./.dna). |
| `--help` | Show this message and exit. |
| `--scope` | Default scope for tools that omit one (else the sole/first scope). |
| `--transport` | MCP transport. The MVP ships stdio (local clients); remote Streamable HTTP is Phase 2 (story s-mcp-remote-transport). _(default: `stdio`)_ |

