# Class: DeclarativeKindPort

WHO — identity + composition role.

Core contract + the optional `KindPresentation` slice. Python's twin
keeps the two apart at runtime (`KindPort` runtime_checkable Protocol
+ `KindPresentation` typing-only capability); TS folds the optional
slice in via `extends` — structural typing has no isinstance gate to
protect.

## Implements

- [`KindPort`](Interface.KindPort.md)
- `DeclarativeMarker`

## Constructors

### Constructor

```ts
new DeclarativeKindPort(typedDef): DeclarativeKindPort;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `typedDef` | \{ `apiVersion`: `"github.com/ruinosus/dna/core/v1"`; `kind`: `"KindDefinition"`; `metadata`: \{ `description`: `string`; `group`: `string`; `icon`: `string`; `labels`: `Record`\<`string`, `string`\>; `name`: `string`; `version`: `string`; \}; `spec`: \{ `alias`: `string`; `ascii_icon?`: `string` \| `null`; `default_agent?`: `string` \| `null`; `default_agent_field?`: `string` \| `null`; `dep_filters?`: `Record`\<`string`, `string`\> \| `null`; `describe?`: `string` \| `Record`\<`string`, `unknown`\> \| `null`; `description_fallback_field?`: `string` \| `null`; `display_label?`: `string` \| `null`; `docs?`: `string`; `embed?`: `string`[] \| `null`; `flatten_in_context`: `boolean`; `graph_style?`: `Record`\<`string`, `string`\> \| `null`; `is_overlayable`: `boolean`; `is_root`: `boolean`; `is_runtime_artifact`: `boolean`; `origin`: `string`; `plane`: `"record"` \| `"composition"`; `prompt_target`: `boolean`; `prompt_target_priority`: `number`; `schema`: `Record`\<`string`, `unknown`\>; `scope_inheritable`: `boolean`; `spec_defaults?`: `Record`\<`string`, `unknown`\> \| `null`; `storage`: `Record`\<`string`, `unknown`\>; `summary`: `Record`\<`string`, `unknown`\> \| `null`; `target_api_version`: `string`; `target_kind`: `string`; `tenant_scope`: `"tenanted"` \| `"global"`; `tenant_scope_declared`: `boolean`; `ui?`: `Record`\<`string`, `unknown`\> \| `null`; `ui_schema?`: `Record`\<`string`, `unknown`\> \| `null`; `volatile_spec_fields?`: `string`[] \| `null`; \}; \} |
| `typedDef.apiVersion` | `"github.com/ruinosus/dna/core/v1"` |
| `typedDef.kind` | `"KindDefinition"` |
| `typedDef.metadata` | \{ `description`: `string`; `group`: `string`; `icon`: `string`; `labels`: `Record`\<`string`, `string`\>; `name`: `string`; `version`: `string`; \} |
| `typedDef.metadata.description` | `string` |
| `typedDef.metadata.group` | `string` |
| `typedDef.metadata.icon` | `string` |
| `typedDef.metadata.labels` | `Record`\<`string`, `string`\> |
| `typedDef.metadata.name` | `string` |
| `typedDef.metadata.version` | `string` |
| `typedDef.spec` | \{ `alias`: `string`; `ascii_icon?`: `string` \| `null`; `default_agent?`: `string` \| `null`; `default_agent_field?`: `string` \| `null`; `dep_filters?`: `Record`\<`string`, `string`\> \| `null`; `describe?`: `string` \| `Record`\<`string`, `unknown`\> \| `null`; `description_fallback_field?`: `string` \| `null`; `display_label?`: `string` \| `null`; `docs?`: `string`; `embed?`: `string`[] \| `null`; `flatten_in_context`: `boolean`; `graph_style?`: `Record`\<`string`, `string`\> \| `null`; `is_overlayable`: `boolean`; `is_root`: `boolean`; `is_runtime_artifact`: `boolean`; `origin`: `string`; `plane`: `"record"` \| `"composition"`; `prompt_target`: `boolean`; `prompt_target_priority`: `number`; `schema`: `Record`\<`string`, `unknown`\>; `scope_inheritable`: `boolean`; `spec_defaults?`: `Record`\<`string`, `unknown`\> \| `null`; `storage`: `Record`\<`string`, `unknown`\>; `summary`: `Record`\<`string`, `unknown`\> \| `null`; `target_api_version`: `string`; `target_kind`: `string`; `tenant_scope`: `"tenanted"` \| `"global"`; `tenant_scope_declared`: `boolean`; `ui?`: `Record`\<`string`, `unknown`\> \| `null`; `ui_schema?`: `Record`\<`string`, `unknown`\> \| `null`; `volatile_spec_fields?`: `string`[] \| `null`; \} |
| `typedDef.spec.alias` | `string` |
| `typedDef.spec.ascii_icon?` | `string` \| `null` |
| `typedDef.spec.default_agent?` | `string` \| `null` |
| `typedDef.spec.default_agent_field?` | `string` \| `null` |
| `typedDef.spec.dep_filters?` | `Record`\<`string`, `string`\> \| `null` |
| `typedDef.spec.describe?` | `string` \| `Record`\<`string`, `unknown`\> \| `null` |
| `typedDef.spec.description_fallback_field?` | `string` \| `null` |
| `typedDef.spec.display_label?` | `string` \| `null` |
| `typedDef.spec.docs?` | `string` |
| `typedDef.spec.embed?` | `string`[] \| `null` |
| `typedDef.spec.flatten_in_context` | `boolean` |
| `typedDef.spec.graph_style?` | `Record`\<`string`, `string`\> \| `null` |
| `typedDef.spec.is_overlayable` | `boolean` |
| `typedDef.spec.is_root` | `boolean` |
| `typedDef.spec.is_runtime_artifact` | `boolean` |
| `typedDef.spec.origin` | `string` |
| `typedDef.spec.plane` | `"record"` \| `"composition"` |
| `typedDef.spec.prompt_target` | `boolean` |
| `typedDef.spec.prompt_target_priority` | `number` |
| `typedDef.spec.schema` | `Record`\<`string`, `unknown`\> |
| `typedDef.spec.scope_inheritable` | `boolean` |
| `typedDef.spec.spec_defaults?` | `Record`\<`string`, `unknown`\> \| `null` |
| `typedDef.spec.storage` | `Record`\<`string`, `unknown`\> |
| `typedDef.spec.summary` | `Record`\<`string`, `unknown`\> \| `null` |
| `typedDef.spec.target_api_version` | `string` |
| `typedDef.spec.target_kind` | `string` |
| `typedDef.spec.tenant_scope` | `"tenanted"` \| `"global"` |
| `typedDef.spec.tenant_scope_declared` | `boolean` |
| `typedDef.spec.ui?` | `Record`\<`string`, `unknown`\> \| `null` |
| `typedDef.spec.ui_schema?` | `Record`\<`string`, `unknown`\> \| `null` |
| `typedDef.spec.volatile_spec_fields?` | `string`[] \| `null` |

#### Returns

`DeclarativeKindPort`

## Properties

### \_\_declarative\_\_

```ts
readonly __declarative__: true;
```

#### Implementation of

```ts
DeclarativeMarker.__declarative__
```

***

### alias

```ts
readonly alias: string;
```

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`alias`](Interface.KindPort.md#alias)

***

### apiVersion

```ts
readonly apiVersion: string;
```

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`apiVersion`](Interface.KindPort.md#apiversion)

***

### asciiIcon

```ts
readonly asciiIcon: string;
```

Single emoji or character for ASCII tree / compact views.

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`asciiIcon`](Interface.KindPort.md#asciiicon)

***

### descriptionFallbackField?

```ts
readonly optional descriptionFallbackField?: string;
```

Spec field to derive metadata.description from when none was declared.

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`descriptionFallbackField`](Interface.KindPort.md#descriptionfallbackfield)

***

### displayLabel

```ts
readonly displayLabel: string;
```

Human-friendly plural label (e.g. "Agents" for Agent).

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`displayLabel`](Interface.KindPort.md#displaylabel)

***

### docs?

```ts
readonly optional docs?: string;
```

Canonical prose documentation. May be overridden at load time by a DOCS.md file
 alongside the extension's source. Resolved prose is cached on `_resolvedDocs`.

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`docs`](Interface.KindPort.md#docs)

***

### embedFields

```ts
readonly embedFields: string[] | null;
```

***

### flattenInContext

```ts
readonly flattenInContext: boolean;
```

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`flattenInContext`](Interface.KindPort.md#flattenincontext)

***

### graphStyle

```ts
readonly graphStyle: {
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

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`graphStyle`](Interface.KindPort.md#graphstyle)

***

### isOverlayable

```ts
readonly isOverlayable: boolean;
```

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`isOverlayable`](Interface.KindPort.md#isoverlayable)

***

### isPromptTarget

```ts
readonly isPromptTarget: boolean;
```

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`isPromptTarget`](Interface.KindPort.md#isprompttarget)

***

### isRoot

```ts
readonly isRoot: boolean;
```

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`isRoot`](Interface.KindPort.md#isroot)

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

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`isRuntimeArtifact`](Interface.KindPort.md#isruntimeartifact)

***

### jsonSchema

```ts
readonly jsonSchema: Record<string, unknown>;
```

Public read-only view of the JSON Schema authored in the KindDefinition.
 Consumers like the Studio's NewDocumentWizard use this to pre-populate
 required fields with empty-but-valid stubs.

***

### kind

```ts
readonly kind: string;
```

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`kind`](Interface.KindPort.md#kind)

***

### origin

```ts
readonly origin: string;
```

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`origin`](Interface.KindPort.md#origin)

***

### plane

```ts
readonly plane: "record" | "composition";
```

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`plane`](Interface.KindPort.md#plane)

***

### promptTargetPriority

```ts
readonly promptTargetPriority: number;
```

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`promptTargetPriority`](Interface.KindPort.md#prompttargetpriority)

***

### scope?

```ts
readonly optional scope?: TenantScope;
```

Optional tenant scope declaration. When unset (Phase 1 default),
the kernel treats the kind permissively (back-compat). Phase 2
iterates through every Extension to set TENANTED or GLOBAL
explicitly, flipping enforcement on per-Kind. See TenantScope.

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`scope`](Interface.KindPort.md#scope)

***

### scopeInheritable

```ts
readonly scopeInheritable: boolean;
```

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`scopeInheritable`](Interface.KindPort.md#scopeinheritable)

***

### storage

```ts
readonly storage: StorageDescriptor;
```

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`storage`](Interface.KindPort.md#storage)

***

### ui?

```ts
readonly optional ui?: StudioUIMetadata;
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

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`uiSchema`](Interface.KindPort.md#uischema)

***

### volatileSpecFields

```ts
readonly volatileSpecFields: ReadonlySet<string>;
```

## Methods

### dependencies()

```ts
dependencies(): Record<string, string> | null;
```

Which spec fields reference other kinds by alias.
 Clearer name for depFilters().

#### Returns

`Record`\<`string`, `string`\> \| `null`

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`dependencies`](Interface.KindPort.md#dependencies)

***

### depFilters()

```ts
depFilters(): Record<string, string> | null;
```

#### Returns

`Record`\<`string`, `string`\> \| `null`

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`depFilters`](Interface.KindPort.md#depfilters)

***

### describe()

```ts
describe(doc): string | null;
```

Display string for a doc (spec D3).
 - Template form (string): substitute `{field}` placeholders from the
   spec top level; a missing/None field renders as "".
 - Projection form ({path: field}): return the spec field verbatim (or
   null if absent).
 - No `describe` declared → null (today's behavior).
 Twin of Python DeclarativeKindPort.describe.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | [`Document`](Class.Document.md) |

#### Returns

`string` \| `null`

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`describe`](Interface.KindPort.md#describe)

***

### fromTyped()

```ts
static fromTyped(typedDef): DeclarativeKindPort;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `typedDef` | \{ `apiVersion`: `"github.com/ruinosus/dna/core/v1"`; `kind`: `"KindDefinition"`; `metadata`: \{ `description`: `string`; `group`: `string`; `icon`: `string`; `labels`: `Record`\<`string`, `string`\>; `name`: `string`; `version`: `string`; \}; `spec`: \{ `alias`: `string`; `ascii_icon?`: `string` \| `null`; `default_agent?`: `string` \| `null`; `default_agent_field?`: `string` \| `null`; `dep_filters?`: `Record`\<`string`, `string`\> \| `null`; `describe?`: `string` \| `Record`\<`string`, `unknown`\> \| `null`; `description_fallback_field?`: `string` \| `null`; `display_label?`: `string` \| `null`; `docs?`: `string`; `embed?`: `string`[] \| `null`; `flatten_in_context`: `boolean`; `graph_style?`: `Record`\<`string`, `string`\> \| `null`; `is_overlayable`: `boolean`; `is_root`: `boolean`; `is_runtime_artifact`: `boolean`; `origin`: `string`; `plane`: `"record"` \| `"composition"`; `prompt_target`: `boolean`; `prompt_target_priority`: `number`; `schema`: `Record`\<`string`, `unknown`\>; `scope_inheritable`: `boolean`; `spec_defaults?`: `Record`\<`string`, `unknown`\> \| `null`; `storage`: `Record`\<`string`, `unknown`\>; `summary`: `Record`\<`string`, `unknown`\> \| `null`; `target_api_version`: `string`; `target_kind`: `string`; `tenant_scope`: `"tenanted"` \| `"global"`; `tenant_scope_declared`: `boolean`; `ui?`: `Record`\<`string`, `unknown`\> \| `null`; `ui_schema?`: `Record`\<`string`, `unknown`\> \| `null`; `volatile_spec_fields?`: `string`[] \| `null`; \}; \} |
| `typedDef.apiVersion` | `"github.com/ruinosus/dna/core/v1"` |
| `typedDef.kind` | `"KindDefinition"` |
| `typedDef.metadata` | \{ `description`: `string`; `group`: `string`; `icon`: `string`; `labels`: `Record`\<`string`, `string`\>; `name`: `string`; `version`: `string`; \} |
| `typedDef.metadata.description` | `string` |
| `typedDef.metadata.group` | `string` |
| `typedDef.metadata.icon` | `string` |
| `typedDef.metadata.labels` | `Record`\<`string`, `string`\> |
| `typedDef.metadata.name` | `string` |
| `typedDef.metadata.version` | `string` |
| `typedDef.spec` | \{ `alias`: `string`; `ascii_icon?`: `string` \| `null`; `default_agent?`: `string` \| `null`; `default_agent_field?`: `string` \| `null`; `dep_filters?`: `Record`\<`string`, `string`\> \| `null`; `describe?`: `string` \| `Record`\<`string`, `unknown`\> \| `null`; `description_fallback_field?`: `string` \| `null`; `display_label?`: `string` \| `null`; `docs?`: `string`; `embed?`: `string`[] \| `null`; `flatten_in_context`: `boolean`; `graph_style?`: `Record`\<`string`, `string`\> \| `null`; `is_overlayable`: `boolean`; `is_root`: `boolean`; `is_runtime_artifact`: `boolean`; `origin`: `string`; `plane`: `"record"` \| `"composition"`; `prompt_target`: `boolean`; `prompt_target_priority`: `number`; `schema`: `Record`\<`string`, `unknown`\>; `scope_inheritable`: `boolean`; `spec_defaults?`: `Record`\<`string`, `unknown`\> \| `null`; `storage`: `Record`\<`string`, `unknown`\>; `summary`: `Record`\<`string`, `unknown`\> \| `null`; `target_api_version`: `string`; `target_kind`: `string`; `tenant_scope`: `"tenanted"` \| `"global"`; `tenant_scope_declared`: `boolean`; `ui?`: `Record`\<`string`, `unknown`\> \| `null`; `ui_schema?`: `Record`\<`string`, `unknown`\> \| `null`; `volatile_spec_fields?`: `string`[] \| `null`; \} |
| `typedDef.spec.alias` | `string` |
| `typedDef.spec.ascii_icon?` | `string` \| `null` |
| `typedDef.spec.default_agent?` | `string` \| `null` |
| `typedDef.spec.default_agent_field?` | `string` \| `null` |
| `typedDef.spec.dep_filters?` | `Record`\<`string`, `string`\> \| `null` |
| `typedDef.spec.describe?` | `string` \| `Record`\<`string`, `unknown`\> \| `null` |
| `typedDef.spec.description_fallback_field?` | `string` \| `null` |
| `typedDef.spec.display_label?` | `string` \| `null` |
| `typedDef.spec.docs?` | `string` |
| `typedDef.spec.embed?` | `string`[] \| `null` |
| `typedDef.spec.flatten_in_context` | `boolean` |
| `typedDef.spec.graph_style?` | `Record`\<`string`, `string`\> \| `null` |
| `typedDef.spec.is_overlayable` | `boolean` |
| `typedDef.spec.is_root` | `boolean` |
| `typedDef.spec.is_runtime_artifact` | `boolean` |
| `typedDef.spec.origin` | `string` |
| `typedDef.spec.plane` | `"record"` \| `"composition"` |
| `typedDef.spec.prompt_target` | `boolean` |
| `typedDef.spec.prompt_target_priority` | `number` |
| `typedDef.spec.schema` | `Record`\<`string`, `unknown`\> |
| `typedDef.spec.scope_inheritable` | `boolean` |
| `typedDef.spec.spec_defaults?` | `Record`\<`string`, `unknown`\> \| `null` |
| `typedDef.spec.storage` | `Record`\<`string`, `unknown`\> |
| `typedDef.spec.summary` | `Record`\<`string`, `unknown`\> \| `null` |
| `typedDef.spec.target_api_version` | `string` |
| `typedDef.spec.target_kind` | `string` |
| `typedDef.spec.tenant_scope` | `"tenanted"` \| `"global"` |
| `typedDef.spec.tenant_scope_declared` | `boolean` |
| `typedDef.spec.ui?` | `Record`\<`string`, `unknown`\> \| `null` |
| `typedDef.spec.ui_schema?` | `Record`\<`string`, `unknown`\> \| `null` |
| `typedDef.spec.volatile_spec_fields?` | `string`[] \| `null` |

#### Returns

`DeclarativeKindPort`

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

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`getDefaultAgentName`](Interface.KindPort.md#getdefaultagentname)

***

### getLayerPolicies()

```ts
getLayerPolicies(_doc): Record<string, string> | null;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `_doc` | [`Document`](Class.Document.md) |

#### Returns

`Record`\<`string`, `string`\> \| `null`

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`getLayerPolicies`](Interface.KindPort.md#getlayerpolicies)

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

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`parse`](Interface.KindPort.md#parse)

***

### preview()

```ts
preview(doc): PreviewBlock[];
```

Preview blocks derived from the kind's JSON schema. Walks the
top-level `properties` of `jsonSchema` and renders each one based on
its declared type:
  - string with format=markdown OR maxLength>=400 → markdown block
  - string                                       → fields entry
  - integer / number / boolean                    → fields entry
  - array of strings                              → fields entry (bullets)
  - array of objects / object                     → code block (json)
  - enum                                          → fields entry

Required fields surface first, optional after.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | [`Document`](Class.Document.md) |

#### Returns

[`PreviewBlock`](Interface.PreviewBlock.md)[]

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`preview`](Interface.KindPort.md#preview)

***

### promptTemplate()

```ts
promptTemplate(): string | null;
```

#### Returns

`string` \| `null`

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`promptTemplate`](Interface.KindPort.md#prompttemplate)

***

### schema()

```ts
schema(): Record<string, unknown> | null;
```

JSON Schema for this kind's spec. Zod-based kinds convert their schema;
 declarative kinds return native JSON Schema.

#### Returns

`Record`\<`string`, `unknown`\> \| `null`

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`schema`](Interface.KindPort.md#schema)

***

### summary()

```ts
summary(doc): Record<string, unknown> | null;
```

Declarative projection (F3 spec D2): when the KindDefinition declares
 `summary: {field: <plain default | projection object>}`, project the
 doc's spec. A PLAIN value keeps today's meaning (present field from
 spec, else the declared default). A PROJECTION object runs the closed
 vocabulary (count_of/path/paths/format + combinators). No declaration →
 null (today's behavior). Twin of Python DeclarativeKindPort.summary.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | [`Document`](Class.Document.md) |

#### Returns

`Record`\<`string`, `unknown`\> \| `null`

#### Implementation of

[`KindPort`](Interface.KindPort.md).[`summary`](Interface.KindPort.md#summary)
