---
apiVersion: github.com/ruinosus/dna/sdlc/v1
kind: Research
metadata:
  name: rsh-agent-config-landscape-2026
spec:
  title: Agent-configuration landscape 2026 — prompt managers, cloud frameworks, and neutral standards
  objective: Map the 2026 competitive landscape for agent configuration to ground DNA's pivot from a prompt-manager
    into a vendor-neutral author-once → emit-per-runtime portability layer. Determine where DNA is out-competed
    (prompt management), where the market is heading (definition/runtime decoupling), and which neutral
    standard (Oracle Agent Spec) DNA should align to rather than reinvent.
  methodology: web-search-curated
  overall_confidence: high
  conducted_by: claude-code
  conducted_at: '2026-07-11T00:00:00+00:00'
  scope_ref: dna-development
  status: published
  visibility: shared
  owner: claude-code
  tags:
  - portability
  - emitters
  - oracle-agent-spec
  - agent-framework
  - landscape
  - pivot
  key_takeaways:
  - DNA as a pure prompt-manager LOSES — Langfuse (tracing+prompt mgmt+evals) and Agenta (Git-like prompt
    versioning) are more mature at that job, and Microsoft agent-framework already ships a native declarative
    PromptAgent loader. Competing on prompt management is a dead end.
  - The 2026 macro trend is decoupling agent DEFINITION from RUNTIME so runtimes are swappable — the explicit
    "Terraform / write-once-run-anywhere for agents" framing. Oracle Agent Spec and Microsoft's declarative
    YAML are the two concrete author-once instances; AWS Bedrock AgentCore ("use any framework") and the
    LF protocol consolidation (MCP + A2A) are the interop substrate.
  - Oracle Agent Spec (github.com/oracle/agent-spec, ~386★, UPL/Apache-2.0) is the ONLY shipped author-once→transpile
    standard today, with adapters for LangGraph, AutoGen, CrewAI and WayFlow — and NO adapters for Microsoft
    agent-framework, OpenAI Agents SDK, AWS Bedrock or Google Vertex/ADK. That gap is exactly where DNA's
    agent-framework emitter adds net-new value.
  - Neutral standards split by layer — MCP/A2A = interop protocols (tool + agent wire), Google Open Knowledge
    Format (OKF, not "Framework") = curated knowledge, AGENTS.md + agentskills.io (SKILL.md, both Linux-Foundation-stewarded)
    = instructions + skills. DNA already speaks AGENTS.md and SKILL.md natively as Kinds; OAS is the missing
    definition-portability peer.
  - DNA's durable value is portability / anti-lock-in — the Agent/Soul/Guardrail/Tool Kinds become the
    neutral SOURCE; emitters materialize each runtime's native artifact. The strategic question is emit-THROUGH-OAS
    vs emit-DIRECT (decided in adr-dna-pivot-portability).
  executive_summary: 'The 2026 agent-tooling market has bifurcated. Prompt-management platforms (Langfuse,
    Agenta, PromptLayer, Latitude) own prompt versioning/observability and are more mature than DNA at
    that narrow job, so a DNA positioned as a prompt-manager loses. Simultaneously, every major vendor
    now ships an agent RUNTIME (AWS Bedrock AgentCore + Strands, Google Vertex + ADK, OpenAI Agents SDK,
    Microsoft agent-framework, LangGraph), and the clear macro-trend is to DECOUPLE the agent definition
    from the runtime so teams can swap runtimes — the "Terraform for agents" framing. Two concrete author-once
    instances exist: Microsoft''s declarative PromptAgent YAML (loaded by AgentFactory, an open AgentSchema)
    and Oracle''s Open Agent Specification (PyAgentSpec + WayFlow reference runtime), the latter being
    the only shipped standard that transpiles ONE definition to multiple runtimes — but only to LangGraph,
    AutoGen, CrewAI and WayFlow, with no adapter for agent-framework, OpenAI, Bedrock or Vertex. The interop
    substrate is consolidating under the Linux Foundation (MCP for agent→tool, A2A for agent→agent, both
    donated to the Agentic AI Foundation / LF AI & Data), and the knowledge/instruction/skill layers are
    standardizing separately (Google OKF; AGENTS.md; agentskills.io SKILL.md). DNA already consumes AGENTS.md
    and SKILL.md as first-class Kinds; the missing peer is definition-portability. The recommendation
    this landscape supports: reposition DNA as the vendor-neutral definition + emitter layer, prove it
    on agent-framework (the gap OAS does not cover), and align DNA''s schema to the Oracle Agent Spec
    where it fits rather than reinventing a neutral schema.'
  sources:
  - ref-oracle-agent-spec
  - ref-oas-technical-report
  - ref-ms-agent-framework-declarative
  - ref-ms-agentschema-promptagent
  - ref-langfuse-prompt-mgmt
  - ref-agenta-prompt-mgmt
  - ref-bedrock-agentcore
  - ref-google-okf
  - ref-mcp-a2a-lf
  findings:
  - id: f-prompt-managers-mature
    title: Prompt-management platforms out-compete DNA at prompt management
    evidence_rating: evidence-based
    summary: Langfuse is an open-source LLM-engineering platform (tracing + prompt management + evals)
      with name+version prompt versioning and deployment labels (production). Agenta offers Git-like prompt
      versioning with variants/branches + commit history. PromptLayer is a prompt registry decoupling
      prompts from code; Latitude is an open platform for prompt engineering + eval. All four are more
      mature at prompt management than DNA — competing there loses.
    source_refs:
    - ref-langfuse-prompt-mgmt
    - ref-agenta-prompt-mgmt
    tags:
    - prompt-managers
  - id: f-definition-runtime-decoupling
    title: The 2026 trend is decoupling agent definition from runtime ("Terraform for agents")
    evidence_rating: evidence-based
    summary: AWS Bedrock AgentCore explicitly runs agents built with ANY framework (CrewAI, LangGraph,
      LlamaIndex, Google ADK, OpenAI Agents SDK, Strands); Oracle Agent Spec markets "export from AutoGen
      → run in LangGraph/WayFlow/CrewAI"; Microsoft ships a declarative YAML loaded by AgentFactory. The
      convergent pattern is a portable DEFINITION over a swappable RUNTIME.
    source_refs:
    - ref-bedrock-agentcore
    - ref-oracle-agent-spec
    tags:
    - trend
  - id: f-oas-only-transpiler
    title: Oracle Agent Spec is the only shipped author-once→transpile standard, and it does NOT target
      agent-framework
    evidence_rating: evidence-based
    summary: github.com/oracle/agent-spec (~386★, dual UPL-1.0/Apache-2.0) ships adapters for LangGraph,
      AutoGen, CrewAI and WayFlow — the four runtimes its technical report (arXiv 2510.04173) validates.
      It ships NO adapter for Microsoft agent-framework, OpenAI Agents SDK, AWS Bedrock or Google Vertex/ADK
      today (an agent-framework integration is only a community discussion). DNA's agent-framework emitter
      fills a gap OAS does not cover.
    source_refs:
    - ref-oracle-agent-spec
    - ref-oas-technical-report
    tags:
    - oracle-agent-spec
  - id: f-oas-schema-shape
    title: OAS models Agent/Flow with system_prompt + llm_config + typed tools (Server/Client/Remote/MCP)
    evidence_rating: evidence-based
    summary: An OAS Agent carries name, system_prompt (Mustache {{var}} templating), llm_config (provider
      config classes OciGenAiConfig/OpenAiConfig/OllamaConfig), and inputs (JSON-schema Property list).
      Tools are typed — ServerTool (runtime-executed), ClientTool (client-executed, OpenAI-style function
      calling), RemoteTool (external API/RPC), MCPTool (MCP server). Serializes to JSON/YAML via PyAgentSpec;
      reference runtime is WayFlow.
    source_refs:
    - ref-oracle-agent-spec
    - ref-oas-technical-report
    tags:
    - oracle-agent-spec
    - schema
  - id: f-ms-declarative-schema
    title: Microsoft agent-framework declarative PromptAgent uses kind:function tools and model.connection
    evidence_rating: evidence-based
    summary: The declarative PromptAgent (open AgentSchema, microsoft.github.io/AgentSchema) has fields
      kind/name/displayName/description/instructions/model/tools/inputSchema/outputSchema, loaded by AgentFactory.create_agent_from_yaml.
      Function tools use `kind function` (the YAML key kind with value function — NOT a `type` key) with
      name/description/parameters; other tool kinds are openapi/code_interpreter/file_search/mcp/web_search/custom.
      The current AgentSchema binds the model via model.id + model.connection.kind (remote or key) — though
      the proven rc2 line the DNA spike loaded accepts model.{id,provider}.
    source_refs:
    - ref-ms-agent-framework-declarative
    - ref-ms-agentschema-promptagent
    tags:
    - agent-framework
    - schema
  - id: f-neutral-standards-by-layer
    title: Neutral standards split cleanly by layer — DNA already speaks two of them
    evidence_rating: evidence-based
    summary: MCP (agent→tool, "USB-C for tools") and A2A (agent→agent, "HTTP for agents") are interop
      protocols, both under the Linux Foundation (Agentic AI Foundation / LF AI & Data; A2A hit v1.0 in
      Apr 2026). Google Open Knowledge Format (OKF, v0.1 Jun 2026, Apache-2.0) standardizes curated agent
      knowledge as markdown+YAML. AGENTS.md (agent constitution, LF Dec 2025) and agentskills.io SKILL.md
      (open standard Dec 2025) standardize instructions and skills. DNA already consumes AGENTS.md and
      SKILL.md as Kinds; the missing peer is a definition-portability standard (OAS).
    source_refs:
    - ref-mcp-a2a-lf
    - ref-google-okf
    tags:
    - standards
  recommendations:
  - id: rec-reposition-emitter-layer
    priority: high
    summary: Reposition DNA as the vendor-neutral DEFINITION + EMITTER layer (Agent/Soul/Guardrail/Tool
      Kinds as the neutral source), not a prompt-manager. Prove it first on Microsoft agent-framework
      — the author-once gap the Oracle Agent Spec does not cover today.
    backed_by_findings:
    - f-prompt-managers-mature
    - f-oas-only-transpiler
    - f-definition-runtime-decoupling
  - id: rec-align-to-oas
    priority: high
    summary: Align DNA's schema to the Oracle Agent Spec where it fits (system_prompt, llm_config, typed
      tools) rather than reinventing a neutral schema; keep emitting DIRECT for runtimes OAS omits (agent-framework
      first). Exact emit-through vs emit-direct verdict in adr-dna-pivot-portability.
    backed_by_findings:
    - f-oas-schema-shape
    - f-oas-only-transpiler
  - id: rec-lean-on-lf-standards
    priority: medium
    summary: Keep leaning on the Linux-Foundation interop/knowledge/skill standards DNA already speaks
      (MCP, AGENTS.md, SKILL.md) and treat OKF as the knowledge peer; do not reinvent interop.
    backed_by_findings:
    - f-neutral-standards-by-layer
  created_at: '2026-07-11T12:49:10+00:00'
  updated_at: '2026-07-11T16:37:50+00:00'
  instruction: |-
    # Research — Agent-configuration landscape 2026 — prompt managers, cloud frameworks, and neutral standards

    Methodology: web-search-curated · 9 sources · 6 findings.

    This file's spec (frontmatter above) is the authoritative data. The prose below is for human reading and is regenerated on each write. Edit via `dna research` CLI or the Studio viewer; raw frontmatter edits are also supported.
  cited_by:
  - ADR/adr-dna-mcp-runtime-face
  - ADR/adr-dna-cloud-saas
  - Feature/f-dna-cloud
---

# Research — Agent-configuration landscape 2026 — prompt managers, cloud frameworks, and neutral standards

Methodology: web-search-curated · 9 sources · 6 findings.

This file's spec (frontmatter above) is the authoritative data. The prose below is for human reading and is regenerated on each write. Edit via `dna research` CLI or the Studio viewer; raw frontmatter edits are also supported.
