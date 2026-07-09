# Interface: PreviewBlock

## Properties

### body?

```ts
optional body?: string;
```

Free-form body content. Type depends on `kind`.

***

### fields?

```ts
optional fields?: {
  label: string;
  value: string;
}[];
```

Used by fields blocks. Ordered.

#### label

```ts
label: string;
```

#### value

```ts
value: string;
```

***

### kind

```ts
kind: PreviewBlockKind;
```

***

### language?

```ts
optional language?: string;
```

Used by code blocks to choose syntax highlighting.

***

### title

```ts
title: string;
```

Section header shown above the body.
