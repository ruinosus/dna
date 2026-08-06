# Judgement — where something decides

Four seams where DNA deliberately declines to ship an opinion. Each is a place a model, a heuristic, or a human gets to be the authority — and DNA's position is that the authority is **yours to supply**, not ours to bundle.

!!! info "Generated from the source"

    Names, signatures and docstrings are parsed out of `packages/sdk-py/dna`
    by `scripts/gen_ports_docs.py`. The prose around each contract is
    hand-written in `scripts/ports_prose.py`, and the generator **fails**
    if a port has none — so a new port cannot ship undocumented.

## Analyzer

`dna.extensions.intel.analyzer.Analyzer` · `@runtime_checkable` · :material-power-plug: **extension point**

The pluggable stage of the intel pipeline: read a source spec plus engine-built context, return candidates. Two ship — a deterministic offline one and an LLM one — which is the pattern to copy when you want a pipeline testable without a model.

!!! quote "From the source"

    The pluggable pass-stage contract. Implementations read ``source``
    (the IntelSource spec) + ``context`` (engine-built extras) and return a
    list of candidate insight dicts. Pure — no I/O beyond what an impl needs
    to research; NEVER writes docs (the engine owns persistence).

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `analyze` | <code>def analyze(self, source: dict[str, Any], context: dict[str, Any]) -> list[Candidate]</code> |  |

**Swap it when** — You have a different extraction strategy, or a domain-specific one.

**The minimum that works** — `analyze(source, context) -> list[Candidate]`.

**What it lights up** — Selection through `select_analyzer(mode)`. The offline `SeedAnalyzer` is what keeps the pipeline's tests hermetic; if you add a model-backed analyzer, add a deterministic sibling too or the pipeline's tests start needing an API key.

**How you prove it** — `SeedAnalyzer` and `LLMAnalyzer` (`dna.extensions.intel.analyzer`) are both in one file — read them side by side.

**Shipped implementations** — `SeedAnalyzer` (`dna.extensions.intel.analyzer`) — deterministic, offline; `LLMAnalyzer` (`dna.extensions.intel.analyzer`) — model-backed

## ContradictionScribe

`dna.memory.contradiction.ContradictionScribe` · typing-only (not `@runtime_checkable`) · :material-power-plug: **extension point**

The external judgement seam, for the pairs the deterministic rule cannot settle. **Zero in-tree implementations, by design** — DNA ships the question and declines to ship the judge.

!!! quote "From the source"

    The EXTERNAL judgement seam — for the pairs the rule cannot decide.

    Input: the member specs of one ``undecided`` group (memories that share a
    declared referent but carry no comparable claims), each the full memory
    ``spec`` dict, read-only, sorted by name.

    Output: ``{"contradicts": bool, "reason": str, "predicate"?: str}``. A
    ``True`` verdict promotes the group into ``contradictions`` marked
    ``decided_by: "scribe"`` — never marked as a rule, because a reader must be
    able to tell the syntactic verdict from the modelled one.

    The caller (a service, never this SDK) owns the model, the prompt and the
    cost. A raising or malformed scribe leaves the group in ``undecided`` with a
    ``scribe_error`` — it never breaks the pass, and it never upgrades silence
    into a verdict.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `__call__` | <code>def __call__(self, group: Sequence[dict[str, Any]]) -> dict[str, Any]</code> |  |

**Swap it when** — You want a model or a human to adjudicate the ambiguous cases. Note it is a plain callable, not a class — the simplest port on this page to satisfy.

**The minimum that works** — One `__call__`. A function is enough.

**What it lights up** — Contradiction detection beyond what the rule decides on its own. Supply nothing and the ambiguous pairs are left undecided rather than guessed at — the intended behaviour, not a gap.

**How you prove it** — `dna.testing.memory_conformance_suite(...)`, which grades the memory plane's behaviour as a whole.

**Shipped implementations** — none in-tree. This port has no reference adapter yet: you would be writing the first one.

## EvalTargetPort

`dna.extensions.eval.runner.EvalTargetPort` · `@runtime_checkable` · :material-power-plug: **extension point**

Turns one `EvalCase` into the **text** the checks are applied to. The shipped target composes a prompt; anything you can produce text from can be a target.

!!! quote "From the source"

    Turns one EvalCase into the TEXT the checks are applied to.

    ``target`` is the resolved target mapping (case ``target`` → suite
    ``target`` → ``{"type": "prompt"}``); ``case`` is the EvalCase spec.
    ``kernel``/``scope`` give the target the same blessed surface the
    runner itself uses (``kernel.instance(scope)`` → query/build_prompt).

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `run` | <code>def run(self, target: dict, case: dict, *, kernel: Any, scope: str) -> str</code> |  |

**Swap it when** — You want to evaluate a live agent, a deployed endpoint, or a whole pipeline rather than a composed prompt — which is the common case once evaluation stops being about composition.

**The minimum that works** — `run`. Inject via `run_eval(..., targets=...)`.

**What it lights up** — `dna eval` against your target. The default `PromptCompositionTarget` evaluates the composed prompt — worth knowing, because an eval suite that is green against composition has not yet said anything about the running agent.

**How you prove it** — `PromptCompositionTarget` (`dna.extensions.eval.runner`) is the sole built-in and the shape to copy.

**Shipped implementations** — `PromptCompositionTarget` (`dna.extensions.eval.runner`) — the only built-in target

## MergeScribe

`dna.memory.merge.MergeScribe` · typing-only (not `@runtime_checkable`) · :material-power-plug: **extension point**

The external synthesis seam, and the exact contract a fusion scribe fills. Also zero in-tree implementations, for the same reason.

!!! quote "From the source"

    The EXTERNAL synthesis seam — the exact contract a fusion scribe fills.

    Input: the group's member specs, canonical FIRST (each the full memory
    ``spec`` dict, read-only). Output: the proposed FUSED spec — at minimum a
    ``summary`` (the fused text); any other Engram spec fields it returns ride
    along verbatim. The caller (a service, never this SDK) owns the model, the
    prompt and the cost; the kernel only carries the proposal in the report.
    A raising scribe degrades the group to the deterministic ``supersede``
    proposal — it never breaks the pass.

**The contract**

| Member | Signature | What it must do |
| --- | --- | --- |
| `__call__` | <code>def __call__(self, group: Sequence[dict[str, Any]]) -> dict[str, Any]</code> |  |

**Swap it when** — You want consolidation to synthesize rather than merely pick a winner.

**The minimum that works** — One `__call__`.

**What it lights up** — Synthesizing consolidation. Without one, consolidation keeps to its deterministic behaviour.

**How you prove it** — `dna.testing.memory_conformance_suite(...)`.

**Shipped implementations** — none in-tree. This port has no reference adapter yet: you would be writing the first one.

