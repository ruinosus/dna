# Emit — materializing an agent into a runtime

Where the storage ports face *inward*, these face **out**: the kernel composes a neutral agent, and an emitter turns it into the native artifact one specific runtime consumes. Author once, emit per runtime.

!!! info "Generated from the source"

    Names, signatures and docstrings are parsed out of `packages/sdk-py/dna`
    by `scripts/gen_ports_docs.py`. The prose around each contract is
    hand-written in `scripts/ports_prose.py`, and the generator **fails**
    if a port has none — so a new port cannot ship undocumented.

## EmitterPort

`dna.emit.EmitterPort` · `@runtime_checkable` · :material-power-plug: **extension point**

Seven targets ship. A new one is a class plus one `register_emitter(...)` call, and the emit core never changes — which is the claim the port exists to make good on.

!!! quote "From the source"

    A runtime emitter — materializes an :class:`EmitContext` into a native
    artifact. Implement this + call :func:`register_emitter` to add a target.

    An emitter is PURE: it reads the neutral :class:`EmitContext` and returns an
    :class:`EmitResult`. It performs NO kernel I/O and NO network — that is the
    high-level :func:`emit_agent`'s job. This keeps every target trivially
    unit-testable against a hand-built context.

    A conforming emitter provides three things:

    ``target`` / ``file_extension``
        Identity: the id used on ``dna emit --target <id>`` and the extension of
        the default output filename.

    :meth:`emit`
        The materialization — the de-para from the neutral context into the
        target's native artifact, plus an honest :class:`EmitResult.losses` list.

    :meth:`extract_instructions`
        The **byte-equal invariant hook**: recover the composed instruction from
        this target's own artifact. It is what makes the central invariant
        (emitted instruction == ``build_prompt``) inheritable — one generic test
        loops every registered target and asserts
        ``extract_instructions(emit(ctx).artifact) == ctx.instructions``. An
        emitter that genuinely has no instruction slot may return ``None`` (the
        generic check skips it), but every real target carries the prompt.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `emit` | <code>def emit(self, ctx: EmitContext) -> EmitResult</code> | Materialize ``ctx`` into a native artifact. |
| `extract_instructions` | <code>def extract_instructions(self, artifact: str) -> str \| None</code> | Recover the composed instruction embedded in ``artifact``. |

**Swap it when** — You want to run DNA-authored agents on a runtime DNA does not emit for yet. Two flavours satisfy the same port: **config-declarative** (project onto a published YAML/JSON schema) and **scaffold-code** (fill a curated `{framework × case}` template).

**The minimum that works** — `emit(ctx)` and `extract_instructions(artifact)` — plus a `target` id. The second is not optional bookkeeping: it is how the invariant below is checked against your own output.

**What it lights up** — `dna emit --target <yours>`. The **central invariant** is that the composed instruction in your artifact is **byte-equal** to `build_prompt`: the emit carries the composition verbatim, and one generic test runs that check over *every* registered target, yours included the moment you register. Return `None` from `extract_instructions` only when the target genuinely has no instruction slot — returning a re-serialized approximation defeats the check without failing it.

**How you prove it** — Register the emitter and the generic round-trip test adopts it automatically. `packages/sdk-py/tests/test_emit_agent_framework.py` shows the shape, including how an upstream bug is carried as a documented `strict=True` xfail rather than worked around.

**Shipped implementations** — `ScaffoldEmitter` (`dna.emit.scaffold`) — the base for code-first targets; `AgentFrameworkEmitter` (`dna.emit.agent_framework`); `BedrockEmitter` (`dna.emit.bedrock`); `VertexEmitter` (`dna.emit.vertex`); `OpenAIAgentsEmitter` (`dna.emit.openai_agents`); `LanggraphEmitter` (`dna.emit.langgraph`); `AgnoEmitter` (`dna.emit.agno`); `DeepAgentsEmitter` (`dna.emit.deepagents`)

## ScaffoldResolver

`dna.emit.scaffold.ScaffoldResolver` · `@runtime_checkable` · :material-power-plug: **extension point**

Resolves a `{framework × case}` template to its Mustache source. One implementation ships, reading templates out of package data.

!!! quote "From the source"

    Resolve a ``{framework × case}`` template to its Mustache source.

    The ABSTRACT seam between an emitter and *where a template lives*. The MVP
    reads package-data (:class:`PackageDataScaffoldResolver`); a future
    kernel-backed resolver returns a per-scope/per-tenant **Scaffold Kind** body
    instead — swapping one for the other requires no change to any emitter.
    Returns ``None`` when the source has no template for that pair.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `resolve` | <code>def resolve(self, framework: str, case: str) -> str \| None</code> |  |

**Swap it when** — You want scaffold templates to come from somewhere else — a kernel-backed Kind so they are editable as data, a remote catalogue, a per-tenant override. Serving templates from the kernel is named future work (`s-scaffold-as-kind`), so this seam has a known intended second user.

**The minimum that works** — `resolve`. Install it with `set_scaffold_resolver(...)`.

**What it lights up** — Every scaffold-code emitter at once, since they all resolve through the active resolver. An unresolvable template fails the emit loudly.

**How you prove it** — Emit through a scaffold target and assert the byte-equality invariant still holds — a resolver that returns the wrong template breaks it, which is the check you want.

**Shipped implementations** — `PackageDataScaffoldResolver` (`dna.emit.scaffold`) — the default, reads from package data

