# Interface: QuadrantHint

Quadrant chart configuration for a composition slot.

## Properties

### axis

```ts
readonly axis: "x" | "y";
```

***

### label

```ts
readonly label: string;
```

Axis label. e.g. "Few Skills --> Many Skills".

***

### maxScale

```ts
readonly maxScale: number;
```

Divide doc count by this to normalize to 0..1 range.
