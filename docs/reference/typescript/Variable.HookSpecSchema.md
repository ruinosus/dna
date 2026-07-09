# Variable: HookSpecSchema

```ts
const HookSpecSchema: ZodObject<{
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
}>;
```
