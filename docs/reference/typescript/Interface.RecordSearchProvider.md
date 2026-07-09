# Interface: RecordSearchProvider

Two-planes F2 (spec D2): semantic search over record docs. The PG
adapter (pgvector+RRF) lives in harness-shared (Py) and registers
itself on the kernel at app boot — the kernel core gains NO
LLM/embedding deps. Without a provider, `kernel.search()` degrades to
an in-memory lexical scan (explicit `degraded: true` — never fake
similarity). 1:1 with the Py `RecordSearchProvider` Protocol.

Hit shape: the guaranteed intersection across providers and the
lexical fallback is `{scope, kind, name, score}` — richer providers
may carry extra fields that callers must treat as optional.

## Methods

### search()

```ts
search(opts): Promise<Record<string, unknown>[]>;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `opts` | \{ `k?`: `number`; `kind?`: `string` \| `null`; `queryText`: `string`; `scope`: `string`; `tenant?`: `string`; \} |
| `opts.k?` | `number` |
| `opts.kind?` | `string` \| `null` |
| `opts.queryText` | `string` |
| `opts.scope` | `string` |
| `opts.tenant?` | `string` |

#### Returns

`Promise`\<`Record`\<`string`, `unknown`\>[]\>
