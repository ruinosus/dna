# Variable: SD

```ts
const SD: {
  bundle: StorageDescriptor;
  root: StorageDescriptor;
  standalone: StorageDescriptor;
  yaml: StorageDescriptor;
};
```

## Type Declaration

### bundle()

```ts
bundle(
   container, 
   marker, 
   bodyAs?, 
   bodyField?): StorageDescriptor;
```

#### Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `container` | `string` | `undefined` |
| `marker` | `string` | `undefined` |
| `bodyAs` | [`BodyMode`](TypeAlias.BodyMode.md) | `"text"` |
| `bodyField` | `string` | `"instruction"` |

#### Returns

[`StorageDescriptor`](Interface.StorageDescriptor.md)

### root()

```ts
root(filename?): StorageDescriptor;
```

#### Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `filename` | `string` | `"manifest.yaml"` |

#### Returns

[`StorageDescriptor`](Interface.StorageDescriptor.md)

### standalone()

```ts
standalone(
   filename, 
   bodyAs?, 
   bodyField?): StorageDescriptor;
```

#### Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `filename` | `string` | `undefined` |
| `bodyAs` | [`BodyMode`](TypeAlias.BodyMode.md) | `"text"` |
| `bodyField` | `string` | `"content"` |

#### Returns

[`StorageDescriptor`](Interface.StorageDescriptor.md)

### yaml()

```ts
yaml(container): StorageDescriptor;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `container` | `string` |

#### Returns

[`StorageDescriptor`](Interface.StorageDescriptor.md)
