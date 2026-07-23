# DNA SDK — Kernel Subpackaging + Metering Rename (Spec C), 0.29.0

**Goal:** two SDK-core changes in one careful, test-gated release:
1. **Kernel subpackaging** — `dna/kernel/` is 60 flat modules; group them into
   subpackages by responsibility, WITHOUT changing behavior.
2. **Metering rename/debrand (Spec C)** — `Tier → PricingPlan`,
   `AccountPlan → PlanBinding`; remove "DNA Cloud" branding from the SDK (the SDK
   is a neutral metering mechanism; the commercial policy lives in dna-cloud).

**Release:** 0.29.0 (a minor — structural + a Kind rename; NOT a patch).

**Status:** design. Naming decision made (PricingPlan/PlanBinding). Execution is a
DEDICATED effort — see "Execution discipline".

---

## Decision: the `Plan` collision (what paused Spec C)

The metering Kinds live in `extensions/cloud/kinds/` as `tier.kind.yaml` +
`account-plan.kind.yaml`. Spec C wanted `Tier → Plan`, but **`Plan` is already the
SDLC Kind** (implementation plans). Renaming to `Plan` collides.

**Resolved:** `Tier → PricingPlan`, `AccountPlan → PlanBinding`. Fully-qualified
commercial names — zero collision with the SDLC `Plan`, and the name says what it
is (a *pricing* plan) without depending on scope isolation to disambiguate.

Rename map:

| Old (SDK) | New | Where |
|---|---|---|
| `Tier` Kind | `PricingPlan` | `extensions/cloud/kinds/tier.kind.yaml` → `pricing-plan.kind.yaml` |
| `AccountPlan` Kind | `PlanBinding` | `extensions/cloud/kinds/account-plan.kind.yaml` → `plan-binding.kind.yaml` |
| `catalog_tier` (kernel) | `catalog_pricing_plan` | `dna/kernel/` |
| `default_tier`, `*_tier` config | `default_pricing_plan`, `*_pricing_plan` | grep-driven |
| "DNA Cloud" strings in SDK | neutral copy | debrand pass |

dna-cloud consumers (`infra/tiers/*.yaml` → now `config/tiers/`, the plan-store,
the quota gates) update to the new Kind names — a lockstep bump after the release.

---

## Kernel subpackaging — PROPOSED grouping (validate against deps first)

The 60 modules cluster into these subpackages. **This is a proposal — the FIRST
execution step is to build the module dependency graph and adjust so no subpackage
imports create a cycle** (the kernel is the core; a circular import breaks the SDK).

```
dna/kernel/
├─ __init__.py                 # re-exports the public kernel surface (unchanged imports for consumers)
├─ models.py  errors.py  protocols.py  meta.py  semver.py  capabilities.py   # primitives (stay top-level)
├─ prompt/        prompt_budget, prompt_builder, prompt_kernel
├─ kinds/         kind_base, kind_definition_schema, kind_registry
├─ source/        source_facade, source_sync, generic_rw, descriptor_loader,
│                 document, bundle_handle, bundle_io
├─ write/         write_pipeline, writer_helpers, evidence_capture, bitemporal_guard
├─ query/         query_engine, query_fallback, search_engine, resolver,
│                 navigator, nav_kernel, references, preview
├─ compose/       composition, composition_resolver, layer_policy, layer_resolver,
│                 templates, instance, instance_builder
├─ registry/      registry_accessor, tool_registry, catalog_cache,
│                 catalog_pricing_plan (was catalog_tier)
├─ boot/          kernel_bootstrap, kernel_cache, runtime, hooks, eventbus,
│                 events, invalidation
├─ lock/          lock, lock_manager, module_lock
└─ (misc to place after dep analysis: embedding, resource, reports, reports_kernel,
    studio_ui, collaborator_ports, _text)
```

**The `__init__.py` re-export rule:** consumers import from `dna.kernel` (public
surface). The subpackaging must keep `dna.kernel.<PublicName>` working — the
`__init__.py` re-exports every public symbol from its new subpackage home, so NO
consumer import changes. This is the safety net: the refactor is internal-only.

### ⚠️ Scope reality (dependency analysis, 2026-07-23)

The dep graph + a consumer survey ran. Two findings resize this effort:

1. **59 modules, 105 intra-kernel edges.** Core primitives (stay top-level):
   `protocols` (fan-in 20), `collaborator_ports` (12), `document` (9),
   `instance` (8), `capabilities` (6), `preview` (6), `hooks`, `errors`. 21 leaf
   modules (no intra-kernel deps) move first.
2. **Consumers import by MODULE PATH, not symbol.** `from dna.kernel.protocols
   import …` (84 uses), `dna.kernel.instance`, `.hooks`, `.kind_base`, … — **50
   SDK files** + the CLI + dna-cloud all reference `dna.kernel.<module>` paths.
   The `kernel/__init__.py` barely re-exports. So moving a module BREAKS those
   paths everywhere — a symbol re-export in `__init__` does NOT save a
   `from dna.kernel.instance import X`.

**Consequence:** this is NOT an internal-only refactor like the copilot/web apps.
It is a **coordinated cross-repo change** — move the modules, then update every
`dna.kernel.<module>` path across the SDK (50 files), the CLI, AND dna-cloud, with
compat shims (`dna/kernel/<old>.py` re-importing from the new home) if a phased
rollout is wanted. It ships as 0.29.0 and dna-cloud bumps its pin in lockstep.

This is a DEDICATED, focused effort with a clean test env — the analysis here
(dep graph + import survey) de-risks it, but executing 59 moves + ~200 consumer
import updates against a non-clean baseline at the tail of a long session is
exactly the recklessness this spec's discipline section warns against.

---

## Execution discipline (why this is a dedicated effort, not improvised)

The web/lib subpackaging (simpler, one app) took 5+ rounds of import fixes. The
kernel is the SDK CORE — everything imports it, and a subtle break ships to every
consumer + the just-released 0.28.1 line. So:

1. **Dependency graph FIRST.** Build the intra-kernel import graph; adjust the
   grouping so subpackage edges are acyclic. Do NOT move a file until its group's
   edges are known.
2. **Move + rewrite in small, test-green increments** — one subpackage at a time,
   `pytest packages/sdk-py` green after each. Keep `dna.kernel.__init__` re-exporting
   so the public surface is stable throughout.
3. **The rename is its own increment** — `Tier→PricingPlan`/`AccountPlan→PlanBinding`
   + the Kind YAML renames + the debrand, with the metering tests as the gate.
4. **Full SDK suite + the cli suite green** before tagging 0.29.0.
5. **Release 0.29.0**, then bump dna-cloud's pins (`>=0.29,<0.30`) + rename its
   consumers (config/tiers → PricingPlan docs, plan-store, quota gates) in lockstep.

This is the honest scope: a focused SDK-core effort with the dependency analysis +
per-increment testing that the core deserves — not a tail-of-session improvisation.
