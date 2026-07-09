# Variable: AgentSchema

```ts
const AgentSchema: ZodObject<{
  apiVersion: ZodLiteral<"github.com/ruinosus/dna/v1">;
  kind: ZodLiteral<"Agent">;
  metadata: ZodObject<{
     description: ZodDefault<ZodOptional<ZodString>>;
     group: ZodDefault<ZodOptional<ZodString>>;
     icon: ZodDefault<ZodOptional<ZodString>>;
     labels: ZodDefault<ZodRecord<ZodString, ZodString>>;
     name: ZodString;
     version: ZodDefault<ZodOptional<ZodString>>;
   }, "strip", ZodTypeAny, {
     description: string;
     group: string;
     icon: string;
     labels: Record<string, string>;
     name: string;
     version: string;
   }, {
     description?: string;
     group?: string;
     icon?: string;
     labels?: Record<string, string>;
     name: string;
     version?: string;
  }>;
  spec: ZodDefault<ZodObject<{
     agent_kind: ZodOptional<ZodEnum<["deepagent", "langgraph-react"]>>;
     creative_slots: ZodDefault<ZodArray<ZodString, "many">>;
     delegation_target_for: ZodOptional<ZodObject<{
        agents: ZodDefault<ZodArray<ZodString, "many">>;
        format: ZodDefault<ZodEnum<[..., ..., ...]>>;
        purpose: ZodOptional<ZodString>;
        typical_seconds: ZodOptional<ZodNumber>;
        use_when: ZodOptional<ZodString>;
      }, "strip", ZodTypeAny, {
        agents: string[];
        format: "text" | "json" | "slug";
        purpose?: string;
        typical_seconds?: number;
        use_when?: string;
      }, {
        agents?: string[];
        format?: "text" | "json" | "slug";
        purpose?: string;
        typical_seconds?: number;
        use_when?: string;
     }>>;
     guardrails: ZodDefault<ZodArray<ZodString, "many">>;
     input_schema: ZodOptional<ZodUnion<[ZodRecord<ZodString, ZodUnknown>, ZodString]>>;
     instruction: ZodDefault<ZodOptional<ZodString>>;
     instruction_file: ZodOptional<ZodString>;
     invoked_by_engine: ZodOptional<ZodString>;
     locale_strings: ZodOptional<ZodRecord<ZodString, ZodRecord<ZodString, ZodString>>>;
     mandatory_tool_calls: ZodDefault<ZodArray<ZodString, "many">>;
     max_turns: ZodOptional<ZodNumber>;
     mcp_servers: ZodDefault<ZodArray<ZodUnion<[ZodString, ZodObject<{
        allowed_tools: ...;
        ref: ...;
        timeout_s: ...;
     }, "passthrough", ZodTypeAny, objectOutputType<..., ..., ...>, objectInputType<..., ..., ...>>]>, "many">>;
     model: ZodOptional<ZodString>;
     objective: ZodDefault<ZodOptional<ZodString>>;
     prompt_format: ZodOptional<ZodEnum<["json", "toon"]>>;
     promptTemplate: ZodOptional<ZodString>;
     reads: ZodDefault<ZodRecord<ZodString, ZodRecord<ZodString, ZodAny>>>;
     reflect_before_write: ZodOptional<ZodBoolean>;
     shell_sandbox: ZodOptional<ZodBoolean>;
     skills: ZodDefault<ZodArray<ZodString, "many">>;
     soul: ZodOptional<ZodString>;
     system_slots: ZodDefault<ZodRecord<ZodString, ZodString>>;
     tags: ZodDefault<ZodArray<ZodString, "many">>;
     target_scopes: ZodOptional<ZodArray<ZodString, "many">>;
     team_members: ZodDefault<ZodArray<ZodString, "many">>;
     tool_groups: ZodDefault<ZodArray<ZodString, "many">>;
     tools: ZodDefault<ZodArray<ZodString, "many">>;
     type: ZodOptional<ZodString>;
     voice_persona: ZodOptional<ZodObject<{
        archetype: ZodOptional<ZodString>;
        budget: ZodDefault<ZodNumber>;
        interruption_tolerance: ZodDefault<ZodEnum<[..., ..., ...]>>;
        mcp_egress: ZodDefault<ZodBoolean>;
        preamble: ZodDefault<ZodBoolean>;
        style: ZodOptional<ZodString>;
        voice: ZodDefault<ZodString>;
        wake_word: ZodOptional<ZodString>;
      }, "strip", ZodTypeAny, {
        archetype?: string;
        budget: number;
        interruption_tolerance: "high" | "medium" | "low";
        mcp_egress: boolean;
        preamble: boolean;
        style?: string;
        voice: string;
        wake_word?: string;
      }, {
        archetype?: string;
        budget?: number;
        interruption_tolerance?: "high" | "medium" | "low";
        mcp_egress?: boolean;
        preamble?: boolean;
        style?: string;
        voice?: string;
        wake_word?: string;
     }>>;
     writes_kind: ZodOptional<ZodString>;
     writes_kinds: ZodDefault<ZodRecord<ZodString, ZodRecord<ZodString, ZodAny>>>;
   }, "strip", ZodTypeAny, {
     agent_kind?: "deepagent" | "langgraph-react";
     creative_slots: string[];
     delegation_target_for?: {
        agents: string[];
        format: "text" | "json" | "slug";
        purpose?: string;
        typical_seconds?: number;
        use_when?: string;
     };
     guardrails: string[];
     input_schema?: string | Record<string, unknown>;
     instruction: string;
     instruction_file?: string;
     invoked_by_engine?: string;
     locale_strings?: Record<string, Record<string, string>>;
     mandatory_tool_calls: string[];
     max_turns?: number;
     mcp_servers: (
        | string
        | objectOutputType<{
        allowed_tools: ZodOptional<ZodArray<..., ...>>;
        ref: ZodString;
        timeout_s: ZodOptional<ZodNumber>;
     }, ZodTypeAny, "passthrough">)[];
     model?: string;
     objective: string;
     prompt_format?: "json" | "toon";
     promptTemplate?: string;
     reads: Record<string, Record<string, any>>;
     reflect_before_write?: boolean;
     shell_sandbox?: boolean;
     skills: string[];
     soul?: string;
     system_slots: Record<string, string>;
     tags: string[];
     target_scopes?: string[];
     team_members: string[];
     tool_groups: string[];
     tools: string[];
     type?: string;
     voice_persona?: {
        archetype?: string;
        budget: number;
        interruption_tolerance: "high" | "medium" | "low";
        mcp_egress: boolean;
        preamble: boolean;
        style?: string;
        voice: string;
        wake_word?: string;
     };
     writes_kind?: string;
     writes_kinds: Record<string, Record<string, any>>;
   }, {
     agent_kind?: "deepagent" | "langgraph-react";
     creative_slots?: string[];
     delegation_target_for?: {
        agents?: string[];
        format?: "text" | "json" | "slug";
        purpose?: string;
        typical_seconds?: number;
        use_when?: string;
     };
     guardrails?: string[];
     input_schema?: string | Record<string, unknown>;
     instruction?: string;
     instruction_file?: string;
     invoked_by_engine?: string;
     locale_strings?: Record<string, Record<string, string>>;
     mandatory_tool_calls?: string[];
     max_turns?: number;
     mcp_servers?: (
        | string
        | objectInputType<{
        allowed_tools: ZodOptional<...>;
        ref: ZodString;
        timeout_s: ZodOptional<...>;
     }, ZodTypeAny, "passthrough">)[];
     model?: string;
     objective?: string;
     prompt_format?: "json" | "toon";
     promptTemplate?: string;
     reads?: Record<string, Record<string, any>>;
     reflect_before_write?: boolean;
     shell_sandbox?: boolean;
     skills?: string[];
     soul?: string;
     system_slots?: Record<string, string>;
     tags?: string[];
     target_scopes?: string[];
     team_members?: string[];
     tool_groups?: string[];
     tools?: string[];
     type?: string;
     voice_persona?: {
        archetype?: string;
        budget?: number;
        interruption_tolerance?: "high" | "medium" | "low";
        mcp_egress?: boolean;
        preamble?: boolean;
        style?: string;
        voice?: string;
        wake_word?: string;
     };
     writes_kind?: string;
     writes_kinds?: Record<string, Record<string, any>>;
  }>>;
}, "strip", ZodTypeAny, {
  apiVersion: "github.com/ruinosus/dna/v1";
  kind: "Agent";
  metadata: {
     description: string;
     group: string;
     icon: string;
     labels: Record<string, string>;
     name: string;
     version: string;
  };
  spec: {
     agent_kind?: "deepagent" | "langgraph-react";
     creative_slots: string[];
     delegation_target_for?: {
        agents: string[];
        format: "text" | "json" | "slug";
        purpose?: string;
        typical_seconds?: number;
        use_when?: string;
     };
     guardrails: string[];
     input_schema?: string | Record<string, unknown>;
     instruction: string;
     instruction_file?: string;
     invoked_by_engine?: string;
     locale_strings?: Record<string, Record<string, string>>;
     mandatory_tool_calls: string[];
     max_turns?: number;
     mcp_servers: (
        | string
        | objectOutputType<{
        allowed_tools: ZodOptional<ZodArray<ZodString, "many">>;
        ref: ZodString;
        timeout_s: ZodOptional<ZodNumber>;
     }, ZodTypeAny, "passthrough">)[];
     model?: string;
     objective: string;
     prompt_format?: "json" | "toon";
     promptTemplate?: string;
     reads: Record<string, Record<string, any>>;
     reflect_before_write?: boolean;
     shell_sandbox?: boolean;
     skills: string[];
     soul?: string;
     system_slots: Record<string, string>;
     tags: string[];
     target_scopes?: string[];
     team_members: string[];
     tool_groups: string[];
     tools: string[];
     type?: string;
     voice_persona?: {
        archetype?: string;
        budget: number;
        interruption_tolerance: "high" | "medium" | "low";
        mcp_egress: boolean;
        preamble: boolean;
        style?: string;
        voice: string;
        wake_word?: string;
     };
     writes_kind?: string;
     writes_kinds: Record<string, Record<string, any>>;
  };
}, {
  apiVersion: "github.com/ruinosus/dna/v1";
  kind: "Agent";
  metadata: {
     description?: string;
     group?: string;
     icon?: string;
     labels?: Record<string, string>;
     name: string;
     version?: string;
  };
  spec?: {
     agent_kind?: "deepagent" | "langgraph-react";
     creative_slots?: string[];
     delegation_target_for?: {
        agents?: string[];
        format?: "text" | "json" | "slug";
        purpose?: string;
        typical_seconds?: number;
        use_when?: string;
     };
     guardrails?: string[];
     input_schema?: string | Record<string, unknown>;
     instruction?: string;
     instruction_file?: string;
     invoked_by_engine?: string;
     locale_strings?: Record<string, Record<string, string>>;
     mandatory_tool_calls?: string[];
     max_turns?: number;
     mcp_servers?: (
        | string
        | objectInputType<{
        allowed_tools: ZodOptional<ZodArray<..., ...>>;
        ref: ZodString;
        timeout_s: ZodOptional<ZodNumber>;
     }, ZodTypeAny, "passthrough">)[];
     model?: string;
     objective?: string;
     prompt_format?: "json" | "toon";
     promptTemplate?: string;
     reads?: Record<string, Record<string, any>>;
     reflect_before_write?: boolean;
     shell_sandbox?: boolean;
     skills?: string[];
     soul?: string;
     system_slots?: Record<string, string>;
     tags?: string[];
     target_scopes?: string[];
     team_members?: string[];
     tool_groups?: string[];
     tools?: string[];
     type?: string;
     voice_persona?: {
        archetype?: string;
        budget?: number;
        interruption_tolerance?: "high" | "medium" | "low";
        mcp_egress?: boolean;
        preamble?: boolean;
        style?: string;
        voice?: string;
        wake_word?: string;
     };
     writes_kind?: string;
     writes_kinds?: Record<string, Record<string, any>>;
  };
}>;
```
