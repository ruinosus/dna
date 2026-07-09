# Function: erModel()

```ts
function erModel(mi): {
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

Visualization module — barrel re-export.

Standalone functions that operate on ManifestInstance, extracted from
the class to keep the kernel focused on query/prompt/composition.

## Parameters

| Parameter | Type |
| ------ | ------ |
| `mi` | [`ManifestInstance`](Class.ManifestInstance.md) |

## Returns

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

### entities

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

### relationships

```ts
relationships: {
  isMany: boolean;
  label: string;
  sourceId: string;
  targetId: string;
}[];
```
