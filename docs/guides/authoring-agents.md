# How to author an agent (without writing Mustache)

This guide is about the *authoring* side of a DNA scope: creating an agent and
the soul that gives it a voice, and ordering the two in the composed prompt —
all without hand-writing a template. If you want to *read* the composed prompt
back out at boot, see [How to consume prompts](consuming-prompts.md).

There are three moving parts, each a small convenience over the raw kernel:

- **`dna new`** — scaffold a valid skeleton so you never remember the envelope.
- **named layouts** — order the persona and the instruction by *name*, not by
  copy-pasting Mustache section tags.
- **single-file souls** — a soul is one `SOUL.md`; the two-file soulspec.org
  bundle stays available but is no longer the price of entry.

## Scaffold with `dna new`

`dna new` writes a correct, minimal skeleton into a scope through the kernel
(every write guard and schema check runs — it is not a text template), leaving
you with a valid document whose only empty part is the prose you came to write.

```bash
dna new soul warm-host -d "Patient, warm, concise concierge voice"
dna new agent concierge --soul warm-host --layout persona-first
dna new guardrail no-pii --severity error --guard-scope output
```

- `dna new agent <name>` creates `agents/<name>/AGENT.md` with a placeholder
  instruction body and any `--soul` / `--guardrails` / `--layout` / `--model`
  wiring pre-filled.
- `dna new soul <name>` creates a **single** `souls/<name>/SOUL.md` — no
  `soul.json` (see below).
- `dna new guardrail <name>` creates `guardrails/<name>/GUARDRAIL.md` with a
  starter rule plus a severity and scope.

`dna new` is idempotent: it refuses to overwrite an existing document unless you
pass `--force`. Add `--json` for machine-readable output, and `--scope` to
target a scope other than the auto-detected one.

## Named layouts — order the persona by name

An agent's system prompt is composed from several pieces: the agent's own
instruction, the soul (persona/voice), and any guardrails. The *order* of those
pieces used to be a raw `promptTemplate` full of internal section names
(`{{{soul_content}}}`, `{{#guardrails-guardrail}}`) — a cliff you fell off the
moment you wanted the persona to speak first.

A `layout:` field on the agent picks the order by name:

| Layout | Order |
|--------|-------|
| `instruction-first` (a.k.a. `default`, or absent) | instruction → soul → guardrails |
| `persona-first` | soul → instruction → guardrails |

```yaml
# agents/concierge/AGENT.md
---
name: concierge
soul: warm-host
layout: persona-first
---
# concierge

You help guests check in...
```

Guardrails always compose **last** — they are hard policy enforced every turn,
regardless of the layout. The kernel resolves the named layout to an embedded
template, so the common case never authors a single `{{ }}`.

A misspelled layout fails loud rather than silently falling back to the default
order:

```text
UnknownLayout: Unknown layout 'persona_first' on agent 'concierge' — available: default, instruction-first, persona-first
```

### The 20% escape hatch

A raw `promptTemplate` still wins over `layout` when both are present — the
poweruser who genuinely needs a bespoke composition keeps full control:

```yaml
---
name: concierge
promptTemplate: "{{{soul_content}}}\n\n---\n\n{{{agent.instruction}}}"
---
```

## Single-file souls

A soul following the [soulspec.org](https://soulspec.org) standard is a
two-file bundle: `SOUL.md` plus a `soul.json` manifest (`specVersion`, a `files`
map, tags). DNA reads `SOUL.md` directly, so **`soul.json` is optional** — a
soul authored as a single file reads and composes exactly the same:

```markdown
<!-- souls/warm-host/SOUL.md -->
# warm-host

A patient, warm concierge. Speaks in short, reassuring sentences...
```

That is all a soul needs. The two-file form is still fully supported — author it
(or install a market bundle) with a `soul.json` present and DNA preserves it
byte-faithfully on the round-trip. Single-file authoring is the convenience;
soulspec.org fidelity is intact for the marketplace.

When you omit frontmatter entirely, the soul's name is inferred from its bundle
directory (`souls/warm-host/` → `warm-host`).

## Putting it together

Three commands take you from an empty scope to a composing, persona-first agent
with no Mustache anywhere:

```bash
dna new soul warm-host -d "Warm, concise concierge voice"
dna new agent concierge --soul warm-host --layout persona-first
# edit agents/concierge/AGENT.md and souls/warm-host/SOUL.md — prose only
```

```python
from dna import load_prompts

prompt = load_prompts("your-scope")["concierge"]
# → the warm-host soul speaks first, then the concierge instruction, then guardrails
```
