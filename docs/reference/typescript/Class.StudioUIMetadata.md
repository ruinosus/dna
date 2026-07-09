# Class: StudioUIMetadata

UI declarations for a Kind, consumed by Studio's manifest. Defaults are
conservative: no mode, no sidebar, no routes — the Kind is invisible in
Studio unless explicitly opted in. 1:1 with Python `StudioUIMetadata`.

## Constructors

### Constructor

```ts
new StudioUIMetadata(init?): StudioUIMetadata;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `init` | [`StudioUIMetadataInit`](Interface.StudioUIMetadataInit.md) |

#### Returns

`StudioUIMetadata`

## Properties

### breadcrumb

```ts
readonly breadcrumb: string[] | null;
```

***

### description

```ts
readonly description: string | LabelI18n | null;
```

***

### display\_order

```ts
readonly display_order: number;
```

***

### feature\_flag

```ts
readonly feature_flag: string | null;
```

***

### icon

```ts
readonly icon: string | null;
```

***

### in\_sidebar

```ts
readonly in_sidebar: boolean;
```

***

### label

```ts
readonly label: string | LabelI18n | null;
```

***

### mode

```ts
readonly mode: ModeId | null;
```

***

### note

```ts
readonly note: string | null;
```

***

### permissions

```ts
readonly permissions: Record<string, string[] | string>;
```

***

### routes

```ts
readonly routes: Record<string, string>;
```

## Methods

### fields()

```ts
static fields(): readonly (
  | "mode"
  | "in_sidebar"
  | "display_order"
  | "label"
  | "icon"
  | "description"
  | "breadcrumb"
  | "routes"
  | "permissions"
  | "note"
  | "feature_flag")[];
```

The canonical field-name set (single source of truth for `ui:` validation).

#### Returns

readonly (
  \| `"mode"`
  \| `"in_sidebar"`
  \| `"display_order"`
  \| `"label"`
  \| `"icon"`
  \| `"description"`
  \| `"breadcrumb"`
  \| `"routes"`
  \| `"permissions"`
  \| `"note"`
  \| `"feature_flag"`)[]

***

### resolveLabel()

```ts
resolveLabel(locale?): string | null;
```

Resolve i18n label for the requested locale. Fallback order (mirrors
Python `resolve_label`):
  1. Exact locale match (e.g. 'pt-BR').
  2. Language-only fallback (e.g. 'pt' from 'pt-BR').
  3. 'en' (project default).
  4. null.
A plain-string label is returned as-is regardless of locale.

#### Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `locale` | `string` | `"en"` |

#### Returns

`string` \| `null`

***

### toDict()

```ts
toDict(): Record<string, unknown>;
```

Serialize for the /kinds/manifest JSON response. Omits None/empty fields
so the wire payload stays small — EXACTLY the Python `to_dict()` omission
rules (studio_ui.py:161-192):
  - mode: only if not null
  - in_sidebar: only if true
  - display_order: only if !== 100
  - label/icon/description/note/feature_flag: only if not null
  - breadcrumb: only if not null (an empty list IS kept, like Python)
  - routes/permissions: only if non-empty

#### Returns

`Record`\<`string`, `unknown`\>
