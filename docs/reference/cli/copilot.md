# `dna copilot`

Copilot kits — fluxos completos instaláveis como instâncias.

!!! info "Generated from the command definitions"

    This page is introspected from the `dna` Click command tree by
    `scripts/gen_cli_docs.py`, so it stays in lockstep with
    `dna copilot --help`.

## `dna copilot install`

Instala um kit de copiloto: cada doc pelo ``kernel.write_instance``,
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

## `dna copilot provenance`

De onde veio cada copiloto — e quem ainda não disse.

``Copilot.created_by`` é a relação reflexiva que a `s-procedencia-do-agente`
instalou: quem cria um copiloto é um copiloto. Ela é OPCIONAL, e a ausência
dela é **não-respondida**, jamais "escrito à mão" — presumir seria fabricar
um passado para os copilotos que nasceram antes do campo existir.

```text
dna copilot provenance [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | Saída legível por máquina. |
| `--scope` | Scope a ler (default: env / sole scope). |
| `--tenant` | Ler os copilotos deste tenant. |

