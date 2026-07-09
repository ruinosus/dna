# Variable: SkillSchema

```ts
const SkillSchema: ZodObject<{
  apiVersion: ZodLiteral<"agentskills.io/v1">;
  kind: ZodLiteral<"Skill">;
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
     assets: ZodDefault<ZodRecord<ZodString, ZodString>>;
     extras: ZodDefault<ZodRecord<ZodString, ZodRecord<ZodString, ZodString>>>;
     instruction: ZodDefault<ZodOptional<ZodString>>;
     references: ZodDefault<ZodRecord<ZodString, ZodString>>;
     root_files: ZodDefault<ZodRecord<ZodString, ZodString>>;
     scripts: ZodDefault<ZodRecord<ZodString, ZodString>>;
   }, "strip", ZodTypeAny, {
     assets: Record<string, string>;
     extras: Record<string, Record<string, string>>;
     instruction: string;
     references: Record<string, string>;
     root_files: Record<string, string>;
     scripts: Record<string, string>;
   }, {
     assets?: Record<string, string>;
     extras?: Record<string, Record<string, string>>;
     instruction?: string;
     references?: Record<string, string>;
     root_files?: Record<string, string>;
     scripts?: Record<string, string>;
  }>>;
}, "strip", ZodTypeAny, {
  apiVersion: "agentskills.io/v1";
  kind: "Skill";
  metadata: {
     description: string;
     group: string;
     icon: string;
     labels: Record<string, string>;
     name: string;
     version: string;
  };
  spec: {
     assets: Record<string, string>;
     extras: Record<string, Record<string, string>>;
     instruction: string;
     references: Record<string, string>;
     root_files: Record<string, string>;
     scripts: Record<string, string>;
  };
}, {
  apiVersion: "agentskills.io/v1";
  kind: "Skill";
  metadata: {
     description?: string;
     group?: string;
     icon?: string;
     labels?: Record<string, string>;
     name: string;
     version?: string;
  };
  spec?: {
     assets?: Record<string, string>;
     extras?: Record<string, Record<string, string>>;
     instruction?: string;
     references?: Record<string, string>;
     root_files?: Record<string, string>;
     scripts?: Record<string, string>;
  };
}>;
```
