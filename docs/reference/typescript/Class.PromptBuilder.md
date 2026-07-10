# Class: PromptBuilder

## Constructors

### Constructor

```ts
new PromptBuilder(host): PromptBuilder;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `host` | [`ManifestInstance`](Class.ManifestInstance.md) |

#### Returns

`PromptBuilder`

## Methods

### build()

```ts
build(opts?): Promise<string>;
```

Build the final prompt string for the given (or default) agent.
Equivalent to `mi.buildPrompt(opts)`.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `opts?` | [`BuildPromptOpts`](Interface.BuildPromptOpts.md) |

#### Returns

`Promise`\<`string`\>
