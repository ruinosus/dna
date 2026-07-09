# Variable: SafetyPolicySchema

```ts
const SafetyPolicySchema: ZodObject<{
  apiVersion: ZodLiteral<"github.com/ruinosus/dna/v1">;
  kind: ZodLiteral<"SafetyPolicy">;
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
     action: ZodDefault<ZodEnum<["mask", "block", "log"]>>;
     backend: ZodDefault<ZodEnum<["auto", "transformers", "onnxruntime"]>>;
     budget_ms: ZodDefault<ZodNumber>;
     categories: ZodDefault<ZodNullable<ZodArray<ZodString, "many">>>;
     engine: ZodDefault<ZodEnum<["presidio", "ml-privacy-filter"]>>;
     mask_char: ZodDefault<ZodString>;
     model: ZodDefault<ZodString>;
     recognizers: ZodDefault<ZodArray<ZodString, "many">>;
     rules: ZodDefault<ZodArray<ZodObject<{
        allowed: ZodOptional<ZodArray<..., ...>>;
        categories: ZodOptional<ZodArray<..., ...>>;
        denied: ZodOptional<ZodArray<..., ...>>;
        entities: ZodOptional<ZodArray<..., ...>>;
        patterns: ZodOptional<ZodArray<..., ...>>;
        region: ZodOptional<ZodString>;
        threshold: ZodOptional<ZodNumber>;
        tier: ZodOptional<ZodEnum<...>>;
        type: ZodEnum<[..., ..., ..., ..., ..., ...]>;
        words: ZodOptional<ZodArray<..., ...>>;
      }, "strip", ZodTypeAny, {
        allowed?: ...[];
        categories?: ...[];
        denied?: ...[];
        entities?: ...[];
        patterns?: ...[];
        region?: string;
        threshold?: number;
        tier?: "regex" | "ml" | "api" | "llm_judge";
        type:   | "pii"
           | "content_safety"
           | "topic_restriction"
           | "prompt_injection"
           | "banned_words"
           | "custom_regex";
        words?: ...[];
      }, {
        allowed?: ...[];
        categories?: ...[];
        denied?: ...[];
        entities?: ...[];
        patterns?: ...[];
        region?: string;
        threshold?: number;
        tier?: "regex" | "ml" | "api" | "llm_judge";
        type:   | "pii"
           | "content_safety"
           | "topic_restriction"
           | "prompt_injection"
           | "banned_words"
           | "custom_regex";
        words?: ...[];
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
  }>>;
}, "strip", ZodTypeAny, {
  apiVersion: "github.com/ruinosus/dna/v1";
  kind: "SafetyPolicy";
  metadata: {
     description: string;
     group: string;
     icon: string;
     labels: Record<string, string>;
     name: string;
     version: string;
  };
  spec: {
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
  };
}, {
  apiVersion: "github.com/ruinosus/dna/v1";
  kind: "SafetyPolicy";
  metadata: {
     description?: string;
     group?: string;
     icon?: string;
     labels?: Record<string, string>;
     name: string;
     version?: string;
  };
  spec?: {
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
  };
}>;
```
