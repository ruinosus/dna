# Function: materialize()

```ts
function materialize(template, opts): string[];
```

Copy every file under `template.filesRoot` into `opts.targetRoot`.

Returns the list of written absolute paths. Binary-safe — files are
read and written as raw `Buffer` bytes. Preserves relative directory
structure.

`onConflict`:
  - `"error"` (default): throw on any existing dest file
  - `"skip"`: leave existing dest files untouched
  - `"overwrite"`: replace existing dest files

Throws:
  - `Error("unknown onConflict: ...")` on invalid policy value
    (runtime validation — TypeScript can catch most at compile time,
    but this mirrors Python's `ValueError` for defensive callers)
  - `Error("filesRoot does not exist: ...")` if the source tree is
    missing
  - `Error("destination exists: ...")` when `onConflict="error"` and
    the destination has a conflicting file

## Parameters

| Parameter | Type |
| ------ | ------ |
| `template` | [`Template`](Interface.Template.md) |
| `opts` | [`MaterializeOptions`](Interface.MaterializeOptions.md) |

## Returns

`string`[]
