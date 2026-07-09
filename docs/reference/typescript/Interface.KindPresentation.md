# Interface: KindPresentation

Optional presentation/UX capability of a Kind.

Py twin: the `KindPresentation` capability Protocol in protocols.py —
kept OFF Python's runtime_checkable `KindPort` so the H1 isinstance
registration gate never requires these members on a minimal Kind
(s-dna-kindport-descriptor-schema). TS interfaces express the same
contract natively as optional members; `KindPort` extends this slice.
The Py↔TS pairing is tracked in
`tests/parity-fixtures/port-surface-parity.json` (KindPresentation port).

## Extended by

- [`KindPort`](Interface.KindPort.md)

## Properties

### asciiIcon?

```ts
readonly optional asciiIcon?: string;
```

Single emoji or character for ASCII tree / compact views.

***

### descriptionFallbackField?

```ts
readonly optional descriptionFallbackField?: string | null;
```

Spec field to derive metadata.description from when none was declared.

***

### displayLabel?

```ts
readonly optional displayLabel?: string;
```

Human-friendly plural label (e.g. "Agents" for Agent).

***

### docs?

```ts
readonly optional docs?: string;
```

Canonical prose documentation. May be overridden at load time by a DOCS.md file
 alongside the extension's source. Resolved prose is cached on `_resolvedDocs`.

***

### graphStyle?

```ts
readonly optional graphStyle?: {
  fill: string;
  stroke: string;
  textColor: string;
};
```

Colors for mermaid diagrams, graph nodes, and other visualizations.

#### fill

```ts
fill: string;
```

#### stroke

```ts
stroke: string;
```

#### textColor

```ts
textColor: string;
```

***

### uiSchema?

```ts
readonly optional uiSchema?: Record<string, Record<string, unknown>>;
```

Per-field UI hints for Studio form rendering, keyed by spec field
 name (widget/label/help/language/height/order — see
 `docs/KIND-UI-HINTS.md`). When absent, consumers infer the widget
 from the value type.

***

### visibleInBackend?

```ts
readonly optional visibleInBackend?: boolean | null;
```

Explicit backend-visibility override; unset/null falls back to
 `defaultVisibleInBackend(storage)` — see `resolveVisibleInBackend`.

## Methods

### graphMeta()?

```ts
optional graphMeta(doc): Record<string, unknown> | null;
```

Per-doc annotations for graph rendering and health checks.
 e.g. Guardrail returns {severity, scope, rules}.
 Agent returns {model, soul, skills_count}.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | [`Document`](Class.Document.md) |

#### Returns

`Record`\<`string`, `unknown`\> \| `null`

***

### preview()?

```ts
optional preview(doc): PreviewBlock[];
```

Optional: returns renderable blocks for the Studio's preview pane.
Each extension implements this for its own kinds. When undefined,
the kernel falls back to `genericSpecDump` from preview.ts.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | [`Document`](Class.Document.md) |

#### Returns

[`PreviewBlock`](Interface.PreviewBlock.md)[]
