# Variable: UI\_METADATA\_FIELDS

```ts
const UI_METADATA_FIELDS: readonly ["mode", "in_sidebar", "display_order", "label", "icon", "description", "breadcrumb", "routes", "permissions", "note", "feature_flag"];
```

Canonical, ordered set of StudioUIMetadata field names. Single source of
truth — `KindDefinitionSpec.from_raw`/zod validate `ui:` keys against THIS
list (no second hardcoded list). Mirrors the Python dataclass field order.
