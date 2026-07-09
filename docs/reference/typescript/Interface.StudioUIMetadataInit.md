# Interface: StudioUIMetadataInit

Constructor input — every field optional, mirroring the Python dataclass
 defaults (no mode, no sidebar, display_order 100, all others None/empty).

## Properties

### breadcrumb?

```ts
optional breadcrumb?: string[] | null;
```

***

### description?

```ts
optional description?: string | LabelI18n | null;
```

***

### display\_order?

```ts
optional display_order?: number;
```

***

### feature\_flag?

```ts
optional feature_flag?: string | null;
```

***

### icon?

```ts
optional icon?: string | null;
```

***

### in\_sidebar?

```ts
optional in_sidebar?: boolean;
```

***

### label?

```ts
optional label?: string | LabelI18n | null;
```

***

### mode?

```ts
optional mode?: ModeId | null;
```

***

### note?

```ts
optional note?: string | null;
```

***

### permissions?

```ts
optional permissions?: Record<string, string | string[]>;
```

***

### routes?

```ts
optional routes?: Record<string, string>;
```
