# Auth de agentes nos padrões de mercado — desenho

**Data:** 2026-07-30
**Repo:** `ruinosus/dna` (SDK).
**Motivo:** o fundador pediu explicitamente para *"adequar TUDO aos padrões de
mercado"* depois de a pesquisa mostrar que a auth de agentes saiu de conceito
para produção em junho/2026. Esta spec ataca as **duas** pontas que a spec de
delegação (`2026-07-30-a2a-delegation-design.md`) resolveu com a versão simples.
**Estado:** proposta, aguardando revisão.

---

## 1. O que estamos consertando, e por que agora

A spec de delegação estabeleceu uma regra que **continua certa**: nunca repassar
o token do usuário a um agente remoto — repassá-lo faria de cada remoto uma
impersonação completa dele contra o nosso próprio MCP.

Mas a **substituição** que ela escolheu está datada, e isso é achado de pesquisa,
não opinião:

| | o que fizemos | o que o mercado shipou em 2026 |
|---|---|---|
| credencial do remoto | uma estática, configurada por workspace | **ID-JAG** — token curto, escopado ao alvo, derivado da identidade do usuário |
| decisão de escopo | `data_scope.kinds`, lista estática por remoto | **AuthZEN** — ponto de decisão consultado **por chamada** |

Uma credencial estática de workspace é **exatamente a chave longeva que o ID-JAG
existe para eliminar.** E ela perde a dimensão do usuário: o remoto não sabe *por
quem* a chamada é feita, então não pode aplicar política nenhuma por pessoa.

**Nada disto invalida o que está no ar.** A fronteira está no lugar certo; o que
muda é **o que enche a credencial** e **quem decide o escopo.** As duas evoluções
são aditivas.

## 2. O que a pesquisa estabeleceu (com datas)

- **ID-JAG** (Identity Assertion JWT Authorization Grant) — o IdP emite um token
  curto e escopado para **um alvo específico**, a partir da identidade do
  usuário, sem tela de consentimento por app e sem chave longeva. Encadeia dois
  fluxos OAuth existentes: **token exchange (RFC 8693)** para obter o ID-JAG no
  IdP, e **JWT bearer grant** para trocá-lo por um access token no alvo. Perfil
  sobre `draft-ietf-oauth-identity-chaining`. Okta o chama **Cross-App Access
  (XAA)**; Auth0 documenta o mesmo.
- **MCP enterprise-managed authorization** shipou **18/06/2026** — e é por ela
  que o ID-JAG saiu do papel: roda em Claude, VS Code e SaaS. Audience binding
  por **RFC 8707 (Resource Indicators)**, delegação por **RFC 8693**.
- **AAP** (Agent Authorization Profile for OAuth 2.0, draft IETF) — claims
  estruturados para identidade do agente, **cadeia de delegação**, task binding
  e oversight. Perfila OAuth existente em vez de criar protocolo.
- **A forma do token delegado**, que é o detalhe load-bearing:
  **`sub`** = o humano · **`act`** = o agente · **`aud`** = o recurso alvo.
- **AuthZEN** — scope não responde *"este agente, agindo por este usuário, pode
  chamar esta tool com estes argumentos?"*. Precisa de um PDP consultado antes
  da tool rodar.

## 3. O que já temos, e que torna isto mais barato do que parece

- **Dois IdPs em produção:** WorkOS (a porta padrão) e Microsoft Entra.
- **Entra OBO já roda**, no pacote Graph do `mcp-entra` — e OBO é o ancestral
  Microsoft exatamente deste padrão. A ideia de "trocar a identidade do usuário
  por um token para outro recurso" **não é nova neste código**.
- **`credential_for` já é uma costura injetada** no `a2a_transport`. Ela pode
  passar a devolver um token trocado sem mudar a forma do executor — por sorte
  mais que por mérito, mas a sorte conta.
- A própria WorkOS publicou sobre o problema (*"AI agents and the multi-hop
  delegation problem"*), o que significa que o nosso IdP tem caminho.

## 4. Fase A — `credential_for` faz token exchange

### 4.1 A forma

`credential_for(target_name)` passa a `credential_for(target, identity)` e
resolve, **em ordem**:

1. **Token exchange (RFC 8693)** no IdP da faixa, quando o remoto declara um
   `security_schemes` compatível e o IdP suporta — produz um token com
   `sub`=usuário, `act`=nosso agente, `aud`=o remoto.
2. **Credencial estática de workspace** — o que existe hoje, mantido como
   **fallback explícito e MARCADO** (o log diz que a chamada saiu com credencial
   longeva, para que o downgrade seja legível).
3. **Recusa** — sem nenhuma das duas, `DelegationRefused`, como hoje.

**A ordem é a política:** o caminho moderno primeiro, o antigo como degradação
declarada, e a recusa como piso. Nunca o inverso, e nunca o antigo em silêncio.

### 4.2 Por que o fallback FICA (e não é preguiça)

Um remoto de terceiro pode não falar OAuth nenhum — um agente interno de um
cliente, um serviço legado. Remover o fallback tornaria o DNA incapaz de
conversar com metade do mundo real. O que **não** pode acontecer é o fallback ser
invisível: hoje ele é o único caminho e ninguém sabe; depois ele é a degradação e
o log diz.

### 4.3 O que NÃO muda

A recusa de repassar o token cru do usuário. O `call_remote` continua **sem
parâmetro algum** por onde uma identidade de caller entre — o teste que assere
isso contra a assinatura permanece, e o token exchange acontece **fora** dele,
na costura injetada. Isto é deliberado: a função que fala com o remoto não deve
nem ter vocabulário para receber identidade.

## 5. Fase B — `data_scope` vira ponto de decisão

### 5.1 O problema com o que temos

`data_scope.kinds` é uma resposta em **forma de scope**: uma lista estática por
remoto. Ela é checável e melhor que nada — mas não sabe responder "este Kind,
**deste** documento, **para este** usuário, **nesta** operação".

### 5.2 A evolução, em duas etapas

**B1 — manter a lista e adicionar o eixo que falta.** `data_scope` ganha campos
**opcionais** (sensibilidade, e um predicado por operação). Aditivo: quem só
declara `kinds` continua valendo.

**B2 — a consulta ao PDP.** `scope_allows` passa de predicado puro sobre uma
lista a uma **chamada a um decisor** (local por padrão, externo quando
configurado), no estilo AuthZEN. A assinatura já é a de um predicado — o
`scope_allows(target, payload_kinds)` de hoje é o caso degenerado de um PDP que
só sabe olhar lista.

### 5.3 A ordem importa, e B fica DEPOIS de A

A Fase A conserta uma **chave longeva em produção**. A Fase B melhora uma decisão
que **já é fail-closed** e já recusa o que não está na lista. Uma é dívida de
segurança; a outra é precisão. Fazer B antes de A seria refinar a decisão sobre
quais dados podem sair, enquanto a credencial que os leva segue sendo uma chave
que não expira.

## 6. Fora desta spec

- **Transaction Tokens** e **Workload Identity Federation** — as outras duas
  camadas do "three layers of agent auth". WIF vale quando o DNA rodar em
  ambiente que o emita; hoje o managed identity do Azure já cobre o caso de
  workload. Registrado, não construído.
- **Ser um IdP.** O DNA consome identidade; não a emite. Nada aqui muda isso.
- **A entrada A2A** (aceitar chamadas de fora) — spec própria, e ela tem uma
  pergunta **comercial** antes da técnica: uma chamada que chega consome
  ferramentas sob quota, e quem paga por ela não está decidido.

## 7. Riscos

- **Token exchange depende do IdP, e os dois nossos diferem.** WorkOS e Entra não
  expõem o mesmo fluxo com o mesmo nome. A implementação precisa de um seam por
  faixa (o mesmo padrão que `identity_claim_key()` já usa para escolher o claim
  durável por provedor) — e **não** de um caminho único que finge que os dois são
  iguais. Fingir isso é o defeito que produziu o bug do `oid`/`sub`.
- **O fallback marcado pode virar o caminho normal** e ninguém notar, se o log
  não for lido. A mitigação honesta não é confiar em disciplina: é uma métrica —
  quantas chamadas A2A saíram com credencial longeva — e não um comentário
  pedindo atenção.
- **A Fase B pode não ter consumidor.** Se nenhum deployment configurar um PDP
  externo, B1 é útil (mais eixos) e B2 é maquinaria sem leitor. O sinal para
  construir B2 é um deployment que peça — não a existência do padrão.

## 8. Como saberemos que funcionou

1. Uma chamada A2A para um remoto que fala OAuth sai com um token **curto**,
   `aud` no remoto, `sub` no usuário e `act` no nosso agente — asserido no
   payload, não no comentário.
2. Uma chamada para um remoto que **não** fala OAuth sai com a credencial de
   workspace **e** deixa registro de que foi degradação.
3. Nenhum caminho aceita o bearer do usuário — o teste contra a assinatura de
   `call_remote` continua verde.
4. O token exchange do WorkOS e o do Entra passam por **seams distintos**, e um
   teste prova que trocar a faixa troca o fluxo.
