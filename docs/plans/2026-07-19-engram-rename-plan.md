# Plano — Story 1 `s-engram-rename` (LessonLearned → Engram)

> Plan gate aprovado pelo founder em 2026-07-19. Aterrado numa investigação do
> código real; referências file:line verificadas.

## Contexto da decisão

A decisão (c) foi **revertida** de "alias read-time" para **rewrite único**:
não há usuário algum nos dois repos, então a compat protegeria consumidores que
não existem. O repo **não tem precedente de rename** — `kind_registry.py:130`
diz que aliases *"CANNOT be renamed without a doc migration"*, ou seja a própria
arquitetura espera migração aqui. Fazer o alias seria inventar mecanismo novo,
permanente, para evitar um script que roda uma vez.

Medição que sustentou: **5 memórias em disco** (4 em `personal:local-user`, 1 em
`dna-cloud-dev`), todas **YAML plano**, rewrite mecânico de dois campos.

## ⚠️ O risco central desta story (não mudou com a decisão)

A resolução de Kind é lookup exato de 2-tupla sem fallback
(`self._kinds.get((doc.api_version, doc.kind))`, `instance.py:686`, ~25×). Mas o
perigo maior são **quatro conjuntos que referenciam o Kind por literal e falham
ABERTOS** — não levantam erro se esquecidos:

| Local | Se esquecer |
|---|---|
| `kernel/resolver.py:69` + `sdk-ts/src/kernel/resolver.ts:57` `DEFAULT_NON_INHERITABLE_KINDS_V1` | **Engram vira scope-inheritable → vazamento de memória entre scopes** |
| `extensions/sdlc/write_guards.py:23` `_KIND` | veto bi-temporal para de disparar → **ressurreição de memória supersedida** |
| `kernel/__init__.py:137` `VERSION_CHURN_KINDS` | Engram guarda histórico completo → board afoga |
| `extensions/intel/engine.py:338,485` | no-op silencioso (guardado por `_kind_registered`) |

Compila, passa typecheck, passa byte-parity — **e mesmo assim corrompe.**
O passo 5 existe por causa disso e é não-negociável.

## Passos

1. **`engram.kind.yaml`** — `target_api_version: github.com/ruinosus/dna/v1`,
   `target_kind: Engram`, schema copiado verbatim do descritor atual,
   `display_label: Engrama`, alias novo. Cópia **byte-idêntica** para
   `packages/sdk-ts/src/extensions/<mesma-ns>/kinds/` — o teste de parity chaveia
   por `<extensão>/<arquivo>`, então o **nome do diretório precisa bater dos dois
   lados**. `/dna/v1` implica diretório de extensão novo (não é `sdlc/`).
2. **Remover `lesson-learned.kind.yaml`** dos dois lados. É rename, não compat.
3. **Literais** — `memory/verbs.py` (`MEMORY_KINDS:55` + ramos `:125,:275,:338-358`),
   `application/runtime.py:1059,1082,1117,1163`, CLI `memory_cmd.py`
   (`click.Choice`, user-visible), `extensions/intel/engine.py`,
   `extensions/sdlc/{write_guards,work_item_outputs}.py`.
4. **O conjunto que falha aberto** — `VERSION_CHURN_KINDS`,
   `DEFAULT_NON_INHERITABLE_KINDS_V1` (**Py e TS**, senão vira drift), `_KIND`.
5. **Teste explícito** de que `Engram` ∈ cada um dos quatro conjuntos.
   Nada mais no repo pega isso.
6. **Goldens** — `goldens/lote1/LessonLearned.golden.json` → Engram; `KINDS` e
   `CURATED_SUMMARY_DEFAULTS` em `test_lote1_descriptor_equivalence.py`.
   (`alias` **não** alimenta hash pinado — o parity é sha256 dos bytes do par
   Py/TS — então nenhum golden de outro Kind é perturbado.)
7. **Script de migração** idempotente: reescreve `apiVersion` + `kind` nos docs
   existentes, reporta contagem antes/depois, seguro para reexecução. Rodar nos
   5 docs locais; disponível para produção no momento do bump de pin.
8. **Verde**: suite de memória, `test_descriptor_hash_parity`,
   `test_kind_registry_parity`, `test_lote1_descriptor_equivalence`, make/CI.

## Fora desta story

Docs e `lote2` (só prosa); a superfície dna-cloud; qualquer bump de pin.

## Não fazer

**Nenhum bump de pin do `dna-sdk`; nenhum `azd up`.** Stories 1–4 são SDK puro —
o pin e o deploy só quando a superfície dna-cloud consumir.
