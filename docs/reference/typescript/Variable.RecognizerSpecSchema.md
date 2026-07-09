# Variable: RecognizerSpecSchema

```ts
const RecognizerSpecSchema: ZodObject<{
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
```
