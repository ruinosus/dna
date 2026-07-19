# Design: onboarding consentido — semear a memória do usuário ("bring your identity") sobre o Engram

*Proposta de design · Julho 2026 · Pesquisa 1 (deep research, 24 fontes, 25 claims verificados 3-0) + aterramento no Engram (provenance/source_refs, bi-temporalidade, forget/supersede, partição pessoal portável). Nada implementado — desenho para decisão. **Não é aconselhamento jurídico**; o fechamento legal por artigo da LGPD fica na Pesquisa 2.*

---

## 0. O achado que muda o enquadramento

A pesquisa confirmou uma coisa que vale ouro: **nenhum produto líder de memória faz isso hoje.** ChatGPT e Claude semeiam memória **só a partir das próprias conversas do usuário** (ou do export dele mesmo). Ninguém oferece um bootstrap que parte de um **identificador externo** (um nome, um LinkedIn, uma credencial) para já chegar te conhecendo. O "bring your identity" é **whitespace**.

E o segundo achado é o que torna isso jogável pra *nós* especificamente: os guardrails que a LGPD/GDPR exigem para fazer isso de forma defensável — **proveniência da fonte, minimização, consentimento, correção/apagamento** — mapeiam **quase 1:1** nas primitivas que o Engram já tem. Os outros teriam que construir a conformidade; o DNA **já nasceu com ela**. Isso é diferenciação *e* defensabilidade no mesmo movimento.

> Tese: o DNA é provavelmente a única base de memória cujo substrato já carrega os mecanismos de compliance que essa funcionalidade exige. O "bring your identity" consentido é o caso de uso que transforma provenance + bi-temporalidade de detalhe técnico em vantagem de produto.

---

## 1. A fronteira que separa "brilhante" de "tóxico"

A pesquisa reforçou o corte que já tínhamos intuído: **quem puxa o gatilho e o que acontece antes de gravar.** Este design é *inteiramente* a versão consentida:

- O usuário **traz** um identificador (não "nós descobrimos você").
- O agente **propõe um rascunho** de memórias — nada é gravado ainda.
- O usuário **revisa e aprova item a item** — só o aprovado vira Engram.
- Cada memória gravada **carrega a fonte** (provenance) e é **reversível** (forget/supersede) e **exportável**.

A versão agressiva (agente descobre sozinho) é a **Pesquisa 2** — e a pesquisa já sinalizou por que ela é o campo minado: puxar de fonte de terceiro (enrichment/scraping) é **coleta indireta**, que dispara o dever de notificar o titular (GDPR Art. 14 / equivalente LGPD) com prazo estrito, e a régua de "necessidade" é **mais alta** para dado de terceiro do que para dado de primeira mão — o que empurra a favor de consentimento explícito e de o usuário trazer o próprio dado.

---

## 2. Prior art — o que existe (e por que o nosso ângulo é novo)

| Fonte | O que faz | Lição para nós |
|---|---|---|
| **ChatGPT / Claude memory** | Semeiam da própria conversa; opt-in, revisável, editável, exportável; guardrail de dado sensível (evitam lembrar saúde etc. sem pedido explícito) | O modelo *consent + review + export* já é padrão de mercado — reutilizável. Mas o bootstrap por identidade externa **ninguém faz** |
| **Claude Import Tool** (mar/2026) | Import manual (colar texto + "Add to memory"), revisão pós-hoc, portável em texto | Confirma o padrão *user-initiated + review*. É o análogo mais próximo — e ainda assim é one-way e a partir do *seu próprio* export, não de uma identidade |
| **Enrichment B2B** (People Data Labs, HubSpot/Breeze) | Enriquecem dado **profissional**; **excluem** categoria especial; **proíbem** perfilamento por atributo sensível e decisões de elegibilidade | Fonte legalmente **constrangida e ruim** para memória de consumidor. E usar = coleta indireta (dever de notificar). Não é o atalho que parece |
| **W3C DID + Verifiable Credentials + OpenID4VP** | Identidade **auto-controlada**, com **selective disclosure** (o usuário escolhe o que revela) | **O primitivo certo.** É o feed de identidade "minimal-disclosure" consentido — a alternativa privacy-preferable ao enrichment. É o norte |

A leitura estratégica: o mercado já validou *consent + review + export* (podemos reusar a UX), o atalho do enrichment é uma armadilha jurídica, e o caminho nobre (DID/VC) existe como padrão pronto pra consumir.

---

## 3. O fluxo (a funcionalidade)

```
[1] Consent gate            → consentimento explícito, com PROPÓSITO declarado e granular
        │                     (LGPD/GDPR: base legal + purpose limitation)
        ▼
[2] Identity feed           → o usuário TRAZ o dado. Três vias, da mais nobre à mais pragmática:
        │                     (a) VC/DID via OpenID4VP (selective disclosure) — o norte
        │                     (b) identificador + conta conectada que o USUÁRIO liga (LinkedIn/OAuth dele)
        │                     (c) colar texto (o padrão Claude Import) — MVP mais barato
        ▼
[3] Draft proposal          → o agente propõe Engrams CANDIDATOS (memory_type + source_ref),
        │                     NADA gravado. Filtro de categoria especial ANTES do rascunho.
        ▼
[4] Review & approve        → aceitar / editar / rejeitar item a item.
        │                     Só o aprovado é escrito (partição PESSOAL, INV-PERSONAL).
        ▼
[5] Direitos contínuos      → forget/supersede, export portável, log de auditoria.
                              (LGPD/GDPR: rectificação, apagamento, transparência)
```

O ponto de design mais importante é o **passo [3]→[4] ser um gate duro**: o rascunho é um *staging* não-persistido. Nenhum Engram nasce sem passar pelo aprovar humano. É isso que torna a coleta *direta do titular* (ele confirma cada fato), neutralizando metade do problema de coleta indireta.

---

## 4. O mapeamento que é o coração do design: dever legal ↔ mecânica do Engram

Cada dever que a pesquisa verificou, o mecanismo do Engram que já o atende, e o que falta construir:

| Dever (LGPD/GDPR) | Já atendido pelo Engram | O que construir |
|---|---|---|
| **Divulgar a fonte** do dado (GDPR Art. 14(2)(f)) | `source_refs` por fato **é** a proveniência | Superficializar a fonte na UI de review e no card de memória |
| **Exatidão / rectificação** (Art. 5(1)(d)) | `forget`/`supersede` + bi-temporalidade (`valid_from/valid_to`) | Botão "corrigir" que faz supersede; nada é hard-delete |
| **Minimização** (Art. 5(1)(c)) | `memory_type` + área já estruturam o que entra | Gate de campos: semear **só** name/role/preferences/context; recusar categoria especial no rascunho |
| **Limitação de propósito** (Art. 5(1)(b)) | — | Carimbar o propósito no consentimento e no `encoding_context` do Engram semeado |
| **Base legal = consentimento explícito** | partição `personal:<oid>`, identidade server-side | Consent gate versionado (guardar o registro do consentimento como um Kind próprio) |
| **Direito de apagar / exportar** | `forget` + o `dna memory export` (design de memória portável) | Reusar o export; expor "apagar tudo o que veio deste onboarding" (filtro por `source_ref`) |
| **Guardrail de categoria especial** | — | Classificador que barra saúde/raça/orientação/etc. **antes** do rascunho (espelhar o que ChatGPT/Claude fazem) |

Repara: das sete linhas, **quatro já estão prontas** no substrato. O trabalho novo é o gate de consentimento, o filtro de categoria especial, e a UI de review — não a fundação de compliance.

---

## 5. O que reusar para acelerar

1. **OpenID4VP + W3C DID/VC** como o feed de identidade minimal-disclosure (via [1] a). É padrão, dá selective disclosure, e é a resposta "necessidade mais alta para dado de terceiro" — porque não é terceiro, é o próprio usuário apresentando uma credencial que ele controla.
2. **A UX de consent/review/export já embarcada** por Claude e ChatGPT — não reinventar; copiar o padrão validado (opt-in, painel editável, export em texto).
3. **O `dna memory export/import`** que já desenhamos — o Engram semeado no onboarding *é* portável pelo mesmo caminho. As duas features se compõem: onboarding **produz** Engrams; portabilidade os **carrega**.
4. **O MCP-App card (SEP-1865)** que já renderiza a lista de memória — vira a tela de review com pouca coisa nova.

---

## 6. Escopo de MVP (o menor caminho defensável)

- **Feed [2] via (c) colar / (b) conta que o usuário liga** — evita completamente o enrichment de terceiro no MVP (a via legalmente limpa). DID/VC (a) fica como norte da v2.
- **Gate [3]→[4] obrigatório** — sem auto-write. Este é o coração; não cortar.
- **Filtro de categoria especial** no rascunho.
- **Consent + propósito** carimbados; um Kind `ConsentGrant` (proposta) guardando o registro.
- **Reuso** do export e do memory card.
- **Fora do MVP:** enrichment de terceiro (é a Pesquisa 2), descoberta autônoma, DID/VC (v2).

Ou seja: no MVP o usuário **traz o texto/uma conta dele**, o agente **propõe**, ele **aprova**, vira Engram pessoal com fonte. Zero coleta indireta — o caso mais defensável possível.

---

## 7. Ganchos com o resto

- **Engram/portabilidade:** esta feature é *upstream* do `dna memory export/import`. Compartilha partição pessoal, `source_refs`, bi-temporalidade. Implementar depois (ou em paralelo tardio) do MVP de portabilidade.
- **dna-cloud:** é onboarding — mora no fluxo de cadastro do portal. "Comece já te conhecendo, e você aprova cada coisa" é uma promessa de onboarding forte *e* um selo de confiança (o controle é visível). Provável recurso de Pro; o `ConsentGrant` + audit log são argumento enterprise/compliance.
- **Responsible AI:** o gate de aprovação + provenance + o filtro de categoria especial são exatamente o que uma DPIA/RIPD vai querer ver. O design já nasce auditável.

---

## 8. Riscos e decisões abertas

1. **Legal não-fechado.** A pesquisa foi rigorosa em GDPR (texto primário + EDPB), mas **LGPD e CCPA foram inferidos por analogia**, não verificados por artigo. → **É exatamente o trabalho da Pesquisa 2** antes de qualquer código que toque dado real.
2. **Categoria especial é o maior perigo.** Um LinkedIn revela cargo (ok), mas um nome + busca pode arrastar afiliação política/religiosa/saúde (proibido). O filtro tem que ser conservador e barrar na dúvida.
3. **Onde mora o consentimento** — Kind `ConsentGrant` no DNA (versionado, auditável) vs. só no dna-cloud? Proponho no DNA (é dado de governança de primeira classe, e viaja com a identidade). A confirmar.
4. **DID/VC agora ou v2?** Recomendo v2 — o MVP com "trazer texto/conta própria" já é defensável e muito mais barato. A confirmar.
5. **Escopo do feed** — restringir a **contexto profissional** (name/role/company/preferences) no MVP reduz drasticamente a superfície de categoria especial. Recomendo travar nisso.

---

## 9. Próximo passo

Rodar a **Pesquisa 2** (envelope legal LGPD por artigo + a versão agressiva) — as *open questions* que a Pesquisa 1 deixou já são a espinha dela: obrigações exatas da LGPD (Art. 9 transparência, Art. 18 direitos, orientação da ANPD sobre coleta indireta e legítimo interesse) e CCPA/CPRA para dado de terceiro; se algum enrichment pode ser usado com consentimento explícito como base; e o schema concreto de consent UX + audit log. Fechada a #2, este doc vira uma feature `f-consented-bootstrap` no board (provavelmente com uma story de `ConsentGrant` no SDK e o resto no dna-cloud).

---

## Fontes (Pesquisa 1 — verificadas 3-0)

- [OpenAI — Memory and new controls for ChatGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) — memória opt-in, revisável, guardrail de sensível
- [Claude — Memory](https://claude.com/blog/memory) · [Import/export your memory from Claude](https://support.claude.com/en/articles/12123587-import-and-export-your-memory-from-claude) — opt-in, review, portável em texto
- [People Data Labs — Acceptable Data Use Policy](https://privacy.peopledatalabs.com/policies?name=acceptable-data-use-policy) — proibição de perfilamento sensível/elegibilidade; sem categoria especial
- [HubSpot — Privacy Policy](https://legal.hubspot.com/privacy-policy) — coleta de terceiros/fontes públicas (cenário de coleta indireta)
- [GDPR Art. 14](https://gdpr-info.eu/art-14-gdpr/) · [Art. 5](https://gdpr-info.eu/art-5-gdpr/) — divulgar fonte, prazo; propósito, minimização, exatidão
- [EDPB Opinion 28/2024 (AI models)](https://www.edpb.europa.eu/system/files/2024-12/edpb_opinion_202428_ai-models_en.pdf) — sem hierarquia de bases; necessidade mais estrita para dado de terceiro
- [W3C DID 1.0](https://www.w3.org/TR/did-1.0/) — identidade auto-controlada · [OpenID4VP (iGrant)](https://docs.igrant.io/concepts/openID4vc/) — selective disclosure
- [AI Agents with DIDs and VCs (arXiv)](https://arxiv.org/html/2511.02841v1) — agente consumindo credenciais verificáveis

*Ressalvas da pesquisa: claims de produto são auto-reportados pelos fornecedores (não auditados); cobertura LGPD/CCPA é por analogia ao GDPR — a verificação por artigo é a Pesquisa 2.*
