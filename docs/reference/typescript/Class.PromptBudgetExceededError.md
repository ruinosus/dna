# Class: PromptBudgetExceededError

## Extends

- `Error`

## Constructors

### Constructor

```ts
new PromptBudgetExceededError(opts): PromptBudgetExceededError;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `opts` | \{ `agentName`: `string`; `cap`: `number`; `estimatedTokens`: `number`; `modelId`: `string`; \} |
| `opts.agentName` | `string` |
| `opts.cap` | `number` |
| `opts.estimatedTokens` | `number` |
| `opts.modelId` | `string` |

#### Returns

`PromptBudgetExceededError`

#### Overrides

```ts
Error.constructor
```

## Properties

### agentName

```ts
readonly agentName: string;
```

***

### cap

```ts
readonly cap: number;
```

***

### estimatedTokens

```ts
readonly estimatedTokens: number;
```

***

### modelId

```ts
readonly modelId: string;
```
