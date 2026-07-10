# Interface: PreviewResult

Return value of Kernel.previewDocument().

- `target` — absolute path for filesystem sources, synthetic URL
  (e.g. "sqlite://<scope>/<kind>/<name>") for others.
- `files` — the exact bytes that would be written. Readonly.
- `existsAlready` — true iff the target is already present; UIs use
  this to render "create" vs "overwrite" affordances. Optimistic
  concurrency (ifMatch) is deferred per
  docs/superpowers/specs/2026-04-04-kernel-write-path-design.md
  Out-of-Scope.

## Properties

### existsAlready

```ts
readonly existsAlready: boolean;
```

***

### files

```ts
readonly files: readonly SerializedFile[];
```

L3 (2026-05-25): files may have `content` (str) or `contentBytes`
(Uint8Array). Preview UIs that only render text should fallback
to an empty-string display when contentBytes is set.

***

### target

```ts
readonly target: string;
```
