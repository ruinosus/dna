# Variable: GenomeSchema

```ts
const GenomeSchema: ZodObject<{
  apiVersion: ZodLiteral<"github.com/ruinosus/dna/v1">;
  kind: ZodLiteral<"Genome">;
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
     budget: ZodOptional<ZodNullable<ZodRecord<ZodString, ZodUnknown>>>;
     capabilities: ZodDefault<ZodArray<ZodRecord<ZodString, ZodUnknown>, "many">>;
     changelog_url: ZodOptional<ZodNullable<ZodString>>;
     default_agent: ZodOptional<ZodString>;
     default_llm: ZodOptional<ZodString>;
     dependencies: ZodDefault<ZodArray<ZodRecord<ZodString, ZodUnknown>, "many">>;
     deprecated: ZodDefault<ZodBoolean>;
     deprecated_message: ZodOptional<ZodNullable<ZodString>>;
     global_scope: ZodDefault<ZodBoolean>;
     mandatory: ZodDefault<ZodBoolean>;
     owner: ZodOptional<ZodNullable<ZodString>>;
     owner_tenant: ZodOptional<ZodNullable<ZodString>>;
     parent_scope: ZodOptional<ZodNullable<ZodString>>;
     repository: ZodOptional<ZodNullable<ZodString>>;
     tags: ZodDefault<ZodArray<ZodString, "many">>;
     version: ZodOptional<ZodNullable<ZodString>>;
     visibility: ZodDefault<ZodEnum<["public", "internal", "private"]>>;
   }, "strip", ZodTypeAny, {
     budget?: Record<string, unknown> | null;
     capabilities: Record<string, unknown>[];
     changelog_url?: string | null;
     default_agent?: string;
     default_llm?: string;
     dependencies: Record<string, unknown>[];
     deprecated: boolean;
     deprecated_message?: string | null;
     global_scope: boolean;
     mandatory: boolean;
     owner?: string | null;
     owner_tenant?: string | null;
     parent_scope?: string | null;
     repository?: string | null;
     tags: string[];
     version?: string | null;
     visibility: "public" | "internal" | "private";
   }, {
     budget?: Record<string, unknown> | null;
     capabilities?: Record<string, unknown>[];
     changelog_url?: string | null;
     default_agent?: string;
     default_llm?: string;
     dependencies?: Record<string, unknown>[];
     deprecated?: boolean;
     deprecated_message?: string | null;
     global_scope?: boolean;
     mandatory?: boolean;
     owner?: string | null;
     owner_tenant?: string | null;
     parent_scope?: string | null;
     repository?: string | null;
     tags?: string[];
     version?: string | null;
     visibility?: "public" | "internal" | "private";
  }>>;
}, "strip", ZodTypeAny, {
  apiVersion: "github.com/ruinosus/dna/v1";
  kind: "Genome";
  metadata: {
     description: string;
     group: string;
     icon: string;
     labels: Record<string, string>;
     name: string;
     version: string;
  };
  spec: {
     budget?: Record<string, unknown> | null;
     capabilities: Record<string, unknown>[];
     changelog_url?: string | null;
     default_agent?: string;
     default_llm?: string;
     dependencies: Record<string, unknown>[];
     deprecated: boolean;
     deprecated_message?: string | null;
     global_scope: boolean;
     mandatory: boolean;
     owner?: string | null;
     owner_tenant?: string | null;
     parent_scope?: string | null;
     repository?: string | null;
     tags: string[];
     version?: string | null;
     visibility: "public" | "internal" | "private";
  };
}, {
  apiVersion: "github.com/ruinosus/dna/v1";
  kind: "Genome";
  metadata: {
     description?: string;
     group?: string;
     icon?: string;
     labels?: Record<string, string>;
     name: string;
     version?: string;
  };
  spec?: {
     budget?: Record<string, unknown> | null;
     capabilities?: Record<string, unknown>[];
     changelog_url?: string | null;
     default_agent?: string;
     default_llm?: string;
     dependencies?: Record<string, unknown>[];
     deprecated?: boolean;
     deprecated_message?: string | null;
     global_scope?: boolean;
     mandatory?: boolean;
     owner?: string | null;
     owner_tenant?: string | null;
     parent_scope?: string | null;
     repository?: string | null;
     tags?: string[];
     version?: string | null;
     visibility?: "public" | "internal" | "private";
  };
}>;
```
