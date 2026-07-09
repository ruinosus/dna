# Type Alias: HookNameArg

```ts
type HookNameArg = 
  | HookName
  | string & {
};
```

Parameter type for hook-name arguments: the known vocabulary (with editor
autocomplete) plus arbitrary strings for back-compat (custom hooks stay
legal — they warn at runtime, never break). A misspelled builtin name
like `on("pre_saev", fn)` used to compile, run, and never fire, silently;
the registry now console.warns once per (registry, name).
