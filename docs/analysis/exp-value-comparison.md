# Experiment 3 — Does DNA pay for itself vs YAML + Pydantic + Git + a framework?

> Spike `sp-exp-value-comparison`. The founder's self-critique concluded: *"DNA
> hasn't proven it needs to exist vs a folder of YAML + Pydantic + Git + your
> framework."* This experiment builds the **same** agent two ways and measures
> honestly. A flattering result would be worthless — where DNA loses, it says so.

## The use case (realistic, not a toy)

**Acme Cloud customer support.** Two agents that share machinery:

- `support` — front-line support agent.
- `billing` — billing specialist.

Both **share**: one persona (`support-host` Soul), one policy Guardrail
(`refund-policy` — *"never promise a refund"*), and one Skill (`kb-grounding`).
`support` additionally wires `troubleshoot-login` and `escalation-protocol`.
So there is real composition (soul + guardrail land in the prompt), real reuse
(both agents pull the same soul + guardrail + kb skill), and real policy.

Both solutions compose the **byte-identical** system prompt for each agent
(verified in code — see "Parity check" below), so this is an apples-to-apples
fight over *everything around* the prompt.

- **Solution A** — `examples/exp-value-comparison/solution-a-yaml/`: a folder of
  plain YAML + Pydantic models + a hand-rolled `compose.py` (persona-first:
  soul → instruction → guardrails-last) + a hand-rolled `emit_langgraph.py`.
  Git is the version control. This is "what a competent dev does without DNA."
- **Solution B** — `examples/exp-value-comparison/solution-b-dna/`: the same
  agent as DNA Kinds (Genome + Agent + Soul + Guardrail + Skill), composed by
  `mi.build_prompt()`, emitted by `dna emit`, overlaid per-tenant by the kernel.

## Headline numbers

| Metric | A — YAML + Pydantic | B — DNA |
|---|---|---|
| Config lines (the YAML/MD you author) | **53** across 7 files | **91** across 9 files (+72%) |
| Framework lines **you write and maintain** | **153** (`compose.py` 67 + `models.py` 51 + `emit_langgraph.py` 35) | **0** (the composer/validator/overlay/emitters are the DNA library) |
| Total authored | 206 across 10 files | 91 across 9 files |
| Runtime emit targets available | 1 (the one you wrote, ~35 lines) | 7, tested for byte-parity |

The whole trade in one line: **DNA moves 153 lines of Python off your plate and
onto the library, and charges you +38 lines of `apiVersion/kind/metadata`
envelope boilerplate for the privilege.** Whether that's a good deal depends
entirely on the dimensions below.

## Dimension-by-dimension — with real numbers and a blunt verdict

### 1. Lines of code / config — **A better (for this case)**
Author-time config is 53 lines (A) vs 91 lines (B). Every DNA file carries a
4-line `apiVersion/kind/metadata` envelope that a plain YAML file omits. For a
single app that envelope is pure ceremony. DNA only "wins" on total lines
because it absorbs the 153-line composer — but you were comparing *authoring
effort*, and per artifact DNA is **more** to type, not less.

### 2. Number of files — **tie**
10 (A) vs 9 (B). DNA needs a `Genome.yaml` scope root; A needs `models.py` +
`compose.py`. Wash.

### 3. Onboarding — what a new dev must learn — **A better**
- A: Python, Pydantic, `yaml.safe_load`, and ~130 lines of one repo's own
  `compose.py`/`models.py`. A mid-level dev reads it in 15 minutes.
- B: the DNA mental model — Kinds, the mandatory `<owner>-<kind>` alias
  convention, Genome-as-scope-root, named layouts (`persona-first`), layers &
  tenant overlay, and a **23-subcommand** `dna` CLI. That is a genuine
  framework to learn before you can debug a composed prompt.

  DNA trades "learn my 130 lines" for "learn my framework." For one app that is
  a **worse** trade; the framework only amortizes across many agents/scopes.

### 4a. Change a behavior: add a skill — **tie**
Both are 2 edits (write the skill file, add its name to the agent). Notably
`dna new` scaffolds agent/soul/guardrail/tool but **not** skill, so DNA offers
no scaffolding advantage here.

### 4b. Change a behavior: override ONE instruction for ONE tenant — **B clearly better (the standout)**
- B: **one** partial overlay file
  (`.dna/tenants/acme-eu/scopes/acme-support/support.yaml`, 7 lines) overrides
  just `spec.instruction`; the Soul and Guardrail are still inherited from base,
  and `kernel.instance(scope, layers={"tenant":"acme-eu"})` composes the
  overridden prompt **on demand**. Verified live: base composes the base
  instruction, `acme-eu` composes the EU/GDPR variant, from the same source.
- A: **not possible** without new engine code. You would build a
  deep-merge-with-overlay-rules loader (which fields are overlayable, scalar vs
  list semantics) — realistically 30–80 lines before it's correct, i.e. you
  start reimplementing DNA's layer engine.

  This is the one dimension where DNA's abstraction buys something a competent
  dev cannot cheaply hand-roll.

### 5. Traceability — "which file added this instruction?" — **tie (single scope)**
Both store every Kind as a discrete file, so `git log -p` / `grep` answers it in
both. DNA adds a structured `doc.origin` — **but** for the tenant-overridden
agent `origin` still read `local` in both the base and overlay instance, so DNA
did **not** cleanly attribute "this line came from the tenant layer" at field
granularity through that API. Provenance only pulls ahead once **cross-scope
inheritance / catalog** is in play (origin = `inherited`/`catalog`), which the
baseline doesn't have because it has no inheritance at all.

### 6. Validation — **split: A deeper, B cheaper — and a real DNA gap found**
A deliberate schema error in each:

| Probe | A (Pydantic) | B (DNA) |
|---|---|---|
| bad enum `severity: critical` | **caught** — `Input should be 'info','warning' or 'error'` | **NOT caught** — composed `critical` straight into the prompt; the write path accepted it too |
| empty `rules: []` | **caught** — `List should have at least 1 item` | not enforced |
| `skills: "a-string"` (wrong type) | **caught** on load | **caught on real write** — *"'a-string' is not of type 'array' — see `dna kind show Agent`"*, exit 1 |
| any error on the **read/compose** path | **caught** (validates every load) | **not caught** — `Kernel.quick(...).build_prompt()` composes invalid docs happily |
| `--dry-run` write of a garbage doc | n/a | **not caught** — echoes it back as `would_write` |

Findings, blunt:
- DNA's schema is **auto-generated from the dataclass** (`str → {"type":"string"}`,
  no enum), so it is *shallower* than a 51-line Pydantic file: it enforces JSON
  types on write but **not** the `warn|error|hard` severity vocabulary it
  documents. The hand-rolled `Literal[...]` is a **stricter** validator.
- DNA validation fires **only on the real write path** (`dna doc create` /
  `kernel.write_document`), not on read/compose and not on `--dry-run`. A repo
  whose runtime reads a filesystem `.dna` never gets validated at compose time.
- Where DNA wins: the write-path error message is good and points you to
  `dna kind show`, exit code is 1 (CI-friendly), and it costs **you** zero lines.

Net: **A better on depth and when-it-fires; B better on cost.** If validation
depth matters, a Pydantic file beats DNA's auto-schema today. (Two real
follow-ups for DNA: enum enforcement, and validate-on-compose.)

### 7. Portability / emit — **B better *iff* you need >1 runtime**
- B: `dna emit <agent> --target <t>` for **7** targets (agent-framework,
  bedrock, vertex, openai-agents, langgraph, agno, deepagents), the composed
  prompt carried byte-equal, plus an honest `losses` report on stderr for what
  each target can't express (composition structure, tenant overlay,
  eval-as-contract, tool bodies). All 7 are covered by parity tests.
- A: `emit_langgraph.py` is **35 lines** and matches DNA's langgraph output for
  this agent. But that is ONE trivial target; Bedrock (CloudFormation), Vertex
  (ADK config) and agent-framework each have real format weight, and you'd own
  the byte-parity testing yourself.

  Verdict: if you ship to a single runtime forever, A's ~35 lines win. The
  moment you need a second or third runtime, DNA's tested fan-out is real value
  you'd otherwise rebuild N times.

### 8. Debugging — **A better**
A composed prompt that comes out wrong: in A you read a 67-line `compose.py` and
a plain Python stack trace. In B you reason about Mustache template resolution
(agent override → Kind default → layout), `dep_filters`, layer/tenant merge, and
pre/post-build hooks — more indirection, more magic, more to learn before the
bug is obvious. Small-surface wins for debuggability.

### 9. Governance / provenance — **B better at fleet scale, overkill for one app**
DNA brings write-path veto, `Genome` catalog identity, tenant isolation, and an
SDLC board — real governance when you run **many** agents across **many**
tenants and need audited, no-deploy changes. For a single support bot in one
repo, Git + PR review of a YAML folder delivers the same assurance with none of
the apparatus.

### Bonus finding — Skills are inert in the compose/emit path (**both weak; honest surprise**)
The default Agent layouts inline **Soul + instruction + Guardrail only**. A Skill
referenced by `spec.skills` is **not** inlined into `build_prompt`, **not**
emitted as a tool, and **not even listed** in the emitter's `losses`. Verified:
the `support` agent wires three skills; none of their text reaches the composed
prompt or the langgraph emit (`tools=[]`). So of the "composition" story, only
Soul + Guardrail reuse is real for the *prompt*; the three Skill Kinds are
governance/catalog metadata that buy nothing at runtime here. The baseline
mirrors this honestly (skills validated, not inlined) — so it's a wash, but it
means DNA's composition value for this case is **narrower** than the pitch
implies.

## Where DNA is more ceremony for less value (the "Kubernetes cosplay" risk)

1. **The `apiVersion/kind/metadata` envelope** on every file: +72% config lines
   for zero behavior in a single-app case.
2. **Validation**: DNA's auto-schema is *shallower* than a 51-line Pydantic
   model (no enums, doesn't fire on compose) yet demands a whole framework's
   mental model. More apparatus, less checking.
3. **Skills as Kinds** that don't compose or emit: three files of ceremony that
   change nothing at runtime for this agent.

## Parity check (so the fight is fair)

`build_prompt` in both solutions returns the **byte-identical** system prompt
for `support` and `billing` (asserted in code: `A(agent) == mi.build_prompt(agent)`
is `True` for both). Neither solution's composition is cheating.

## Verdict per dimension

| Dimension | Winner | Why |
|---|---|---|
| Config verbosity | **A** | no per-file envelope |
| Framework LOC to maintain | **B** | 0 vs 153 |
| # files | tie | 9 vs 10 |
| Onboarding | **A** | 130 lines vs a 23-command framework |
| Add a skill | tie | 2 edits either way |
| **Per-tenant field override** | **B** | 1 overlay file vs building a merge engine |
| Traceability (single scope) | tie | both are greppable files |
| Validation depth / when | **A** | Pydantic enums, fires on every read |
| Validation cost | **B** | free, good message, exit 1 |
| **Portability (>1 runtime)** | **B** | 7 tested emitters vs N hand-rolled |
| Portability (1 runtime) | **A** | 35 lines, done |
| Debugging | **A** | plain stack traces, no template/layer magic |
| Governance at fleet scale | **B** | veto + catalog + tenancy + SDLC |
| Governance for one app | **A** | Git + PR is enough |

## Answer to the founder's question

**DNA's value is clearly real and worth the abstraction on exactly two
dimensions:**

1. **Per-tenant (per-layer) field overlay** — override one field for one tenant
   from one small partial file, inherit the rest, compose on demand. The
   baseline cannot do this without reimplementing DNA's layer engine. This alone
   is a legitimate reason for DNA to exist.
2. **Multi-runtime portability** — seven tested, byte-parity emitters. Real
   value the moment you target more than one runtime.

**A YAML folder + Pydantic + Git is simply better for:** config terseness,
onboarding, validation depth, debuggability, and governance — *whenever the
project is a single app, on a single runtime, for a single tenant.* In that
world DNA is net more ceremony for less value.

### The single most honest sentence

> DNA earns its existence precisely at **multi-tenant + multi-runtime** scale —
> per-tenant overlay and tested cross-runtime emitters are things you'd
> otherwise have to build and maintain — but for a single-app, single-runtime,
> single-tenant support agent it is measurably **more ceremony for less value**
> than a folder of YAML and a ~150-line Pydantic composer, so this experiment
> **supports the critique for the small case and only undermines it once tenancy
> or portability become real requirements.**

## Reproduce

```bash
# Solution A — byte-identical composed prompts, from plain YAML + Pydantic
cd examples/exp-value-comparison/solution-a-yaml
python compose.py support ; python compose.py billing
python emit_langgraph.py support

# Solution B — DNA
cd examples/exp-value-comparison/solution-b-dna
python -c "from dna import Kernel; print(Kernel.quick('acme-support', base_dir='.dna').build_prompt(agent='support'))"
DNA_BASE_DIR=.dna dna emit support --target langgraph --scope acme-support
# per-tenant overlay:
DNA_BASE_DIR=.dna python -c "from dna import Kernel; k=Kernel.from_config(); print(k.instance('acme-support', layers={'tenant':'acme-eu'}).build_prompt(agent='support'))"
```
