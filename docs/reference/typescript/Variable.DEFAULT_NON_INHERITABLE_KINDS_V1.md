# Variable: DEFAULT\_NON\_INHERITABLE\_KINDS\_V1

```ts
const DEFAULT_NON_INHERITABLE_KINDS_V1: ReadonlySet<string>;
```

Scope inheritance default = DENYLIST (s-platform-inherit-by-default).
 When a scope has NO LayerPolicy with composition_rules, EVERY Kind defaults
 to scope_inheritance=enabled EXCEPT the per-scope ledger + structural Kinds
 below. Mirrors the kernel's `_NON_INHERITABLE_KINDS`.
