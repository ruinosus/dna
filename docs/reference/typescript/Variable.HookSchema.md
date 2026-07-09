# Variable: HookSchema

```ts
const HookSchema: ZodObject<{
  apiVersion: ZodLiteral<"github.com/ruinosus/dna/v1">;
  kind: ZodLiteral<"Hook">;
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
     action: ZodDefault<ZodEnum<["inject_fields", "log", "script"]>>;
     body: ZodDefault<ZodOptional<ZodString>>;
     fields: ZodDefault<ZodRecord<ZodString, ZodUnknown>>;
     target: ZodDefault<ZodString>;
     type: ZodDefault<ZodEnum<["middleware", "event"]>>;
   }, "strip", ZodTypeAny, {
     action: "inject_fields" | "log" | "script";
     body: string;
     fields: Record<string, unknown>;
     target: string;
     type: "middleware" | "event";
   }, {
     action?: "inject_fields" | "log" | "script";
     body?: string;
     fields?: Record<string, unknown>;
     target?: string;
     type?: "middleware" | "event";
  }>>;
}, "strip", ZodTypeAny, {
  apiVersion: "github.com/ruinosus/dna/v1";
  kind: "Hook";
  metadata: {
     description: string;
     group: string;
     icon: string;
     labels: Record<string, string>;
     name: string;
     version: string;
  };
  spec: {
     action: "inject_fields" | "log" | "script";
     body: string;
     fields: Record<string, unknown>;
     target: string;
     type: "middleware" | "event";
  };
}, {
  apiVersion: "github.com/ruinosus/dna/v1";
  kind: "Hook";
  metadata: {
     description?: string;
     group?: string;
     icon?: string;
     labels?: Record<string, string>;
     name: string;
     version?: string;
  };
  spec?: {
     action?: "inject_fields" | "log" | "script";
     body?: string;
     fields?: Record<string, unknown>;
     target?: string;
     type?: "middleware" | "event";
  };
}>;
```
