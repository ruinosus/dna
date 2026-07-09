# Variable: RecognizerSchema

```ts
const RecognizerSchema: ZodObject<{
  apiVersion: ZodLiteral<"presidio/v1">;
  kind: ZodLiteral<"Recognizer">;
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
  spec: ZodObject<{
     context: ZodDefault<ZodArray<ZodString, "many">>;
     deny_list: ZodDefault<ZodArray<ZodString, "many">>;
     entity_type: ZodString;
     language: ZodDefault<ZodString>;
     patterns: ZodDefault<ZodArray<ZodObject<{
        name: ZodString;
        regex: ZodString;
        score: ZodNumber;
      }, "strip", ZodTypeAny, {
        name: string;
        regex: string;
        score: number;
      }, {
        name: string;
        regex: string;
        score: number;
     }>, "many">>;
   }, "strip", ZodTypeAny, {
     context: string[];
     deny_list: string[];
     entity_type: string;
     language: string;
     patterns: {
        name: string;
        regex: string;
        score: number;
     }[];
   }, {
     context?: string[];
     deny_list?: string[];
     entity_type: string;
     language?: string;
     patterns?: {
        name: string;
        regex: string;
        score: number;
     }[];
  }>;
}, "strip", ZodTypeAny, {
  apiVersion: "presidio/v1";
  kind: "Recognizer";
  metadata: {
     description: string;
     group: string;
     icon: string;
     labels: Record<string, string>;
     name: string;
     version: string;
  };
  spec: {
     context: string[];
     deny_list: string[];
     entity_type: string;
     language: string;
     patterns: {
        name: string;
        regex: string;
        score: number;
     }[];
  };
}, {
  apiVersion: "presidio/v1";
  kind: "Recognizer";
  metadata: {
     description?: string;
     group?: string;
     icon?: string;
     labels?: Record<string, string>;
     name: string;
     version?: string;
  };
  spec: {
     context?: string[];
     deny_list?: string[];
     entity_type: string;
     language?: string;
     patterns?: {
        name: string;
        regex: string;
        score: number;
     }[];
  };
}>;
```
