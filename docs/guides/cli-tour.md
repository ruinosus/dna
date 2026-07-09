# A tour of the `dna` CLI

The `dna` binary is the terminal surface over the same kernel the SDKs
expose: every command boots a local `Kernel`, points it at your manifests
via `DNA_SOURCE_URL` (or `DNA_BASE_DIR` for a plain filesystem directory),
and reads or writes documents through the same ports. Nothing here is a
second code path — what the CLI validates and stores is exactly what
`Kernel.quick()` would load.

This page is a practical tour of every command group — what it is for and
one real, executed example each. It does **not** list flags; each heading
links to the [generated CLI reference](../reference/cli/index.md), which is
regenerated from the live Click tree on every build and can't drift.

```console
$ dna --help
Usage: dna [OPTIONS] COMMAND [ARGS]...

  DNA — declarative lifecycle + document CLI.

  Boots a local kernel via DNA_SOURCE_URL / DNA_BASE_DIR (filesystem source).
  Run `dna kind list` to start exploring, `dna sdlc --help` for the lifecycle
  verbs.

Options:
  --version   Show the version and exit.
  -h, --help  Show this message and exit.

Commands:
  doc       List, show, create, edit, delete documents.
  docs      Browse the in-product Doc corpus.
  kind      List + inspect registered Kinds.
  memory    Declarative memory over existing Kinds...
  recall    Hybrid semantic search (dense + lexical + RRF) over the...
  research  Manage Research synthesis documents (curated syntheses of...
  scope     List + inspect scopes (manifest modules).
  sdlc      Declarative lifecycle tracking...
  search    Alias of ``dna recall`` (neutral naming).
  source    Source-level operations: declarative replicas, introspection.
```

## Set up a playground

The examples below run in a small throwaway scope, so you can paste along
without touching a real project. Create a playground directory with one
scope named `docs` containing a `Genome` (the scope root), two pages of
the built-in [`Doc` Kind](../concepts/builtin-kinds.md#doc) (one per
locale), and a [`KindDefinition`](../concepts/kinds.md) declaring a custom
Kind called `Snippet` — to show how you extend the type system with your
own Kinds, no Python required:

```bash
mkdir -p ~/dna-playground/.dna/{_lib,docs/docs/welcome,docs/docs/boas-vindas,docs/kinds/snippet,docs/snippets}
cd ~/dna-playground
export DNA_BASE_DIR=~/dna-playground/.dna

# Scopes inherit from a shared `_lib` library scope by default — give the
# playground an empty one so nothing warns about a missing parent.
cat > .dna/_lib/Genome.yaml <<'EOF'
apiVersion: github.com/ruinosus/dna/v1
kind: Genome
metadata: { name: _lib }
spec: {}
EOF

cat > .dna/docs/Genome.yaml <<'EOF'
apiVersion: github.com/ruinosus/dna/v1
kind: Genome
metadata:
  name: docs
  description: In-product documentation corpus
spec: {}
EOF

# A Doc is authored as a bundle: docs/<name>/DOC.md, YAML frontmatter +
# markdown body. No KindDefinition needed — the Kind ships with the SDK.
cat > .dna/docs/docs/welcome/DOC.md <<'EOF'
---
description: Welcome to the corpus
icon: "👋"
order: 1
locale: en
kind_of: tutorial
category: Getting started
---

# Welcome

This corpus is served in-product: agents and the UI read these pages
through the kernel, so editing markdown updates the product help.
EOF

cat > .dna/docs/docs/boas-vindas/DOC.md <<'EOF'
---
description: Bem-vindo ao corpus
icon: "👋"
order: 1
locale: pt-BR
kind_of: tutorial
category: Primeiros passos
---

# Bem-vindo

Este corpus é servido dentro do produto: os agentes e a UI leem estas
páginas pelo kernel.
EOF

cat > .dna/docs/kinds/snippet/KIND.yaml <<'EOF'
apiVersion: github.com/ruinosus/dna/core/v1
kind: KindDefinition
metadata: { name: snippet }
spec:
  target_api_version: example.com/docs/v1
  target_kind: Snippet
  alias: docs-snippet
  origin: example.com
  docs: A reusable content snippet (markdown body + audience tag).
  schema:
    type: object
    required: [body]
    additionalProperties: false
    properties:
      body: { type: string }
      audience: { type: string }
  storage:
    type: yaml
    container: snippets
EOF

cat > .dna/docs/snippets/hello.yaml <<'EOF'
apiVersion: example.com/docs/v1
kind: Snippet
metadata:
  name: hello
  description: Greeting snippet
spec:
  audience: newcomers
  body: Welcome! Everything in this playground is throwaway.
EOF
```

## `dna scope` — list and inspect scopes

[Reference →](../reference/cli/scope.md)

A **scope** is a directory of manifests — the unit of loading, inheritance
and tenancy ([Tenancy & layers](../concepts/tenancy-layers.md)). `dna scope
list` shows every scope the configured source can see; `dna scope tree`
inventories one scope's documents grouped by Kind — the fastest way to
answer "what is actually in here?".

```console
$ dna scope list
scope
-----
_lib 
docs 

$ dna scope tree docs

Genome
  • docs

KindDefinition
  • snippet

Snippet
  • hello
```

Note the two-phase load at work: the `KindDefinition` registered the
`Snippet` Kind, and the `hello` document was then parsed as a first-class
instance of it — no Python was written. The two `Doc` pages are absent on
purpose: `Doc` is a *record-plane* Kind (pure typed content that never
composes into agent prompts), and the tree inventories the composition
plane — records are reached with `dna doc list Doc --scope docs` and the
[`dna docs`](#dna-docs-browse-the-in-product-doc-corpus) group below.

## `dna kind` — list and inspect registered Kinds

[Reference →](../reference/cli/kind.md)

Kinds are the type system ([Kinds — identity &
composition](../concepts/kinds.md)). `dna kind list` prints everything
registered on the kernel — built-ins plus any `KindDefinition`-declared
Kinds in the scope — and `dna kind describe` dumps one Kind's identity,
JSON Schema and storage descriptor, which is exactly what the write
boundary will enforce.

```console
$ dna kind list | wc -l
      66

$ dna kind list | grep -E '^(Genome|Agent|Doc|Skill|Soul|Comment) '
Agent               (use describe)  (use describe)                           
Comment             (use describe)  (use describe)                           
Doc                 (use describe)  (use describe)                           
Genome              (use describe)  (use describe)                           
Skill               (use describe)  (use describe)                           
Soul                (use describe)  (use describe)                           

$ dna kind describe Doc | head -8
{
  "kind": "Doc",
  "alias": "dna-doc",
  "api_version": "github.com/ruinosus/dna/doc/v1",
  "display_label": "Docs",
  "schema": {
    "type": "object",
    "required": [
```

## `dna doc` — generic document CRUD

[Reference →](../reference/cli/doc.md)

The workhorse group: list, show, create, edit and delete documents of
*any* Kind, with the Kind's JSON Schema enforced on every write. `dna doc
fields` prints the fields a Kind accepts (straight from its schema), and
`dna doc make` builds a document from `field=value` arguments — values are
coerced to the schema's types, so you rarely need to hand-craft JSON. For
bulk upserts from files there is `dna doc apply`, and Kinds that declare a
status machine get generic `dna doc transition`.

```console
$ dna doc fields Comment --scope docs
Fields for Comment
  required: ['author', 'body', 'created_at', 'target_ref', 'type']

  assignee                 (string)   
  attachments              (array)   
  author                   (string) *   
  body                     (string) *   
  created_at               (string) *   
  edited_at                (string)   
  from_status              (string)   
  target_ref               (string) *   Kind:name of the target document
  to_status                (string)   
  type                     (string) enum=['note', 'status_change', 'assignment', 'system'] *   

$ dna doc make Comment note-1 --scope docs target_ref=Doc:welcome \
    author=ada body='Ship the welcome page.' type=note \
    created_at=2026-07-09T12:00:00Z
Created Comment/note-1 in scope docs (5 fields)

$ dna doc show Comment note-1 --scope docs
{
  "kind": "Comment",
  "name": "note-1",
  "metadata": {
    "name": "note-1"
  },
  "spec": {
    "target_ref": "Doc:welcome",
    "author": "ada",
    "body": "Ship the welcome page.",
    "type": "note",
    "created_at": "2026-07-09T12:00:00Z"
  }
}
```

## `dna docs` — browse the in-product Doc corpus

[Reference →](../reference/cli/docs.md)

Not to be confused with `dna doc` above: `dna docs` (plural) is a reader
over one specific corpus — a scope named `docs` holding documents of the
built-in [`Doc` Kind](../concepts/builtin-kinds.md#doc), the pattern a
DNA-based product uses to serve its own help pages from the kernel. Each
page is a `docs/<name>/DOC.md` bundle: a markdown body plus sidebar
metadata (icon, order, locale, Diátaxis `kind_of`, category). It works
out of the box — the two pages authored in the playground setup are
already a corpus, one per locale:

```console
$ dna docs list
order  icon  name         title                kind_of   category        
-----  ----  -----------  -------------------  --------  ----------------
1      👋     boas-vindas  Bem-vindo ao corpus  tutorial  Primeiros passos

$ dna docs list --locale en
order  icon  name     title                  kind_of   category       
-----  ----  -------  ---------------------  --------  ---------------
1      👋     welcome  Welcome to the corpus  tutorial  Getting started

$ dna docs show welcome --locale en
# Welcome

This corpus is served in-product: agents and the UI read these pages
through the kernel, so editing markdown updates the product help.
```

The `Doc` schema is deliberately content-shaped (`dna kind describe Doc`
shows the exact contract the write boundary enforces). If your product
needs a *different* documentation shape, the `KindDefinition` route the
playground used for `Snippet` works just as well for a custom docs Kind —
it is an extension point now, not a prerequisite.

## `dna research` — curated Research syntheses

[Reference →](../reference/cli/research.md)

A `Research` document is a curated synthesis of external sources — the
[agent-facing knowledge](../concepts/agent-knowledge.md) model: cited
findings and recommendations as data, not generated wiki prose. The CLI
lists a scope's research catalog and pretty-prints one synthesis with its
citation graph. This repo dogfoods it — run from a DNA checkout:

```console
$ dna research list --scope dna-development
name                           status     method                #F  #S when        title
--------------------------------------------------------------------------------------------------------------
rsh-doc-frameworks-oss         published  web-search-curated     4   0 2026-07-09  Documentation frameworks & tooling for a public OS
rsh-exemplar-sdk-repos         published  web-search-curated     5   0 2026-07-09  How exemplary OSS SDK repos structure their docume
rsh-memory-similarity-evolution published  synthesis              6   0 2026-07-09  Evolving memory + similarity search into DNA, serv
rsh-openwiki-analysis          published  synthesis              3   0 2026-07-09  LangChain OpenWiki — analysis and fit with DNA arc

$ dna research show rsh-doc-frameworks-oss --scope dna-development | head -12

🔬 Research/rsh-doc-frameworks-oss
  title:        Documentation frameworks & tooling for a public OSS SDK
  status:       published
  methodology:  web-search-curated
  confidence:   high
  conducted_by: claude-code
  conducted_at: 2026-07-09T00:00:00+00:00
  scope_ref:    dna-development
  visibility:   shared

  objective:
```

There is also `dna research recall` — semantic search over the research
catalog — which needs the search extras installed (see [How to use
semantic recall & memory](semantic-recall.md)).

## `dna source` — replicas and source-level introspection

[Reference →](../reference/cli/source.md)

Where every other group works *inside* a source, this group works *on*
sources. `dna source replica` manages `.dna-replicas.yaml`, a declarative
config (discovered by upward walk, like `.gitignore`) that host platforms
read at boot to mirror writes into other sources — e.g. keep a filesystem
copy of selected scopes while the source of truth is a database. `dna
source diff` and `dna source push` compare and reconcile one scope between
the current source and another URL using Kind-aware content digests, so
formatting and volatile stamps never show as drift.

```console
$ dna source replica add docs-backup --replica fs://./backup --scopes docs
ADDED replica/docs-backup -> ~/dna-playground/.dna-replicas.yaml

$ dna source replica list
id           replica        scopes  kinds  enabled
-----------  -------------  ------  -----  -------
docs-backup  fs://./backup  docs    all    yes    
```

`diff` reports drift in three buckets — added (in the current source,
missing in the other), changed (content digest drifted), removed (in the
other only). `push` is dry-run by default; `--apply` writes the minimal
set through the target's atomic save path (doc + bundle entries
together). Here the `./copy` replica is stale: one agent drifted, one is
missing entirely:

```console
$ dna source diff fs://./copy --scope demo
demo: 1 added · 1 changed · 0 removed  (current ↔ fs://./copy)
  A Agent/release-notes
  C Agent/code-reviewer

$ dna source push fs://./copy --scope demo
[DRY-RUN] demo → fs://./copy: would write 2 (1 added, 1 changed)
  + Agent/release-notes
  ~ Agent/code-reviewer
  (dry-run — re-run with --apply to write)

$ dna source push fs://./copy --scope demo --apply
[APPLIED] demo → fs://./copy: wrote 2 (1 added, 1 changed)
  + Agent/release-notes
  ~ Agent/code-reviewer

$ dna source diff fs://./copy --scope demo
✔ in sync — demo matches fs://./copy (0 diffs)
```

The digests are Kind-aware and source-independent: the same scope held
in a filesystem tree and in a database digests identically when in sync,
so a diff never needs to transfer content — and re-serialization noise
(key order, volatile stamps) never shows up as drift.

## The groups with their own guides

Four groups already have dedicated prose — one line each here:

- **`dna recall`** (and its neutral-name alias **`dna search`**) — hybrid
  semantic search (dense + lexical + RRF) over a scope's documents; the
  full walkthrough is in [How to use semantic recall &
  memory](semantic-recall.md) and the model behind it in [Search &
  memory](../concepts/search-and-memory.md).
  ([recall reference](../reference/cli/recall.md) ·
  [search reference](../reference/cli/search.md))
- **`dna memory`** — the remember / recall-as-memory verbs layered over
  the Kinds you already have; same guide, memory half.
  ([reference](../reference/cli/memory.md))
- **`dna sdlc`** — the lifecycle tracker (Story/Feature/Issue/… plus the
  git symbiosis hooks) this repo runs itself on; the whole story is in
  [Your git log is your SDLC](sdlc.md).
  ([reference](../reference/cli/sdlc.md))
