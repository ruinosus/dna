# `dna copilot`

Copilot kits — fluxos completos instaláveis como documentos.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna copilot --help`.

## `dna copilot install`

Instala um kit de copiloto: cada doc pelo ``kernel.write_document``,
com todos os guards da porta.

```text
dna copilot install [OPTIONS] PATH
```

**Arguments**

| Argument | Required |
| --- | --- |
| `PATH` | yes |

**Options**

| Option | Description |
| --- | --- |
| `--approve` | Carimba o OPERADOR (git user.email) como aprovador dos KindDefinition do kit — o ato humano, no self-host. |
| `--dry-run` | Lista o plano; escreve nada. |
| `--help` | Show this message and exit. |
| `--json` | Saída legível por máquina. |
| `--scope` | Scope de destino (default: env / sole scope). |

