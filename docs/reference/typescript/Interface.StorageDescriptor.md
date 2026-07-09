# Interface: StorageDescriptor

## Properties

### bodyAs?

```ts
optional bodyAs?: BodyMode;
```

***

### bodyField?

```ts
optional bodyField?: string;
```

***

### bodyParser?

```ts
optional bodyParser?: (body) => Record<string, unknown>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `body` | `string` |

#### Returns

`Record`\<`string`, `unknown`\>

***

### container

```ts
container: string;
```

***

### marker?

```ts
optional marker?: string;
```

***

### pattern

```ts
pattern: StoragePattern;
```
