# Variable: SafetyRuleSchema

```ts
const SafetyRuleSchema: ZodObject<{
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
}>;
```
