# Variable: KNOWN\_HOOK\_NAMES

```ts
const KNOWN_HOOK_NAMES: readonly ["pre_build_prompt", "post_build_prompt", "pre_save", "post_save", "post_delete", "kinddef_conflict", "parse_error", "extension_error"];
```

The full vocabulary of hook names the SDK itself emits/consumes
(s-dna-typed-hook-names). Py twin: `HookName` / `KNOWN_HOOK_NAMES` in
dna/kernel/hooks.py. Both sides are locked to the shared fixture
`tests/parity-fixtures/port-surface-parity.json` (section `hook_names`)
by tests/hook-names.test.ts + tests/test_hook_names.py — vocabulary
drift turns both suites red. Add a name HERE + fixture + Py, never ad hoc.
