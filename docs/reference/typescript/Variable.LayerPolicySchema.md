# Variable: LayerPolicySchema

```ts
const LayerPolicySchema: ZodObject<{
  apiVersion: ZodLiteral<"github.com/ruinosus/dna/policy/v1">;
  kind: ZodLiteral<"LayerPolicy">;
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
     composition_rules: ZodDefault<ZodRecord<ZodString, ZodObject<{
        merge_strategy: ZodDefault<ZodEnum<...>>;
        scope_inheritance: ZodDefault<ZodEnum<...>>;
        tenant_overlay: ZodDefault<ZodEnum<...>>;
      }, "strip", ZodTypeAny, {
        merge_strategy: "override_full" | "field_level";
        scope_inheritance: "enabled" | "disabled";
        tenant_overlay: "field_level" | "none";
      }, {
        merge_strategy?: "override_full" | "field_level";
        scope_inheritance?: "enabled" | "disabled";
        tenant_overlay?: "field_level" | "none";
     }>>>;
     layer_id: ZodDefault<ZodString>;
     policies: ZodDefault<ZodRecord<ZodString, ZodString>>;
   }, "strip", ZodTypeAny, {
     composition_rules: Record<string, {
        merge_strategy: "override_full" | "field_level";
        scope_inheritance: "enabled" | "disabled";
        tenant_overlay: "field_level" | "none";
     }>;
     layer_id: string;
     policies: Record<string, string>;
   }, {
     composition_rules?: Record<string, {
        merge_strategy?: "override_full" | "field_level";
        scope_inheritance?: "enabled" | "disabled";
        tenant_overlay?: "field_level" | "none";
     }>;
     layer_id?: string;
     policies?: Record<string, string>;
  }>>;
}, "strip", ZodTypeAny, {
  apiVersion: "github.com/ruinosus/dna/policy/v1";
  kind: "LayerPolicy";
  metadata: {
     description: string;
     group: string;
     icon: string;
     labels: Record<string, string>;
     name: string;
     version: string;
  };
  spec: {
     composition_rules: Record<string, {
        merge_strategy: "override_full" | "field_level";
        scope_inheritance: "enabled" | "disabled";
        tenant_overlay: "field_level" | "none";
     }>;
     layer_id: string;
     policies: Record<string, string>;
  };
}, {
  apiVersion: "github.com/ruinosus/dna/policy/v1";
  kind: "LayerPolicy";
  metadata: {
     description?: string;
     group?: string;
     icon?: string;
     labels?: Record<string, string>;
     name: string;
     version?: string;
  };
  spec?: {
     composition_rules?: Record<string, {
        merge_strategy?: "override_full" | "field_level";
        scope_inheritance?: "enabled" | "disabled";
        tenant_overlay?: "field_level" | "none";
     }>;
     layer_id?: string;
     policies?: Record<string, string>;
  };
}>;
```
