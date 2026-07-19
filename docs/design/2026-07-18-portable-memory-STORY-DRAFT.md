# Rascunho de board — Feature `f-portable-memory` (para `dna sdlc`)

*Base para o Claude Code criar via CLI (`dna sdlc` / create_feature / create_story) — NÃO hand-editar YAML do board. Design completo: `docs/design/2026-07-18-portable-memory-design.md`.*

---

## Feature: `f-portable-memory` — Memória portável (Engram ⇄ MIF)

**Intenção.** Dar ao DNA a membrana de intercâmbio que falta: exportar/importar memória sem perda, adotando o MIF como fio neutro. Motor nativo mantido (renomeado `LessonLearned` → `Engram`); MIF carregado byte-fiel via a regra "o dono nomeia o schema".

**Fora de escopo (MVP).** Byte-fidelidade literal; `--format omp|pam`; Círculo C (triângulo 3-fornecedores); superfície dna-cloud (vai para o scope `dna-cloud-dev`).

**Decisões a confirmar antes do plan gate da Story 1:** (a) identidade `github.com/ruinosus/dna/v1 · Engram` (tirar do `/sdlc/`); (b) política de tier (export Free / import Pro); (c) dados antigos via alias read-time (zero migração) vs rewrite único.

---

### Story 1 — Renomear `LessonLearned` → `Engram` (com alias de compat) · *bloqueia as demais*

**Como** substrato de memória do DNA, **quero** um nome que reflita o que virou (um traço de memória, não uma lição de SDLC), **sem** quebrar dados nem paridade.

**Acceptance:**
- Novo descritor `engram.kind.yaml` — `apiVersion: github.com/ruinosus/dna/v1`, `kind: Engram`, schema idêntico ao atual; espelho Py↔TS byte-idêntico; golden de hash-parity atualizado.
- `LessonLearned` (`/sdlc/v1`) e o alias `sdlc-lesson-learned` resolvem para `Engram` via mapa read-time; um doc gravado como `kind: LessonLearned` é lido como `Engram` (novo golden prova a resolução do alias).
- `display_label` do Kind = `Engrama` (pt-BR); a view SDLC "Lições Aprendidas" segue funcionando como **lente** (Engram com affect reflexivo em área de SDLC), não como nome do tipo.
- Zero migração obrigatória de dados; a suite de memória existente permanece verde.

### Story 2 — Kind de passthrough `mif-spec.dev/v1 · Memory`

**Acceptance:**
- `mif-memory.kind.yaml` (já rascunhado em `docs/design/`) movido para o path de extensão real + espelho TS; registra `mif-spec.dev/v1 · Memory`, plano `record`; golden de hash-parity.
- Um `.memory.json` de exemplo do MIF (Level 1/2) valida sem deformação; `extensions` aceita `additionalProperties`.

### Story 3 — Projeção `interchange` + verbos CLI `export`/`import`

**Acceptance:**
- `dna/memory/interchange.py`: `to_mif(spec)` / `from_mif(doc)` puros, determinísticos, sem rede, espelho Py↔TS; cobrem 100% do mapeamento §2 do design, com o cofre `x-dna`.
- Estabilidade de `@id` (URN `urn:mif:` pinado; `--dedupe id` idempotente — round-trip não duplica).
- `dna memory export` (`--format mif`, `--out`, `--bundle`, `--personal`, `--include-forgotten`) e `dna memory import` (`--as {passthrough|native|both}`, `--dedupe`, `--personal`) na superfície Click existente.
- `--personal` respeita `INV-PERSONAL` (identidade server-side; nunca vaza memória de workspace).

### Story 4 — Prova de round-trip (Círculo A) + adaptador Claude (Círculo B)

**Acceptance (A — a prova barata):**
- Caso "interchange round-trip" no `memory_conformance_suite`: N Engrams → export → import → diff; 100% dos campos §2, `x-dna` idênticos, cadeia `supersede`/`valid_to` preservada, zero duplicata.

**Acceptance (B — a prova que vende):**
- Adaptador `claude-export → MIF` (< ~150 LOC); `import --as both --personal`; um `recall` por **paráfrase** de um fato importado retorna hit no top-3 (com `embed-onnx`).

---

### (Follow-up, scope `dna-cloud-dev`) Story 5 — Superfície dna-cloud

Export no Free, import no Pro; tela "Minha memória" no portal (reusa o MCP-App card SEP-1865). Posicionamento anti-lock-in. Fora do MVP — ver §8 do design.
