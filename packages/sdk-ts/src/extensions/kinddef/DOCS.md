# KindDefinition

`KindDefinition` is the Helix meta-kind: a declarative way to register
brand-new kinds into a manifest without writing any extension code.

A KindDefinition document lives at
`.dna/<scope>/kinds/<name>/KIND.yaml` and carries:

- `target_api_version` — the apiVersion new documents of this kind will claim
- `target_kind` — the kind name (e.g. `Recipe`, `Meeting`)
- `alias` — the `<owner>-<kind>` alias used in dep_filters and prompts
- `origin` — provenance string
- `schema` — a JSON Schema that validates each document's `spec`
- `storage` — layout descriptor (`bundle`, `yaml`, `standalone`, `root`)
- `docs` — prose description surfaced by `describeKind`
- `is_root`, `prompt_target`, `flatten_in_context`, `dep_filters`,
  `default_agent` — the same prompt + composition flags hand-written kinds
  expose

At load time the kernel performs a 2-phase parse: KindDefinitions are
parsed first and each is wrapped in a synthesized `DeclarativeKindPort`
that's registered on the kernel before any other document is parsed. If a
KindDefinition claims the same `(apiVersion, kind)` as an extension-backed
kind, the extension wins and the KindDefinition is skipped with a warning.
