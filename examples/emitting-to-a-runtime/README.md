# emitting-to-a-runtime

DNA describes an agent **once** and `dna emit` **materializes the native artifact
each runtime consumes** — author once, emit per runtime, swap runtimes without a
rewrite. This example is the portability proof: the **same** `concierge` DNA
source emits to **seven** different runtimes — three *config-declarative*
(agent-framework, bedrock, vertex) and four *code-first scaffolds* (openai-agents,
langgraph, agno, deepagents) — with the composed prompt **byte-identical** in
every artifact.

```
.dna/
└── concierge/
    ├── Genome.yaml                 # scope root: identity + default_llm (azure/gpt-4o)
    ├── agents/
    │   └── concierge.yaml          # kind: Agent — ONE-line instruction + soul + guardrail + tool wiring
    ├── souls/
    │   └── helpdesk-host/SOUL.md   # kind: Soul — the reusable persona (composed in, not copy-pasted)
    ├── guardrails/
    │   └── grounded-citation/GUARDRAIL.md   # kind: Guardrail — a wired citation duty
    └── tools/
        └── kb-search.yaml          # kind: Tool — the agent-facing tool surface + JSON Schema
```

The agent's `instruction` is a single line; the persona (`Soul`) and the citation
duty (`Guardrail`) are **composed in** by `build_prompt`, not pasted. That
composition is exactly the DNA-only value that collapses to a flat instruction
string on emit — and the emitters report it honestly as a loss.

## One source → seven runtimes

**Microsoft agent-framework** — a declarative `PromptAgent` YAML that
`AgentFactory` loads:

```bash
dna emit concierge --target agent-framework --scope concierge
# kind: Prompt / name: Concierge / model: {id: gpt-4o, provider: AzureOpenAI}
# tools: [{name: kb-search, kind: function, ...}] / instructions: <composed prompt>
```

**Amazon Bedrock Agent** — an AWS CloudFormation `AWS::Bedrock::Agent` template:

```bash
dna emit concierge --target bedrock --scope concierge
# Resources.ConciergeAgent (Type: AWS::Bedrock::Agent)
#   Properties.AgentName: concierge / FoundationModel: gpt-4o
#   Instruction: <composed prompt, BYTE-EQUAL to agent-framework's instructions>
#   ActionGroups[0].FunctionSchema.Functions[0].Name: kb-search
```

**Google ADK Agent Config** — a declarative `LlmAgent` YAML (loaded with
`config_agent_utils.from_config`):

```bash
dna emit concierge --target vertex --scope concierge
# # yaml-language-server: $schema=https://.../AgentConfig.json
# agent_class: LlmAgent / name: concierge / model: gpt-4o
# instruction: <composed prompt, BYTE-EQUAL to the other two>
# tools: [{name: kb-search}]   # ADK binds tools by code reference (see losses)
```

The three targets above are **config-declarative**. The **same** source also emits
to four **code-first** runtimes that have no declarative agent format — the emitter
fills a curated `{framework × case}` scaffold and the composed prompt rides in a
byte-equal `INSTRUCTIONS` constant:

```bash
dna emit concierge --target openai-agents --scope concierge   # Agent(instructions=INSTRUCTIONS, tools=[kb_search])
dna emit concierge --target langgraph     --scope concierge   # create_react_agent(model, tools=[kb_search], prompt=INSTRUCTIONS)
dna emit concierge --target agno          --scope concierge   # Agent(name, model, instructions=INSTRUCTIONS, tools=[kb_search])
dna emit concierge --target deepagents    --scope concierge   # create_deep_agent(model, tools=[kb_search], system_prompt=INSTRUCTIONS)
```

The composed prompt is **byte-equal** across all **seven** artifacts — the same
author-time definition, materialized seven ways. What each target has no slot for
(composition structure, tenant overlay, eval-as-contract; for Bedrock also
tool-parameter depth and the model coordinate; for ADK the tool binding is a code
reference so a Tool's schema/description have no declarative slot, and
`output_schema` is a Pydantic-class reference; for the code-first scaffolds the
tool *body* is a stub to wire, and for deepagents the DNA prompt is a *prefix* of
the harness system prompt and there is no name slot) is reported on stderr / under
`--json` `losses`, never hidden.

See `dna emit --list-targets` for the registered runtimes, and the guide
[Emitting to a runtime](../../docs/guides/emitting-to-a-runtime.md) for the full
de-para tables.

## Never rots

The example is exercised by all seven emitter suites
(`packages/sdk-py/tests/test_emit_{agent_framework,bedrock,vertex,openai_agents,langgraph,agno,deepagents}.py`),
the CLI suite (`packages/cli/tests/test_emit_cmd.py`), and a dedicated
portability proof (`test_emit_portability.py`) that asserts the composed
instruction is byte-identical across all seven artifacts — so the seven-runtime
proof can never silently break.
