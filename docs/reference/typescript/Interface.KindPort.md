# Interface: KindPort

WHO — identity + composition role.

Core contract + the optional `KindPresentation` slice. Python's twin
keeps the two apart at runtime (`KindPort` runtime_checkable Protocol
+ `KindPresentation` typing-only capability); TS folds the optional
slice in via `extends` — structural typing has no isinstance gate to
protect.

## Extends

- [`KindPresentation`](Interface.KindPresentation.md)

## Properties

### alias

```ts
readonly alias: string;
```

***

### apiVersion

```ts
readonly apiVersion: string;
```

***

### asciiIcon?

```ts
readonly optional asciiIcon?: string;
```

Single emoji or character for ASCII tree / compact views.

#### Inherited from

[`KindPresentation`](Interface.KindPresentation.md).[`asciiIcon`](Interface.KindPresentation.md#asciiicon)

***

### descriptionFallbackField?

```ts
readonly optional descriptionFallbackField?: string | null;
```

Spec field to derive metadata.description from when none was declared.

#### Inherited from

[`KindPresentation`](Interface.KindPresentation.md).[`descriptionFallbackField`](Interface.KindPresentation.md#descriptionfallbackfield)

***

### displayLabel?

```ts
readonly optional displayLabel?: string;
```

Human-friendly plural label (e.g. "Agents" for Agent).

#### Inherited from

[`KindPresentation`](Interface.KindPresentation.md).[`displayLabel`](Interface.KindPresentation.md#displaylabel)

***

### docs?

```ts
readonly optional docs?: string;
```

Canonical prose documentation. May be overridden at load time by a DOCS.md file
 alongside the extension's source. Resolved prose is cached on `_resolvedDocs`.

#### Inherited from

[`KindPresentation`](Interface.KindPresentation.md).[`docs`](Interface.KindPresentation.md#docs)

***

### flattenInContext

```ts
readonly flattenInContext: boolean;
```

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

#### Inherited from

[`KindPresentation`](Interface.KindPresentation.md).[`graphStyle`](Interface.KindPresentation.md#graphstyle)

***

### isOverlayable?

```ts
readonly optional isOverlayable?: boolean;
```

***

### isPromptTarget

```ts
readonly isPromptTarget: boolean;
```

***

### isRoot

```ts
readonly isRoot: boolean;
```

***

### isRuntimeArtifact

```ts
readonly isRuntimeArtifact: boolean;
```

`true` for Kinds whose documents are produced by runtime workflows
(eval engine, GAIA pipeline, autolab loop, evidence-capture hooks)
rather than authored as source-of-truth. Tools that replicate "the
inputs to the system" — filesystem→Postgres seed, catalog publish,
manifest export — MUST skip Kinds where this is true so they don't
re-inject historical execution data as canonical configuration.
Default `false` (provided by KindBase) keeps existing extensions
unchanged.

***

### isSchemaAffecting?

```ts
readonly optional isSchemaAffecting?: boolean;
```

***

### kind

```ts
readonly kind: string;
```

***

### origin?

```ts
readonly optional origin?: string;
```

***

### plane?

```ts
readonly optional plane?: "record" | "composition";
```

***

### promptTargetPriority

```ts
readonly promptTargetPriority: number;
```

***

### scope?

```ts
readonly optional scope?: TenantScope;
```

Optional tenant scope declaration. When unset (Phase 1 default),
the kernel treats the kind permissively (back-compat). Phase 2
iterates through every Extension to set TENANTED or GLOBAL
explicitly, flipping enforcement on per-Kind. See TenantScope.

***

### scopeInheritable?

```ts
readonly optional scopeInheritable?: boolean;
```

***

### storage

```ts
readonly storage: StorageDescriptor;
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

#### Inherited from

[`KindPresentation`](Interface.KindPresentation.md).[`uiSchema`](Interface.KindPresentation.md#uischema)

***

### visibleInBackend?

```ts
readonly optional visibleInBackend?: boolean | null;
```

Explicit backend-visibility override; unset/null falls back to
 `defaultVisibleInBackend(storage)` — see `resolveVisibleInBackend`.

#### Inherited from

[`KindPresentation`](Interface.KindPresentation.md).[`visibleInBackend`](Interface.KindPresentation.md#visibleinbackend)

## Methods

### dependencies()?

```ts
optional dependencies(): Record<string, string> | null;
```

Which spec fields reference other kinds by alias.
 Clearer name for depFilters().

#### Returns

`Record`\<`string`, `string`\> \| `null`

***

### depFilters()

```ts
depFilters(): Record<string, string> | null;
```

#### Returns

`Record`\<`string`, `string`\> \| `null`

***

### describe()

```ts
describe(doc): string | null;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | [`Document`](Class.Document.md) |

#### Returns

`string` \| `null`

***

### getDefaultAgentName()

```ts
getDefaultAgentName(doc): string | null;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | [`Document`](Class.Document.md) |

#### Returns

`string` \| `null`

***

### getLayerPolicies()

```ts
getLayerPolicies(doc): Record<string, string> | null;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | [`Document`](Class.Document.md) |

#### Returns

`Record`\<`string`, `string`\> \| `null`

***

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

#### Inherited from

[`KindPresentation`](Interface.KindPresentation.md).[`graphMeta`](Interface.KindPresentation.md#graphmeta)

***

### parse()

```ts
parse(raw): unknown;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `raw` | `Record`\<`string`, `unknown`\> |

#### Returns

`unknown`

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

#### Inherited from

[`KindPresentation`](Interface.KindPresentation.md).[`preview`](Interface.KindPresentation.md#preview)

***

### promptTemplate()

```ts
promptTemplate(): string | null;
```

#### Returns

`string` \| `null`

***

### schema()?

```ts
optional schema(): Record<string, unknown> | null;
```

JSON Schema for this kind's spec. Zod-based kinds convert their schema;
 declarative kinds return native JSON Schema.

#### Returns

`Record`\<`string`, `unknown`\> \| `null`

***

### summary()

```ts
summary(doc): Record<string, unknown> | null;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | [`Document`](Class.Document.md) |

#### Returns

`Record`\<`string`, `unknown`\> \| `null`
