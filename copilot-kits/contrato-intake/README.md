# Kit: contrato-intake

O template de vitrine do F3 (`adr-copiloto-como-dado`, dna-cloud): um fluxo de
**intake de contrato** completo — Kind, agente e copiloto com a surface — em
**zero linhas de código**. A surface de instância do runtime já é
schema-directed (`update_instance_draft` funciona para qualquer Kind), então
um fluxo novo é só dados.

## Instalar

```bash
dna copilot install copilot-kits/contrato-intake --scope <seu-escopo>
# Kind inerte até aprovação humana; no self-host, o operador aprova no ato:
dna copilot install copilot-kits/contrato-intake --scope <seu-escopo> --approve
```

## O que entra

| doc | papel |
|---|---|
| `KindDefinition/contrato-de-servico` | o schema do domínio (inerte até aprovação — o humano fica no circuito) |
| `Agent/contrato-agent` | a instrução do agente de intake (voz em pt-BR, editável na tela de Agentes) |
| `Copilot/contrato-copiloto` | o binder: monta o agente e declara a **surface** `contrato-intake` (state, tool, canvas, gate) |

Depois de aprovado o Kind, o fluxo inteiro do produto vale: anexar um contrato,
o agente extrai campo a campo pela surface de instância, o humano revisa no
canvas e grava.
