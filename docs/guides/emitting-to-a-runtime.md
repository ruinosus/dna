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
  - agno
  - bedrock
  - deepagents
  - langgraph
  - openai-agents
  - vertex

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

## The de-para — Google ADK (`LlmAgent` Agent Config)

The **third** proven target. The **same** `concierge` source emits a **Google
Agent Development Kit (ADK) Agent Config** YAML — the declarative, code-free way
to define an ADK `LlmAgent`, loaded with `config_agent_utils.from_config(<path>)`.
Three runtimes from one definition is the whole point: *author once, emit per
runtime*.

```console
$ dna emit concierge --target vertex --scope concierge
# yaml-language-server: $schema=https://raw.githubusercontent.com/google/adk-python/refs/heads/main/src/google/adk/agents/config_schemas/AgentConfig.json
agent_class: LlmAgent
name: concierge
description: Internal engineering support concierge grounded in runbooks.
model: gpt-4o
instruction: |-
  You are the Helpdesk Concierge ...
tools:
- name: kb-search
```

**Why the ADK *Agent Config* (not the code-first `LlmAgent` object or Vertex AI
Agent Engine).** Google ships two ADK authoring surfaces: **Agent Config** (a
*published, declarative* YAML schema — `agent_class`, `name`, `model`,
`instruction`, `tools`, …) and the **code-first** Python/Java `LlmAgent` object.
Only Agent Config has a field-for-field declarative schema, so it is the only
honest de-para target; **Vertex AI Agent Engine** is a *deployment host* that runs
an ADK agent, not a declarative agent definition of its own. Emitting the Agent
Config YAML yields a lintable artifact you can produce and validate **without any
GCP credential** — the emitted `# yaml-language-server` header binds the artifact
to the real published schema in any editor.

| DNA (source of truth) | ADK `LlmAgentConfig` | Notes |
|---|---|---|
| *(fixed)* | `agent_class: LlmAgent` | the declarative LLM agent class |
| `metadata.name` | `name` | snake_cased — ADK requires a valid Python identifier (`concierge-grounded` → `concierge_grounded`) |
| `metadata.description` | `description` | verbatim (when present) |
| **`Soul` + `Guardrail`s + `Agent.instruction`** (composed by `build_prompt`) | `instruction` | **flat string** — carried **byte-equal** (identical to the agent-framework `instructions` and the Bedrock `Instruction`) |
| `Agent.spec.model` → else `Genome.spec.default_llm` | `model` | Gemini id; DNA provider token stripped (`vertex/gemini-2.0-flash` → `gemini-2.0-flash`); a bare id passes through |
| `Agent.spec.tools[]` → `Tool` Kind | `tools[].name` | a **code reference** (`- name: <fqn>`); ADK has no inline function-schema slot |

### What does **not** survive — ADK-specific

On top of the three DNA-only axes (composition structure / tenant overlay /
eval-as-contract), the ADK target also drops:

- **Tool binding shape.** ADK binds a tool by a **code reference** — a fully
  qualified Python path (`my_pkg.my_tools.my_tool`) or a built-in name
  (`google_search`) — **not** a declarative schema. A Tool's `description` and
  `parameters` (JSON Schema) have no Agent Config slot; ADK derives them from the
  referenced Python function's signature + docstring at load. Each emitted
  `- name` is a **placeholder** to repoint to the tool's real FQN.
- **`output_schema`.** ADK `output_schema` is a `CodeConfig` (a reference to a
  Pydantic class by FQN), not an inline JSON Schema — DNA's inline
  `spec.output_schema` has no inline slot.
- **Model coordinate.** ADK `model` natively accepts a **Gemini** id; a DNA
  `azure/openai` coordinate needs `model_code` (a `LiteLlm` `CodeConfig`) at
  deploy, plus a GCP project/region.

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

## The de-para — OpenAI Agents SDK (code-first scaffold)

The **fourth** target is the first **code-first** one. The OpenAI Agents SDK has
no declarative agent file — you construct an `Agent(...)` in Python — so the
emitter produces *source code* by filling a curated template (a **scaffold**),
not a schema. The composed prompt is emitted as a byte-equal `INSTRUCTIONS`
constant; the emitter selects a `{framework × case}` template from the DNA
signals (an agent with tools → the tool-calling idiom; without → prompt-only):

```console
$ dna emit concierge --target openai-agents --scope concierge
"""DNA-emitted OpenAI Agents SDK agent (tool-calling / ReAct): concierge."""
from agents import Agent, function_tool

INSTRUCTIONS = "You are the Helpdesk Concierge ..."   # byte-equal to build_prompt

@function_tool
def kb_search() -> str:
    "Search the runbook knowledge base ..."
    raise NotImplementedError("DNA scaffold: implement the kb-search tool")

agent = Agent(
    name='concierge',
    instructions=INSTRUCTIONS,
    model='gpt-4o',
    tools=[kb_search],
)
```

The config targets and this scaffold target are **both** the same `EmitterPort`
in two flavors. How the scaffold `{framework × case}` mechanism works — and how to
add a new case or a whole new code-first framework — is the
[How to write an emitter](writing-an-emitter.md) guide.

## The de-para — LangGraph (`create_react_agent`, code-first scaffold)

The **fifth** target. LangGraph's prebuilt agent is code-first —
`create_react_agent(model, tools=[...], prompt="...")` from `langgraph.prebuilt` —
so the emitter fills a `{langgraph × case}` scaffold. An agent with tools →
the ReAct idiom (`@tool` stubs); without → `tools=[]`:

```console
$ dna emit concierge --target langgraph --scope concierge
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

INSTRUCTIONS = "You are the Helpdesk Concierge ..."   # byte-equal to build_prompt

@tool
def kb_search() -> str:
    "Search the runbook knowledge base ..."
    raise NotImplementedError("DNA scaffold: implement the kb-search tool")

agent = create_react_agent(
    model='azure/gpt-4o',
    tools=[kb_search],
    prompt=INSTRUCTIONS,
    name='concierge',
)
```

| DNA (source of truth) | LangGraph | Notes |
|---|---|---|
| **`Soul` + `Guardrail`s + `Agent.instruction`** (composed by `build_prompt`) | `INSTRUCTIONS` constant → `prompt=INSTRUCTIONS` | **flat string** — carried **byte-equal** (identical across all seven targets) |
| `metadata.name` | `create_react_agent(name=...)` | the LangGraph graph name |
| `Agent.spec.model` → else `Genome.spec.default_llm` | `model=...` | DNA coordinate **preserved verbatim** — LangGraph resolves it via `init_chat_model`, which takes a `provider:model` string |
| `spec.tools[]` (Tool Kind) | `@tool` stubs → `tools=[...]` | one stub per Tool; body + typed signature is wired at deploy (a loss) |

### What does **not** survive — LangGraph-specific

Beyond the three DNA-only axes (composition structure, tenant overlay,
eval-as-contract), the LangGraph target also drops: the **tool body** (each `@tool`
is a `NotImplementedError` stub); and it flags the **model-coordinate convention** —
`init_chat_model` provider prefixes are `openai` / `anthropic` / `azure_openai` /
`google_genai`, so a DNA `azure/…` coordinate needs the `azure_openai:` prefix (or
a model instance) at wire-up. `create_react_agent` **requires** a model, so an
unbound DNA model is a reported loss (supply one at wire-up). `output_schema` maps
to `response_format` by hand.

## The de-para — Agno (`agno.agent.Agent`, code-first scaffold)

The **sixth** target. Agno is code-first — `Agent(name=..., model=...,
instructions=..., tools=[...])` from `agno.agent` — so the emitter fills an
`{agno × case}` scaffold. Agno auto-wraps plain callables as tools, so a stub is a
bare function:

```console
$ dna emit concierge --target agno --scope concierge
from agno.agent import Agent

INSTRUCTIONS = "You are the Helpdesk Concierge ..."   # byte-equal to build_prompt

def kb_search() -> str:
    "Search the runbook knowledge base ..."
    raise NotImplementedError("DNA scaffold: implement the kb-search tool")

agent = Agent(
    name='concierge',
    model='azure/gpt-4o',
    instructions=INSTRUCTIONS,
    tools=[kb_search],
)
```

| DNA (source of truth) | Agno | Notes |
|---|---|---|
| **`Soul` + `Guardrail`s + `Agent.instruction`** (composed by `build_prompt`) | `INSTRUCTIONS` constant → `instructions=INSTRUCTIONS` | **flat string** — carried **byte-equal** |
| `metadata.name` | `Agent(name=...)` | the display name |
| `Agent.spec.model` → else `Genome.spec.default_llm` | `model=...` | DNA coordinate **preserved** as a string (Agno accepts a `provider:model` string) |
| `spec.tools[]` (Tool Kind) | plain-function stubs → `tools=[...]` | Agno turns a callable into a tool; body is wired at deploy (a loss) |

### What does **not** survive — Agno-specific

Beyond the three DNA-only axes, the Agno target drops the **tool body** (a bare
callable stub) and notes the **model coordinate** assumes Agno's string-model
resolution (a specific `Model` object like `OpenAIChat(id=...)` is the alternative).
`output_schema` maps to `Agent(output_schema=...)` by hand.

## The de-para — DeepAgents (`create_deep_agent`, code-first scaffold)

The **seventh** target. LangChain's DeepAgents (the "batteries-included agent
harness") is code-first — `create_deep_agent(model=..., tools=[...],
system_prompt="...")` — so the emitter fills a `{deepagents × case}` scaffold:

```console
$ dna emit concierge --target deepagents --scope concierge
from deepagents import create_deep_agent

INSTRUCTIONS = "You are the Helpdesk Concierge ..."   # byte-equal to build_prompt

def kb_search() -> str:
    "Search the runbook knowledge base ..."
    raise NotImplementedError("DNA scaffold: implement the kb-search tool")

agent = create_deep_agent(
    model='azure/gpt-4o',
    tools=[kb_search],
    system_prompt=INSTRUCTIONS,
)
```

| DNA (source of truth) | DeepAgents | Notes |
|---|---|---|
| **`Soul` + `Guardrail`s + `Agent.instruction`** (composed by `build_prompt`) | `INSTRUCTIONS` constant → `system_prompt=INSTRUCTIONS` | **flat string** — carried **byte-equal**, but a **PREFIX** of the effective system prompt (see below) |
| `Agent.spec.model` → else `Genome.spec.default_llm` | `model=...` | DNA coordinate **preserved** — resolved via `init_chat_model` |
| `spec.tools[]` (Tool Kind) | callable stubs → `tools=[...]` | body is wired at deploy (a loss) |

### What does **not** survive — DeepAgents-specific

Beyond the three DNA-only axes, the DeepAgents target has two distinctive drops:
`system_prompt` sits **in front of** the deep-agent's built-in harness prompt
(planning / filesystem / sub-agent scaffolding) that the framework appends — so the
DNA prompt is a **prefix** of the effective system prompt, not the whole of it; and
`create_deep_agent` has **no declarative name slot**, so `metadata.name` is not
carried. Plus the **tool body** stub and the same model-coordinate convention as
LangGraph (unbound falls back to the deep-agent default model).

## Emitting a servable Copilot

Everything above emits a **single agent** — one artifact the target runtime
consumes. A `Copilot` is one step up: a *binder* that mounts an agent and adds the
copilot-level concerns (MCP servers, an inbound-tenant policy, a HITL write-gate,
RAG collections). Emitting a Copilot produces a **servable app** — not a stub —
so the same `dna emit` command routes it differently: when the name resolves to a
`Copilot` Kind, DNA composes it through `build_copilot_context` and emits the
target's **copilot case** (a two-artifact output: the `agent` module + an AG-UI
`serving` app exposing `/agui`).

```console
$ dna emit memory-copilot --target agno --out app/
Emitted memory-copilot → agno: 2 files under app/
# app/memory_agent.py        — build_agent() factory + MCP mounts + HITL write-gate
# app/memory_agent_serve.py  — Agno AgentOS serving the mounted agent over /agui
```

Because a copilot is multi-artifact, `--out` is a **directory** (it writes N
files), exactly like `--infra` / `--hosting`. `--target` picks the servable
runtime — **`agno`** (the default when `--target` is omitted), `agent-framework`,
or `langgraph`; each emits its own `agent` + `serving` pair from the *same*
Copilot source:

```console
$ dna emit memory-copilot --target langgraph --out app/   # same source, LangGraph app
$ dna emit memory-copilot --out app/                      # no --target → agno
```

A name that is an **Agent** (not a Copilot) keeps the original single-artifact
path unchanged — the routing is by Kind, so nothing about the agent emits above
shifts. The `--infra`, `--hosting` (and the Terraform / Foundry paths documented
in the [Copilot hosting](copilot-hosting.md) and
[infra-binding](copilot-infra-binding.md) guides) flags then add the deployment
artifacts alongside the servable app.

> Before this command, a consumer that wanted the servable app had to call the SDK
> seam (`build_copilot_context(...)`) directly — `dna emit <copilot>` closes that
> gap so the copilot app is a first-class CLI artifact like every single-agent emit.

## Adding a new target

Targets are a **registry, not a hardcode** — a new one is a class + one call, and
the CLI core never changes. The four shipped emitters (`agent-framework`,
`bedrock`, `vertex`, `openai-agents`) are the reference. For a **declarative**
runtime a config emitter looks identical to the three below; for a **code-first**
runtime you subclass `ScaffoldEmitter` and add a template. Full recipe (both
flavors + the *Passo 0* decision): [How to write an emitter](writing-an-emitter.md).

```python
from dna.emit import EmitContext, EmitResult, register_emitter

class OpenAIEmitter:
    target = "openai"
    file_extension = "json"

    def emit(self, ctx: EmitContext) -> EmitResult:
        # ctx is the runtime-agnostic view: ctx.instructions (the composed
        # prompt), ctx.model, ctx.tools, ctx.description, ctx.output_schema.
        artifact = ...  # render the target's native artifact
        return EmitResult(artifact=artifact, target=self.target,
                          filename=f"{ctx.name}.json",
                          losses=[...], mapping={...})

register_emitter(OpenAIEmitter())
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
