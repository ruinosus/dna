# Type Alias: TenantScope

```ts
type TenantScope = typeof TenantScope[keyof typeof TenantScope];
```

Whether a Kind's documents belong to a tenant or are globally shared.

Mirrors the Kubernetes CRD `scope: Namespaced | Cluster` model. Each
KindPort declares its scope; the kernel enforces it on every write.

- `TENANTED` (default): documents belong to one tenant. Writing
  requires a tenant arg; reading is filtered by tenant.
  Agent, EvalCase, EvalRun, AssessmentRun, Finding, etc.
- `GLOBAL`: documents are shared across all tenants. Writes must
  not pass a tenant; reads ignore the bound tenant.
  Doc, KindDefinition, Module-level configs, etc.
