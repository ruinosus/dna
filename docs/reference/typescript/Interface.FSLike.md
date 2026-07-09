# Interface: FSLike

## Methods

### exists()

```ts
exists(path): boolean;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `path` | `string` |

#### Returns

`boolean`

***

### isDirectory()

```ts
isDirectory(path): boolean;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `path` | `string` |

#### Returns

`boolean`

***

### isFile()

```ts
isFile(path): boolean;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `path` | `string` |

#### Returns

`boolean`

***

### mkdir()

```ts
mkdir(path): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `path` | `string` |

#### Returns

`void`

***

### readDir()

```ts
readDir(path): string[];
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `path` | `string` |

#### Returns

`string`[]

***

### readFile()

```ts
readFile(path): string;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `path` | `string` |

#### Returns

`string`

***

### writeFile()

```ts
writeFile(path, content): void;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `path` | `string` |
| `content` | `string` |

#### Returns

`void`
