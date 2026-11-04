# The solution file (opening-night/v1)

One `key: value` per line; `#` starts a comment; a value may be in quotes. Paths are relative to the solution file.

| Field | What | Read by |
|---|---|---|
| `format` | always `opening-night/v1` | — |
| `name` | the solution's name, as people say it | the page's title |
| `about` | one or two sentences: what process, from where to where | the page |
| `lang` | `en` (default) or `pt`: the page and the messages | every piece's page |
| `way` | the way of working, `<id>.way.yaml` — the source of the lenses | way-of-working |
| `sim` | the what-if simulation, `<id>.sim` | process-simulation |
| `blueprint` | the customer's journey, `<id>.blueprint.yaml` | service-blueprint |
| `drill` | the incident drill, `<id>.drill.yaml` | incident-drill |
| `agents` | a folder of Copilot Studio agents, as the VS Code extension clones them | agent-review |
| `profile` | the team's profile for the agents, `<team>.standard.yaml` (only with `agents`) | agent-review |
| `lesson` | the idea explained by drawing, `.chalk`, `.json` or `.mmd` | visual-explainer |

Every piece is optional; a solution names at least one. A field that is not one of these, or one written twice, is an
error with its line.

## Lenses

`sim`, `blueprint` and `drill` may be **lenses** of the way: written by way-of-working `--lens`, their first line
is `# from: <id>.way.yaml@<version>` (the first 8 characters of the sha256 of the way's text when it was written). The
check compares it with the way as it is now:

| The piece's first line | The check says |
|---|---|
| no `# from:` | nothing: written by hand, kept as it is |
| `# from:` this way, at its current version | nothing: up to date |
| `# from:` this way, at an earlier version | it fell behind, with the command that makes it again (`--force`: look first) |
| `# from:` another way | it came from another way: is it the right one? |

## Exit codes

`--check`: 0 every piece passes (what to look at is printed, and is not an error); 1 the solution file breaks its
format; 2 bad arguments; 4 a piece is missing or fails its own skill's check. `--check --format` reads only the solution
file. `--check --json` prints `{ format: "solution/read-v1", name, about, lang, file, pieces: [{ kind, file, skill,
state: ok|missing|broken|unchecked, stale?, said, looks }] }`.
