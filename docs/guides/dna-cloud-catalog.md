# The DNA Cloud starter catalog & BYO-DNA

DNA Cloud ships two things a customer consumes over MCP:

1. a **starter catalog** — a few generic, ready-to-use agents in the shared
   `_lib` scope that *every* tenant inherits (the on-ramp), and
2. **BYO-DNA** — each customer authors their *own* agents as a **tenant
   overlay** on top of that base (the product, and the moat).

Both are the same mechanism you already know: `_lib` inheritance for the
catalog, tenant overlays for the customer's DNA, and the [PricingPlan](../reference/kinds/index.md)
caps for plan gating. There is **zero new architecture** here — see
`adr-dna-cloud-content`.

## The three starter agents

They live in `examples/dna-cloud/.dna/_lib/agents/` — each a real, composable
agent (a Soul + baseline Guardrails + a focused instruction), inheritable by
every tenant:

| Agent | What it is | Composes |
|-------|------------|----------|
| **`assistant`** | A clean, general-purpose helpful assistant — the solid default. The "hello world" of the catalog. | soul `helpful-assistant` + guardrail `baseline-safety` |
| **`code-reviewer`** | Reviews code and diffs for correctness, security, and clarity — structured findings, no rubber-stamping. | soul `senior-engineer` + guardrails `baseline-safety`, `review-integrity` + skill `structured-code-review` |
| **`dna-copilot`** | Coaches the user to author their **own** DNA — the on-ramp from *using* the catalog to *building* it. | soul `dna-mentor` + guardrail `baseline-safety` |

None of them pins a `model`: the model falls through to the consuming scope's
`Genome.default_llm`, so a tenant runs the catalog on their own model without
editing the agent.

Preview any of them — the persona and guardrails are **composed in** by
`build_prompt`, not pasted:

```python
from dna.kernel import Kernel
mi = Kernel.quick("_lib", base_dir="examples/dna-cloud/.dna")
print(mi.build_prompt("code-reviewer"))
```

!!! note "Multiple personas in one scope"
    The shared `_lib` catalog packs three *different* Souls into one scope. The
    built-in `layout: persona-first` reads a single top-level `{{{soul_content}}}`
    that flattens **last-wins** across every Soul in scope, so with more than one
    Soul the personas would collide. The catalog agents therefore pin their Soul
    with a small section-based `promptTemplate` (`{{#soulspec-soul}}…`), which
    resolves the agent's *declared* `soul`. When **you** author in your own scope
    with a single persona, just use `layout: persona-first` — it is the cleaner
    form and composes identically. (Tightening the flatten to honour the declared
    `soul` is tracked as a follow-up.)

## BYO — author your own agent and push it live

Your DNA is your **tenant overlay**: you author an agent and push it to the
hosted source, and the MCP server serves *your* version — author once, any
runtime, no deploy. An overlay of a catalog agent wins for *your* tenant while
every other tenant still sees the base.

```console
# 1. Scaffold your own agent in your scope (dna-copilot will walk you through this)
$ dna new agent assistant --scope my-scope --soul my-brand-voice --layout persona-first

# 2. Author it — fill the AGENT.md instruction + wire your Soul / Guardrails / Skills.

# 3. Preview the composed prompt before you ship
$ dna doc show Agent assistant --scope my-scope

# 4. Push it to the hosted DNA source as your tenant overlay
$ DNA_TENANT=my-tenant dna doc apply agents/assistant/AGENT.md \
      --scope my-scope --source "$DNA_SOURCE_URL"
```

Now the MCP server resolves `assistant` for `my-tenant` to *your* overlay;
another tenant with no overlay keeps reading the base catalog agent. That
isolation is proved by `packages/sdk-py/tests/test_dna_cloud_catalog_overlay.py`.

### Gated by your plan

Authoring + emit is a **Pro** capability; **Free** reads the base catalog. The
caps are declared on the `PricingPlan` Kind (`examples/dna-cloud/.dna/_lib/tiers/`):

| Plan | `feature_families` | Catalog | BYO overlay |
|------|--------------------|---------|-------------|
| **Free** | `definitions`, `sdlc` | read the base | — |
| **Pro** | `+ memory`, `emit` | read the base | **author own + emit** |

If you hit a cap, upgrade rather than working around it — `dna-copilot` will
point you there.

## Seeding the catalog into the hosted source

These `_lib` agents are exactly what the hosted deployment seeds into its DNA
source (the same "Phase 2" seed step as the demo scope in
[Hosting the MCP server on Azure](hosting-mcp-aca.md)):

```console
# push the whole _lib catalog to the hosted Postgres source
$ dna doc apply examples/dna-cloud/.dna/_lib --source "$DNA_SOURCE_URL"
# …or, on the ACA deployment, the mounted-source helper:
$ ./scripts/push-scope.sh examples/dna-cloud/.dna
```

After the seed, every tenant inherits the three agents immediately, and Pro
tenants can start overlaying their own.
