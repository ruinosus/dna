# Emitting to a runtime (the de-para)

DNA describes an agent **once** — a persona (`Soul`), an instruction (`Agent`),
wired `Guardrail`s, and `Tool`s — as declarative Kinds. `dna emit` **materializes
that one neutral definition into the native artifact a target runtime consumes**.
Author once; emit per runtime; swap runtimes without rewriting the agent. This is
the first concrete step of *"DNA as the Terraform of agents"*.

> **de-para** (Portuguese *"from-to"*): a field-by-field mapping from a source
> shape to a target shape — not a string dump.

## The one command

```console
$ dna emit --list-targets
Registered emit targets:
  - agent-framework
  - bedrock

$ dna emit concierge --target agent-framework --scope concierge
kind: Prompt
name: Concierge
description: Internal engineering support concierge grounded in runbooks.
model:
  id: gpt-4o
  provider: AzureOpenAI
tools:
- name: kb-search
  kind: function
  description: Search the runbook knowledge base ...
  parameters:
    type: object
    required: [query]
    properties: { query: { type: string, ... }, top_k: { type: integer, ... } }
instructions: |-
  You are the Helpdesk Concierge ...

  Answer using the runbook knowledge base.

  ## Guardrail: grounded-citation (error)
  ...
```

The emitted artifact is exactly what Microsoft **agent-framework**'s
`AgentFactory` loads (`create_agent_from_yaml`). Write it to a file with `-o`:

```console
$ dna emit concierge -t agent-framework --scope concierge -o concierge.agent.yaml
```

The example scope above ships in the repo:
[`examples/emitting-to-a-runtime`](https://github.com/ruinosus/dna/tree/main/examples/emitting-to-a-runtime).

## The de-para — agent-framework (`kind: Prompt`)

| DNA (source of truth) | agent-framework PromptAgent | Notes |
|---|---|---|
| `metadata.name` | `name` | CamelCased (`concierge-grounded` → `ConciergeGrounded`) |
| `metadata.description` | `description` | verbatim |
| **`Soul` + `Guardrail`s + `Agent.instruction`** (composed by `build_prompt`) | `instructions` | **flat string** — the composition is done at author time; the emit carries the result **byte-equal** |
| `Agent.spec.model` → else `Genome.spec.default_llm` | `model.{id, provider}` | `openai:gpt-4o-mini` / `azure/gpt-4o` / bare → split; `--model`/`--provider` override |
| `Agent.spec.tools[]` → `Tool` Kind surfaces | `tools[]` (`kind: function`) | each Tool's `metadata.description` + `spec.input_schema` (as `parameters`) |
| `Agent.spec.output_schema` | `outputSchema` | only when present |

### What does **not** survive — and why that is the point

For a single agent, a native framework is genuinely clean. DNA earns its keep on
the axes the emit **drops** — so the emitter reports them honestly (on stderr, and
in `--json` under `losses`), never hand-waves them:

- **Composition structure.** `Soul` reuse and a `Guardrail` wired as its own
  document collapse to one flat `instructions` string. A PromptAgent has no
  `soul:`/`guardrails:` slot — so two agents that *share* a Soul in DNA would each
  carry a **copied** persona in their emitted YAML (edit-in-two-places drift). The
  structure is a DNA authoring-time concept.
- **Tenant overlay.** A per-tenant persona *without a fork* — no PromptAgent field.
- **Eval-as-contract.** Prompt invariants asserted as `EvalCase`s — no slot.

These are the reasons the neutral layer exists. The emit is faithful about the
trade-off so you can see exactly what you keep by authoring in DNA.

## The de-para — Amazon Bedrock (`AWS::Bedrock::Agent`)

The **second** proven target. The **same** `concierge` source emits an AWS
**CloudFormation** template declaring an `AWS::Bedrock::Agent` — the managed,
declarative Bedrock Agents service. Two runtimes from one definition is the whole
point: *author once, emit per runtime*.

```console
$ dna emit concierge --target bedrock --scope concierge
{
  "AWSTemplateFormatVersion": "2010-09-09",
  "Description": "DNA-emitted Amazon Bedrock Agent: concierge",
  "Resources": {
    "ConciergeAgent": {
      "Type": "AWS::Bedrock::Agent",
      "Properties": {
        "AgentName": "concierge",
        "Description": "Internal engineering support concierge grounded in runbooks.",
        "FoundationModel": "gpt-4o",
        "Instruction": "You are the Helpdesk Concierge ...",
        "ActionGroups": [
          {
            "ActionGroupName": "concierge-actions",
            "ActionGroupExecutor": { "CustomControl": "RETURN_CONTROL" },
            "FunctionSchema": {
              "Functions": [
                { "Name": "kb-search", "Description": "Search the runbook ...",
                  "Parameters": { "query": { "Type": "string", "Required": true }, ... } }
              ]
            }
          }
        ],
        "AutoPrepare": true
      }
    }
  }
}
```

**Why Bedrock *Agents* (not Strands / AgentCore).** AWS ships three agent
surfaces: **Bedrock Agents** (a managed service with a published *declarative*
schema), **Strands Agents SDK** (code-first Python), and **Bedrock AgentCore** (a
runtime that *hosts* any framework). Only Bedrock Agents has a field-for-field
declarative schema, so it is the only honest de-para target — and emitting it as a
**CloudFormation** template yields a lintable, deployable artifact you can produce
and validate **without any AWS credential** (`cfn-lint <file>`).

| DNA (source of truth) | Bedrock `AWS::Bedrock::Agent` | Notes |
|---|---|---|
| `metadata.name` | `Resources.<Id>Agent.Properties.AgentName` | logical id is CamelCased + `Agent` |
| `metadata.description` | `Properties.Description` | verbatim (when present) |
| **`Soul` + `Guardrail`s + `Agent.instruction`** (composed by `build_prompt`) | `Properties.Instruction` | **flat string** — carried **byte-equal** (identical to the agent-framework `instructions`) |
| `Agent.spec.model` → else `Genome.spec.default_llm` | `Properties.FoundationModel` | DNA provider token stripped (`azure/gpt-4o` → `gpt-4o`); a Bedrock-native id / `arn:` passes through untouched |
| `Agent.spec.tools[]` → `Tool` Kind | `Properties.ActionGroups[0].FunctionSchema.Functions[]` | one action group, one `Function` per tool; executor `CustomControl: RETURN_CONTROL` (client-side tools, no Lambda) |
| `Tool.spec.input_schema.properties` | `Function.Parameters{ Type, Description, Required }` | flat map; `Type` ∈ `string\|number\|integer\|boolean\|array` |

### What does **not** survive — Bedrock-specific

On top of the three DNA-only axes above (composition structure / tenant overlay /
eval-as-contract), the Bedrock target also drops:

- **Tool parameter depth.** Bedrock `ParameterDetail` is a flat
  `{Type, Description, Required}`; JSON-Schema `default`, `enum`, nested object
  `properties`, and array `items` typing have no slot (a non-scalar type is
  flattened to `string`).
- **`output_schema`.** Bedrock Agent has no structured-response field.
- **Model coordinate.** A DNA `azure/openai` coordinate is **not** a Bedrock
  foundation-model id; a real deploy needs a Bedrock model id / inference-profile
  ARN (pass `--model`) plus an `AgentResourceRoleArn`.

## The proof: it round-trips into the live runtime

The emitted `instructions` is **byte-equal** to `mi.build_prompt(agent)`, and the
artifact loads into a live agent-framework `Agent`:

```python
from dna import emit_agent_from_scope
from agent_framework_declarative import AgentFactory   # pip install agent-framework-declarative

result = emit_agent_from_scope("concierge", "concierge", "agent-framework",
                               base_dir="examples/emitting-to-a-runtime/.dna")
agent = AgentFactory().create_agent_from_yaml(result.artifact)   # live Agent
```

The test `test_emitted_yaml_loads_into_agent_framework` proves this end-to-end;
it `importorskip`s the runtime, so the suite stays green where .NET/agent-framework
is not installed.

## Using it from the SDK

`dna emit` is a thin wrapper over the `dna.emit` package. Both Python and
TypeScript expose the same surface (the pure de-para is parity-checked; only the
YAML *rendering* differs between PyYAML and js-yaml):

```python
from dna import emit_agent, Kernel
mi = Kernel.quick("concierge", base_dir=".dna")
result = emit_agent(mi, "concierge", "agent-framework")   # -> EmitResult
result.artifact       # the PromptAgent YAML
result.losses         # what did not survive
result.mapping        # the field-level de-para
```

```ts
import { emitAgent, quickInstance } from "@ruinosus/dna";
const mi = await quickInstance("concierge", ".dna");
const result = await emitAgent(mi, "concierge", "agent-framework");
```

## Adding a new target (vertex / openai / …)

Targets are a **registry, not a hardcode** — a new one is a class + one call, and
the CLI core never changes. The two shipped emitters (`agent-framework`,
`bedrock`) are the reference; a third looks identical:

```python
from dna.emit import EmitContext, EmitResult, register_emitter

class VertexEmitter:
    target = "vertex"
    file_extension = "json"

    def emit(self, ctx: EmitContext) -> EmitResult:
        # ctx is the runtime-agnostic view: ctx.instructions (the composed
        # prompt), ctx.model, ctx.tools, ctx.description, ctx.output_schema.
        artifact = ...  # render the target's native artifact
        return EmitResult(artifact=artifact, target=self.target,
                          filename=f"{ctx.name}.json",
                          losses=[...], mapping={...})

register_emitter(VertexEmitter())
```

An emitter is **pure**: it reads the neutral `EmitContext` and returns an
`EmitResult` — no kernel I/O, no network (the high-level `emit_agent` does the
composition). That makes every target trivially unit-testable against a
hand-built context, and lets a host **override** a built-in target by registering
its own before first use.

> **Direct vs through-OAS.** Whether DNA should emit *directly* per runtime (as
> above) or *through* the Oracle Agent Spec (DNA → OAS → runtimes via OAS
> adapters) is decided in the `adr-dna-pivot-portability` ADR and grounded by the
> `rsh-agent-config-landscape-2026` research — both on the `dna-development` SDLC
> board (`dna sdlc adr show adr-dna-pivot-portability`).
