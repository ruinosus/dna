# Class: LayerPolicyViolationError

Raised when a write to a layer violates the declared LayerPolicy in
`Module.spec.layers`. Thrown by `Kernel.writeDocument` before the adapter
is touched. Harness endpoints translate to HTTP 403.

## Extends

- `Error`

## Constructors

### Constructor

```ts
new LayerPolicyViolationError(message): LayerPolicyViolationError;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `message` | `string` |

#### Returns

`LayerPolicyViolationError`

#### Overrides

```ts
Error.constructor
```
