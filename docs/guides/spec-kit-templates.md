# Spec Kit templates, served by DNA

> **Prerequisite:** install the real Spec Kit CLI first — see
> [the Spec Kit guide](spec-kit.md#prerequisites-install-the-real-spec-kit-cli).
> DNA composes with `specify`; it does not bundle or replace it.

[`dna specify import`](spec-kit.md) bridges a *run*. This guide covers **Layer 3**
of the adoption (ADR *ADR-spec-kit-adoption* §5): bridging the **toolkit itself**
— the `.specify/templates/`, the slash-command definitions, the shared
`.specify/scripts/`, and the constitution — into durable DNA Kinds that are:

- **served live** over `dna mcp serve` to any MCP client (Claude, Copilot, Cursor…),
- **overridable per workspace/tenant** through DNA's overlay machinery — *no redeploy*,
- **versioned + governed**, instead of files copied into every repo.

The spec-kit toolkit stops being a per-repo pile of files and becomes portable,
governed policy.

## Ingest the toolkit

```console
$ dna specify install-templates .specify/ --scope my-team
Installed Spec Kit toolkit: 11 Kinds.
  PromptTemplate/speckit-spec-template
  PromptTemplate/speckit-plan-template
  …
  Skill/speckit-specify
  Skill/speckit-scripts
  Guardrail/speckit-constitution
```

Preview first with `--dry-run --json` — it prints the full mapping and writes
nothing. `install-templates` accepts the project root, the `.specify/` dir, or a
`--commands-from <dir>` override for a projected agent command directory.

### What maps to what

| Spec Kit toolkit artifact | → DNA Kind | Served as |
|---|---|---|
| `.specify/templates/*.md` (spec/plan/tasks/agent-file) | **PromptTemplate** `speckit-<stem>` | `get_template` |
| slash-command defs (`templates/commands/*.md` or `.claude/commands/speckit.*.md`) | **Skill** `speckit-<cmd>` (verbatim) | `get_skill` |
| `.specify/scripts/**` (bash + powershell) | **Skill** `speckit-scripts` (bundle) | `get_skill` |
| `.specify/memory/constitution.md` | **PromptTemplate** `speckit-constitution-template` + **Guardrail** (`+Soul`) `speckit-constitution` | `get_template` + live governance |

Each Kind carries its `.specify/`-relative `origin`, so the ingest is
**byte-faithful**: `install-templates` then `export-templates` reproduces the
source `.specify/` tree byte-for-byte (an acceptance test in the suite).

```console
$ dna specify export-templates --scope my-team --out ./regenerated
Projected Spec Kit toolkit → ./regenerated (11 files)
```

## Serve it over MCP

Point any MCP client at the live DNA and the toolkit is right there:

```console
$ dna mcp serve --scope my-team          # stdio for Claude/Cursor/Copilot
```

Four tools surface the toolkit (alongside `compose_prompt`, `sdlc_digest`, …):

| Tool | Returns |
|---|---|
| `list_templates` | every PromptTemplate (name, description, variable count) |
| `get_template` | one template's full body + variables |
| `list_skills` | every Skill (name, description) |
| `get_skill` | one slash-command's verbatim instruction (+ bundled scripts) |

All four take an optional `tenant` — which is where the payoff lands.

## Override per workspace — no redeploy

`PromptTemplate` and `Skill` are inheritable Kinds, so a workspace/tenant can
**override** a template or slash-command without touching the base. Write the
override at the tenant overlay; the base is untouched and every other workspace
keeps the shared template:

```console
# base team template
$ dna doc apply --scope my-team speckit-spec-template.prompt

# ACME's house override of the SAME template (overlay — base untouched)
$ DNA_TENANT=acme dna doc apply --scope my-team speckit-spec-template.prompt
```

`get_template("speckit-spec-template", tenant="acme")` now returns ACME's body;
the base scope still returns the shared one. **No redeploy** — the kernel
resolves the overlay live on every read. That is the whole point of serving the
toolkit as Kinds rather than shipping files.

## The constitution as *live* governance

The constitution is special: `install-templates` maps it to **both** a servable
`PromptTemplate` (`speckit-constitution-template`) **and** a live `Guardrail`
(`speckit-constitution`). The Guardrail is enforced at **write time** — flip its
`severity` and the very next write is governed differently, *no restart, no
deploy*:

- With `severity: hard`, a governed spec-kit `Story`/`Plan` written into the
  scope **must trace to a Spec** (`spec_refs` / `spec_ref`) — otherwise the write
  is **vetoed** by DNA's `kernel.write_document` guard.
- Softer severities (`warn`/`error`) warn but allow; no constitution passes.

```console
# tighten governance live — the next non-traceable spec-kit write is refused
$ dna doc apply --scope my-team speckit-constitution.guardrail   # severity: hard

# loosen it again with zero redeploy — writes flow, advisory only
$ dna doc apply --scope my-team speckit-constitution.guardrail   # severity: warn
```

Governance stops being a markdown file you hope people read and becomes policy
the platform enforces — versioned, overridable, and effective the instant you
change it.

## See also

- [Spec Kit — the supported spec-driven flow](spec-kit.md) — the run-level bridge.
- [The MCP server — DNA as a live layer](mcp-server.md) — the transport.
- ADR *ADR-spec-kit-adoption* — the full adoption design (Layers 1–4).
