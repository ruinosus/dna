# Class: QueryError

Raised when a query filter / order_by is malformed in a way the
adapter can detect statically (unknown operator, …). 1:1 with the Py
`QueryError`.

## Extends

- `Error`

## Constructors

### Constructor

```ts
new QueryError(message?): QueryError;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `message?` | `string` |

#### Returns

`QueryError`

#### Overrides

```ts
Error.constructor
```
