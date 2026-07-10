# Type Alias: PreviewBlockKind

```ts
type PreviewBlockKind = "markdown" | "code" | "fields" | "empty";
```

A single renderable section of a document preview. Documents can produce
multiple blocks (e.g. a Soul has SOUL.md + STYLE.md + soul.json), which
the Studio renders stacked.

`kind` is the renderer hint:
  - "markdown"  → MarkdownBlock (prose, headings, lists)
  - "code"      → CodeBlock (yaml, json, plain text in monospace)
  - "fields"    → FieldsBlock (key/value pairs)
  - "empty"     → no body, just the title (used for empty states)
