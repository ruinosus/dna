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

## Background automation

### Automation

An [`Automation`](../reference/kinds/record.md#automation)
(`dna-automation`) declares background work as data: `on` says **when** it
fires and `runner` says **what** runs. One doc, zero deploy — adding,
retargeting or pausing an automation is a YAML edit, not a code change.
The Kind is a direct port of the internal SDK's unification of three
structurally identical trigger Kinds (async-tool job / event hook / cron
schedule) into one schema discriminated by `on.type`:

- **`cron`** — a 5-field cron expression (`0 10 * * 1,3,5`). The write
  path parses it with a zero-dependency validator (numbers, `*`, ranges,
  lists, steps; no `JAN`/`MON` name aliases), so `61 * * * *` is vetoed at
  write time, not discovered at 3 a.m.
- **`hook`** — a kernel lifecycle hook name (`post_save`,
  `post_build_prompt`, …). The name must belong to the kernel's typed
  vocabulary (`KNOWN_HOOK_NAMES`): a misspelled hook would be declared,
  listed and silently never fire, so an unknown name is a veto, not a
  warning.
- **`tool`** — an async dispatch tool the host exposes to the model
  (`tool_name` + a declared `input_schema` + `primary_input`), for
  "fire-and-forget from a conversation" work like deep research.

Validation happens **at the write, not at scan**: the write guard runs the
Kind's schema (per-trigger required fields, runner enum) and the semantic
checks above before anything persists, so a broken Automation is vetoed
while the author is still present. One authoring note for hand-edited
YAML: prefer quoting the trigger key (`'on':`) — YAML 1.1 parsers such as
PyYAML read a bare `on` as a boolean. The Python write path heals the
boolean-key form before validating, and docs emitted by the SDK are
always quoted, so the round-trip is safe either way.

The runner is a reference to a real Kind — an `Agent` (`kind: agent`) or a
`Tool` (`kind: tool`) by name — plus the shared directive surface:
`agent_directive` (the dispatch instruction, with `{arg}` placeholders),
`input` (structured context), `result_kind`/`result_spec_template`
(deterministic persistence of the output), `running_message`/`done_message`
(user-facing copy) and a `safety` block (debounce, cooldown, rate cap,
fan-out cap, idempotency key) that the host enforces as loop protection.
Automation is an inheritable `_lib` default: declare the fleet once in the
library scope, let every scope inherit it, and let a tenant override one
doc in its overlay.

Contrast with [`Hook`](#hook): a Hook is an *in-process* interceptor the
SDK itself runs around prompt building; an Automation is *out-of-process*
work — a report at 03:00, reindexing after a save — that only a host
runtime can execute.

### The execution extension point

Deliberately, **execution does not ship in the SDK** — there is no
scheduler, bus or worker in a notation library. The contract is split the
same way as the CLI's post-transition hooks
(`dna_cli.sdlc_cmd.register_post_transition_hook`, where the CLI declares
the hook point and the host registers the executor): the SDK **declares,
validates and lists**; the host **reads and runs**. The read side is the
query helpers `automations_for(instance, trigger_type)` and
`trigger_key(doc)` (`automationsFor` / `triggerKey` in TypeScript), built
on the blessed instance query surface. A minimal cron runner is ~20 lines:

```python
# host_runner.py — a minimal cron executor over declared Automations
import time

from dna.kernel import Kernel
from dna.extensions.automation import automations_for, trigger_key

mi = Kernel.quick("my-scope")

while True:
    for doc in automations_for(mi, "cron"):  # enabled-only by default
        if cron_matches_now(trigger_key(doc)):  # your cron matcher
            runner = doc.spec["runner"]
            run_agent(                           # your agent runtime
                name=runner["ref"],
                directive=doc.spec.get("agent_directive", ""),
                inputs=doc.spec.get("input", {}),
            )
    time.sleep(60)
```

A hook-triggered executor is the same pattern on the kernel's own event
channel: for each doc from `automations_for(mi, "hook")`, subscribe
`kernel.hooks.on(trigger_key(doc), ...)` and dispatch the runner from the
listener. Whatever the trigger, honor `spec.safety` before firing — the
doc declares the loop protection, the host enforces it.

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

## Evaluation

Four Kinds make evaluation authoring data — ported from the internal
SDK's eval extension minus its runtime (the upstream runner was a
Temporal worker driving live agents through LLM judges; none of that
belongs in a notation library). What ships instead is a **local,
synchronous, offline runner** whose default target is the kernel itself:
composing a prompt is a deterministic function of the declared documents,
so *"does my agent compose the prompt I expect?"* is a real evaluation of
declarative config — no LLM required. The [evaluating agents
guide](../guides/evaluating-agents.md) walks the full workflow, including
how a host registers an LLM target (`EvalTargetPort` — the same
declare-here/execute-in-the-host split as [Automation](#automation)
runners).

### EvalCase

An [`EvalCase`](../reference/kinds/record.md#evalcase) (`eval-eval-case`)
is one scenario: a `target` (what produces the text under test — default
`{type: prompt, agent: X}`, the composed system prompt) and a list of
deterministic `checks` (`contains`, `not_contains`, `regex`, `not_regex`,
`equals`, `min_length`, `max_length`) that ALL must pass. Upstream fields
that presuppose a live agent loop (trajectory matching, HITL policies,
judge engines) deliberately did not travel.

### EvalSuite

An [`EvalSuite`](../reference/kinds/record.md#evalsuite)
(`eval-eval-suite`) groups cases and configures the run: the `cases` list
(empty = every EvalCase in the scope), a default `target` the cases
inherit, and `stop_on_fail`. Execute it with `dna eval run <suite>` —
offline, in seconds, in CI.

### EvalRun

An [`EvalRun`](../reference/kinds/record.md#evalrun) (`eval-eval-run`) is
the persisted ledger of one execution: counts, timestamps, the resolved
target and per-case results with the outcome of every declared check.
`dna eval run --save` writes it; being a document, runs are queryable,
diffable and versioned like everything else.

### EvalBaseline

An [`EvalBaseline`](../reference/kinds/record.md#evalbaseline)
(`eval-eval-baseline`) pins one EvalRun as the "known good" reference for
a suite (`dna eval pin <run>`). Future runs compared against it
(`dna eval run <suite> --baseline <name>`) report regressions,
improvements and unchanged cases — and exit non-zero only on a
regression, so a pre-existing failure doesn't re-fail your CI.

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

### HtmlArtifact

An [`HtmlArtifact`](../reference/kinds/record.md#htmlartifact)
(`sdlc-html-artifact`) stores an HTML page as a first-class, linkable output of
a work item (Story/Feature/Epic/Spike). It is a bundle: `ARTIFACT.html` holds
the raw HTML **byte-faithful** (the writer never injects frontmatter or
re-escapes, so a design doc or rendered report round-trips untouched) plus an
optional `artifact.json` companion with structured metadata — the same mechanic
as a Soul's `SOUL.md` + `soul.json`. Attach one to the board with `dna sdlc
produces add <WiKind>/<wi> HtmlArtifact/<name>`; the [SDLC
guide](../guides/sdlc.md#work-items-produce-artifacts) walks the flow.

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
