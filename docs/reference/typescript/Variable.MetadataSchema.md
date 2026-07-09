# Variable: MetadataSchema

```ts
const MetadataSchema: ZodObject<{
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
```
