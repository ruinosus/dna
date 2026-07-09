# Class: Resource

## Constructors

### Constructor

```ts
new Resource(opts): Resource;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `opts` | \{ `apiVersion`: `string`; `kind`: `string`; `kindRef?`: `KindLike` \| `null`; `metadata?`: `Record`\<`string`, `unknown`\>; `name`: `string`; `origin?`: `string`; `raw?`: `Record`\<`string`, `unknown`\>; `spec?`: `Record`\<`string`, `unknown`\>; `typed?`: `unknown`; \} |
| `opts.apiVersion` | `string` |
| `opts.kind` | `string` |
| `opts.kindRef?` | `KindLike` \| `null` |
| `opts.metadata?` | `Record`\<`string`, `unknown`\> |
| `opts.name` | `string` |
| `opts.origin?` | `string` |
| `opts.raw?` | `Record`\<`string`, `unknown`\> |
| `opts.spec?` | `Record`\<`string`, `unknown`\> |
| `opts.typed?` | `unknown` |

#### Returns

`Resource`

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

### kindRef

```ts
readonly kindRef: KindLike | null;
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
get spec(): Record<string, unknown>;
```

Always returns Record<string, unknown> — typed spec when available, raw dict otherwise.

##### Returns

`Record`\<`string`, `unknown`\>

## Methods

### deps()

```ts
deps(): ResourceDep[];
```

Resolve this resource's outgoing dependency edges using kindRef.depFilters().

Returns one entry per dep_filter field that has a non-empty value in spec.
Scalar spec values (e.g. `soul: "brad"`) become single-element name lists.
Returns empty array when kindRef is null or depFilters() returns null.

#### Returns

[`ResourceDep`](Interface.ResourceDep.md)[]

***

### fromRaw()

```ts
static fromRaw(
   raw, 
   typed?, 
   origin?, 
   kindRef?): Resource;
```

Create a Resource from a raw dict.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `raw` | `Record`\<`string`, `unknown`\> |
| `typed?` | `unknown` |
| `origin?` | `string` |
| `kindRef?` | `KindLike` \| `null` |

#### Returns

`Resource`

***

### toString()

```ts
toString(): string;
```

#### Returns

`string`
