# Interface: Template

A scaffoldable file tree declared by an Extension.

 - `id`              Namespaced identifier: `<extension>/<name>`.
 - `label`           Human-friendly name shown in UIs.
 - `kind`            Primary Kind this template scaffolds (may span
                     multiple kinds in the file tree, but this is the
                     headline one for filtering/grouping).
 - `description`     One-line description.
 - `filesRoot`       Absolute path to the root of the template tree on
                     disk (typically resolved via `fileURLToPath` from
                     the Extension's `import.meta.url`).
 - `ownerExtension`  Name of the Extension that owns this template.
 - `postInitHint`    Optional shell/cli snippet shown after scaffold
                     (e.g. "cd .dna/<scope>/programs/research && bun
                     install").
 - `upstreamRef`     Optional upstream pin (e.g. a git sha of the
                     source repo the template was cloned from).

## Properties

### description

```ts
readonly description: string;
```

***

### filesRoot

```ts
readonly filesRoot: string;
```

***

### id

```ts
readonly id: string;
```

***

### kind

```ts
readonly kind: string;
```

***

### label

```ts
readonly label: string;
```

***

### ownerExtension

```ts
readonly ownerExtension: string;
```

***

### postInitHint?

```ts
readonly optional postInitHint?: string;
```

***

### upstreamRef?

```ts
readonly optional upstreamRef?: string;
```
