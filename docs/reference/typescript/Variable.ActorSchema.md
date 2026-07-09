# Variable: ActorSchema

```ts
const ActorSchema: ZodObject<{
  apiVersion: ZodLiteral<"github.com/ruinosus/dna/v1">;
  kind: ZodLiteral<"Actor">;
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
     actorType: ZodDefault<ZodEnum<["human", "system", "time"]>>;
     instruction: ZodDefault<ZodOptional<ZodString>>;
     role: ZodDefault<ZodOptional<ZodString>>;
     traits: ZodDefault<ZodArray<ZodString, "many">>;
   }, "strip", ZodTypeAny, {
     actorType: "time" | "human" | "system";
     instruction: string;
     role: string;
     traits: string[];
   }, {
     actorType?: "time" | "human" | "system";
     instruction?: string;
     role?: string;
     traits?: string[];
  }>>;
}, "strip", ZodTypeAny, {
  apiVersion: "github.com/ruinosus/dna/v1";
  kind: "Actor";
  metadata: {
     description: string;
     group: string;
     icon: string;
     labels: Record<string, string>;
     name: string;
     version: string;
  };
  spec: {
     actorType: "time" | "human" | "system";
     instruction: string;
     role: string;
     traits: string[];
  };
}, {
  apiVersion: "github.com/ruinosus/dna/v1";
  kind: "Actor";
  metadata: {
     description?: string;
     group?: string;
     icon?: string;
     labels?: Record<string, string>;
     name: string;
     version?: string;
  };
  spec?: {
     actorType?: "time" | "human" | "system";
     instruction?: string;
     role?: string;
     traits?: string[];
  };
}>;
```
