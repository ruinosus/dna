# Class: CompositionResolver

## Constructors

### Constructor

```ts
new CompositionResolver(kernel): CompositionResolver;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kernel` | `CompositionResolverHost` |

#### Returns

`CompositionResolver`

## Methods

### computeResolutionChain()

```ts
computeResolutionChain(scope, tenant): Promise<[string, string | null][]>;
```

Walk `Genome.spec.parent_scope` transitively → ordered chain of
`[scope, tenant]` pairs, HIGHEST priority first. Cycle-guarded; depth
capped at MAX_RESOLUTION_DEPTH; missing Genome terminates the walk.
1:1 with Py `compute_resolution_chain`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `tenant` | `string` \| `null` |

#### Returns

`Promise`\<\[`string`, `string` \| `null`\][]\>

***

### getCompositionRule()

```ts
getCompositionRule(scope, kind): Promise<[string, string, string]>;
```

Resolve `[scope_inheritance, merge_strategy, tenant_overlay]` for
(scope, kind) — from the scope's LayerPolicy composition_rules, else
the inherit-by-default denylist (everything inherits from _lib except
the per-scope ledger + structural Kinds). 1:1 with Py
`get_composition_rule`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |

#### Returns

`Promise`\<\[`string`, `string`, `string`\]\>

***

### personalizeDocument()

```ts
personalizeDocument(
   targetScope, 
   kind, 
   name, 
opts?): Promise<ResolvedDocument>;
```

Clone an inherited doc into `targetScope` as a local override
(Phase 17). Throws if the doc isn't inherited / target exists (without
overwrite). Clones spec + envelope atomically via `writeDocument`.
1:1 with Py `personalize_document` EXCEPT bundle-entry payload cloning
(Py-only — see divergence #4 in the module docstring).

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `targetScope` | `string` |
| `kind` | `string` |
| `name` | `string` |
| `opts?` | \{ `overwrite?`: `boolean`; `tenant?`: `string` \| `null`; \} |
| `opts.overwrite?` | `boolean` |
| `opts.tenant?` | `string` \| `null` |

#### Returns

`Promise`\<[`ResolvedDocument`](Class.ResolvedDocument.md)\>

***

### resolveDocument()

```ts
resolveDocument(
   scope, 
   kind, 
   name, 
opts?): Promise<ResolvedDocument>;
```

Resolve a doc through the composition chain (Phase 17). Returns a
ResolvedDocument with merged doc + full provenance. Bootstrap Kinds
bypass inheritance (local-only). 1:1 with Py `resolve_document`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `scope` | `string` |
| `kind` | `string` |
| `name` | `string` |
| `opts?` | \{ `tenant?`: `string` \| `null`; \} |
| `opts.tenant?` | `string` \| `null` |

#### Returns

`Promise`\<[`ResolvedDocument`](Class.ResolvedDocument.md)\>
