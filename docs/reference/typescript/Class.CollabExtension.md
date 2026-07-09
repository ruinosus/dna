# Class: CollabExtension

Registers kinds, readers, and writers on the Kernel.

The `templates?()` method is INTENTIONALLY OPTIONAL so extensions that
predate Phase 0 (i.e. shipped before the Template contract existed)
keep satisfying the `Extension` contract without modification. When
present, `Kernel.listTemplates()` aggregates entries from every loaded
extension so UIs (Tauri Studio, CLI) can offer `scaffold()` for any
extension-shipped file tree. See `./templates.ts` for the payload
shape.

## Implements

- [`Extension`](Interface.Extension.md)

## Constructors

### Constructor

```ts
new CollabExtension(): CollabExtension;
```

#### Returns

`CollabExtension`

## Properties

### name

```ts
readonly name: "collab" = "collab";
```

#### Implementation of

[`Extension`](Interface.Extension.md).[`name`](Interface.Extension.md#name)

***

### version

```ts
readonly version: "1.0.0" = "1.0.0";
```

#### Implementation of

[`Extension`](Interface.Extension.md).[`version`](Interface.Extension.md#version)

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

#### Implementation of

[`Extension`](Interface.Extension.md).[`register`](Interface.Extension.md#register)
