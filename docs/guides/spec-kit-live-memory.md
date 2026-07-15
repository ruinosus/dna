# Spec Kit + DNA's live memory over MCP

[GitHub **Spec Kit**](https://github.com/github/spec-kit) drives an AI coding
agent through `constitution → spec → plan → tasks → implement`. It is
*agent-agnostic*: at `specify init --integration <agent>` it projects one command
set into ~30 agents (Copilot, Claude, Cursor, Codex, opencode…). But whichever
agent it drives starts **blind** — it has only what is in the repo, not your
accumulated context.

This guide wires the **other half** of the adoption (ADR
*ADR-spec-kit-adoption* **Layer 2**): point that Spec-Kit-driven agent at the
**live DNA over MCP**, so mid-run it has
your portable **memory**, your **soul** (persona + guardrails) and your **board**
— and it is the **same** context whether Spec Kit drives Copilot or Claude.

> Layer 1 (`dna specify import`/`export`, see [Spec Kit — the supported
> spec-driven flow](spec-kit.md)) captures a run *into* DNA **after** it happens.
> Layer 2 feeds DNA *into* the run **while** it happens. They compose.

## One command: `dna specify wire`

Spec Kit is agent-agnostic because it projects one command set into N agents.
DNA is agent-agnostic the same way — `dna init` projects one Skill Kind into each
agent's skill dir ("one source, N projections"). `dna specify wire` applies that
exact philosophy to the **MCP server block**: one DNA MCP endpoint, projected
into each agent's *own* MCP config file.

```console
$ dna specify wire                       # here — claude + copilot, stdio
Wired DNA MCP (stdio) into 2 agent config(s):
  created  claude    .mcp.json
  created  copilot   .vscode/mcp.json

Now a Spec Kit run driving these agents reaches DNA live over MCP:
  memory  recall / remember / list_memories
  soul    compose_prompt (Soul + Guardrails, composed live + tenant-aware)
  board   sdlc_digest / list_stories / get_adr
```

Each agent reads MCP servers from a **different file in a different JSON shape**;
`wire` projects the correct one for each:

| Agent (`--tools`) | Config file | Server map key | Block shape |
|---|---|---|---|
| `claude` | `.mcp.json` | `mcpServers` | `command`/`args`/`env` |
| `cursor` | `.cursor/mcp.json` | `mcpServers` | `command`/`args`/`env` |
| `copilot` | `.vscode/mcp.json` | `servers` | `type: stdio` + `command`/`args`/`env` |
| `opencode` | `opencode.json` | `mcp` | `type: local` + `command[]`/`environment`/`enabled` |

The stdio block pins `DNA_SOURCE_URL` to the **same source your `dna` CLI reads**,
so the agent's `dna mcp serve` sees exactly your DNA:

```json
{
  "mcpServers": {
    "dna": {
      "command": "dna",
      "args": ["mcp", "serve"],
      "env": { "DNA_SOURCE_URL": "postgresql://dna@localhost:5433/dna" }
    }
  }
}
```

### Options

```console
$ dna specify wire --tools all                    # every supported agent
$ dna specify wire --tools claude,cursor          # an explicit set
$ dna specify wire --source-url file:///abs/.dna  # pin a specific source
$ dna specify wire --http https://dna.example.com/mcp/   # a hosted remote DNA MCP
$ dna specify wire --dry-run --json               # preview; write nothing
$ dna specify wire --force                         # replace an existing `dna` entry
```

`wire` is **non-destructive and idempotent**: any other MCP server the config
already declares is preserved, and a re-run leaves an existing `dna` entry
untouched (byte-identical) unless you pass `--force`.

Use `--http` when DNA is [hosted remotely](hosting-mcp-aca.md)
(`dna mcp serve --transport http`) instead of spawned locally — the block becomes
the agent's remote-server form (`{"type": "http", "url": …}`; opencode:
`{"type": "remote", …}`), and no source env is injected (the source lives on the
server).

## The two-command story — fully grounding a run

DNA grounds a Spec Kit run in two complementary projections:

```console
# skills + the AGENTS.md instruction surface (byte-faithful into each agent's dirs)
$ dna init --tools claude,copilot

# the LIVE layer over MCP — memory + soul + board
$ dna specify wire --tools claude,copilot
```

- **`dna init`** delivers **skills** and `AGENTS.md` as files the agent reads
  (the same `.claude/skills` / `.github/skills` projection Spec Kit itself uses
  for its slash-commands).
- **`dna specify wire`** delivers **memory + soul + board** *live* over MCP —
  the context that changes between sessions and must not be frozen into a file.

Skills travel as files (they are static instructions); memory and soul are served
live because they are exactly the axes a static artifact flattens — per-tenant
overlays, no-deploy edits, and cross-session recall. (See
[The MCP server — DNA as a live layer](mcp-server.md) for why the live face
recovers what a static emit drops.)

## What the agent gets, mid-run

Once wired, the Spec-Kit-driven agent can call — through its normal MCP surface,
during `/speckit.specify`, `/speckit.plan`, `/speckit.implement` — every DNA tool:

- **`recall` / `remember` / `list_memories`** — portable memory across sessions
  and across clients. What you learned driving Spec Kit in Claude is recallable
  when Spec Kit next drives Cursor.
- **`compose_prompt`** — the agent's **soul**: Soul + Guardrails composed **live**
  and **tenant-aware**. The constitution you imported as a Guardrail (Layer 1) is
  enforced here, no-deploy.
- **`sdlc_digest` / `list_stories` / `get_adr`** — the **board**: the Stories the
  `tasks.md` became, the ADRs behind the work, what moved in the last window.

It is the **same** DNA whichever of the 30+ agents Spec Kit projected into —
that portability is the whole point.

## Verifying the wiring

The wired block is exactly what launches a working server, proven end-to-end in
`packages/cli/tests/test_speckit_live_recipe.py`: it projects the config, reads
the `dna` block back, boots the DNA MCP server against the source the block names,
and — through the real MCP protocol — calls `recall`, `compose_prompt` and
`list_stories` and gets live data. To try it by hand:

```console
$ dna specify wire --tools claude
$ dna mcp serve            # what the .mcp.json block launches for the agent
# …point any MCP client at it and call recall / compose_prompt / list_stories.
```

## Why this is additive (the founder's thesis)

Spec Kit's process is **untouched** — `wire` only writes an MCP server entry into
a config file the agent already reads. Run Spec Kit with zero DNA and it works
exactly as its docs describe. Point it at DNA and the run is *additionally*
grounded in durable memory, live governance and a real board — the same layer,
every agent. That is Layer 2 of *"DNA não substitui nada"*: DNA sits **beneath**
the methodology, feeding it context and identity.
