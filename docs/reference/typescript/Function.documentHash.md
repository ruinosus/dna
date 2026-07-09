# Function: documentHash()

```ts
function documentHash(raw): string;
```

Compute SHA-256 hash of a document's raw dict.

Matches Python's: hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

## Parameters

| Parameter | Type |
| ------ | ------ |
| `raw` | `Record`\<`string`, `unknown`\> |

## Returns

`string`
