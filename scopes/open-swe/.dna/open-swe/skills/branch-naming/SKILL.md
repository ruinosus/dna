---
name: branch-naming
description: Instrução para nomear branches de acordo com a convenção do projeto
---

Ao revisar um Pull Request, siga este checklist estruturado:

## O que verificar

**Funcionalidade**
- A implementação resolve o que o issue pede?
- Há edge cases não cobertos?

**Qualidade de código**
- O código segue os padrões do repositório?
- Há duplicação desnecessária?
- Os nomes de variáveis e funções são claros?

**Testes**
- Há testes para o caso principal?
- Há testes para casos de erro?
- A cobertura é adequada?

**Documentação**
- Funções públicas têm docstring?
- O CHANGELOG foi atualizado se necessário?

## Formato do feedback

Para cada ponto de atenção, use:
- **Blocker** — deve ser corrigido antes do merge
- **Suggestion** — melhoria recomendada, não bloqueia
- **Praise** — algo que foi bem feito (importante reconhecer!)

## Output esperado

Termine sempre com uma das três conclusões:
- **Aprovado** — pode fazer merge
- **Mudanças solicitadas** — liste os blockers
- **Comentários** — apenas sugestões, aprovado condicionalmente