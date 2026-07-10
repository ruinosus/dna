# Interface: CompositionProfile

A CompositionProfile describes how an orchestrator kind connects to
other kinds. Registered by extensions via kernel.compositionProfile().

## Properties

### label

```ts
readonly label: string;
```

Human-readable label for the profile. e.g. "Helix Agent".

***

### orchestratorAlias

```ts
readonly orchestratorAlias: string;
```

Alias of the orchestrator KindPort. e.g. "helix-agent".

***

### slots

```ts
readonly slots: readonly CompositionSlot[];
```

Ordered list of composition slots.
