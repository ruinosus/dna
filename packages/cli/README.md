# dna-cli

The `dna` command-line interface for **DNA — Domain Notation of Anything**:
document CRUD (`dna doc`, `dna kind`, `dna scope`, `dna source`), semantic
recall and memory (`dna recall`, `dna memory`), research syntheses
(`dna research`), and a declarative, story-first SDLC (`dna sdlc`) — all
kernel-local against your filesystem or SQL source, no service required.

## Install

```bash
pip install dna-cli        # or: uv tool install dna-cli
```

Pre-release / exact-pin alternative — from the repo:

```bash
cd packages/sdk-py && uv venv && uv pip install -e ".[dev]" -e ../cli
```

## Quick taste

```console
$ dna scope list
$ dna doc show Agent greeter --scope hello-genome
$ dna sdlc story create s-my-story --title "..." --ac "..." --dod "..."
$ dna recall "reciprocal rank fusion" --kind Story -k 1
```

Full CLI reference: <https://ruinosus.github.io/dna/reference/cli/> ·
Repository: <https://github.com/ruinosus/dna>
