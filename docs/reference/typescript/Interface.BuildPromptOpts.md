# Interface: BuildPromptOpts

## Properties

### agent?

```ts
optional agent?: string;
```

***

### context?

```ts
optional context?: Record<string, unknown>;
```

***

### ~~enabledGuardrails?~~

```ts
optional enabledGuardrails?: string[];
```

#### Deprecated

Use enabledSlots.guardrails instead.

***

### ~~enabledSkills?~~

```ts
optional enabledSkills?: string[];
```

#### Deprecated

Use enabledSlots.skills instead. Kept for backwards compat.

***

### enabledSlots?

```ts
optional enabledSlots?: Record<string, string[]>;
```

Generic slot filtering: keys are slot names from the CompositionProfile,
 values are arrays of doc names to keep.
