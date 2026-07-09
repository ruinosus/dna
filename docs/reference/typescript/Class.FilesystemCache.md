# Class: FilesystemCache

WHERE — store/retrieve installed deps.

v1.0: fully async. All four methods may do filesystem / network IO
(FilesystemCache uses fs/promises; Redis/HTTP caches are inherently
async). Hot path concerns about prompt-building are addressed by
caching results in-memory at higher layers, not by sync IO.

## Implements

- [`CachePort`](Interface.CachePort.md)

## Constructors

### Constructor

```ts
new FilesystemCache(baseDir): FilesystemCache;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `baseDir` | `string` |

#### Returns

`FilesystemCache`

## Properties

### baseDir

```ts
readonly baseDir: string;
```

## Methods

### has()

```ts
has(scope, key): Promise<boolean>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `key` | `string` |

#### Returns

`Promise`\<`boolean`\>

#### Implementation of

[`CachePort`](Interface.CachePort.md).[`has`](Interface.CachePort.md#has)

***

### loadAll()

```ts
loadAll(scope, readers?): Promise<Record<string, unknown>[]>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `readers?` | [`ReaderPort`](Interface.ReaderPort.md)[] |

#### Returns

`Promise`\<`Record`\<`string`, `unknown`\>[]\>

#### Implementation of

[`CachePort`](Interface.CachePort.md).[`loadAll`](Interface.CachePort.md#loadall)

***

### loadKey()

```ts
loadKey(
   scope, 
   key, 
readers?): Promise<Record<string, unknown>[]>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `key` | `string` |
| `readers?` | [`ReaderPort`](Interface.ReaderPort.md)[] |

#### Returns

`Promise`\<`Record`\<`string`, `unknown`\>[]\>

#### Implementation of

[`CachePort`](Interface.CachePort.md).[`loadKey`](Interface.CachePort.md#loadkey)

***

### store()

```ts
store(
   scope, 
   key, 
items): Promise<void>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `key` | `string` |
| `items` | [`CacheItem`](Interface.CacheItem.md)[] |

#### Returns

`Promise`\<`void`\>

#### Implementation of

[`CachePort`](Interface.CachePort.md).[`store`](Interface.CachePort.md#store)
