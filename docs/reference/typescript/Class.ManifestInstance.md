# Class: ManifestInstance

## Constructors

### Constructor

```ts
new ManifestInstance(opts): ManifestInstance;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `opts` | `ManifestInstanceOpts` |

#### Returns

`ManifestInstance`

## Properties

### \_profiles

```ts
readonly _profiles: readonly CompositionProfile[];
```

Composition profiles registered by extensions.

***

### documents

```ts
readonly documents: Document<Record<string, unknown>>[];
```

***

### resolveErrors

```ts
readonly resolveErrors: string[];
```

***

### scope

```ts
readonly scope: string;
```

## Accessors

### composition

#### Get Signature

```ts
get composition(): CompositionEngine;
```

##### Returns

[`CompositionEngine`](Class.CompositionEngine.md)

***

### compositionResult

#### Get Signature

```ts
get compositionResult(): CompositionResult;
```

##### Returns

[`CompositionResult`](Interface.CompositionResult.md)

***

### lock

#### Get Signature

```ts
get lock(): LockManager;
```

##### Returns

[`LockManager`](Class.LockManager.md)

***

### nav

#### Get Signature

```ts
get nav(): Navigator;
```

##### Returns

[`Navigator`](Class.Navigator.md)

***

### prompt

#### Get Signature

```ts
get prompt(): PromptBuilder;
```

##### Returns

[`PromptBuilder`](Class.PromptBuilder.md)

***

### reports

#### Get Signature

```ts
get reports(): ReportBuilder;
```

##### Returns

[`ReportBuilder`](Class.ReportBuilder.md)

***

### root

#### Get Signature

```ts
get root(): 
  | Document<Record<string, unknown>>
  | null;
```

##### Returns

  \| [`Document`](Class.Document.md)\<`Record`\<`string`, `unknown`\>\>
  \| `null`

## Methods

### ~~all()~~

```ts
all(kind): Document<Record<string, unknown>>[];
```

Return all docs of `kind`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |

#### Returns

[`Document`](Class.Document.md)\<`Record`\<`string`, `unknown`\>\>[]

#### Deprecated

Will be removed in 1.0 — filter `mi.documents`
(e.g. `mi.documents.filter((d) => d.kind === kind)`) or use
`kernel.query(scope, kind)` for indexed/record-plane reads.
(s-blessed-query-surface)

***

### allKinds()

```ts
allKinds(): {
  alias: string;
  apiVersion: string;
  kind: string;
  origin: string | null;
}[];
```

Return every kind REGISTERED in this manifest (not just those that have
documents on disk).

#### Returns

\{
  `alias`: `string`;
  `apiVersion`: `string`;
  `kind`: `string`;
  `origin`: `string` \| `null`;
\}[]

***

### allWhere()

```ts
allWhere(predicate): Document<Record<string, unknown>>[];
```

Return all documents whose registered KindPort satisfies a predicate.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `predicate` | (`kp`) => `boolean` |

#### Returns

[`Document`](Class.Document.md)\<`Record`\<`string`, `unknown`\>\>[]

***

### applyHooks()

```ts
applyHooks(): void;
```

Auto-register Hook documents on the kernel's HookRegistry.

#### Returns

`void`

***

### asciiTree()

```ts
asciiTree(): string;
```

#### Returns

`string`

***

### buildPrompt()

```ts
buildPrompt(opts?): Promise<string>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `opts?` | [`BuildPromptOpts`](Interface.BuildPromptOpts.md) |

#### Returns

`Promise`\<`string`\>

***

### c4ComponentMermaid()

```ts
c4ComponentMermaid(): string;
```

#### Returns

`string`

***

### compositionFlowchartMermaid()

```ts
compositionFlowchartMermaid(): string;
```

#### Returns

`string`

***

### consumersOf()

```ts
consumersOf(kind, name): {
  kind: string;
  name: string;
}[];
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |
| `name` | `string` |

#### Returns

\{
  `kind`: `string`;
  `name`: `string`;
\}[]

***

### defaultAgent()

```ts
defaultAgent(): 
  | Document<Record<string, unknown>>
  | null;
```

#### Returns

  \| [`Document`](Class.Document.md)\<`Record`\<`string`, `unknown`\>\>
  \| `null`

***

### dependencyTree()

```ts
dependencyTree(): Record<string, unknown>;
```

#### Returns

`Record`\<`string`, `unknown`\>

***

### dependencyTreeMermaid()

```ts
dependencyTreeMermaid(): string;
```

#### Returns

`string`

***

### describe()

```ts
describe(kind, name): string;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |
| `name` | `string` |

#### Returns

`string`

***

### erDiagramMermaid()

```ts
erDiagramMermaid(): string;
```

#### Returns

`string`

***

### erModel()

```ts
erModel(): {
  entities: {
     attrs: {
        key: string;
        type: string;
        value: string;
     }[];
     id: string;
     kind: string;
     name: string;
  }[];
  relationships: {
     isMany: boolean;
     label: string;
     sourceId: string;
     targetId: string;
  }[];
};
```

#### Returns

```ts
{
  entities: {
     attrs: {
        key: string;
        type: string;
        value: string;
     }[];
     id: string;
     kind: string;
     name: string;
  }[];
  relationships: {
     isMany: boolean;
     label: string;
     sourceId: string;
     targetId: string;
  }[];
}
```

##### entities

```ts
entities: {
  attrs: {
     key: string;
     type: string;
     value: string;
  }[];
  id: string;
  kind: string;
  name: string;
}[];
```

##### relationships

```ts
relationships: {
  isMany: boolean;
  label: string;
  sourceId: string;
  targetId: string;
}[];
```

***

### exportDiagramsMd()

```ts
exportDiagramsMd(path?): Record<string, string>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `path?` | `string` |

#### Returns

`Record`\<`string`, `string`\>

***

### findAgent()

```ts
findAgent(name): 
  | Document<Record<string, unknown>>
  | null;
```

Find the best prompt-target document matching `name`.
 Considers promptTargetPriority when multiple kinds match.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `name` | `string` |

#### Returns

  \| [`Document`](Class.Document.md)\<`Record`\<`string`, `unknown`\>\>
  \| `null`

***

### generateLock()

```ts
generateLock(): Lockfile;
```

#### Returns

[`Lockfile`](Interface.Lockfile.md)

***

### get()

```ts
get(kind?): {
  apiVersion: string;
  kind: string;
  name: string;
}[];
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind?` | `string` |

#### Returns

\{
  `apiVersion`: `string`;
  `kind`: `string`;
  `name`: `string`;
\}[]

***

### health()

```ts
health(): Record<string, unknown>;
```

#### Returns

`Record`\<`string`, `unknown`\>

***

### impact()

```ts
impact(kind, name): Record<string, unknown>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |
| `name` | `string` |

#### Returns

`Record`\<`string`, `unknown`\>

***

### inventory()

```ts
inventory(): Record<string, unknown>;
```

#### Returns

`Record`\<`string`, `unknown`\>

***

### isRootDoc()

```ts
isRootDoc(doc): boolean;
```

True when the document's KindPort is marked as the manifest root.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | [`Document`](Class.Document.md) |

#### Returns

`boolean`

***

### iterDocDeps()

```ts
iterDocDeps(doc): {
  label: string;
  names: string[];
  targetKind: string;
}[];
```

Iterate a document's declared dep_filters dynamically.
Delegates to CompositionEngine.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | [`Document`](Class.Document.md) |

#### Returns

\{
  `label`: `string`;
  `names`: `string`[];
  `targetKind`: `string`;
\}[]

***

### kindCatalogMermaid()

```ts
kindCatalogMermaid(): string;
```

#### Returns

`string`

***

### kindFor()

```ts
kindFor(kind): KindPort | null;
```

Return the KindPort registered for `kind` (by kind name), or null.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |

#### Returns

[`KindPort`](Interface.KindPort.md) \| `null`

***

### kindForAlias()

```ts
kindForAlias(alias): KindPort | null;
```

Return the KindPort whose `alias` matches, or null.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `alias` | `string` |

#### Returns

[`KindPort`](Interface.KindPort.md) \| `null`

***

### listKinds()

```ts
listKinds(): string[];
```

#### Returns

`string`[]

***

### matrix()

```ts
matrix(): Record<string, unknown>;
```

#### Returns

`Record`\<`string`, `unknown`\>

***

### matrixMarkdown()

```ts
matrixMarkdown(): string;
```

#### Returns

`string`

***

### mindmapMermaid()

```ts
mindmapMermaid(): string;
```

#### Returns

`string`

***

### ~~one()~~

```ts
one(kind, name): 
  | Document<Record<string, unknown>>
  | null;
```

Lookup a single doc by (kind, name).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |
| `name` | `string` |

#### Returns

  \| [`Document`](Class.Document.md)\<`Record`\<`string`, `unknown`\>\>
  \| `null`

#### Deprecated

Will be removed in 1.0 — search `mi.documents`
(e.g. `mi.documents.find((d) => d.kind === kind && d.name === name) ??
null`) or use `kernel.query(scope, kind)` with a filter for
indexed/record-plane reads. (s-blessed-query-surface)

***

### pieChartMermaid()

```ts
pieChartMermaid(): string;
```

#### Returns

`string`

***

### profileFor()

```ts
profileFor(doc): CompositionProfile | null;
```

Find the CompositionProfile for a document's kind (via its alias).
Returns null if no profile covers this kind.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `doc` | [`Document`](Class.Document.md) |

#### Returns

[`CompositionProfile`](Interface.CompositionProfile.md) \| `null`

***

### quadrantMermaid()

```ts
quadrantMermaid(): string;
```

#### Returns

`string`

***

### readMetadata()

```ts
readMetadata(
   kind, 
   name, 
   field): unknown;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |
| `name` | `string` |
| `field` | `string` |

#### Returns

`unknown`

***

### readSpec()

```ts
readSpec(
   kind, 
   name, 
   field): unknown;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |
| `name` | `string` |
| `field` | `string` |

#### Returns

`unknown`

***

### readSpecString()

```ts
readSpecString(
   kind, 
   name, 
   field): string | undefined;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |
| `name` | `string` |
| `field` | `string` |

#### Returns

`string` \| `undefined`

***

### readSpecStringArray()

```ts
readSpecStringArray(
   kind, 
   name, 
   field): string[];
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |
| `name` | `string` |
| `field` | `string` |

#### Returns

`string`[]

***

### ref()

```ts
ref(value): Promise<string>;
```

Resolve a ref-like value (path or markdown/yaml/txt filename).

v1.0 async refactor: SourcePort.resolveRef is async, so this is
async too. Cascades to PromptBuilder.build() and
ManifestInstance.buildPrompt() — every prompt build is async.
That's the honest contract — the alternative (cache-based sync
ref) requires knowing every ref at scope load time, which doesn't
hold for dynamic context fields.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `value` | `string` |

#### Returns

`Promise`\<`string`\>

***

### renderDoc()

```ts
renderDoc(kind, name): PreviewBlock[];
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kind` | `string` |
| `name` | `string` |

#### Returns

[`PreviewBlock`](Interface.PreviewBlock.md)[]

***

### resolve()

```ts
resolve(layers?): ManifestInstance;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `layers?` | `Record`\<`string`, `string`\> |

#### Returns

`ManifestInstance`

***

### sankeyMermaid()

```ts
sankeyMermaid(): string;
```

#### Returns

`string`

***

### summary()

```ts
summary(): string;
```

#### Returns

`string`

***

### timelineMermaid()

```ts
timelineMermaid(): string;
```

#### Returns

`string`
