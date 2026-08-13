# `dna new`

Scaffold a valid skeleton into a scope — an INSTANCE (agent | soul | guardrail | tool), or a KIND of your own (kind).

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna new --help`.

## `dna new agent`

Scaffold an Agent bundle (agents/<name>/AGENT.md) — fill in the instruction.

The skeleton is a VALID Agent from the first write: correct envelope, a
placeholder instruction body, and any --soul/--guardrails/--layout/--model
wiring pre-filled. With --layout you order persona-vs-instruction by name
and never hand-write Mustache.

Examples:


  dna new agent triage
  dna new agent concierge --soul warm-host --layout persona-first
  dna new agent reviewer --guardrails safety,review-ethics --model openai:gpt-4o

```text
dna new agent [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--description`, `-d` | One-line description. |
| `--force` | Overwrite an existing agent. |
| `--guardrails` | Comma-separated Guardrail names to attach. |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--layout` | Named composition layout (s-dx-named-layouts) — 'persona-first' puts the Soul before the instruction. Omit for the default. |
| `--model` | Model id (e.g. openai:gpt-4o-mini). |
| `--scope` | Scope to write into (default: env / sole scope). |
| `--soul` | Name of a Soul doc to compose in. |

## `dna new guardrail`

Scaffold a Guardrail bundle (guardrails/<name>/GUARDRAIL.md).

Example:


  dna new guardrail no-pii --severity error --guard-scope output

```text
dna new guardrail [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--description`, `-d` | One-line description. |
| `--force` | Overwrite an existing guardrail. |
| `--guard-scope` | Which side the guardrail runs on. _(default: `both`)_ |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--scope` | Scope to write into (default: env / sole scope). |
| `--severity` | warn lets the turn continue; error fails it. _(default: `warn`)_ |

## `dna new kind`

Author a KIND of your own — a typed instance shape, INERT until approved.


The one command in this group that creates a Kind rather than an instance of
one. `dna new kind Contrato` is enough: the name and, ideally, one line saying
what it is. Everything else — the apiVersion namespace, the alias, the storage
container, the plane — is derived or defaulted, and nothing that can be derived
is asked for.


What lands is a real, auditable `KindDefinition` instance with NO approval
marker, so it validates nothing and routes nothing until a human approves it.
Re-running for the same Kind EDITS the declaration and drops the approval,
which is why --force is required for the second run.


Examples:
  dna new kind Contrato -d "Um contrato assinado com um cliente"
  dna new kind Contrato -f 'titulo:string!=O titulo' -f assinado_em:string
  dna new kind Apolice --relation 'contratos=Contrato:many'
  dna new kind Contrato --dry-run


--field is `NAME[:TYPE][!][=DESCRIPTION]`; the trailing `!` marks it required
and the type defaults to string. --relation is `FIELD=KIND:CARDINALITY`, or the
full form `FIELD={to: Contrato, cardinality: many, inverse_of: apolice}` whose
keys are the declaration's own. A relation whose field you did not declare gets
one.


``traits`` (optional) declares WHAT YOUR KIND IS — the roles it takes part
in. It is the other axis from ``relations``: relations say what your Kind
POINTS AT, traits say what it *is*. A Kind that declares neither is findable
by name and answers no question about itself.


A trait is not a label. Declaring one opts your Kind into everything that
reads that role — a digest, a gallery, a board lane, a refusal — and a trait
that CARRIES brings its fields and its relations with it, so you declare
them once here instead of restating them in ``schema``. The vocabulary is
OPEN; this is what is registered on THIS server right now, and ``[carries
...]`` is what comes with the name:


    execution.declared
        Declares work a RUNNER executes, and is only ever the script — never
        the outcome. A TestGuide's steps, an EvalSuite's cases, an
        Automation's trigger and runner: the instance says what should
        happen, a host executes it, and what happened is written somewhere
        else (see `execution.run`). The pair is the structural difference
        that earns both names — a Kind on this side may be edited freely
        because it makes no claim about the past.
    execution.run
        The record of ONE execution of an `execution.declared` instance:
        when it ran, what it ran against, and what came out. It is a claim
        about the past, which is what separates it from the declaration it
        executed — a run that turns out to be wrong is not corrected, it is
        superseded by another run. Every member points back at its
        declaration, by a differently-named field, which is why this trait
        carries no relation.
    governance.policy
        Declarative rules an ENFORCEMENT POINT reads at runtime — not prose
        for a human, and not configuration in the ordinary sense. Editing
        one changes what the system refuses, immediately, with no deploy.
        That is the behavioural commonality: a policy instance is read by a
        guard, a scanner, an overlay resolver or a decay function, never by
        somebody wanting to know what happened. It is also why
        `record.append-only` is wrong for them and right for a run: a policy
        is MEANT to be rewritten.
    governance.spec-traced
        A write of this Kind must trace to a Spec when the scope's
        constitution demands it (the spec-kit governance guard).
    memory.recallable
        Participates in `recall` / `remember` / the memory index — the set
        the memory verbs search. DISTINCT from `embed:`, which declares
        WHICH FIELDS carry an embeddable payload: an ADR should be
        searchable without being decay-ranked as a memory.
    record.append-only
        An audit / evidence record: it may be WRITTEN and READ but never
        deleted through a generic tool. The record is what proves what
        happened, so deleting it is the first move of anyone with something
        to hide — and unlike a bad write, it is not recoverable by writing a
        better one.
    record.invalidate-only
        A bi-temporal record, RETIRED by stamping the end of its world-time
        validity (`valid_to`) and never by removing the row — so it stays
        auditable, point-in-time reconstructable and revivable. Two things
        separate it from `record.append-only`, and both matter: this one may
        be REWRITTEN freely (a recalled Engram is reconsolidated on every
        surfacing), and its refusal binds EVERY door rather than only the
        generic tool, because it is a promise about the row and not a rule
        about a tool. Enforced at the kernel delete chokepoint
        (`dna.kernel.write.hard_delete`), which names the Kind's own
        retirement verb in the refusal.
    record.is-evidence
        This Kind IS the evidence record, which the capture path must know
        so it does not capture evidence ABOUT evidence — an unguarded write
        of a captured record re-triggers the handler that wrote it. The
        trait exists as the declarative half of `record.produces-evidence`:
        without it the kernel would still need one hard-coded name to break
        the loop, and one hard-coded name is the whole problem in miniature.
        Expected to be declared by exactly one Kind per deployment, but
        deliberately not enforced as such — a tenant that runs its own
        evidence Kind alongside the built-in one is not doing anything
        wrong.
    record.produces-evidence
        Writing an instance of this Kind is an event worth CAPTURING as
        Evidence — the evidence handler reads the write and stamps the
        suite/source it came from. Distinct from `execution.run`, which says
        the instance IS the record of an execution: a run is evidence-worthy
        because it is a claim about the past, but a Kind may be
        evidence-worthy without being a run (a baseline is pinned, not run).
        Capture is still gated by the scope's EvidencePolicy — this trait
        says the Kind is ELIGIBLE, never that capture is on.
    sdlc.dated
        Carries `created_at` AND `updated_at`: a read surface dates, sorts
        or windows it by both.
    sdlc.dated-create-only
        Carries `created_at` but has no `updated_at` arc — an observation is
        dated when it is made and does not move.
    sdlc.decision
        A recorded decision (ADR). Walked by the digest and the gallery, and
        it may produce outputs, but it is not assigned and does not
        progress.
    sdlc.exit-criteria-required
        A create of this Kind is REFUSED without acceptance criteria and a
        definition of done — a work item that does not declare what `done`
        means cannot be shown to be done.
    sdlc.filed
        Enters the board by being FILED rather than planned — the digest's
        `found` bucket (Issue, Kaizen). Deliberately implies NOTHING: Kaizen
        is filed and is not a work item, so the two do not travel together.
    sdlc.journey-derived
        Its journey phases are derived locally from its own spec + timeline
        (no WorkflowEvent ledger read).
    sdlc.observation
        A filed observation (Kaizen) — noticed, not planned. Reaches the
        digest's `found` bucket; carries no `updated_at` arc.
    sdlc.rollup  [carries implies sdlc.work-item]
        A work item that AGGREGATES other work items (Feature / Epic /
        Initiative). Movement at this level is roadmap movement, which is
        what the digest's `parents_progressed` bucket reports. IMPLIES
        `sdlc.work-item` — a thing that rolls work items up is one.
    sdlc.test-gated
        A CLOSE of this Kind is REFUSED without a passing product-lane
        TestRun verifying it. The escape hatches require a reason and land
        on the timeline.
    sdlc.work-item  [carries implies sdlc.dated]
        A board item with a status arc, a timeline and an owner — the thing
        a person is assigned and closes. Participates in the digest, the
        gallery, status transitions and comments. CARRIES the work-item
        activity fields (`timeline`, `produces`) and the `produces`
        relation, so a work item does not restate either; IMPLIES
        `sdlc.dated`.
    tenancy.access-grant
        A row that GRANTS access: a subject, a scope it reaches, and the
        level it reaches it at. Read by an authorization decision — which is
        the whole role, and the reason the set has to be enumerable rather
        than inferable. Revoking is editing (or expiring) a row, so these
        are deliberately NOT append-only. Distinct from the Kind that
        DEFINES the ladder rather than granting a rung of it: a role
        definition is a catalogue entry, not a grant, and conflating the two
        would make "who can reach this?" return the vocabulary instead of
        the answer.


Declaring nothing is a legitimate answer and is never refused: a Kind that
takes part in none of these roles is a statement, not a gap. What is not an
answer is reaching for the nearest name — a role declared and not exercised
is worse than one absent, because it also LOOKS like a declaration.

```text
dna new kind [OPTIONS] KIND_NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `KIND_NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--description`, `-d` | What this Kind IS, in one line — becomes the schema's own `description`. |
| `--dry-run` | Print the plan and write nothing. |
| `--field`, `-f` | `NAME[:TYPE][!][=DESCRIPTION]`. Repeatable; order is kept. |
| `--force` | Re-author an existing Kind. The declaration is REBUILT, not merged: a field you do not pass again is gone. The edit also drops the approval. |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--plane` | Omit unless you know which you mean — the difference is a cost, not a taste. Undeclared is NOT the same as declaring the default, and is stored as such. |
| `--presentation` | Comma-separated field order for how instances READ (the short form: 'name,titulo,situacao'). |
| `--relation` | FIELD=KIND:CARDINALITY, or FIELD={to: …, cardinality: …}. Repeatable. |
| `--scope` | Scope to author into (default: env / sole scope). |
| `--trait` | A role this Kind takes part in. Repeatable, OPTIONAL, and never required — the vocabulary is in this help, and in `dna kind traits`. |
| `--workspace`, `-w` | The workspace authoring this Kind (default: $DNA_TENANT). It owns the apiVersion namespace the Kind lands under. |

## `dna new soul`

Scaffold a Soul as a SINGLE SOUL.md file — no soul.json ceremony.

s-dx-single-file-soul: a Soul is authored from one SOUL.md; the
2-file soulspec.org format (SOUL.md + soul.json + companions) stays fully
supported for market fidelity, but the common case is a single file.

Example:


  dna new soul warm-host -d "Patient, warm, concise concierge voice"

```text
dna new soul [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--description`, `-d` | One-line description. |
| `--force` | Overwrite an existing soul. |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--scope` | Scope to write into (default: env / sole scope). |

## `dna new tool`

Scaffold a Tool descriptor (tools/<name>.yaml) — tools as data.

A Tool moves the agent-facing surface of a tool into the declarative plane:
the ``description`` the model reads (metadata.description) + the
``input_schema`` of its arguments (surfaced as ``parameters`` by
``dna.load_tools`` / ``loadTools``). The skeleton is a VALID Tool from the
first write, with a placeholder single-arg ``input_schema`` to edit.

Examples:


  dna new tool generate-artifact -d "Render HTML/Markdown into a shareable artifact."
  dna new tool github-search --type http -d "Search GitHub code."

```text
dna new tool [OPTIONS] NAME
```

**Arguments**

| Argument | Required |
| --- | --- |
| `NAME` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--description`, `-d` | Agent-facing description — the text the model reads to decide whether to call the tool (goes in metadata.description). |
| `--force` | Overwrite an existing tool. |
| `--help` | Show this message and exit. |
| `--json` | Machine-readable output. |
| `--scope` | Scope to write into (default: env / sole scope). |
| `--type` | Invocation type. builtin \| http \| mcp \| python \| shell. _(default: `builtin`)_ |

