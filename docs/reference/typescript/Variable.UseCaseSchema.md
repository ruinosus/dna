# Variable: UseCaseSchema

```ts
const UseCaseSchema: ZodObject<{
  apiVersion: ZodLiteral<"github.com/ruinosus/dna/v1">;
  kind: ZodLiteral<"UseCase">;
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
     agents: ZodDefault<ZodArray<ZodString, "many">>;
     alternate_flows: ZodDefault<ZodArray<ZodRecord<ZodString, ZodUnknown>, "many">>;
     guardrails: ZodDefault<ZodArray<ZodString, "many">>;
     main_flow: ZodDefault<ZodArray<ZodString, "many">>;
     postconditions: ZodDefault<ZodArray<ZodString, "many">>;
     preconditions: ZodDefault<ZodArray<ZodString, "many">>;
     primary_actor: ZodOptional<ZodString>;
     skills: ZodDefault<ZodArray<ZodString, "many">>;
     soul: ZodOptional<ZodString>;
     success_criteria: ZodDefault<ZodArray<ZodString, "many">>;
     supporting_actors: ZodDefault<ZodArray<ZodString, "many">>;
     tools: ZodDefault<ZodArray<ZodString, "many">>;
   }, "strip", ZodTypeAny, {
     agents: string[];
     alternate_flows: Record<string, unknown>[];
     guardrails: string[];
     main_flow: string[];
     postconditions: string[];
     preconditions: string[];
     primary_actor?: string;
     skills: string[];
     soul?: string;
     success_criteria: string[];
     supporting_actors: string[];
     tools: string[];
   }, {
     agents?: string[];
     alternate_flows?: Record<string, unknown>[];
     guardrails?: string[];
     main_flow?: string[];
     postconditions?: string[];
     preconditions?: string[];
     primary_actor?: string;
     skills?: string[];
     soul?: string;
     success_criteria?: string[];
     supporting_actors?: string[];
     tools?: string[];
  }>>;
}, "strip", ZodTypeAny, {
  apiVersion: "github.com/ruinosus/dna/v1";
  kind: "UseCase";
  metadata: {
     description: string;
     group: string;
     icon: string;
     labels: Record<string, string>;
     name: string;
     version: string;
  };
  spec: {
     agents: string[];
     alternate_flows: Record<string, unknown>[];
     guardrails: string[];
     main_flow: string[];
     postconditions: string[];
     preconditions: string[];
     primary_actor?: string;
     skills: string[];
     soul?: string;
     success_criteria: string[];
     supporting_actors: string[];
     tools: string[];
  };
}, {
  apiVersion: "github.com/ruinosus/dna/v1";
  kind: "UseCase";
  metadata: {
     description?: string;
     group?: string;
     icon?: string;
     labels?: Record<string, string>;
     name: string;
     version?: string;
  };
  spec?: {
     agents?: string[];
     alternate_flows?: Record<string, unknown>[];
     guardrails?: string[];
     main_flow?: string[];
     postconditions?: string[];
     preconditions?: string[];
     primary_actor?: string;
     skills?: string[];
     soul?: string;
     success_criteria?: string[];
     supporting_actors?: string[];
     tools?: string[];
  };
}>;
```
