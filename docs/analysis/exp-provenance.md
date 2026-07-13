# Experiment 2 — Provenance of a composed agent

**Spike:** `sp-exp-provenance`
**Question:** Does the DNA answer *provenance* of a composition — which artifact
originated each instruction, the precedence/order, overrides, and the hash +
version of each contributor?
**Verdict (one line):** **Half real, half aspirational.** The DNA already has a
genuine, parity-tested *layer/overlay* provenance engine (which **layer** a doc
came from, which fields a tenant overrode) — but it has **no per-prompt-section
attribution** out of the box: `build_prompt` renders a flat string and throws
the section→artifact map away. That map is *trivially recoverable* from the
kernel's own building blocks (I did it in ~200 lines), which is exactly why this
differentiator is **real and hard to fake with a YAML folder** — but today it is
a capability the engine *enables*, not a feature it *ships*.

---

## The composition under test

A single agent `aria` (scope `provenance-demo`), composed from **6 layered
artifacts across 4 Kinds**, plus a **tenant overlay** that deliberately
overrides one of them:

| Artifact | Kind | Role in the prompt |
|---|---|---|
| `agents/aria.yaml` | Agent | task instruction + `layout: persona-first` + dep lists |
| `souls/aria-persona/SOUL.md` | Soul | persona, flattened into the prompt |
| `skills/citation-discipline/SKILL.md` | Skill | on-demand know-how (progressive disclosure) |
| `skills/concise-answers/SKILL.md` | Skill | on-demand know-how (progressive disclosure) |
| `guardrails/no-medical-advice/GUARDRAIL.md` | Guardrail | hard policy, always in prompt |
| `guardrails/cite-sources/GUARDRAIL.md` | Guardrail | hard policy, always in prompt |
| `tenants/acme/…/souls/aria-persona/SOUL.md` | Soul (overlay) | **overrides** `spec.soul_content` for tenant `acme` |

The whole scope + the renderer live under
[`docs/analysis/exp-provenance/`](./exp-provenance/) so the demo is
self-contained and reproducible:

```bash
python docs/analysis/exp-provenance/render_provenance.py        # base
python docs/analysis/exp-provenance/render_provenance.py acme   # tenant overlay
```

---

## The provenance artifact (real output)

### Base composition

```
 #  PROMPT SECTION                  SOURCE ARTIFACT (file)                                        HASH          VER     ORIGIN
-----------------------------------------------------------------------------------------------------------------------------
 1  Soul: soul_content              provenance-demo/souls/aria-persona/SOUL.md                    8443458a1e81  1.0.0   local
 2  Agent: instruction              provenance-demo/agents/aria.yaml                              338ab36cc560  2.1.0   local
 3  Guardrail: cite-sources         provenance-demo/guardrails/cite-sources/GUARDRAIL.md          e0f9b6756e03  —       local
 4  Guardrail: no-medical-advice    provenance-demo/guardrails/no-medical-advice/GUARDRAIL.md     ec3326bcb528  —       local
```

Composition tree (precedence = top-to-bottom render order, `layout:
persona-first`):

```
aria  (Agent, helix-agent · layout=persona-first)
├─ §1  Soul.soul_content        ← souls/aria-persona/SOUL.md          #8443458a  v1.0.0
├─ §2  Agent.instruction        ← agents/aria.yaml                    #338ab36c  v2.1.0
└─ guardrails (always last, hard policy)
   ├─ §3  Guardrail cite-sources     ← guardrails/cite-sources/…      #e0f9b675
   └─ §4  Guardrail no-medical-advice ← guardrails/no-medical-advice/… #ec3326bc
   (Skills citation-discipline / concise-answers are declared deps but
    NOT in the prompt — exposed via progressive disclosure, by design.)
```

### Tenant `acme` — the override, made visible

```
 #  PROMPT SECTION                  SOURCE ARTIFACT (file)                                        HASH          VER     ORIGIN
-----------------------------------------------------------------------------------------------------------------------------
 1  Soul: soul_content              tenants/acme/scopes/provenance-demo/souls/aria-persona/SOUL.md 81f11110c93c  1.0.0   local
 2  Agent: instruction              provenance-demo/agents/aria.yaml                              338ab36cc560  2.1.0   local
 3  Guardrail: cite-sources         guardrails/cite-sources/GUARDRAIL.md                          e0f9b6756e03  —       local
 4  Guardrail: no-medical-advice    guardrails/no-medical-advice/GUARDRAIL.md                     ec3326bcb528  —       local

OVERRIDES / CONFLICTS:
   §1  ◄ OVERRIDDEN by tenant overlay (spec.soul_content)
```

Section §1's **hash changes** (`8443458a → 81f11110`) and its **source file
flips** to the tenant path; every other section's hash is byte-identical to the
base. The composed prompt's opening line changes from *"warm and calm"* to
*"brisk and efficient"* — and the table says exactly which file, at which layer,
caused it.

Both prompts are emitted under a **byte-equality gate**: the renderer asserts
that concatenating its attributed segments reproduces `mi.build_prompt(agent)`
character-for-character. If attribution ever drifts from what the kernel
actually composes, the script fails loudly rather than lying.

---

## Does the DNA answer the 5 provenance questions? (blunt scorecard)

| # | Question | Answer today | Where it comes from |
|---|---|---|---|
| 1 | Which artifact contributed which **section**? | ⚠️ **Recoverable, not shipped** | Not in `build_prompt`; reconstructed by my renderer from the kernel's own layout template + dep_filters + flatten map |
| 2 | **Precedence / order** of composition | ✅ / ⚠️ | Layout template (`persona-first`) gives Soul→instruction→guardrails deterministically. **But** within the guardrails block the order is document/alphabetical order, **not** the agent's declared `guardrails:` list order — a real fidelity gap |
| 3 | **Overrides / conflicts** | ✅ **Real** | The kernel stamps `has_overlay` + `overlay_fields` into a resolved doc, and `kernel.resolve_document()` returns a full `ResolutionPath` (every layer tried, `found`, `contributed`, `effective_layer`) |
| 4 | **Hash + version** per contributor | ⚠️ **Hash: had to compute; version: partial** | No hash on `Document`; I hashed the canonical raw with lock.py's scheme. `version_sha` in the resolver is `None` for the FS source. Version reads from metadata but is model-dependent (Guardrail drops it → `—`) |
| 5 | **Tree / graph** of composition | ⚠️ **Built here** | The kernel has all edges (agent→soul/skills/guardrails via `dep_filters`); the tree above is assembled by the renderer, not emitted by the engine |

Legend: ✅ ships in the engine · ⚠️ the *data* is there, the *rendered answer* is not.

---

## What was already there vs. what I had to build

**Already in the DNA (real, parity-tested, load-bearing):**

- **Layer/overlay provenance is a first-class engine.**
  `kernel.resolve_document(scope, kind, name, tenant=…)` →
  `ResolvedDocument{ doc, provenance: ResolutionPath, is_inherited,
  contributions_by_field }`. For tenant `acme` it returned the full chain —
  `(provenance-demo, acme) found+contributed` (winner), `(provenance-demo, None)
  found, NOT contributed` (shadowed base), `(_lib, …) miss`. This is a genuine,
  non-trivial answer to "where did this **document** come from and what
  overrode it," and it exists in **both** Python and TypeScript
  (`kernel/resolver.py` ↔ `kernel/resolver.ts`).
- **Inline override breadcrumbs.** A resolved doc carries `has_overlay: true` +
  `overlay_fields: ['soul_content']` in its metadata — the engine tells you a
  tenant touched it and *which fields*.
- **The composition wiring is fully declared and introspectable.** `dep_filters`
  (`soul→soulspec-soul`, `skills→agentskills-skill`, `guardrails→…`),
  `flatten_in_context`, `is_prompt_target`, and the named `layout` templates are
  all data on the KindPorts. The section→artifact map is *derivable* from them.
- **A canonical hashing scheme** already exists for the lockfile
  (`sha256(canonical raw)`), and every artifact is a versionable file.

**What I had to build (the ~200-line renderer,
[`render_provenance.py`](./exp-provenance/render_provenance.py)):**

- Segment the real layout template into ordered pieces, map each piece back to
  its owning Document (via `dep_filters` + `flatten_in_context`), and render
  per-artifact so each **prompt section** gets a source, hash, version, and
  layer — the thing `build_prompt` discards.
- Fold in the override signal (`has_overlay`/`overlay_fields`) as a
  conflicts list.
- The byte-equality correctness gate.

**What is genuinely missing / weak (honest gaps):**

1. **No `build_prompt(..., explain=True)` and no `dna explain` CLI.** The
   per-section provenance lives nowhere in the shipped surface — not the CLI,
   not the SDK return type. `grep` for `explain`/`provenance` on the prompt path
   finds nothing.
2. **`resolve_document`'s rich provenance is library-only** — it is not exposed
   by any `dna` subcommand; only the harness/Studio consume it.
3. **`version_sha` is `None` from the filesystem source** — the resolver's own
   provenance struct has a slot for the per-artifact version hash but doesn't
   populate it for FS.
4. **Declared guardrail order is not preserved** in the composed prompt (fidelity
   gap for question #2).
5. **`Document` has no hash and no source file-path** — I recomputed both;
   `doc.origin` stayed `"local"` even for the overlaid doc, so it is *not* a
   reliable layer indicator on its own.

---

## Is this a REAL differentiator, or aspirational?

**Real — and structurally hard to reproduce with a YAML folder.** A plain
folder of YAML has no composition engine, so "which of these six files produced
line 7 of the running system prompt, and which tenant layer overrode it" is a
question it *cannot answer at all* — there is no notion of layout precedence,
dep-filtered slots, flatten rules, or layer overlay to attribute against. The
DNA has every one of those as declared, typed data, which is precisely why a
~200-line renderer can produce a verified, byte-exact section→artifact→hash→layer
map. That is a capability a flat folder is *architecturally incapable* of, not
merely one it hasn't written yet.

**But it is not yet a shipped feature.** Today the DNA *enables* provenance; it
does not *deliver* it. The overlay/layer half (`resolve_document`) is real and
tested; the per-section-prompt half is latent — the data is all present, the
rendering surface is not. To make the claim true without an asterisk, the DNA
needs to promote this renderer into the engine: a `build_prompt(explain=True)`
returning `[{section, source_artifact, hash, version, layer, overridden_by}]`,
surfaced via `dna explain <agent>` and the REST/MCP `compose_prompt`, with
`version_sha` populated and declared-order fidelity fixed.

**Bottom line for the founder:** provenance is the DNA's most defensible thesis —
a YAML folder can never answer it — but right now you can only *demonstrate* it
with a script, not *point to a feature*. The gap between the two is small
(~a day of engine work) and worth closing, because the demo is the moat.
