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

## `dna copilot orphans`

Quantos copilotos não dizem em que App rodam — e o dia em que zerar.

``Copilot.runs_in`` nasceu OPCIONAL por decisão registrada do founder, com
a data: *vira obrigatório no dia em que a contagem de órfãos chegar a zero
— e a guarda é o que torna esse dia visível em vez de esquecido.*

Ela REPORTA (órfão é estado legítimo hoje) e só FALHA quando o universo é
vazio, porque aí a quebrada é ela. O porquê inteiro, incluindo por que não
é uma seção de ``dna copilot provenance``, está em
``dna_cli/copilot_orphans.py``.

```text
dna copilot orphans [OPTIONS]
```

**Options**

| Option | Description |
| --- | --- |
| `--help` | Show this message and exit. |
| `--json` | Saída legível por máquina. |
| `--scope` | Scope a ler (default: env / sole scope). |
| `--self-test` | Roda só o auto-teste da guarda e sai (não lê store nenhum). |
| `--tenant` | Ler os copilotos deste tenant. |

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

