# `s-roundtrip-proof` — plano

## Objetivo

Provar as duas afirmações que a feature de memória portável faz sobre si mesma:

- **Círculo A** — round-trip interno sem perda, ligado ao
  `memory_conformance_suite` como caso `interchange_round_trip`.
- **Círculo B** — um fato exportado do Claude é recuperável no DNA **por
  paráfrase**, via um adaptador `claude-export → MIF` de <~150 LOC.

## Estado / dependências

- Base: `feat/memory-interchange-verbs` (o `interchange.py` ainda **não está no
  `main`** — PR #168 aberto). Esta branch é empilhada e rebaseia quando #168 entrar.
- **Círculo B está BLOQUEADO** aguardando um export de memória real do Claude.
  Não existe amostra no repo nem especificação do formato no design
  (`docs/design/2026-07-18-portable-memory-design.md` §"Círculo B" cita a Import
  Tool da Anthropic mas não descreve o arquivo). Construir o adaptador contra um
  formato inventado o validaria contra a própria ficção — sem valor probatório
  para o critério de aceite. O founder vai fornecer o arquivo real.

## Círculo A — o que entra

Um caso novo no registry `_CASES` de
`packages/sdk-py/dna/testing/memory_conformance.py`, `requires="always"`
(a projeção é pura — não precisa de search provider):

```
("interchange_round_trip", "always", _case_interchange_round_trip)
```

O caso semeia Engrams via `remember`, projeta com `to_mif`, reidrata com
`from_mif` e compara os specs. As quatro asserções vêm direto da AC 1:

1. **Fidelidade de campo** — todo campo da §2 do design sobrevive. A lista de
   campos é derivada do **descritor** (`engram.kind.yaml`), não de uma lista
   escrita à mão no teste: uma lista à mão envelhece em silêncio quando o Kind
   ganha campo. Campos que o MIF não representa devem voltar pelo cofre `x-dna`.
2. **Cofre idêntico** — os `x-dna.*` voltam byte-a-byte iguais.
3. **Cadeia bi-temporal** — `valid_to` / `superseded_by` preservados através de
   um `forget` (que é o que cria a cadeia).
4. **Sem duplicatas** — reprojetar duas vezes não multiplica documentos; a
   identidade é o id MIF (ver o fix de `_engram_doc_name` em `273687d`).

### Riscos que o plano assume

- O caso roda contra a **projeção pura**, não contra os verbos CLI. É o nível
  certo para um kit de conformance (um autor de adaptador roda contra o *seu*
  stack, não contra o Click do DNA) — mas significa que este caso **não** cobre
  a camada de arquivo/naming. Aquela camada é onde os dois blockers do review
  moravam, e ficou coberta pelos testes de `273687d`. Registrar isso no
  docstring do caso para ninguém ler a suíte verde como "o CLI está provado".
- `requires="always"` só se a projeção realmente não tocar provider. Confirmar
  antes de fixar, senão o caso quebra o leg sem provider.

## Círculo B — o que entra (quando o export chegar)

- `claude_export` → MIF, <~150 LOC, contado e registrado.
- Teste: import `--as both --personal` → `recall` por **paráfrase sem token
  compartilhado** com `embed-onnx` → hit no top-3.
- A paráfrase precisa ser genuinamente disjunta em tokens do fato original,
  senão o teste prova recuperação léxica e não semântica. Verificar a
  disjunção programaticamente, não a olho.

## Verificação

- Suíte py completa; os dois legs do kit (com e sem provider).
- Mutação: quebrar cada asserção do caso isoladamente e confirmar que **só** o
  caso novo falha. Uma asserção que não mata seu mutante não está provando nada.
- Métricas do DoD registradas: fidelidade de campo, preservação bi-temporal,
  recuperabilidade por paráfrase, idempotência, LOC do adaptador.

## Fora de escopo

Círculo C (o triângulo de três fornecedores) — explicitamente fast-follow no
design, não MVP.
