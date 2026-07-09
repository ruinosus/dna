# Variable: SafetyPolicySpecSchema

```ts
const SafetyPolicySpecSchema: ZodObject<{
  action: ZodDefault<ZodEnum<["mask", "block", "log"]>>;
  backend: ZodDefault<ZodEnum<["auto", "transformers", "onnxruntime"]>>;
  budget_ms: ZodDefault<ZodNumber>;
  categories: ZodDefault<ZodNullable<ZodArray<ZodString, "many">>>;
  engine: ZodDefault<ZodEnum<["presidio", "ml-privacy-filter"]>>;
  mask_char: ZodDefault<ZodString>;
  model: ZodDefault<ZodString>;
  recognizers: ZodDefault<ZodArray<ZodString, "many">>;
  rules: ZodDefault<ZodArray<ZodObject<{
     allowed: ZodOptional<ZodArray<ZodString, "many">>;
     categories: ZodOptional<ZodArray<ZodString, "many">>;
     denied: ZodOptional<ZodArray<ZodString, "many">>;
     entities: ZodOptional<ZodArray<ZodString, "many">>;
     patterns: ZodOptional<ZodArray<ZodString, "many">>;
     region: ZodOptional<ZodString>;
     threshold: ZodOptional<ZodNumber>;
     tier: ZodOptional<ZodEnum<["regex", "ml", "api", "llm_judge"]>>;
     type: ZodEnum<["pii", "content_safety", "topic_restriction", "prompt_injection", "banned_words", "custom_regex"]>;
     words: ZodOptional<ZodArray<ZodString, "many">>;
   }, "strip", ZodTypeAny, {
     allowed?: string[];
     categories?: string[];
     denied?: string[];
     entities?: string[];
     patterns?: string[];
     region?: string;
     threshold?: number;
     tier?: "regex" | "ml" | "api" | "llm_judge";
     type:   | "pii"
        | "content_safety"
        | "topic_restriction"
        | "prompt_injection"
        | "banned_words"
        | "custom_regex";
     words?: string[];
   }, {
     allowed?: string[];
     categories?: string[];
     denied?: string[];
     entities?: string[];
     patterns?: string[];
     region?: string;
     threshold?: number;
     tier?: "regex" | "ml" | "api" | "llm_judge";
     type:   | "pii"
        | "content_safety"
        | "topic_restriction"
        | "prompt_injection"
        | "banned_words"
        | "custom_regex";
     words?: string[];
  }>, "many">>;
  scope: ZodDefault<ZodEnum<["input", "output", "both"]>>;
  severity: ZodDefault<ZodEnum<["error", "warn"]>>;
  threshold: ZodDefault<ZodNumber>;
}, "strip", ZodTypeAny, {
  action: "log" | "mask" | "block";
  backend: "auto" | "transformers" | "onnxruntime";
  budget_ms: number;
  categories: string[] | null;
  engine: "presidio" | "ml-privacy-filter";
  mask_char: string;
  model: string;
  recognizers: string[];
  rules: {
     allowed?: string[];
     categories?: string[];
     denied?: string[];
     entities?: string[];
     patterns?: string[];
     region?: string;
     threshold?: number;
     tier?: "regex" | "ml" | "api" | "llm_judge";
     type:   | "pii"
        | "content_safety"
        | "topic_restriction"
        | "prompt_injection"
        | "banned_words"
        | "custom_regex";
     words?: string[];
  }[];
  scope: "input" | "output" | "both";
  severity: "error" | "warn";
  threshold: number;
}, {
  action?: "log" | "mask" | "block";
  backend?: "auto" | "transformers" | "onnxruntime";
  budget_ms?: number;
  categories?: string[] | null;
  engine?: "presidio" | "ml-privacy-filter";
  mask_char?: string;
  model?: string;
  recognizers?: string[];
  rules?: {
     allowed?: string[];
     categories?: string[];
     denied?: string[];
     entities?: string[];
     patterns?: string[];
     region?: string;
     threshold?: number;
     tier?: "regex" | "ml" | "api" | "llm_judge";
     type:   | "pii"
        | "content_safety"
        | "topic_restriction"
        | "prompt_injection"
        | "banned_words"
        | "custom_regex";
     words?: string[];
  }[];
  scope?: "input" | "output" | "both";
  severity?: "error" | "warn";
  threshold?: number;
}>;
```
