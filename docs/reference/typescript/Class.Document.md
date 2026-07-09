# Class: Document\<SpecT\>

Document — unified wrapper for all manifest documents.

1:1 parity with Python dna.v3.kernel.document.

v1.0 — `Document<SpecT>` generic typing. Consumers can declare
spec type at the call site without a runtime cost:

    const doc = mi.documents.find((d) => d.kind === "Asset" && d.name === "x") as Document<AssetSpec>;
    doc.spec.summary?.byte_count;  // type-checker validated

Bare `Document` defaults to `Record<string, unknown>` so existing
untyped code continues working. Purely additive — no API change
for callers that don't opt in.

## Type Parameters

| Type Parameter | Default type |
| ------ | ------ |
| `SpecT` *extends* `Record`\<`string`, `unknown`\> | `Record`\<`string`, `unknown`\> |

## Constructors

### Constructor

```ts
new Document<SpecT>(opts): Document<SpecT>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `opts` | \{ `apiVersion`: `string`; `kind`: `string`; `metadata?`: `Record`\<`string`, `unknown`\>; `name`: `string`; `origin?`: `string`; `raw?`: `Record`\<`string`, `unknown`\>; `spec?`: `Record`\<`string`, `unknown`\>; `typed?`: `unknown`; \} |
| `opts.apiVersion` | `string` |
| `opts.kind` | `string` |
| `opts.metadata?` | `Record`\<`string`, `unknown`\> |
| `opts.name` | `string` |
| `opts.origin?` | `string` |
| `opts.raw?` | `Record`\<`string`, `unknown`\> |
| `opts.spec?` | `Record`\<`string`, `unknown`\> |
| `opts.typed?` | `unknown` |

#### Returns

`Document`\<`SpecT`\>

## Properties

### apiVersion

```ts
readonly apiVersion: string;
```

***

### kind

```ts
readonly kind: string;
```

***

### name

```ts
readonly name: string;
```

***

### origin

```ts
readonly origin: string;
```

***

### raw

```ts
readonly raw: Record<string, unknown>;
```

***

### typed

```ts
readonly typed: unknown;
```

## Accessors

### metadata

#### Get Signature

```ts
get metadata(): Record<string, unknown>;
```

Always returns Record<string, unknown> — typed metadata when available, raw dict otherwise.

##### Returns

`Record`\<`string`, `unknown`\>

***

### spec

#### Get Signature

```ts
get spec(): SpecT;
```

Returns the spec, typed as `SpecT` when consumers parameterize
 the Document. Runtime: still a plain dict.

##### Returns

`SpecT`

## Methods

### fromRaw()

```ts
static fromRaw(
   raw, 
   typed?, 
   origin?): Document;
```

Create a Document from a raw dict.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `raw` | `Record`\<`string`, `unknown`\> |
| `typed?` | `unknown` |
| `origin?` | `string` |

#### Returns

`Document`

***

### toString()

```ts
toString(): string;
```

#### Returns

`string`
