# Variable: AgentDefinitionSchema

```ts
const AgentDefinitionSchema: ZodObject<{
  apiVersion: ZodLiteral<"agents.md/v1">;
  kind: ZodLiteral<"AgentDefinition">;
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
     content: ZodDefault<ZodOptional<ZodString>>;
   }, "strip", ZodTypeAny, {
     content: string;
   }, {
     content?: string;
  }>>;
}, "strip", ZodTypeAny, {
  apiVersion: "agents.md/v1";
  kind: "AgentDefinition";
  metadata: {
     description: string;
     group: string;
     icon: string;
     labels: Record<string, string>;
     name: string;
     version: string;
  };
  spec: {
     content: string;
  };
}, {
  apiVersion: "agents.md/v1";
  kind: "AgentDefinition";
  metadata: {
     description?: string;
     group?: string;
     icon?: string;
     labels?: Record<string, string>;
     name: string;
     version?: string;
  };
  spec?: {
     content?: string;
  };
}>;
```
