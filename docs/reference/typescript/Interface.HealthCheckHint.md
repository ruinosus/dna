# Interface: HealthCheckHint

Health check rule for a composition slot.

## Properties

### issueKey

```ts
readonly issueKey: string;
```

Key in the health report output dict. e.g. "agents_without_guardrails".

***

### message

```ts
readonly message: string;
```

Human message for the issue.

***

### rule

```ts
readonly rule: "at-least-one" | "has-error-severity";
```

"at-least-one": agent must reference ≥1 doc of this slot.
 "has-error-severity": at least one doc of this kind with
 severity=error must be referenced.

***

### severity

```ts
readonly severity: "error" | "warn";
```
