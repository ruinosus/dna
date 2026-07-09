# Variable: SoulSchema

```ts
const SoulSchema: ZodObject<{
  apiVersion: ZodLiteral<"soulspec.org/v1">;
  kind: ZodLiteral<"Soul">;
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
     agents_content: ZodDefault<ZodOptional<ZodString>>;
     soul_content: ZodDefault<ZodOptional<ZodString>>;
     soul_json: ZodOptional<ZodRecord<ZodString, ZodUnknown>>;
     style_content: ZodDefault<ZodOptional<ZodString>>;
   }, "strip", ZodTypeAny, {
     agents_content: string;
     soul_content: string;
     soul_json?: Record<string, unknown>;
     style_content: string;
   }, {
     agents_content?: string;
     soul_content?: string;
     soul_json?: Record<string, unknown>;
     style_content?: string;
  }>>;
}, "strip", ZodTypeAny, {
  apiVersion: "soulspec.org/v1";
  kind: "Soul";
  metadata: {
     description: string;
     group: string;
     icon: string;
     labels: Record<string, string>;
     name: string;
     version: string;
  };
  spec: {
     agents_content: string;
     soul_content: string;
     soul_json?: Record<string, unknown>;
     style_content: string;
  };
}, {
  apiVersion: "soulspec.org/v1";
  kind: "Soul";
  metadata: {
     description?: string;
     group?: string;
     icon?: string;
     labels?: Record<string, string>;
     name: string;
     version?: string;
  };
  spec?: {
     agents_content?: string;
     soul_content?: string;
     soul_json?: Record<string, unknown>;
     style_content?: string;
  };
}>;
```
