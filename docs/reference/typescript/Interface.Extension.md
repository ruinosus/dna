# Interface: Extension

Registers kinds, readers, and writers on the Kernel.

The `templates?()` method is INTENTIONALLY OPTIONAL so extensions that
predate Phase 0 (i.e. shipped before the Template contract existed)
keep satisfying the `Extension` contract without modification. When
present, `Kernel.listTemplates()` aggregates entries from every loaded
extension so UIs (Tauri Studio, CLI) can offer `scaffold()` for any
extension-shipped file tree. See `./templates.ts` for the payload
shape.

## Properties

### name

```ts
readonly name: string;
```

***

### version

```ts
readonly version: string;
```

## Methods

### register()

```ts
register(kernel): void;
```

Wire the extension into the kernel. `kernel.load(ext)` fail-loud
validates the whole contract first (`name` non-empty string,
`version` string, `register` callable → `ExtensionLoadError`
otherwise), then calls `register()` with the registration-time
host slice — see [ExtensionHost](Interface.ExtensionHost.md) for the exact vocabulary.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `kernel` | [`ExtensionHost`](Interface.ExtensionHost.md) |

#### Returns

`void`

***

### templates()?

```ts
optional templates(): Template[];
```

Optional — return the file-tree scaffolds this extension ships.

#### Returns

[`Template`](Interface.Template.md)[]
