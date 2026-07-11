# How to write an emitter

An **emitter** materializes one neutral DNA agent into the native artifact a
runtime consumes — the *de-para*. The [`EmitterPort`](../concepts/microkernel-ports.md#the-emitterport-materialize-per-runtime)
is a first-class, documented DNA port: adding a target is a small, additive job
that never touches the emit core. This guide is the step-by-step; the three
shipped config targets (agent-framework / bedrock / vertex) and the `openai-agents`
scaffold target are your worked examples.

If you just want to *use* `dna emit`, read
[Emitting to a runtime](emitting-to-a-runtime.md) instead — this guide is for
adding a **new** target.

## The contract in one screen

An emitter reads a neutral [`EmitContext`](emitting-to-a-runtime.md#using-it-from-the-sdk)
and returns an `EmitResult`. Two surfaces make up the contract:

| Surface | Who calls it | What it does |
|---|---|---|
| `build_emit_context(mi, agent)` | the framework (once per emit) | composes the DNA agent (`build_prompt`) and projects it to the neutral `EmitContext` — every target reads the same context |
| `EmitterPort.emit(ctx) -> EmitResult` | you implement | the de-para: map the context into the target's native artifact + an honest `losses` list |
| `EmitterPort.extract_instructions(artifact) -> str \| None` | the contract test | recover the composed instruction from your own artifact — the byte-equal invariant hook |

An emitter is **pure**: it reads the context and returns a result — no kernel
I/O, no network. That is what makes every target trivially unit-testable against
a hand-built context, and lets a host **override** a built-in target by
registering its own first.

### The central invariant — the composed prompt is carried byte-equal

The single promise every emitter MUST keep: the composed **instruction** in the
emitted artifact is **byte-equal** to `mi.build_prompt(agent)`. The emit carries
the DNA composition (Soul + guardrails + instruction) verbatim; it never
paraphrases it. This is what makes the de-para trustworthy — the agent that runs
on the target is *the agent you authored in DNA*.

The contract makes the invariant **inheritable**: `extract_instructions` recovers
the instruction from your artifact, and one generic test
(`test_emit_contract` / `emit-contract.test.ts`) runs the byte-equal assertion
over **every** registered target. The moment your emitter registers, it is under
the check — you do not write that assertion yourself.

## Passo 0 — investigate the runtime, then pick a flavor

Before writing any code, answer one question about the target runtime, because
it decides the whole shape of your emitter:

> **Does the runtime have a *published declarative* agent format** (a YAML/JSON
> schema you load an agent from), or is it **code-first** (you construct an agent
> object in code)?

- **Declarative** → write a **config emitter**. You map the context field-for-field
  onto the published schema. Prefer the runtime's *own* declarative schema over a
  bespoke one, and pick the surface that needs **no credential to produce or
  validate** (e.g. a CloudFormation template over a live `CreateAgent` call). The
  three shipped targets are of this flavor.
- **Code-first** → write a **scaffold emitter**. There is no schema to map onto,
  so you emit *source code* by filling a curated template. `openai-agents` is the
  reference.

Then, whichever flavor: **map structurally, and report the losses honestly.**
List every DNA axis the target has no slot for (composition structure, tenant
overlay, eval-as-contract, and any target-specific drop) in `EmitResult.losses`.
The de-para earns trust by being honest about what does *not* survive — never
hand-wave a dropped axis.

## Flavor A — a config emitter (declarative runtime)

Implement the port directly. The whole emitter is the pure de-para plus the loss
list:

```python
from dna.emit import EmitContext, EmitResult, register_emitter

class MyRuntimeEmitter:
    target = "my-runtime"
    file_extension = "agent.yaml"

    def emit(self, ctx: EmitContext) -> EmitResult:
        doc = {
            "name": ctx.name,
            "model": ctx.model,
            # the byte-equal gate — carry the composed prompt VERBATIM:
            "instructions": ctx.instructions,
            "tools": [t["name"] for t in ctx.tools],
        }
        artifact = render(doc)  # yaml.safe_dump / json.dumps / ...
        return EmitResult(
            artifact=artifact, target=self.target,
            filename=f"{ctx.name}.{self.file_extension}",
            losses=[
                "composition structure — Soul + wired Guardrails flatten to one string",
                "tenant overlay — no per-tenant field",
                "eval-as-contract — no slot",
            ],
            mapping={"build_prompt": "instructions", "metadata.name": "name"},
        )

    def extract_instructions(self, artifact: str) -> str | None:
        return parse(artifact).get("instructions")  # the inverse — parse it back

register_emitter(MyRuntimeEmitter())
```

`extract_instructions` just parses your own serialized shape and returns the
instruction field — that is all the byte-equal test needs.

## Flavor B — a scaffold emitter (code-first runtime)

A code-first runtime has no schema to map onto — you emit **source code**. The
key discipline: **fill a curated template, never generate code ad-hoc.** The
template captures the framework's best-practice idiom; your emitter only *routes*
to the right template and fills the blanks. Four scaffold targets ship as worked
examples — `openai-agents` (the reference), `langgraph` (`create_react_agent`),
`agno` (`agno.agent.Agent`), and `deepagents` (`create_deep_agent`) — each a thin
emitter class plus a `prompt-only` and a `with-tools` template.

### The template library — `{framework × case}`

There is deliberately **no single template per framework**. A prompt-only agent,
a tool-calling (ReAct) agent, and a structured-output agent are *different
structures* in the *same* framework — each deserves its own curated template. So
the library is indexed by `{framework × case}`:

```
dna/emit/scaffolds/<framework>/<case>.py.tmpl
  e.g. openai-agents/prompt-only.py.tmpl
       openai-agents/with-tools.py.tmpl
```

A **case classifier** reads the signals the neutral context already carries and
picks the case:

| Signal in `EmitContext` | Case |
|---|---|
| no tools | `prompt-only` |
| tools present | `with-tools` (the ReAct / tool-calling idiom) |
| `output_schema` present | `structured-output` |

`select_scaffold(framework, ctx)` does the routing and falls back down a
generality chain (`structured-output` → `with-tools` → `prompt-only`) when a
framework does not ship a case, **recording the fallback as a loss**. Start with
**2–3 meaningful cases** per framework, not all of them.

> This is pure **selection + fill**, never code generation. The selector routes;
> the template is the idiom. There is no logic that assembles code by hand.

### The `ScaffoldEmitter` base — subclasses stay thin

`ScaffoldEmitter` (over the same `EmitterPort`) inherits case selection, template
fill, and the byte-equal hook. A concrete target only declares its ids and
supplies the framework-specific template variables:

```python
from dna.emit import EmitContext
from dna.emit.scaffold import ScaffoldChoice, ScaffoldEmitter, py_identifier, py_str_literal

class OpenAIAgentsEmitter(ScaffoldEmitter):
    framework = "openai-agents"   # subdir under scaffolds/
    target = "openai-agents"
    file_extension = "py"

    def render_context(self, ctx: EmitContext, case: str) -> dict:
        return {
            "has_model": ctx.model is not None,
            "model_literal": py_str_literal(ctx.model) if ctx.model else "",
            "tools": [{"func_name": py_identifier(t["name"]), "name": t["name"],
                       "docstring_literal": py_str_literal(t["description"])}
                      for t in ctx.tools],
            "tool_list": ", ".join(py_identifier(t["name"]) for t in ctx.tools),
        }

    def losses(self, ctx, choice: ScaffoldChoice) -> list[str]:
        return ["tool body — each @function_tool is a scaffolded STUB to wire"]

    def mapping(self) -> dict:
        return {"build_prompt": "INSTRUCTIONS constant (byte-equal)"}
```

The base provides the common template variables — including
`instructions_literal`, the composed prompt rendered as a Python string literal
and emitted as a top-level `INSTRUCTIONS = ...` constant. That constant is why the
scaffold's `extract_instructions` is uniform (it AST-reads `INSTRUCTIONS`
regardless of the constructor shape) — so **your subclass inherits the byte-equal
check for free**, and the emitted source is guaranteed to parse.

A template is plain Mustache. The `openai-agents/prompt-only.py.tmpl`:

```python
from agents import Agent

INSTRUCTIONS = {{{instructions_literal}}}

agent = Agent(
    name={{{name_literal}}},
    instructions=INSTRUCTIONS,
{{#has_model}}    model={{{model_literal}}},
{{/has_model}})
```

### Adding a CASE is additive — one template + (maybe) one rule

To support a new structure for a framework you already have, drop one template
file and — only if it needs a genuinely new signal — add one line to the
classifier. No change to the emit core:

1. Add `scaffolds/<framework>/<new-case>.py.tmpl` (the curated idiom).
2. If the case keys off a new signal, override `classify()` on your emitter (or
   extend `classify_case`) to return the new case name for that signal.

### Where templates come from — the resolution seam

`ScaffoldEmitter` never reads a file path directly. It resolves a template
through an abstract seam — `resolve_scaffold(framework, case)` / a
`ScaffoldResolver` — whose MVP implementation reads the in-tree package-data
(`emit/scaffolds/<framework>/<case>.py.tmpl`). A host can swap the active resolver
(`set_scaffold_resolver(...)`) or pass one per emitter, and no emitter changes.
That seam is deliberate: it is where the next source plugs in.

The fallback chain means you can ship `prompt-only` + `with-tools` first and add
`structured-output` later without breaking anything — until it exists, a
structured-output agent falls back to the closest shipped case with a recorded
loss.

## Register it and prove it

Register the emitter in the builtin wiring (`dna/emit/__init__.py`'s
`_ensure_builtins`, and the TS `ensureBuiltins`) — or call `register_emitter`
from a host. Then prove it with a small test:

- **byte-equal** — `extract_instructions(emit(ctx).artifact) == ctx.instructions`
  (the generic contract test already runs this over your target automatically).
- **structural de-para** — the target's key fields map as documented.
- **scaffold-specific** — the classifier picks the right case for a ctx with vs
  without the relevant signal, and the emitted source `py_compile`s.
- **honest losses** — every dropped axis is reported.

## Cross-language parity

Every emitter has a Python and a TypeScript twin with identical behavior. For a
config emitter the parity contract is the emitted **object** (the YAML/JSON
*rendering* may differ between PyYAML and js-yaml). For a scaffold emitter the
templates are byte-identical across the two SDKs (both emit the same source), and
each side round-trips its own `INSTRUCTIONS` literal — so the byte-equal invariant
holds independently in both.

## Future direction — Scaffold as a Kind

Today the scaffold library is **package-data** — curated `.py.tmpl` files in the
tree, read by the default `PackageDataScaffoldResolver`. Because every emitter
goes through the `resolve_scaffold` **seam** (never a hardcoded path), promoting a
Scaffold to a first-class **Kind** is a matter of adding a *second resolver*, not
rewriting any emitter: a kernel-backed `ScaffoldResolver` returns a per-scope,
tenant-overridable `Scaffold` Kind body instead of package-data. Then a team ships
its own house-style template for a framework as an overlay — declarative,
versioned, tenant-scoped — without forking the SDK. That is the DNA thesis applied
to DNA's own de-para. The promotion is tracked as story `s-scaffold-as-kind`; the
MVP keeps package-data as the sole resolver but guarantees the seam is in place.

## Where to go next

- [Emitting to a runtime](emitting-to-a-runtime.md) — the user-facing `dna emit`.
- [The microkernel and its ports](../concepts/microkernel-ports.md) — where the
  EmitterPort sits relative to the kernel's five ports.
- [Tools as data](tools-as-data.md) — how the tool surfaces an emitter reads are
  themselves declarative.
