# `dna new`

Scaffold a valid Kind skeleton into a scope (agent | soul | guardrail | tool).

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna new --help`.

## `dna new agent`

Scaffold an Agent bundle (agents/<name>/AGENT.md) — fill in the instruction.

The skeleton is a VALID Agent from the first write: correct envelope, a
placeholder instruction body, and any --soul/--guardrails/--layout/--model
wiring pre-filled. With --layout you order persona-vs-instruction by name
and never hand-write Mustache.

Examples:


  dna new agent triage
  dna new agent concierge --soul warm-host --layout persona-first
  dna new agent reviewer --guardrails safety,review-ethics --model openai:gpt-4o

```text
dna new agent [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--description`, `-d` | One-line description. |
| `--force` | Overwrite an existing agent. |
| `--guardrails` | Comma-separated Guardrail names to attach. |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--layout` | Named composition layout (s-dx-named-layouts) — 'persona-first' puts the Soul before the instruction. Omit for the default. |
| `--model` | Model id (e.g. openai:gpt-4o-mini). |
| `--scope` | Scope to write into (default: env / sole scope). |
| `--soul` | Name of a Soul doc to compose in. |

## `dna new guardrail`

Scaffold a Guardrail bundle (guardrails/<name>/GUARDRAIL.md).

Example:


  dna new guardrail no-pii --severity error --guard-scope output

```text
dna new guardrail [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--description`, `-d` | One-line description. |
| `--force` | Overwrite an existing guardrail. |
| `--guard-scope` | Which side the guardrail runs on. _(default: `both`)_ |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--scope` | Scope to write into (default: env / sole scope). |
| `--severity` | warn lets the turn continue; error fails it. _(default: `warn`)_ |

## `dna new soul`

Scaffold a Soul as a SINGLE SOUL.md file — no soul.json ceremony.

s-dx-single-file-soul: a Soul is authored from one SOUL.md; the
2-file soulspec.org format (SOUL.md + soul.json + companions) stays fully
supported for market fidelity, but the common case is a single file.

Example:


  dna new soul warm-host -d "Patient, warm, concise concierge voice"

```text
dna new soul [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--description`, `-d` | One-line description. |
| `--force` | Overwrite an existing soul. |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--scope` | Scope to write into (default: env / sole scope). |

## `dna new tool`

Scaffold a Tool descriptor (tools/<name>.yaml) — tools as data.

A Tool moves the agent-facing surface of a tool into the declarative plane:
the ``description`` the model reads (metadata.description) + the
``input_schema`` of its arguments (surfaced as ``parameters`` by
``dna.load_tools`` / ``loadTools``). The skeleton is a VALID Tool from the
first write, with a placeholder single-arg ``input_schema`` to edit.

Examples:


  dna new tool generate-artifact -d "Render HTML/Markdown into a shareable artifact."
  dna new tool github-search --type http -d "Search GitHub code."

```text
dna new tool [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--description`, `-d` | Agent-facing description — the text the model reads to decide whether to call the tool (goes in metadata.description). |
| `--force` | Overwrite an existing tool. |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--scope` | Scope to write into (default: env / sole scope). |
| `--type` | Invocation type. builtin \| http \| mcp \| python \| shell. _(default: `builtin`)_ |

