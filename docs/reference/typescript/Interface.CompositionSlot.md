# Interface: CompositionSlot

A named slot in a composition profile. Each slot describes how an
orchestrator kind connects to a target kind.

## Properties

### cardinality

```ts
readonly cardinality: "one" | "many";
```

"one" = scalar ref (soul), "many" = array ref (skills, guardrails).

***

### filterable

```ts
readonly filterable: boolean;
```

If true, buildPrompt callers can filter this slot via enabledSlots.

***

### healthCheck

```ts
readonly healthCheck: HealthCheckHint | null;
```

Health check rule. Null = no health check for this slot.

***

### name

```ts
readonly name: string;
```

The spec field name on the orchestrator that holds refs to this kind.
 e.g. "skills", "soul", "guardrails".

***

### order

```ts
readonly order: number;
```

Rendering order in timeline diagrams. Lower = earlier.

***

### quadrant

```ts
readonly quadrant: QuadrantHint | null;
```

Quadrant chart configuration. Null = not plotted.

***

### targetAlias

```ts
readonly targetAlias: string;
```

Alias of the target KindPort. e.g. "agentskills-skill".

***

### timeline

```ts
readonly timeline: TimelineHint | null;
```

Timeline rendering hints. Null = skip this slot in timelines.
