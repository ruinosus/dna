# Envelope legal: descoberta autônoma do usuário ("o agente te pesquisa sozinho")

*Estudo de viabilidade · Julho 2026 · Pesquisa 2 (deep research, 22 fontes, 24 claims verificados 3-0, 1 refutado). Contraparte "agressiva" do onboarding consentido do Doc 1. **NÃO é aconselhamento jurídico** — é material de decisão para levar a um advogado antes de qualquer código que toque dado real.*

---

## 0. Veredito

| Cenário | Brasil (LGPD) | UE (GDPR) | Veredito |
|---|---|---|---|
| **Amplo** — qualquer dado público sobre a pessoa (busca de nome, redes, people-search) | proibido de fato | proibido de fato | 🔴 **NO-GO** |
| **Estreito** — só dado profissional B2B (nome/cargo/empresa), com transparência + opt-out fácil | possível **sob condições** | possível **sob condições** | 🟡 **GO CONDICIONADO** |

O ponto que sustenta tudo, em uma frase: **"dado público" nunca significa "dado livre para usar".** Essa é a falácia que derruba a versão agressiva.

---

## 1. Por que o "é público, então posso usar" não vale (o núcleo)

**LGPD.** O art. 7 §4 dispensa consentimento **só** para dados *"tornados manifestamente públicos **pelo titular**"* — e mesmo assim resguardados os direitos e princípios da lei. O *"pelo titular"* é a palavra que mata a ideia: dado postado por terceiro, raspado de rede social alheia, ou vindo de people-search/broker **não** está coberto. Todo o resto de dado público (art. 7 §3) segue **condicionado a finalidade, boa-fé e interesse público** que justificou torná-lo acessível. Ou seja: a base de "coleta livre porque está no Google" simplesmente não existe.

**GDPR.** Idêntico em espírito. As EDPB Guidelines 1/2024 dizem literalmente que *"o fato de dados terem sido manifestamente tornados públicos não significa automaticamente que possam ser tratados sob o Art. 6(1)(f)"* (para. 52), exigem teste estrito de necessidade (*"não cobre o que é meramente útil"*, para. 28; "não haver alternativa menos intrusiva", lido junto com minimização, para. 29), e o Exemplo 6 mostra que nem foto auto-postada pode ser razoavelmente reusada/republicada por um terceiro. Não há isenção de "dado público" no GDPR.

---

## 2. LGPD, artigo por artigo (a jurisdição primária)

| Artigo | O que exige | Efeito na descoberta autônoma |
|---|---|---|
| **Art. 7 §4** | Dispensa de consentimento só p/ dado manifestado público **pelo próprio titular** | Broker/people-search/perfil de terceiro **fora** da dispensa |
| **Art. 7 §3** | Dado público condicionado a finalidade + boa-fé + interesse público | Reuso p/ enriquecer perfil comercial não se encaixa |
| **Art. 7 IX + Art. 10** | Legítimo interesse: finalidade **concreta e articulável**, só dado **estritamente necessário**, com balanceamento/RIPD; cede quando direitos do titular prevalecem | Coleta especulativa e aberta no onboarding **não** passa |
| **Guia ANPD Legítimo Interesse (2024)** | Teste de 3 fases (finalidade / necessidade / balanceamento e salvaguardas) **+ trava de expectativa razoável** (art. 10 II) — a *fonte* do dado (direto vs. terceiro vs. público) pesa | Enriquecer um usuário **novo, sem relação prévia**, de fonte que ele não esperava → pesa **contra** o controlador |
| **Art. 11** | Dado sensível: lista **exaustiva**, exige consentimento específico e destacado; **sem** hipótese de legítimo interesse e **sem** exceção de "dado público" (ao contrário do GDPR Art. 9(2)(e)) | Qualquer via de legítimo interesse **tem que excluir dado sensível na marra** |
| **Art. 9** | Transparência: informação fácil sobre o tratamento | Aviso em camadas + divulgação da fonte |
| **Art. 18** | Direitos do titular: canais fáceis p/ opt-out e eliminação | Botão de sair/apagar acessível |
| **Art. 37** | Registro de tratamento, incluindo o balanceamento | Documentar a decisão |
| **Art. 10 §3** | RIPD para tratamento de alto risco | Provável exigível aqui |

A leitura: o único caminho plausível é **legítimo interesse**, e ele é justamente onde a versão agressiva tropeça — na **trava de expectativa razoável**. Um usuário que acabou de se cadastrar não *espera* que você já tenha vasculhado a internet atrás dele. É esse o ponto que transforma "amplo" em NO-GO.

---

## 3. GDPR e EUA (as outras jurisdições)

**GDPR.** Sem isenção de dado público; base usual é Art. 6(1)(f) legítimo interesse, com necessidade estrita, e o balanceamento **fica menos favorável quanto mais os dados são agregados em perfis** (IAPP/WP29 06/2014, carregado na EDPB 1/2024). Coleta indireta ainda dispara o dever do Art. 14 de notificar o titular (conteúdo + prazo). Direção: contra people-search/agregação.

**EUA (CCPA/CPRA).** As isenções de B2B e de dado trabalhista **expiraram em 31/12/2022** — então dado de contato B2B está **totalmente em escopo**, e o direito de exclusão alcança dado coletado sobre o consumidor **de fontes de terceiros**, não só o coletado direto (FAQ CPPA). Ou seja: **mesmo a faixa estreita B2B** já dispara deveres de aviso/exclusão/opt-out na Califórnia.

---

## 4. Precedente de fiscalização (o que já foi punido)

- **Clearview AI — CNIL, €20M (20/out/2022)**, ordem de cessar coleta e apagar. A CNIL rejeitou legítimo interesse *apesar de todos os dados virem de fontes públicas/redes sociais*, pela intrusividade e pela falta de ciência dos titulares. É **o** precedente de "raspar dado público para um produto de perfilamento é ilegal e executável". **Ressalva honesta:** envolvia dado **biométrico** (categoria especial) e reconhecimento facial extremo — então ele **limita** o risco da faixa estreita não-biométrica, não a define 1:1. Mas é o farol.
- **FTC v. Kochava (EUA)** — broker vendendo geolocalização precisa que rastreava pessoas até locais sensíveis, sem consentimento → acordo (mai/2026) proibindo venda de localização sensível. Sinaliza apetite de fiscalização dos EUA contra dado sensível de terceiro comercializado sem consentimento.

---

## 5. O que isso significa para o NOSSO produto (a síntese)

Três conclusões práticas:

**(1) A versão amplamente agressiva morre aqui.** "O agente pesquisa seu nome e te diz o que achou" é NO-GO em BR e UE. Não construir. O único caso de uso que ela tinha — *pular o usuário* — é exatamente o que a lei proíbe (a trava de expectativa razoável existe justamente contra isso).

**(2) A faixa estreita (B2B profissional) converge de volta pro Doc 1.** Quando você empilha o que o GO-CONDICIONADO exige — finalidade concreta, balanceamento/RIPD, transparência com divulgação de fonte, opt-out e exclusão fáceis, minimização, exclusão dura de dado sensível — você chega **quase no mesmo lugar** do onboarding consentido que já desenhamos. A diferença prática entre "enriquecimento B2B com todas as salvaguardas" e "bring your identity consentido" encolhe até quase sumir. **A lei empurra você para o Doc 1.**

**(3) Existe um meio-termo defensável: "enriquecimento consentido" como passo opcional do Doc 1.** Em vez de descoberta autônoma, ofereça — *depois* do consentimento explícito e dentro do fluxo bring-your-identity — um passo opcional que preenche lacunas **só com dado profissional** (cargo/empresa), com **cada fato mostrado para aprovação** e a **fonte à mostra**. Isso dobra a faixa estreita GO-CONDICIONADO para dentro do design consentido, com o gate de aprovação neutralizando a coleta indireta. É o único jeito de capturar valor do enriquecimento sem entrar no campo minado.

---

## 6. Aviso que vale ouro: tecnologia ≠ base legal

O Engram ajuda a **operacionalizar** os deveres (proveniência = divulgação de fonte; forget/supersede = exclusão/rectificação; bi-temporalidade = retenção; partição pessoal = escopo), mas **não legaliza** o tratamento. A base legal tem que vir do **consentimento** ou do **legítimo interesse + balanceamento** — nunca do fato de "termos a arquitetura para isso". Confundir os dois é a armadilha clássica. Nosso substrato é ótimo para *provar conformidade*; ele não *cria* a permissão.

---

## 7. Condições para a faixa estreita (se um dia for perseguida)

Checklist mínimo antes de qualquer código que toque dado real (a validar com advogado):

- Finalidade concreta e articulável, documentada.
- Balanceamento formal (LIA) + RIPD (LGPD Art. 10 §3).
- **Escopo travado em dado profissional** (nome/cargo/empresa) — exclusão dura de categoria especial (Art. 11).
- Transparência em camadas **com divulgação da fonte** (LGPD Art. 9 / GDPR Art. 14), no ato ou próximo da coleta.
- Opt-out e exclusão fáceis (LGPD Art. 18); direito de revisão se houver perfilamento (Art. 20).
- Minimização e limites de retenção.
- Preferir **consentimento explícito** como base — a trava de expectativa razoável torna o legítimo interesse frágil para usuário novo.

---

## 8. O que um advogado ainda precisa fechar (não resolvido pela pesquisa)

- Prazo/mecânica exata do aviso do GDPR Art. 14 em escala, e se a EDPB Opinion 28/2024 fecha a exceção de "esforço desproporcional" para dado raspado/broker.
- LGPD Art. 20 (revisão de decisão automatizada) + Art. 9: pré-preencher um perfil **conta como decisão automatizada revisável**? Que aviso é obrigatório na coleta?
- Existe ação da ANPD ou decisão judicial **sobre people-search/broker não-biométrico** (fora do padrão Clearview) que calibre o risco de sanção da faixa estreita?
- Na faixa estreita por legítimo interesse: exige notificação individual (Art. 14) a cada usuário, ou um aviso geral/em camadas satisfaz a transparência em escala (LGPD Art. 9 + GDPR Art. 14)?

*Ressalvas da pesquisa: Clearview é biométrico (não é precedente 1:1 para nome/cargo). O veredito Brasil se apoia no texto da LGPD + Guia ANPD 2024; pontos comparativos usam fontes secundárias de alta qualidade (Mattos Filho, Securiti, IAPP) como glosa sobre o texto primário. Art. 14 (prazo) e LGPD Art. 20 foram inferidos da estrutura, não de citação verbatim — daí estarem no §8.*

---

## 9. Recomendação

Fechar a versão agressiva **como NO-GO** e registrar isso (é decisão, não pendência) — o valor era pular o usuário, e é exatamente o ilegal. Levar adiante **apenas** o "enriquecimento consentido" do §5(3), como **passo opcional do `f-consented-bootstrap`** (Doc 1), gated por aprovação e travado em dado profissional. Antes de qualquer código que toque dado real, passar o checklist do §7 e as perguntas do §8 por um advogado de privacidade BR (LGPD/ANPD). O substrato do DNA já cobre a parte de *provar* conformidade; falta a base legal e o parecer.

---

## Fontes (Pesquisa 2 — verificadas 3-0)

**LGPD / ANPD (Brasil):**
- [LGPD — tradução oficial (DataGuidance)](https://www.dataguidance.com/sites/default/files/lgpd_translation.pdf) · [Art. 7 (lgpd-brazil.info)](https://lgpd-brazil.info/chapter_02/article_07)
- [ANPD — tratamento legal de dados / Guia de Legítimo Interesse 2024 (Mattos Filho)](https://www.mattosfilho.com.br/en/unico/anpd-legal-data-processing-brazil/)
- [Brazil guidance on legitimate interest (Securiti)](https://securiti.ai/brazil-guidance-on-degitimate-interest/)

**GDPR (UE):**
- [EDPB Guidelines 1/2024 — Legitimate Interest](https://www.edpb.europa.eu/system/files/2024-10/edpb_guidelines_202401_legitimateinterest_en.pdf)
- [Publicly available data under GDPR (IAPP)](https://iapp.org/news/a/publicly-available-data-under-gdpr-main-considerations)

**EUA:**
- [CPPA FAQ — CCPA/CPRA (isenção B2B expirada; exclusão de dado de terceiros)](https://cppa.ca.gov/faq.html)

**Fiscalização:**
- [CNIL — €20M contra Clearview AI](https://www.cnil.fr/en/facial-recognition-20-million-euros-penalty-against-clearview-ai)
- [FTC v. Kochava](https://www.ftc.gov/legal-library/browse/cases-proceedings/ftc-v-kochava-inc)
