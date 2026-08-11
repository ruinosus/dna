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
instance via `target_ref` (`Kind:name`). It is how discussion and history
become data: the SDLC timelines, review notes on an eval finding, or an
agent narrating its work all land as Comment instances. Reach for it
whenever "who said what about this doc, when" needs to be queryable rather
than buried in chat.

### Canvas

A [`Canvas`](../reference/kinds/composition.md#canvas) (`helix-canvas`) is
a shared whiteboard between a voice/chat agent and the user, backed by a
serialized tldraw snapshot in `spec`. The user draws; the agent reads the
shapes as JSON (or vision-interprets free strokes) and writes back through
discrete shape tools. It exists as a Kind — rather than ephemeral UI state —
so boards are persisted, searchable and embeddable like any other
instance. It is a product-facing Kind: useful when you build an assistant
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
patterns with scores, deny lists and context words. SafetyPolicy instances
reference Recognizers via `dep_filters`, and the runtime exports them to
the Presidio engine. Write one when the built-in entities miss a
domain-specific identifier — an internal employee ID format, a
country-specific instance number.

### EvidencePolicy

An [`EvidencePolicy`](../reference/kinds/composition.md#evidencepolicy)
(`evidence-policy`) controls which event types are automatically captured
as immutable Evidence instances — the content-level audit trail. It
declares the event list to watch, whether auto-capture is on, and the
retention period. Use it to tune the audit surface per scope: capture
everything in a regulated project, only writes elsewhere.

### UserRoleAssignment

A [`UserRoleAssignment`](../reference/kinds/composition.md#userroleassignment)
(`audit-userroleassignment`) maps a user identity to a role list within a
tenant — the instance name *is* the user id. It backs role-gated endpoints
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

## Runtime bindings

### RuntimeBinding

A [`RuntimeBinding`](../reference/kinds/record.md#runtimebinding)
(`runtime-binding`) selects how a portable `Agent` is attached to a runtime.
It names the runtime protocol and optional provider, points to a deployment
host by reference, and declares policies for confirmations, reconnects, and
session authority. Deployments resolve the host reference; the binding never
stores a raw endpoint, credentials, transport objects, subscriptions, or
sessions. Those remain the runtime host's responsibility, so the same agent
definition and binding can move between environments without embedding
deployment state in DNA.

For a local consumer run, resolve the binding with
`dna run --binding local-copilot --prompt "Continue the analysis"`. The command
uses the binding's Agent and provider; it does not treat `spec.host.ref` as an
endpoint.

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
variables at runtime with no rebuild. Because it is an instance, a tenant
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
instance. Write one per feature you expect a human (or agent) to smoke
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
composing a prompt is a deterministic function of the declared instances,
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
`dna eval run --save` writes it; being an instance, runs are queryable,
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

## DNA Cloud

### PricingPlan

A [`PricingPlan`](../reference/kinds/record.md#pricingplan) (`cloud-pricing-plan`)
declares one DNA Cloud pricing plan as data: its hard caps (`calls_per_day`,
`rate_per_sec`, `max_tenants`), the feature families it unlocks
(definitions / sdlc / memory / emit), `memory_mode`, and price. The hosted
MCP server resolves a request's plan and enforces the caps at the same seam
that binds a token to a tenant — so changing a limit is a file edit, not a
redeploy. Free and Pro ship as seed docs. (The Kind was renamed from `Tier` in
0.29.0; its storage container stays `tiers` and the binding field stays `tier_id`.)

### PlanBinding

A [`PlanBinding`](../reference/kinds/record.md#planbinding)
(`cloud-plan-binding`) maps a DNA Cloud **billing account** to its current
`PricingPlan` — the billing→enforcement bridge.

**The subscription belongs to the account, not to a workspace.** One
`PlanBinding` covers *every* workspace whose `Workspace.account_id` matches, so
creating a second workspace is never a second charge and needs no billing write
at all. The account is an opaque id recorded on the workspace at creation from
the caller's verified account claim — whatever the IdP block's `tenant_claim`
names (Entra `tid`, WorkOS/Clerk/Auth0 `org_id`, Google Workspace `hd`). No new
entity: it is the same string the billing portal and the Stripe customer already
key on.

DNA Cloud's Stripe webhook writes the doc on subscribe / cancel
(`PUT /v1/account-plan`); the MCP server resolves **workspace → `account_id` →
plan** (`kernel.account_for_workspace` then `kernel.account_plan`) when the token
carries no explicit `plan` claim. A workspace with no resolvable account falls to
the **Free floor** — fail-closed, never another account's plan and never a paid
default. Zero Stripe or billing code lives in the OSS SDK; it only reads the
assignment.

`PlanBinding` replaces the retired per-workspace `WorkspacePlan`, which is now a
write-block tombstone in `Kernel._REMOVED_KINDS`. Keying the plan per workspace
forced whoever owned billing to fan out one doc per workspace, and workspace
enumeration is by *membership*, not ownership — so a workspace somebody else
founded and invited you into would have been swept into that fan-out and handed a
plan the account never bought. Re-keying on the account removes the question
instead of answering it: one write, one truth. (Renamed from `AccountPlan` in
0.29.0; the `_lib` storage container stays `account-plans/<account_id>.yaml` and
the REST op stays `PUT /v1/account-plan`.)

## Intelligence layer

The `intel` extension is the data foundation for the DNA's intelligence layer
(automated research → ranked insights → feedback). It ships two record Kinds,
both `TENANTED` — they hold a tenant's own portfolio data, not a shared `_lib`
default, and are deliberately not inheritable.

### IntelSource

An [`IntelSource`](../reference/kinds/record.md#intelsource) (`intel-source`)
is a watched portfolio source — the Direction stage of the pipeline: what the
DNA observes. One doc per source (a `repo`, a `scope`, or an `external` URL)
declares its research `cadence` (manual / event / daily / weekly), an
actionability `threshold` below which insights are suppressed, its Priority
Intelligence Requirements (`pirs` — focus areas that get prioritized), and a
`muted` flag to pause research without deleting the source.

### IntelInsight

An [`IntelInsight`](../reference/kinds/record.md#intelinsight)
(`intel-insight`) is the dissemination unit — a ranked, actionable insight
produced from an `IntelSource` that the ranker, digest, dedup and feedback
stages all reference. It carries a `title`, the cited `fact`, an optional
`why` / `action`, an actionability `score` the ranker sets, matched `pirs`,
`citations`, an `evidence_rating`, and a feedback `state` (new / actioned /
dismissed / snoozed). It is embeddable (`title` + `fact`) so a later dedup
stage can recall semantically similar insights. Named `IntelInsight` rather
than `Insight` because the bare `Insight` name already belongs to the SDLC
oracle Kind.

## Portfolio console

The `portfolio` extension is the data foundation for the DNA Cloud portfolio
console — the enterprise multi-tenant model of
[`adr-portfolio-project-model`](../reference/kinds/record.md). It ships five
record Kinds, all `TENANTED` (per-tenant portfolio data, not a shared `_lib`
default, and deliberately not inheritable). The shape follows the Azure DevOps
container model: an Organization owns Projects, a Project is a multi-repo
container that owns its board + intel + memory, and RBAC is a standard role
ladder.

### Organization

An [`Organization`](../reference/kinds/record.md#organization)
(`portfolio-org`) is the tenant's own org profile — the enterprise-familiar
top-level container (as in GitHub / Azure DevOps) whose portfolio of Projects
the console aggregates. It carries a `name`, a URL-safe `slug`, an optional
`display_name`, and a `plan_ref` annotation naming a DNA Cloud `Tier` the org
is on. One Organization per tenant; it is distinct from the platform-level
`Tenant` provisioning-identity Kind (the editable profile *inside* the tenant's
portfolio, not the global identity row).

### Project

A [`Project`](../reference/kinds/record.md#project) (`portfolio-project`) is
the key Kind — the multi-repo development-space container. It owns a SDLC
`board_scope` (convention `<slug>-development`), the `intel_source_refs` the
intelligence layer observes, and scoped memory, and it is the permission
boundary. Repos are attached **by reference** via `repo_refs` — an N—N edge
kept on the Project side, so a repo can belong to many Projects without
duplication. A Project has a `visibility` (private / shared) and an `org_ref`
to its Organization.

### Repo

A [`Repo`](../reference/kinds/record.md#repo) (`portfolio-repo`) is a code
repository the portfolio references — its `name`, `url`, `provider` (github /
gitlab / azure-devops / other) and `default_branch`. It is attached to N
Projects via `Project.repo_refs`; a Repo carries **no** project back-ref, so
the N—N edge has a single source of truth (the Project) and a shared repo is
never duplicated. "Which projects use this repo" is a query over Projects, not
a stored reverse list.

### Membership

A [`Membership`](../reference/kinds/record.md#membership)
(`portfolio-membership`) is the RBAC join — a `user`'s `role` at an org- or
project-scope (`scope_type` + `scope_ref`). The role is the standard ladder
(owner > admin > member > guest); resolution is highest-role-wins across a
user's memberships, with the org owner a superuser. It carries an invitation
`status` (invited / active). It is distinct from the platform-level
`TenantMembership` (which links a user to a provisioning `Tenant`); this grants
access inside the tenant's own Organization / Project graph.

### Role

A [`Role`](../reference/kinds/record.md#role) (`portfolio-role`) is one rung of
the RBAC ladder expressed as **data** (the DNA thesis: everything declarative)
— its `role_id`, `display_name`, `rank` (higher = more access), the
`capabilities` it grants, and a `can_delete` flag protecting built-in rungs.
Modelling the ladder as data (not a hardcoded enum) makes it extensible: a
tenant can add a custom role without a code change, and highest-role-wins
simply compares `rank`. The four standard rungs (owner / admin / member /
guest) ship as per-tenant seed docs under
`examples/dna-cloud/.dna/.../roles/`.

## Provenance — the original behind a derived instance

Some instances are not authored, they are **extracted**. A file arrives, an
agent reads it, and writes typed instances from what it found. Those instances
are a *projection*: lossy, interpreted, and — on their own — an assertion
nobody can check. `SourceArtifact` is what makes the claim testable.

### SourceArtifact

A [`SourceArtifact`](../reference/kinds/record.md#sourceartifact)
(`artifact-source`) records the original a projection came from: the `sha256`
of its bytes, a `uri` naming where they live, and `derived_refs` — the typed
instances extracted from it.

Three properties are worth understanding before you use it, because each is a
deliberate choice rather than an obvious one.

**The `sha256` is the point, not bookkeeping.** Without a content address,
"this instance was derived from that file" is unfalsifiable — and an
unfalsifiable provenance claim is worth less than no claim at all, because it
invites a trust it has not earned. With one, anyone holding the bytes can
verify the pairing, and re-uploading identical content is recognisably the
*same* artifact rather than a second one.

**The edge points from the artifact to its derivations**, never the reverse.
The obvious shape would be a `source_ref` field on each extracted instance, and
it fails twice: an agent composing schemas would have to remember that field
every time (and Kinds nobody authored have nowhere to put it), and one upload
commonly yields many instances — a PDF holding twelve invoices should state
"these came from one file" once, not twelve times.

**The `uri` is an identity, never a credential.** It names where the bytes
live; it does not grant access to them. A signed URL stored here would make the
instance itself the capability — copy the instance, copy the access. The schema
is closed (`additionalProperties: false`) precisely so a token cannot be
attached beside it, and a host is expected to serve artifact reads through an
authenticated route that checks the caller's membership first.

The Kind is deliberately vendor-neutral: where the bytes actually live is a
deployment's own concern (a blob store in a hosted product, a directory in a
self-host), and the kernel treats `uri` as opaque so that stays true.

### KnowledgeChunk

Extraction is one thing a file can become. **Retrieval** is the other: a passage
of the original, kept so an agent can find it and quote it. A
[`KnowledgeChunk`](../reference/kinds/record.md#knowledgechunk)
(`artifact-knowledge-chunk`) is one such passage — the text, the collection it
belongs to, and the `SourceArtifact` it came from.

**A chunk is an instance, and that is the whole design.** Everything a corpus
needs already exists for instances: `embed:` makes the text searchable, tenancy
isolates one workspace's corpus in the index rather than at the door, and the
search door already returns an envelope that says whether the semantic plane
actually ran. A parallel document store would have had to re-earn each of those,
and would have put the corpus outside the Kind system — no version, no tenancy,
no relation back to the file it came from.

**A collection is a name prefix.** Instance names are structured
(`<collection>.<sha12>.<ordinal>`), so a corpus partitions without a new column
and without a Kind per collection. The narrowing is applied where the search
provider *chooses* candidates, never to the list it already chose — both planes
over-fetch a fixed number of rows, so a post-filter would let one voluminous
collection fill that budget and crowd every other row out while the envelope
still reported a healthy hybrid search.

The separator is a dot, and both halves of that choice were measured rather than
picked. An instance name is written to disk as a *single path component*, so
`validate_instance_name` refuses a `/` before any adapter is reached — the
format was `<collection>/<sha12>/<ordinal>` until ingestion tried to write one
and could not. And the separator has to sit *outside* the alphabet a collection
name may use (`[a-z0-9-]`), or the prefix of `handbook` would sweep up every
chunk of `handbook-2024` — which is exactly the leak the trailing separator
exists to prevent.

**A chunk is produced, never authored.** `dna.application.knowledge`'s
`ingest_knowledge_impl` takes *already-extracted Markdown* plus the `sha256` of
a registered `SourceArtifact`, cuts it with
[chonkie](https://github.com/feyninc/chonkie), and writes one instance per
passage. Bytes stop at the host on purpose: `uri` is opaque by contract, so a
vendor-neutral SDK that could resolve `blob://` would have to know about
credentials, and the byte→Markdown converter is the host's dependency already.
The chunk's provenance (`source_uri`, `source_filename`) is read *from the
artifact instance*, never accepted from the caller — a citation the caller could
dictate is not evidence.

Re-ingesting the same file rewrites the same instances, because the name is
derived from the content address. Re-ingesting it with a *different* cut is the
case that needs help: fewer passages leave the surplus ordinals behind, in the
store and in the index, where a search would return them as text from a dead
version of the document. The port prunes them — through the kernel directly,
which is the path `record.append-only` deliberately leaves open for a
purpose-built verb, exactly as `forget` retires an Engram.

**It is embeddable but NOT `memory.recallable`**, and the distinction is the one
that trait exists for. `memory.recallable` means a Kind participates in the
memory verbs — retention decay, affect weighting, reconsolidation on recall. A
passage of a document does not decay, has no affect, and does not change for
having been read: it is what the file says. Declaring the trait would have put a
corpus — voluminous by construction — into `recall` beside a person's Engrams,
ranked by properties it does not have. `embed: [text]` is what makes it
findable; a caller who wants the corpus asks for it by name.

**Only `text` is embedded.** Without that restriction the indexed body would
collect *every* string on the instance — the sha256 in hex, the collection name
repeated on every chunk — and push that noise into both the vector and the
full-text index. A hex digest is not language, and a collection name repeated
across a whole corpus makes a search for that name match all of it.

⚠️ Retrieval over a corpus **ranks; it does not filter**. DNA ships no relevance
floor, because on a real corpus none separates the relevant from the irrelevant
(the measurement is in `dna.kernel.query.relevance`). So a chunk comes back with
its score and its source, and a caller presenting chunks to a person or a model
is expected to pass both along rather than assert on their strength.

## Delegation — the Agent Card of a remote agent

[A2A](https://a2a-protocol.org/) (Agent2Agent, governed by the Linux
Foundation) standardized exactly the thing DNA already treats as an instance: a
self-describing capability descriptor. The A2A *protocol* — the JSON-RPC/gRPC
call, the task lifecycle — is transport, not an instance, and stays out of the
Kind system entirely. What A2A calls the **Agent Card** — the descriptor a
server publishes at `/.well-known/agent-card.json` naming who it is, what it
can do, and where to reach it — is exactly instance-shaped, and `RemoteAgent`
is it.

### RemoteAgent

A [`RemoteAgent`](../reference/kinds/record.md#remoteagent)
(`a2a-remote-agent`) is the Agent Card of a third-party A2A agent, held as a
DNA instance: `name`, `description` and `supported_interfaces` (the A2A 1.0
interface list — each entry a `protocol_binding` of `JSONRPC` / `GRPC` /
`HTTP+JSON` with its own `url`, plus an optional `protocol_version`)
come straight from the A2A spec in snake_case; `skills`, `capabilities` and
`security_schemes` describe what it can do and how to authenticate to it.

It is deliberately a **separate** Kind from `Agent` rather than a mode of it.
The two Kinds' fields are disjoint: `Agent` declares *behaviour* (instruction,
model, tools) that DNA composes and executes; `RemoteAgent` *describes and
points* (interfaces, skills, security schemes) at something DNA locates and
calls over the network. A single Kind carrying both would let a local agent
declare `security_schemes` and a remote one declare `instruction`, which is
exactly the kind of nonsense a closed schema cannot express as "these fields OR
those." What the two Kinds *share* is `delegation_target_for` — the block that
lets a supervisor's roster of delegation targets span both a local `Agent` and
a remote `RemoteAgent` by asking "who declared this block, and does their
allowlist include me?" rather than by enumerating Kinds.

Three properties are worth understanding before you register one:

**`data_scope` is required, and it is DNA's own field, not A2A's.** A
`RemoteAgent` is, by construction, an exfiltration channel: registering one
means DNA will send workspace data to a URL the tenant chose. A2A has no
opinion on that — it is transport protocol. So the scope of what may be sent
is ours, mandatory, and explicit: `data_scope.kinds` names which Kinds'
instances this endpoint may receive. An implicit scope would mean "everything,"
and nobody approves that knowingly — an empty list is the honest "registered,
but permitted to receive nothing," not an error.

**The schema is closed.** `additionalProperties: false` exists so a credential
— a bearer token, an API key — cannot be smuggled into the instance alongside
`security_schemes` (which only says *how* to authenticate, never *with what*).
An instance that could carry its own access token would let anyone who can read
it also call the endpoint with it, the same reasoning that keeps
`SourceArtifact` closed.

**`signature_state` is tri-state on purpose.** A Card that arrives unsigned is
`unsigned`; one that carries an A2A `signatures` block is `present_unverified`
— cryptographic verification of that signature is out of scope for this
version, because it requires deciding a trust chain (whose signatures count?),
which is a product decision, not a schema one. `verified` is reserved for when
that lands. A plain boolean `signed` would make "we didn't check" look
identical to "there was nothing to check," and those are different states a
reviewer needs to be able to tell apart.

### AgentGrant

A [`AgentGrant`](../reference/kinds/record.md#agentgrant) (`a2a-agent-grant`) is
the **inbound twin** of `RemoteAgent`, and the two only make sense as a pair:

| | says |
|---|---|
| `RemoteAgent` | *we may send data over there* |
| `AgentGrant` | *they may act on our behalf* |

A third party's agent — Claude, an integration, a partner's automation — arrives
holding a token of **one of your users**, and acts as that user. Whether it may
is not a property of the token: a valid token only proves the user signed in.
Without a grant, "the user authorized Acme" and "the user is logged in" are the
same statement, and a permissions screen built on that would display a
permission that does not exist.

**Three properties carry the design.**

**`state` is tri-state** — `pending`, `active`, `revoked` — for the same reason
`RemoteAgent.signature_state` is. A boolean `granted` would make *"it asked and
nobody decided"* look identical to *"denied"*, and those are different: the first
needs to surface on a screen so a human can decide; the second was already
decided and asks for nothing.

**What was REQUESTED and what was GRANTED are separate fields.**
`requested_scope_kinds` is what the agent asked for; `scope_kinds` is what a
human allowed. One field would make asking equal to receiving. An agent that
declares nothing leaves the request empty and nothing is pre-selected — silence
never becomes permission, not even a suggestion of one.

**Everything that is not `active` closes.** Absent, pending, revoked,
malformed and *unrecognised* all deny. The allowed list has exactly one entry
and the rest is the rest — a gate written the other way around (denying what it
recognises) would open for whatever it does not, including a state some future
version adds, and it would open silently.

`scope_kinds` speaks the same vocabulary as `RemoteAgent.data_scope.kinds` on
purpose: it is the same question in both directions, and answering it in two
different shapes would be a trap for whoever reads them side by side.

The instance never carries a credential — the schema is closed precisely so a
token cannot be attached to a grant. Who may act, and over what, lives here; the
secret they authenticate with belongs to the deployment.

### AgentCatalogEntry

An [`AgentCatalogEntry`](../reference/kinds/record.md#agentcatalogentry)
(`a2a-agent-catalog-entry`) gives a **human-readable name to an agent whose
`client_id` is opaque** — and it is deliberately the *lesser* half of agent
identity.

The primary mechanism is **CIMD** (Client ID Metadata Instances): the `client_id`
IS an HTTPS URL serving the client's metadata, so the name can only be declared
at `acme.com` by whoever controls `acme.com`, and DNS plus TLS already prove
that. It is the browser padlock's mechanism — you do not trust the text, you
trust where it came from.

This Kind covers what CIMD cannot: legacy clients with opaque ids, which publish
no metadata and which nothing can anchor.

**Two rules keep the difference visible, and both are structural.**

`client_id` **may not be an HTTPS URL** — the schema refuses it. A client that
publishes metadata already has an anchored identity, and letting someone type a
name over it would swap proof for typing. That swap is exactly the mistake an
earlier design made without noticing: it said *"the name must come from whoever
verified"* and then proposed that the verifier be a person filling in a form.
Typing is not verification; it protects against the caller lying, not against
the registrar being wrong or deceived.

`registered_by` is **required**, because it is what makes the label possible. A
consent screen can honestly say *"Sprint Assistant · registered by Maria"* — a
sentence the user can weigh. *"Sprint Assistant"* alone, on an opaque id, is a
claim nobody stands behind; sitting next to an anchored name, it teaches the
reader to trust both the same way.

The entry **names, it does not authorize**. There is no scope, no state, no
grant field: authorization lives in `AgentGrant`, and registering an agent in a
catalog must never be a path to granting it access.

---

Run `dna kind list` for the live registry in your install, and `dna kind
describe <Kind>` for the exact schema the write boundary enforces — the
[CLI tour](../guides/cli-tour.md) shows both in action.
