# Interface: BundleHandle

## Properties

### name

```ts
readonly name: string;
```

Bundle directory name (used as default doc name when frontmatter
 omits `metadata.name`).

***

### path

```ts
readonly path: string | null;
```

Filesystem path when the handle wraps a real directory; null
otherwise. ESCAPE HATCH — prefer explicit read/write/iter methods.
Use only when an external library demands a real path (e.g.
`fs.cp`, third-party tooling).

## Methods

### exists()

```ts
exists(entry): Promise<boolean>;
```

True if the named entry (file or directory) exists in this bundle.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `entry` | `string` |

#### Returns

`Promise`\<`boolean`\>

***

### isFile()

```ts
isFile(entry): Promise<boolean>;
```

True if `entry` points at a regular file (not a directory).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `entry` | `string` |

#### Returns

`Promise`\<`boolean`\>

***

### iterEntries()

```ts
iterEntries(recursive?): Promise<string[]>;
```

Yield entry names (relative to the bundle root).

When `recursive=false` (default), only direct children are
yielded — both regular files and subdirectories.
When `recursive=true`, descend into subdirectories yielding only
regular files (no directory entries).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `recursive?` | `boolean` |

#### Returns

`Promise`\<`string`[]\>

***

### readBytes()

```ts
readBytes(entry): Promise<Uint8Array<ArrayBufferLike>>;
```

Read entry content as bytes. Throws if absent.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `entry` | `string` |

#### Returns

`Promise`\<`Uint8Array`\<`ArrayBufferLike`\>\>

***

### readText()

```ts
readText(entry, encoding?): Promise<string>;
```

Read entry content as text. Throws if absent.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `entry` | `string` |
| `encoding?` | `BufferEncoding` |

#### Returns

`Promise`\<`string`\>

***

### writeBytes()

```ts
writeBytes(entry, content): Promise<void>;
```

Write bytes. Read-only handles throw.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `entry` | `string` |
| `content` | `Uint8Array` |

#### Returns

`Promise`\<`void`\>

***

### writeText()

```ts
writeText(
   entry, 
   content, 
encoding?): Promise<void>;
```

Write text content. Read-only handles throw.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `entry` | `string` |
| `content` | `string` |
| `encoding?` | `BufferEncoding` |

#### Returns

`Promise`\<`void`\>
