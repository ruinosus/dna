# The built-in Kinds — a commented catalog

[Kinds — identity & composition](kinds.md) explains the *mechanics* of a
Kind; this page is the commented catalog of the composition-plane Kinds
that ship with the SDK beyond the core prompt family, grouped by what they
are for. Two–four honest sentences each: what it is, its role, when you
would reach for it. Field-by-field schemas live in the [generated Kinds
reference](../reference/kinds/composition.md), which cannot drift from the
source.

The core prompt-composition family — `Genome`, `Agent`, `Skill`, `Soul`,
`AgentDefinition`, `Guardrail`, `KindDefinition` and friends — is covered
in [Kinds](kinds.md) and the [first-Kind
tutorial](../getting-started/first-kind.md). The record-plane SDLC family
(Story, Feature, Issue, …) is covered in [Your git log is your
SDLC](../guides/sdlc.md). What follows is everything else.

## Composition mechanics

### Hook

A [`Hook`](../reference/kinds/composition.md#hook) (`helix-hook`) is a
declarative lifecycle interceptor: it attaches to a kernel hook point such
as `pre_build_prompt` and runs an action — `inject_fields` merges YAML
key-value pairs into the prompt context, `log` emits a structured message,
`script` executes inline code. Hooks are stored as `hooks/<name>/HOOK.md`
bundles and auto-register when `ManifestInstance.apply_hooks()` is called.
Use one when behavior around prompt building must change without a deploy —
injecting a feature flag or contextual field into every prompt is the
canonical case.

## Collaboration

### Comment

A [`Comment`](../reference/kinds/composition.md#comment) (`collab-comment`)
is a remark, status change or assignment attached to **any** other
document via `target_ref` (`Kind:name`). It is how discussion and history
become data: the SDLC timelines, review notes on an eval finding, or an
agent narrating its work all land as Comment documents. Reach for it
whenever "who said what about this doc, when" needs to be queryable rather
than buried in chat.

### Canvas

A [`Canvas`](../reference/kinds/composition.md#canvas) (`helix-canvas`) is
a shared whiteboard between a voice/chat agent and the user, backed by a
serialized tldraw snapshot in `spec`. The user draws; the agent reads the
shapes as JSON (or vision-interprets free strokes) and writes back through
discrete shape tools. It exists as a Kind — rather than ephemeral UI state —
so boards are persisted, searchable and embeddable like any other
document. It is a product-facing Kind: useful when you build an assistant
UI on DNA, irrelevant for headless setups.

## Safety & governance

### SafetyPolicy

A [`SafetyPolicy`](../reference/kinds/composition.md#safetypolicy)
(`helix-safety-policy`) declares runtime enforcement rules for agent input
and/or output: PII, content safety, topic restriction, prompt injection,
banned words, custom regex. Tier 1 (regex — CPF/CNPJ/email/phone/credit
card plus injection heuristics) is built in; ML and LLM-judge tiers are
opt-in extras. The `action` decides what happens on a hit: `mask` redacts
inline, `block` rejects the message, `log` passes through with violation
metadata. This is the Kind to write when compliance asks "prove nothing
personal reaches the model".

### Recognizer

A [`Recognizer`](../reference/kinds/composition.md#recognizer)
(`presidio-recognizer`) is a [Presidio](https://microsoft.github.io/presidio/)
ad-hoc PII recognizer as data: an entity type (say `BR_CPF`), regex
patterns with scores, deny lists and context words. SafetyPolicy documents
reference Recognizers via `dep_filters`, and the runtime exports them to
the Presidio engine. Write one when the built-in entities miss a
domain-specific identifier — an internal employee ID format, a
country-specific document number.

### EvidencePolicy

An [`EvidencePolicy`](../reference/kinds/composition.md#evidencepolicy)
(`evidence-policy`) controls which event types are automatically captured
as immutable Evidence documents — the content-level audit trail. It
declares the event list to watch, whether auto-capture is on, and the
retention period. Use it to tune the audit surface per scope: capture
everything in a regulated project, only writes elsewhere.

### UserRoleAssignment

A [`UserRoleAssignment`](../reference/kinds/composition.md#userroleassignment)
(`audit-userroleassignment`) maps a user identity to a role list within a
tenant — the document name *is* the user id. It backs role-gated endpoints
in a hosting platform's admin surface and is the persistent mirror of IdP
group membership. You only touch it when running DNA multi-user behind
auth; single-user local setups never see one.

### MCPFederation

An [`MCPFederation`](../reference/kinds/composition.md#mcpfederation)
(`federation-mcp`) declares an external MCP server whose tools agents may
consume: transport (`stdio` command or streamable HTTP URL), an
`allowed_tools` bound, and an `enabled: false` kill switch. An Agent lists
the doc's name in `spec.mcp_servers` and the runtime loads the remote
tools as first-class agent tools — zero code, zero deploy. Secrets never
live in the doc: the auth block carries env-var *names*, read at connect
time.

## Model registry

### ModelProfile

A [`ModelProfile`](../reference/kinds/record.md#modelprofile)
(`modelreg-model-profile`) records one LLM model's hard limits and
capabilities — `instruction_token_cap`, `context_window`, `tools_cap`,
`max_output_tokens`, modalities, cost — as first-class data instead of
implicit knowledge scattered through code. Profiles are GLOBAL and live in
the `_lib` scope (`model-profiles/<model_id>.yaml`); resolve one with
`kernel.model_profile(id_or_alias)` (`modelProfile` in TypeScript), which
matches `model_id` first and the `aliases` list second, regardless of the
caller's scope.

The registry exists for one contract: **never hardcode token caps**. The
kernel's write path enforces it — when an Agent that declares a `model`
(or a `voice_persona`) is written, the prompt-budget guard estimates the
instruction's token count and compares it against the profile's
`instruction_token_cap`. A *strict* model — a voice persona write, or any
profile with `realtime: true` — over the cap **vetoes the write** with a
didactic error; a chat model over the cap writes but warns loud; an Agent
with no declared model, or a model with no profile, passes untouched
(enforcement is opt-in: writing a profile with a cap arms the guard). The
estimate is a deliberate over-count (chars ÷ 3.5), so the guard never
under-blocks; `DNA_PROMPT_BUDGET_ENFORCE=0` is the ops kill-switch that
downgrades the veto to a warning. This ports a lesson paid for in a real
outage: a 17,269-token voice persona silently exceeded a realtime model's
16,384-token session-instructions cap because the cap lived in nobody's
code.

```yaml
# _lib/model-profiles/gpt-realtime-2.yaml
apiVersion: github.com/ruinosus/dna/modelreg/v1
kind: ModelProfile
metadata:
  name: gpt-realtime-2
spec:
  model_id: gpt-realtime-2
  provider: openai
  realtime: true            # strict: over-cap Agent writes are vetoed
  context_window: 32768
  instruction_token_cap: 16384
  modalities: [text, audio]
  aliases: [gpt-realtime-2-2026-05-07]
```

## Preferences & personalization

### Setting

A [`Setting`](../reference/kinds/composition.md#setting) (`helix-setting`)
is a reusable configuration snippet — env vars plus nested config plus
setup prose for one domain ("configure Vertex AI", "corporate proxy").
Selected Settings compose into a coding agent's `settings.json` or the
runtime env. Atomic and idempotent by design, so a "complete workstation
setup" is just a scope of docs.

### Theme

A [`Theme`](../reference/kinds/composition.md#theme) (`helix-theme`)
declares a UI color palette — primary/accent/success in light **and** dark
HSL — plus optional typography and radius overrides, applied as CSS
variables at runtime with no rebuild. Because it is a document, a tenant
ships its brand by publishing `themes/brand.yaml` in its overlay. Only
meaningful when a web UI sits on top of DNA.

### UserProfile

A [`UserProfile`](../reference/kinds/composition.md#userprofile)
(`helix-user-profile`) holds per-user personalization data — display name,
language, communication style, opt-in personal context — that an agent may
inject into its prompt. It is consent-gated: without
`consent.profile_used_in_prompts: true` (or without a doc at all) the
agent treats the user as anonymous, and each user can read/write only
their own profile. Use it when an agent should remember *who* it is
talking to across sessions.

## Testkit

### TestGuide

A [`TestGuide`](../reference/kinds/composition.md#testguide)
(`testkit-test-guide`) is a declarative test script: an ordered list of
steps (action → expected, optionally *where* in the product) that verifies
one or more work items via `verifies` refs. It turns the test roteiro that
used to live in chat into a versioned, schema-validated, re-runnable
document. Write one per feature you expect a human (or agent) to smoke
again later.

### TestRun

A [`TestRun`](../reference/kinds/composition.md#testrun)
(`testkit-test-run`) records one execution of a TestGuide: outcome
(`pass`/`fail`/`partial`/`blocked`), who ran it, per-step results and
evidence. A passing run whose `verifies` points at a work item drives that
item's *verify* phase in the derived journey — it is the proof, where the
guide is the promise.

## Domain content

### Doc

A [`Doc`](../reference/kinds/record.md#doc) (`dna-doc`) is one page of
in-product documentation: a markdown body plus sidebar metadata (icon,
order, locale, Diátaxis `kind_of`, free-form category), authored as a
`docs/<name>/DOC.md` bundle and read back by `dna docs list/show` — so a
DNA-based product serves its own help pages straight from the kernel. It
is a record-plane Kind shipped as a pure descriptor (content as data, no
port class), ported from the internal SDK's doc extension minus its
product-specific help-center machinery (live data/diagram placeholders,
landing-page curation, asset aggregation).

### Lesson

A [`Lesson`](../reference/kinds/composition.md#lesson) (`lesson-lesson`)
is a short, structured educational activity an agent can run with a
pre-reader child — subject, target concepts, spoken prompts — born in an
AAC (augmentative and alternative communication) product built on DNA. It
is deliberately data, not code, so caregivers and therapists curate
content in a UI without code review. It doubles as the reference example
of a narrow domain Kind carried by an extension: your equivalent might be
`Recipe` or `Workout`.

---

Run `dna kind list` for the live registry in your install, and `dna kind
describe <Kind>` for the exact schema the write boundary enforces — the
[CLI tour](../guides/cli-tour.md) shows both in action.
