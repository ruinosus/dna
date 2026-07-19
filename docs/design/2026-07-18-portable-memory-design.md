# Design: memória portável no DNA — o Engram, o `dna memory export/import` e o experimento de round-trip

*Proposta de design · Julho 2026 · aterrada no código real: o Kind de memória (`dna/extensions/sdlc/kinds/lesson-learned.kind.yaml`), os verbos em `dna/memory/`, e o schema do MIF (`mif-spec.dev`). Nada aqui está implementado — é o desenho fechado para o Claude Code implementar após a revisão do Jefferson.*

---

## Decisões travadas (esta rodada)

1. **Motor nativo mantido**, mas **renomeado de `LessonLearned` para `Engram`** (canônico), com `LessonLearned` / `sdlc-lesson-learned` preservados como **alias** de compatibilidade. Ver §3.
2. **MIF é o alvo de intercâmbio primário**; OMP/PAM entram depois como `--format`.
3. **MVP é field-faithful** (todos os campos preservados); byte-faithful literal é passo posterior.
4. **Experimento: Círculo A + B agora, Círculo C (o triângulo de 3 fornecedores) como fast-follow.**

---

## 0. A ideia em uma frase

O DNA **já tem o motor** de memória (recall híbrido, decay, bi-temporalidade, ecphory). Falta a **membrana**: um formato de intercâmbio que deixe uma memória entrar e sair do DNA sem perda. Este design adiciona a membrana com **duas peças pequenas** e **zero reescrita do kernel**:

1. um **Kind de passthrough** — `mif-spec.dev/v1 · Memory` — registrado por descritor, para guardar memórias estrangeiras byte-fiéis (a mesma mecânica que já carrega `agentskills.io/v1 · Skill`);
2. dois **verbos de projeção** — `dna memory export` / `dna memory import` — que traduzem entre o `Engram` (o motor nativo) e o MIF (o fio neutro).

A escolha estratégica que amarra tudo: **não inventamos um formato novo.** Adotamos o MIF (bi-temporal, W3C PROV, local-first, Markdown+JSON-LD) e usamos a regra normativa nº 3 do DNA para carregá-lo inalterado. Se amanhã o OMP ou o PAM vencerem, é só mais um descritor.

---

## 1. Por que a projeção é quase de graça (o alinhamento estrutural)

O achado que torna isso barato: **a forma de armazenamento dos dois já é a mesma.**

- O Engram usa storage `bundle`: um marker `.md` com **YAML frontmatter** para os campos estruturados + corpo em Markdown.
- MIF usa `.memory.md`: **YAML frontmatter** + corpo em Markdown.

Mesma estrutura física. E no eixo mais importante — a taxonomia CoALA — os dois usam **exatamente os mesmos três valores**: `episodic | semantic | procedural`. O `dna/memory/memory_type.py` classifica nisso; o MIF usa isso como `type`. A projeção no eixo de tipo é **identidade, não conversão**.

---

## 2. Mapeamento de campos (`Engram` ↔ MIF)

Cada linha conferida contra o schema real dos dois lados.

> ⚠️ **Esta tabela foi escrita contra suposições, não contra a spec.** A story
> `s-mif-passthrough-kind` buscou o MIF v1.0.0 real e achou vários campos
> inventados. As linhas marcadas CORRIGIDO abaixo já foram ajustadas; a fonte
> de verdade é o descritor em
> `packages/sdk-{py,ts}/**/extensions/mif/kinds/memory.kind.yaml`.
> **Quem implementar `s-memory-interchange-verbs` deve conferir cada linha
> contra o descritor, não contra esta tabela.**
>
> **Atualização (`s-memory-interchange-verbs`, implementado):** duas linhas
> abaixo continuavam erradas mesmo depois da correção acima — ambas
> corrigidas nesta rodada, com a implementação real em
> `dna/memory/interchange.py`:
>
> 1. **`name`/`@id` (linha da estabilidade de id, §6).** A tabela assumia que
>    o id mintado no export É o `urn:mif:<uuid>` e que ele é pinado no
>    `name` do Engram. Os dois estão errados: o `id` do perfil Markdown é uma
>    **string plana** (os próprios exemplos do MIF usam slugs, não só UUID;
>    sem `format: uuid` no schema), e `urn:mif:...` é o **`@id` do JSON-LD**,
>    uma projeção *derivada separadamente* — nunca escrito neste
>    frontmatter. E `Engram.name` é a chave de storage do DNA (o slug do
>    bundle, `rem-<hash>`) — um conceito DIFERENTE de uma identidade MIF; o
>    `spec` nunca vê `name` (ele mora em `metadata.name`, fora do spec). A
>    decisão implementada: o id é pinado em `encoding_context["mif_id"]` — um
>    scalar plano, não um sub-objeto `extensions` aninhado (o schema do
>    Engram já declara `encoding_context.additionalProperties: true`, então
>    isso não precisa de mudança de schema). Ver o docstring do módulo para o
>    raciocínio completo.
> 2. **`homophonic_links` não precisa de cofre.** A tabela dizia que o
>    `resonance_score` "perde -> vai pra extensions" porque `relationships`
>    não teria onde guardá-lo. Falso: o descritor real tem
>    `relationships[].strength` (0.0-1.0) — encaixe exato para
>    `resonance_score` — mais um `metadata` aberto que encaixa o `basis`.
>    `homophonic_links` viaja inteiro por `relationships[type=relates-to]`,
>    sem nenhuma entrada no `extensions.x-dna`.

| `Engram` (DNA) | MIF | Fidelidade | Observação |
|---|---|---|---|
| `memory_type` | `type` | ✅ 1:1 | mesmos enums (`episodic/semantic/procedural`) |
| `summary` + `body` | `title`/`summary` + `content` | ✅ | `summary` (≤280) → `title`; corpo → `content` |
| `area` | `namespace` | ✅ | `Feature/X` → `_episodic/feature-x`; `visibility` reservada → `_public`/`_shared` |
| `valid_from` / `valid_to` | `temporal.validFrom` / **`validUntil`** | ✅ 1:1 | **bi-temporalidade — o segundo eixo onde já concordam.** ⚠️ CORRIGIDO: dizia `validTo`, que **não existe** na spec real |
| `superseded_by_memory` | `relationships[supersedes]` | ✅ | par com o `valid_to` do Engram para auditoria point-in-time |
| `source_refs` | `relationships[derived-from]` + `provenance.wasDerivedFrom` | ✅ | |
| `homophonic_links` | **`relationships[relates-to]`** | ✅ | `resonance_score` → `relationships[].strength` (0-1, encaixe nativo); `basis` → `relationships[].metadata.basis`. **Sem cofre** — ver a atualização acima. ⚠️ CORRIGIDO: dizia `related-to` (não existe) E dizia que `resonance_score` precisava de `extensions` (não precisa) |
| `owner` | `provenance.wasAttributedTo` | ✅ | qual agente engrafou |
| `tags` | `tags` | ✅ 1:1 | |
| `created_at` | `created` | ✅ 1:1 | |
| *(pin de identidade)* | `id` (string plana no perfil Markdown) | ⚠️ | mintado uma vez, pinado em `Engram.spec.encoding_context["mif_id"]` — ver §6. **NÃO** é `Engram.name` nem `urn:mif:...` (isso é o `@id` do JSON-LD, derivado). ⚠️ CORRIGIDO: a coluna dizia `name (rem-<hash))` ↔ `@id (urn:mif:<uuid>)` |
| `confidence_score`, `relevance_decay_seed`, `surface_count`, `cues_history`, `encoding_context`, `affect`, `affect_reason` | `extensions.x-dna.*` | ⚠️ **por design** | é a **física cognitiva** do DNA que o MIF flat-file não tem; viaja no `extensions` (MIF Level 3) e volta intacta num round-trip DNA→MIF→DNA |

A leitura da última linha: os campos que **não** têm casa no MIF não são "perda" — são o **diferencial** do DNA. O MIF exporta uma memória *estática*; o DNA exporta a memória *mais a curva de decay, o histórico de cues e o contexto de engraphy*. Guardamos isso em `extensions.x-dna` para um outro sistema MIF simplesmente ignorar (degradação graciosa), mas um DNA de volta recuperar tudo.

---

## 3. A renomeação `LessonLearned` → `Engram` (o ajuste do nome)

**Por que.** O Kind nasceu no SDLC (uma "lição de um ciclo", o oráculo Sage no deep-sleep ritual) e foi *promovido* a ser o substrato de memória geral. Mas uma preferência do usuário ("prefiro dark mode") ou um fato semântico ("minha empresa usa Postgres") **não são "lições aprendidas"** — são memórias. O nome ficou estreito para o que a coisa virou. E o código inteiro já é construído sobre a teoria do **engrama** (Semon): `ecphory`, `engraphy`, `homophony`, "engram intensity". O modelo mental já era esse; só o nome do Kind não acompanhou. `Engram` também é on-brand com a metáfora biológica do DNA/genoma/dupla-hélice, e é distintivo/ownable (diferente do genérico "Memory", que colidiria com o `mif-spec.dev/v1 · Memory` de intercâmbio).

**"Lição Aprendida" não some — vira uma lente, não o substrato.** A leitura que reconcilia tudo: uma *lição aprendida* é um **Engram com affect reflexivo (regret/wistful) numa área de SDLC**. Então mantemos "Lições Aprendidas" como uma **view filtrada** sobre Engrams no Studio (o `s-sdlcv2-memorias-market-viz`), não como o nome do tipo. O SDLC ganha a lente; a memória ganha o nome certo.

**Como renomear sem quebrar (isto é não-trivial — a identidade DNA é o par `(apiVersion, kind)`, e há goldens de hash-parity Py↔TS + dados em disco).** Plano de compatibilidade:

1. **Novo descritor `engram.kind.yaml`** com `target_kind: Engram` e `target_api_version: github.com/ruinosus/dna/v1` (memória deixa de ser `/sdlc/v1` — é preocupação de núcleo agora). Schema idêntico ao atual.
2. **`LessonLearned` (`/sdlc/v1`) e o alias `sdlc-lesson-learned` continuam registrados como alias depreciado** que resolve para o mesmo storage/schema. É preciso um **mapa de alias em read-time**: `(sdlc/v1 · LessonLearned)` e `sdlc-lesson-learned` → `Engram`. Assim **dados já gravados (`kind: LessonLearned`) continuam resolvendo** sem migração obrigatória.
3. O campo `alias` do descritor é hoje uma string única — back-compat exige ou suporte a `aliases: []`, ou uma re-registro fino. *Item explícito para o Claude Code.*
4. **Novas escritas usam `Engram`.** Migração opcional (reescrever `kind:` nos docs em disco) é um passo separado, não bloqueante.
5. Atualizar os goldens de hash-parity para o novo descritor; adicionar um golden que prova a **resolução do alias** (um doc `LessonLearned` lido como `Engram`).

O `display_label` do Kind passa a `Engrama` (pt-BR); "Lições Aprendidas" permanece como rótulo **da view SDLC**, não do Kind.

---

## 4. Peça 1 — o Kind de passthrough (`mif-memory.kind.yaml`)

> **Implementado em `s-mif-passthrough-kind`** (feature `f-portable-memory`):
> o descritor rascunhado aqui foi movido pra
> `packages/sdk-{py,ts}/{dna/extensions,src/extensions}/mif/kinds/memory.kind.yaml`
> (extensão dedicada `mif`, no mesmo espírito de `agentskills`/`soulspec` — não
> dentro de `helix`), com três correções contra a spec real do MIF (`id` é
> UUID puro no perfil Markdown, não `urn:mif:`; o campo é `validUntil`, não
> `validTo`; `relationships[].type` é string aberta, não um enum fechado — o
> enum do rascunho tinha 4 dos 9 valores errados). Este arquivo `.kind.yaml`
> não fica mais em `docs/design/` — o descritor real é a fonte única.

Entregue junto: `mif-memory.kind.yaml`. É um `KindDefinition` que registra `mif-spec.dev/v1 · Memory` (plano `record`), seguindo o padrão de `evidence.kind.yaml`. Pontos:

- **`origin: mif-spec.dev`** e **`target_api_version: mif-spec.dev/v1`** — o dono nomeia o schema. Um `.memory.json` importado é validado contra o schema do *MIF*, não contra um schema DNA-flavored.
- **Os três níveis de conformidade do MIF** viram três blocos do schema: Level 1 (`required`: id/type/content/created), Level 2 (title, namespace, temporal, relationships…), Level 3 (`provenance`, `embedding`, `extensions`).
- **`extensions` é `additionalProperties: true`** — o cofre onde a física do DNA (`x-dna.*`) viaja.
- **Open item honesto**: o MIF nomeia arquivos `<slug>.memory.md`; o `marker` do bundle DNA é um nome fixo. Byte-fidelidade *literal* precisa de um pequeno ajuste no storage-pattern — **fora do MVP** (decisão #3). Até lá o round-trip é **field-faithful** (todos os campos preservados), não byte-faithful (o arquivo pode reserializar em ordem diferente). Suficiente para os Círculos A/B.

---

## 5. Peça 2 — os verbos `export` / `import`

Seguem a superfície Click que os outros verbos de `dna memory` já usam (`--scope`, `--tenant`, `--personal`, `--kind`, `--json`) — sem vocabulário novo.

### `dna memory export`

```text
dna memory export [OPTIONS]

  Projeta Engrams nativos para um bundle MIF portável.
  Determinístico, sem LLM, sem rede.

  --format {mif|omp|pam}   Formato de intercâmbio.            [default: mif]
  --out PATH               Saída (.memory.md por doc, ou um JSON-LD único
                           com --bundle).
  --bundle                 Emite um único JSON-LD em vez de N arquivos .md.
  --personal               Exporta a SUA partição pessoal (DNA_PERSONAL_ID).
  --include-forgotten      Inclui memórias bi-temporalmente invalidadas
                           (valid_to<now) — com o temporal preservado.
  --scope / --tenant / --kind / --json
```

`--include-forgotten` importa: a portabilidade tem que carregar o *histórico*, não só o vivo — senão o supersession vira delete silencioso na saída.

### `dna memory import`

```text
dna memory import PATH [OPTIONS]

  Ingere um bundle MIF (.memory.md / .memory.json) — armazena verbatim como
  mif-spec.dev/v1·Memory E projeta para Engram (indexável/recuperável).

  --as {passthrough|native|both}   Guardar o Kind MIF cru, projetar para
                                    Engram, ou ambos.          [default: both]
  --personal                       Ingere na SUA partição pessoal.
  --dedupe {id|content-hash|off}   Evita reimportar a mesma memória. [default: id]
  --scope / --tenant / --json
```

`--as both` é o default: o documento MIF original fica guardado byte-fiel (auditoria/re-export estável) **e** uma projeção `Engram` entra no índice para ser recuperável pelo motor de recall.

**Privacidade (não-negociável).** `--personal` respeita `INV-PERSONAL`: só toca a partição `personal:<oid>` do próprio chamador (identidade resolvida server-side, nunca argumento). Um export pessoal **nunca** vaza memória de workspace; um import pessoal **nunca** cai numa partição compartilhada. É isso que torna "exportável" seguro — o usuário leva a *dele*, não a de todos.

---

## 6. A estabilidade de id no round-trip (o detalhe que quebra se ignorado)

Risco clássico: exportar → reimportar cria **duplicata** porque o id mudou.

> ⚠️ **Resolvido em `s-memory-interchange-verbs` — a redação original abaixo
> (numerada 1-3) ficou como registro histórico da pergunta em aberto que a
> story herdou; a decisão REAL implementada diverge dela em dois pontos e
> está em `dna/memory/interchange.py` (module docstring, ponto 1):**
>
> - o id mintado/pinado é uma **string plana** (o `id` do perfil Markdown),
>   **não** `urn:mif:<uuid>` — essa forma é o `@id` do JSON-LD, uma projeção
>   *derivada*, nunca escrita no frontmatter Markdown (ver a correção #1 do
>   descritor `mif/kinds/memory.kind.yaml`);
> - o pin fica em `Engram.spec.encoding_context["mif_id"]` (a chave já é
>   `additionalProperties: true`), **não** num `source_ref` — um
>   `source_ref` é semanticamente "artefato do qual esta memória deriva"
>   (mapeia para `relationships[derived-from]`/`provenance.wasDerivedFrom`);
>   usá-lo para o pin de identidade colidiria com essa mesma linha da tabela
>   num export subsequente.
>
> `--dedupe id` compara esse valor pinado: para `--as native`/`both`, contra
> `encoding_context.mif_id` nos Engrams já existentes; para `--as
> passthrough`/`both`, contra o `id` do próprio doc `Memory` (mesmo campo lá
> — sem pin necessário).

Redação original (histórica):

1. No **export** de um Engram nascido no DNA, minte um `urn:mif:<uuid>` **uma vez** e guarde-o de volta no doc (em `encoding_context.extensions` ou como `source_ref` `mif:urn:...`). Próximo export → mesmo `@id`.
2. No **import** de um MIF, preserve o `@id` no Engram projetado (via `source_ref` `mif:urn:...`). Re-export → mesmo `@id`.
3. `--dedupe id` usa esse `@id` pinado como chave de idempotência (espelhando como `remember` já é idempotente por text-hash no índice).

Resultado: DNA→MIF→DNA e MIF→DNA→MIF convergem, sem duplicar.

---

## 7. O experimento de round-trip (a prova) — decisão #4: A + B agora, C depois

Análogo de memória dos "Experimento 1/2" do `dna-market-critique.md`, e a demonstração de interoperabilidade que aquele doc cobrava.

### Círculo A — round-trip interno (fidelidade de campo) · **MVP**

```text
seed N Engrams (via dna memory remember)
  → dna memory export --format mif --out /tmp/mif
  → dna memory import /tmp/mif --scope roundtrip-test --as native
  → diff semântico dos specs
```

**Aceite:** todo campo da §2 sobrevive; `x-dna.*` voltam idênticos; `valid_to`/`superseded_by` preservam a cadeia de supersession; nenhuma duplicata. Ligar no `memory_conformance_suite` (`dna/testing/memory_conformance.py`) como um caso novo "interchange round-trip".

### Círculo B — import real do Claude (a dor de mercado) · **MVP**

```text
export de memória do Claude (a Import Tool da Anthropic, mar/2026)
  → adaptador claude-export → MIF   (mapeador fino)
  → dna memory import --as both --personal
  → dna memory recall "<paráfrase de um fato importado>" --personal
```

**Aceite:** um fato que veio do Claude é recuperável no DNA por **paráfrase** (não só token exato) — provando que passou pelo plano semântico, não só pelo storage. É o *screenshot* que vende: "sua memória do Claude, recuperável no DNA, offline."

### Círculo C — o triângulo (neutralidade) · **fast-follow, não MVP**

```text
Claude → MIF → DNA → export MIF → import em ferramenta C (mem0/Letta/Obsidian)
```

**Aceite:** a memória sobrevive a três fornecedores sem o DNA ser um beco (não é one-way como a Import Tool). É a prova de "camada neutra" — e o material de marketing do dna-cloud. Depende do import de terceiro funcionar, então vem **depois** que A+B passam.

### O que medir

| Métrica | Como | Meta |
|---|---|---|
| Fidelidade de campo | diff dos specs pré/pós | 100% dos campos §2 |
| Preservação bi-temporal | cadeia supersede→valid_to intacta | sem perda de histórico |
| Recuperabilidade por paráfrase | recall com cue sem token compartilhado | hit no top-3 (com `embed-onnx`) |
| Idempotência | reimportar 2× | zero duplicatas |
| LOC de adaptador por formato | mapeador claude→MIF | baixo (< ~150 LOC = "fino") |

A última métrica responde à pergunta do `dna-market-critique.md` ("valor difícil de reproduzir"): se cada novo formato custa ~150 linhas e ganha de graça o motor de recall/decay/bi-temporalidade, o DNA faz algo que uma pasta de YAML + Pydantic não faz.

---

## 8. O ângulo dna-cloud (evolução do produto)

Export/import de memória não é só SDK — é **produto**, e casa com o `PRODUCT.md` do dna-cloud.

- **Recurso de tier.** Hoje os planos dizem "memory read-only (Free) / read+write (Pro)". `export` cabe no **Free** (levar a sua memória embora é um direito, não um upsell — e é barato de servir); `import` + `--as both` + o passthrough MIF cabem no **Pro** (ingestão + projeção indexada consomem quota). Isso dá uma razão concreta e honesta para o upgrade, sem esconder dados atrás do paywall.
- **Posicionamento anti-lock-in (o contraintuitivo poderoso).** O SaaS pago é justamente o que **te deixa sair com a tua memória**. Num mercado onde a Import Tool da Anthropic é one-way (só *entra* no Claude), o dna-cloud pode ser o único que faz o *round-trip completo*. Isso transforma o `portable` de "engineered, alive, **portable**" (a voz de marca do `PRODUCT.md`) de slogan em recurso demonstrável.
- **Superfície de portal.** Uma tela "Minha memória" no portal: listar (o MCP-App card SEP-1865 já renderiza isso), exportar com um botão, importar de um `.memory.md`. Encaixa no backlog de Settings/perfil de usuário que a `tenancy-layers.md` já menciona como deferido.
- **Confiança = conversão.** Para o público do `PRODUCT.md` (devs que "querem a portabilidade do DNA sem self-hostar"), "você pode exportar tudo a qualquer momento" reduz o medo de adotar. Anti-lock-in vira argumento de vendas, não concessão.

---

## 9. Ordem de implementação (menor caminho até a prova)

1. **Renomeação `Engram`** — `engram.kind.yaml` + alias read-time de `LessonLearned`/`sdlc-lesson-learned` + goldens de parity/alias. (§3) — *primeiro, porque tudo abaixo fala "Engram"*
2. **`mif-memory.kind.yaml`** no scope de extensões + teste de hash-parity Py↔TS. — *pequeno*
3. **Módulo de projeção** `dna/memory/interchange.py` — funções puras `to_mif(spec)` / `from_mif(doc)` da §2, com o cofre `x-dna`. Determinístico, testável, sem rede. — *o coração, ~1 dia*
4. **Verbos CLI** `export`/`import` embrulhando a projeção. — *plumbing Click*
5. **Círculo A** ligado ao `memory_conformance_suite`. — *a prova barata*
6. **Adaptador `claude-export→MIF`** + Círculo B. — *a prova que vende*
7. (depois) storage-pattern byte-faithful; `--format omp|pam`; Círculo C; superfície dna-cloud; participação no W3C CG.

Os passos 1–5 são um spike fechado que responde "dá pra fazer round-trip sem perda?". O 6 vira demo.

---

## Decisões que sobraram para o Jefferson (na revisão)

- Confirmar o par de identidade do novo Kind: **`github.com/ruinosus/dna/v1 · Engram`** (tirar do `/sdlc/`) — é o certo, mas é a mudança de identidade que puxa o trabalho de alias. Ok?
- Confirmar a política de tier do §8 (export no Free, import no Pro).
- Migração de dados: deixar os docs antigos como `kind: LessonLearned` resolvendo via alias (zero migração), ou rodar um rewrite único para `Engram`?

---

## Fontes (código e spec)

**DNA (local):**
- `dna/extensions/sdlc/kinds/lesson-learned.kind.yaml` — schema real do Kind de memória (a ser renomeado)
- `dna/memory/memory_type.py` — classificação CoALA (episodic/semantic/procedural)
- `dna/memory/{verbs,ecphory,decay,personal,encoding_context}.py` — os verbos e a física
- `dna/testing/memory_conformance.py` — a bateria onde o Círculo A se liga
- `dna/docs/concepts/search-and-memory.md` — o modelo (personal vs workspace, bi-temporalidade)
- `dna/docs/concepts/tenancy-layers.md` — Settings/perfil deferido (superfície de portal)
- `dna-cloud/PRODUCT.md` — planos, voz de marca ("portable"), superfície de portal
- `dna/docs/analysis/dna-market-critique.md` — a conversa anterior (experimentos de portabilidade/proveniência)

**MIF (web):**
- [MIF — Memory Interchange Format (GitHub)](https://github.com/zircote/MIF) — schema, níveis de conformidade, 9 tipos de relação, exemplos `.memory.md` / `.memory.json`
