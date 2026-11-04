# Bodega Azul — atendimento: o que o cast-list leu

> Estes diagramas têm dados do cliente: deixe este arquivo no ambiente dele.

6 no elenco (1 orquestrador, 5 especialistas) · 38 padrões · 3 fora do padrão · 4 só um tem

## Para olhar

### Contradições · 2

- bodega-frete: «handoff do frete, seção 4» diz que tem «Escalonamento para humano», mas o YAML não tem
- bodega-devolucoes tem «Só o conhecimento», mas também «Conhecimento geral do modelo ligado» (regra «Quem pede só o conhecimento tem o conhecimento geral desligado»)

### Contrato e telemetria · 6

- bodega-cupons registra «bodega_cupons_onerror»; os outros, «‹nome›_OnError»: é o mesmo evento?
- O orquestrador chama «Bodega Azul - Fidelidade», que não está na pasta
- A descrição de roteamento de bodega-cupons tem só 7 caracteres
- O fluxo «Abrir chamado no ERP» de bodega-cupons não devolve nada
- O evento «BodegaFrete_OnError» de bodega-frete não disparou em 30 dias
- bodega-loja-fisica não tem nenhuma linha na telemetria: está ligado ao Application Insights?

### Fora do padrão · 10

- 1 especialista registra «‹nome›_OnError» sem «ConversationId» (bodega-cupons): é intencional?
- 1 especialista não recebe o histórico da conversa do orquestrador (bodega-frete): é intencional?
- 1 especialista não recebe «CategoriaSolicitacao» do orquestrador (bodega-frete): é intencional?
- 1 especialista tem uma variação do bloco oficial «Formatação de links» (bodega-frete): alinhar?
- 1 especialista não escala para humano (bodega-frete), e o padrão foi aceito: corrigir?
- 1 especialista não registra telemetria (bodega-loja-fisica): é intencional?
- 1 especialista não tem «Sem emojis» (bodega-loja-fisica): é intencional?
- 4 especialistas definem «Tamanho da resposta» de 2 jeitos (3 bullets em 3; 5 frases em 2): unificar?
- bodega-loja-fisica define «Tamanho da resposta» duas vezes (3 bullets; 5 frases): qual vale?
- O tipo «triagem» tem 1 especialista (bodega-frete): nada a comparar dentro dele

### Regras · 1

- Regra «Todo especialista tem KPI»: 1 especialista não cumpre (bodega-loja-fisica)

### Só um tem · 4

- Só bodega-cupons tem «Conector SharePoint»: inovação ou dívida?
- Só bodega-cupons tem «Servidor MCP Bodega Azul Promocoes MCP»: inovação ou dívida?
- Só bodega-frete tem «Desambiguação («você quis dizer…»)»: inovação ou dívida?
- Só bodega-loja-fisica tem «Condição de busca só no YAML (a tela pode apagar)»: inovação ou dívida?

### Sem uso · 4

- Ninguém usa a variável «PreferenciaAntiga» (bodega-frete): remover?
- Ninguém chama o fluxo «Listar lojas» (bodega-loja-fisica): remover ou ligar?
- Ninguém chama o tópico «AvisoAntigo» (bodega-loja-fisica): remover ou ligar?
- bodega-pedidos tem um nó desligado em «topics/Escalate» (SendActivity): remover?

## Os diagramas

Cada diagrama também está sozinho em `bodega-azul.diagrams/`, para colar onde o Mermaid for lido.

### Topologia

Quem atende o cliente e o que cada um alcança. Setas grossas são chamadas; finas, o que cada um usa (um fluxo, um sistema); tracejadas, o que ninguém chama ou não está na pasta. Em vermelho o que falta numa chamada; em âmbar, uma descrição de roteamento curta ou um fluxo que não devolve nada. Os números são os inícios de tópico na telemetria.

```mermaid
flowchart LR
  %% title Topologia · Bodega Azul — atendimento
  %% cast-list 1.11.0
  subgraph s3 ["Cliente"]
    n1(["Cliente"])
  end
  subgraph s6 ["Orquestradores"]
    n7["Orquestrador<br/><small>1840 inícios de tópico</small>"]
  end
  subgraph s9 ["Especialistas · transação"]
    n2["Cupons<br/><small>290 inícios de tópico</small>"]
    n3["Devoluções<br/><small>402 inícios de tópico</small>"]
    n4["Pedidos<br/><small>610 inícios de tópico</small>"]
  end
  subgraph s14 ["Especialistas · orientação"]
    n5["Loja Física<br/><small>sem linha na telemetria</small>"]
  end
  subgraph s17 ["Especialistas · triagem"]
    n6["Frete<br/><small>355 inícios de tópico</small>"]
  end
  subgraph s20 ["Fora da pasta"]
    n8["Fidelidade<br/><small>chamado, fora da pasta</small>"]
  end
  subgraph s23 ["Fluxos"]
    n9[/"Abrir chamado no ERP<br/><small>fluxo</small>"/]
    n10[/"Listar lojas<br/><small>fluxo</small>"/]
  end
  subgraph s27 ["Sistemas"]
    n11[("erp.bodega-azul.example<br/><small>HTTP</small>")]
    n12[("Microsoft Dataverse<br/><small>conector</small>")]
    n13[("SharePoint<br/><small>conector</small>")]
    n14[("Office 365 Outlook<br/><small>conector</small>")]
    n15[("Bodega Azul Promocoes MCP<br/><small>servidor MCP</small>")]
    n16[("Conhecimento no SharePoint<br/><small>conhecimento</small>")]
  end
  n1 ==>|"1840"| n7
  n7 ==>|"roteado por «Cupons.» · 290"| n2
  n7 ==>|"402"| n3
  n7 -.->|"chama, mas não está na pasta"| n8
  n7 ==>|"SEM histórico · SEM «CategoriaSolicitacao» · 355"| n6
  n7 -.-> n5
  n7 ==>|"610"| n4
  n2 -->|"não devolve nada"| n9
  n3 --> n9
  n5 -.->|"ninguém chama"| n10
  n4 --> n9
  n9 -->|"HTTP"| n11
  n10 -.-> n12
  n2 -->|"GetItems"| n13
  n2 -->|"SendEmailV2"| n14
  n2 --> n15
  n2 --> n16
  n3 -->|"SendEmailV2"| n14
  n3 --> n16
  n6 -->|"SendEmailV2"| n14
  n6 --> n16
  n5 -->|"SendEmailV2"| n14
  n5 --> n16
  n4 -->|"SendEmailV2"| n14
  n4 --> n16
  linkStyle 1 stroke:#b7791f,stroke-width:2px
  linkStyle 3 stroke:#888
  linkStyle 4 stroke:#c0392b,stroke-width:2px
  linkStyle 7 stroke:#b7791f,stroke-width:2px
  linkStyle 9 stroke:#888
  linkStyle 12 stroke:#888
  classDef bad fill:#fde2e1,stroke:#c0392b,color:#7b1d16,stroke-width:2px
  classDef amber fill:#fff3d6,stroke:#b7791f,color:#5c3d0b,stroke-width:2px
  classDef ok fill:#e3f4e8,stroke:#2f855a,color:#1c4532
  classDef ghost fill:#f4f4f4,stroke:#888,color:#555,stroke-dasharray:5 4
  classDef muted fill:#f4f4f4,stroke:#bbb,color:#666
  class n5,n8,n10,n12 ghost
  class n6 bad
  class n2,n9 amber
```

### A chamada para Cupons

O que acontece, passo a passo, quando o orquestrador encaminha para Cupons. ⚠ marca o que olhar.

```mermaid
%%{init: {"sequence": {"wrap": true, "width": 220}}}%%
sequenceDiagram
  %% title A chamada para Cupons
  %% cast-list 1.11.0
  participant p1 as Cliente
  participant p2 as Orquestrador
  participant p3 as Cupons
  participant p4 as Abrir chamado no ERP
  participant p5 as erp.bodega-azul.example
  participant p6 as SharePoint
  participant p7 as Office 365 Outlook
  participant p8 as Bodega Azul Promocoes MCP
  participant p9 as Conhecimento no SharePoint
  %% # Cliente
  %% > O cliente escreve.
  p1->>p2: O cliente escreve.
  %% # Orquestrador
  %% > O orquestrador encaminha para Cupons por uma descrição de roteamento de 7 caracteres.
  Note over p2: ⚠ O orquestrador encaminha para Cupons por uma descrição de roteamento de 7 caracteres.<br/>«Cupons.»
  %% # Cupons
  %% > Cupons recebe o histórico e «CategoriaSolicitacao».
  p2->>p3: Cupons recebe o histórico e «CategoriaSolicitacao».
  %% # Abrir chamado no ERP
  %% > O fluxo «Abrir chamado no ERP» não devolve nada para Cupons.
  p3->>p4: ⚠ O fluxo «Abrir chamado no ERP» não devolve nada para Cupons.
  %% # erp.bodega-azul.example
  %% > O fluxo chega a erp.bodega-azul.example.
  p4->>p5: O fluxo chega a erp.bodega-azul.example.
  %% # SharePoint
  %% > Usa SharePoint (GetItems).
  p3->>p6: Usa SharePoint (GetItems).
  %% # Office 365 Outlook
  %% > Usa Office 365 Outlook (SendEmailV2).
  p3->>p7: Usa Office 365 Outlook (SendEmailV2).
  %% # Bodega Azul Promocoes MCP
  %% > Usa Bodega Azul Promocoes MCP.
  p3->>p8: Usa Bodega Azul Promocoes MCP.
  %% # Conhecimento no SharePoint
  %% > Consulta «Conhecimento no SharePoint».
  p3->>p9: Consulta «Conhecimento no SharePoint».
  %% # Orquestrador
  %% > A resposta volta ao cliente pelo orquestrador.
  p3-->>p2: A resposta volta ao cliente pelo orquestrador.
  p2-->>p1: a resposta
```

### A chamada para Devoluções

O que acontece, passo a passo, quando o orquestrador encaminha para Devoluções. ⚠ marca o que olhar.

```mermaid
%%{init: {"sequence": {"wrap": true, "width": 220}}}%%
sequenceDiagram
  %% title A chamada para Devoluções
  %% cast-list 1.11.0
  participant p1 as Cliente
  participant p2 as Orquestrador
  participant p3 as Devoluções
  participant p4 as Abrir chamado no ERP
  participant p5 as erp.bodega-azul.example
  participant p6 as Office 365 Outlook
  participant p7 as Conhecimento no SharePoint
  %% # Cliente
  %% > O cliente escreve.
  p1->>p2: O cliente escreve.
  %% # Orquestrador
  %% > O orquestrador encaminha para Devoluções.
  Note over p2: O orquestrador encaminha para Devoluções.<br/>«Agente especialista em trocas e devoluções: prazo de arrependimento, etiqueta de devolução e reembolso. Use quando a categoria for Devolucoes.»
  %% # Devoluções
  %% > Devoluções recebe o histórico e «CategoriaSolicitacao».
  p2->>p3: Devoluções recebe o histórico e «CategoriaSolicitacao».
  %% # Abrir chamado no ERP
  %% > Usa o fluxo «Abrir chamado no ERP».
  p3->>p4: Usa o fluxo «Abrir chamado no ERP».
  %% # erp.bodega-azul.example
  %% > O fluxo chega a erp.bodega-azul.example.
  p4->>p5: O fluxo chega a erp.bodega-azul.example.
  %% # Office 365 Outlook
  %% > Usa Office 365 Outlook (SendEmailV2).
  p3->>p6: Usa Office 365 Outlook (SendEmailV2).
  %% # Conhecimento no SharePoint
  %% > Consulta «Conhecimento no SharePoint».
  p3->>p7: Consulta «Conhecimento no SharePoint».
  %% # Orquestrador
  %% > A resposta volta ao cliente pelo orquestrador.
  p3-->>p2: A resposta volta ao cliente pelo orquestrador.
  p2-->>p1: a resposta
```

### A chamada para Fidelidade

O que acontece, passo a passo, quando o orquestrador encaminha para Fidelidade. ⚠ marca o que olhar.

```mermaid
%%{init: {"sequence": {"wrap": true, "width": 220}}}%%
sequenceDiagram
  %% title A chamada para Fidelidade
  %% cast-list 1.11.0
  participant p1 as Cliente
  participant p2 as Orquestrador
  participant p3 as Fidelidade
  %% # Cliente
  %% > O cliente escreve.
  p1->>p2: O cliente escreve.
  %% # Orquestrador
  %% > O orquestrador encaminha para Fidelidade.
  Note over p2: O orquestrador encaminha para Fidelidade.<br/>«Agente especialista no programa de fidelidade: pontos, níveis e resgates. Use quando a categoria for Fidelidade.»
  %% # Fidelidade
  %% > Chama Fidelidade, que não está na pasta: não foi clonado, ou não existe mais?
  p2-xp3: ⚠ Chama Fidelidade, que não está na pasta: não foi clonado, ou não existe mais?
```

### A chamada para Frete

O que acontece, passo a passo, quando o orquestrador encaminha para Frete. ⚠ marca o que olhar.

```mermaid
%%{init: {"sequence": {"wrap": true, "width": 220}}}%%
sequenceDiagram
  %% title A chamada para Frete
  %% cast-list 1.11.0
  participant p1 as Cliente
  participant p2 as Orquestrador
  participant p3 as Frete
  participant p4 as Office 365 Outlook
  participant p5 as Conhecimento no SharePoint
  %% # Cliente
  %% > O cliente escreve.
  p1->>p2: O cliente escreve.
  %% # Orquestrador
  %% > O orquestrador encaminha para Frete.
  Note over p2: O orquestrador encaminha para Frete.<br/>«Agente especialista em frete e entregas: modalidades, prazos por região e frete grátis. Use quando a categoria for Frete.»
  %% # Frete
  %% > Frete é chamado SEM o histórico e SEM «CategoriaSolicitacao»: não sabe o que o cliente já disse.
  p2->>p3: ⚠ Frete é chamado SEM o histórico e SEM «CategoriaSolicitacao»: não sabe o que o cliente já disse.
  %% # Office 365 Outlook
  %% > Usa Office 365 Outlook (SendEmailV2).
  p3->>p4: Usa Office 365 Outlook (SendEmailV2).
  %% # Conhecimento no SharePoint
  %% > Consulta «Conhecimento no SharePoint».
  p3->>p5: Consulta «Conhecimento no SharePoint».
  %% # Orquestrador
  %% > A resposta volta ao cliente pelo orquestrador.
  p3-->>p2: A resposta volta ao cliente pelo orquestrador.
  p2-->>p1: a resposta
```

### A chamada para Loja Física

O que acontece, passo a passo, quando o orquestrador encaminha para Loja Física. ⚠ marca o que olhar.

```mermaid
%%{init: {"sequence": {"wrap": true, "width": 220}}}%%
sequenceDiagram
  %% title A chamada para Loja Física
  %% cast-list 1.11.0
  participant p1 as Cliente
  participant p2 as Orquestrador
  participant p3 as Loja Física
  participant p4 as Office 365 Outlook
  participant p5 as Conhecimento no SharePoint
  %% # Cliente
  %% > O cliente escreve.
  p1->>p2: O cliente escreve.
  %% # Orquestrador
  %% > O orquestrador encaminha para Loja Física.
  Note over p2: O orquestrador encaminha para Loja Física.<br/>«Agente especialista na loja física: endereço, horário, serviços e retirada de pedidos. Use quando a categoria for LojaFisica.»
  %% # Loja Física
  %% > Loja Física recebe o histórico e «CategoriaSolicitacao».
  p2->>p3: Loja Física recebe o histórico e «CategoriaSolicitacao».
  %% # Office 365 Outlook
  %% > Usa Office 365 Outlook (SendEmailV2).
  p3->>p4: Usa Office 365 Outlook (SendEmailV2).
  %% # Conhecimento no SharePoint
  %% > Consulta «Conhecimento no SharePoint».
  p3->>p5: Consulta «Conhecimento no SharePoint».
  %% # Orquestrador
  %% > A resposta volta ao cliente pelo orquestrador.
  p3-->>p2: A resposta volta ao cliente pelo orquestrador.
  p2-->>p1: a resposta
```

### A chamada para Pedidos

O que acontece, passo a passo, quando o orquestrador encaminha para Pedidos. ⚠ marca o que olhar.

```mermaid
%%{init: {"sequence": {"wrap": true, "width": 220}}}%%
sequenceDiagram
  %% title A chamada para Pedidos
  %% cast-list 1.11.0
  participant p1 as Cliente
  participant p2 as Orquestrador
  participant p3 as Pedidos
  participant p4 as Abrir chamado no ERP
  participant p5 as erp.bodega-azul.example
  participant p6 as Office 365 Outlook
  participant p7 as Conhecimento no SharePoint
  %% # Cliente
  %% > O cliente escreve.
  p1->>p2: O cliente escreve.
  %% # Orquestrador
  %% > O orquestrador encaminha para Pedidos.
  Note over p2: O orquestrador encaminha para Pedidos.<br/>«Agente especialista em pedidos: status, prazos de processamento, cancelamento antes do envio e formas de pagamento. Use quando a categoria for Pedidos.»
  %% # Pedidos
  %% > Pedidos recebe o histórico e «CategoriaSolicitacao».
  p2->>p3: Pedidos recebe o histórico e «CategoriaSolicitacao».
  %% # Abrir chamado no ERP
  %% > Usa o fluxo «Abrir chamado no ERP».
  p3->>p4: Usa o fluxo «Abrir chamado no ERP».
  %% # erp.bodega-azul.example
  %% > O fluxo chega a erp.bodega-azul.example.
  p4->>p5: O fluxo chega a erp.bodega-azul.example.
  %% # Office 365 Outlook
  %% > Usa Office 365 Outlook (SendEmailV2).
  p3->>p6: Usa Office 365 Outlook (SendEmailV2).
  %% # Conhecimento no SharePoint
  %% > Consulta «Conhecimento no SharePoint».
  p3->>p7: Consulta «Conhecimento no SharePoint».
  %% # Orquestrador
  %% > A resposta volta ao cliente pelo orquestrador.
  p3-->>p2: A resposta volta ao cliente pelo orquestrador.
  p2-->>p1: a resposta
```

### Lente: Escalonamento para humano

«Escalonamento para humano» — padrão de plataforma (5 de 6). Fora: Frete.

```mermaid
flowchart LR
  %% title Lente: Escalonamento para humano
  %% cast-list 1.11.0
  n1["Cupons<br/><small>cumpre</small>"]
  n2["Devoluções<br/><small>cumpre</small>"]
  n3["Pedidos<br/><small>cumpre</small>"]
  n4["Loja Física<br/><small>cumpre</small>"]
  n5["Frete<br/><small>fora</small>"]
  n6["Orquestrador<br/><small>cumpre</small>"]
  n6 --> n1
  n6 --> n2
  n6 --> n5
  n6 --> n4
  n6 --> n3
  classDef bad fill:#fde2e1,stroke:#c0392b,color:#7b1d16,stroke-width:2px
  classDef amber fill:#fff3d6,stroke:#b7791f,color:#5c3d0b,stroke-width:2px
  classDef ok fill:#e3f4e8,stroke:#2f855a,color:#1c4532
  classDef ghost fill:#f4f4f4,stroke:#888,color:#555,stroke-dasharray:5 4
  classDef muted fill:#f4f4f4,stroke:#bbb,color:#666
  class n1,n2,n3,n4,n6 ok
  class n5 bad
```

### Lente: Registra telemetria

«Registra telemetria» — padrão de plataforma (5 de 6). Fora: Loja Física.

```mermaid
flowchart LR
  %% title Lente: Registra telemetria
  %% cast-list 1.11.0
  n1["Cupons<br/><small>cumpre</small>"]
  n2["Devoluções<br/><small>cumpre</small>"]
  n3["Pedidos<br/><small>cumpre</small>"]
  n4["Loja Física<br/><small>fora</small>"]
  n5["Frete<br/><small>cumpre</small>"]
  n6["Orquestrador<br/><small>cumpre</small>"]
  n6 --> n1
  n6 --> n2
  n6 --> n5
  n6 --> n4
  n6 --> n3
  classDef bad fill:#fde2e1,stroke:#c0392b,color:#7b1d16,stroke-width:2px
  classDef amber fill:#fff3d6,stroke:#b7791f,color:#5c3d0b,stroke-width:2px
  classDef ok fill:#e3f4e8,stroke:#2f855a,color:#1c4532
  classDef ghost fill:#f4f4f4,stroke:#888,color:#555,stroke-dasharray:5 4
  classDef muted fill:#f4f4f4,stroke:#bbb,color:#666
  class n1,n2,n3,n5,n6 ok
  class n4 bad
```

### Lente: Sem emojis

«Sem emojis» — padrão de plataforma (5 de 6). Fora: Loja Física.

```mermaid
flowchart LR
  %% title Lente: Sem emojis
  %% cast-list 1.11.0
  n1["Cupons<br/><small>cumpre</small>"]
  n2["Devoluções<br/><small>cumpre</small>"]
  n3["Pedidos<br/><small>cumpre</small>"]
  n4["Loja Física<br/><small>fora</small>"]
  n5["Frete<br/><small>cumpre</small>"]
  n6["Orquestrador<br/><small>cumpre</small>"]
  n6 --> n1
  n6 --> n2
  n6 --> n5
  n6 --> n4
  n6 --> n3
  classDef bad fill:#fde2e1,stroke:#c0392b,color:#7b1d16,stroke-width:2px
  classDef amber fill:#fff3d6,stroke:#b7791f,color:#5c3d0b,stroke-width:2px
  classDef ok fill:#e3f4e8,stroke:#2f855a,color:#1c4532
  classDef ghost fill:#f4f4f4,stroke:#888,color:#555,stroke-dasharray:5 4
  classDef muted fill:#f4f4f4,stroke:#bbb,color:#666
  class n1,n2,n3,n5,n6 ok
  class n4 bad
```

### Lente: Recebe o histórico da conversa

«Recebe o histórico da conversa» — padrão dos especialistas (4 de 5). Fora: Frete.

```mermaid
flowchart LR
  %% title Lente: Recebe o histórico da conversa
  %% cast-list 1.11.0
  n1["Cupons<br/><small>cumpre</small>"]
  n2["Devoluções<br/><small>cumpre</small>"]
  n3["Pedidos<br/><small>cumpre</small>"]
  n4["Loja Física<br/><small>cumpre</small>"]
  n5["Frete<br/><small>fora</small>"]
  n6["Orquestrador"]
  n6 --> n1
  n6 --> n2
  n6 --> n5
  n6 --> n4
  n6 --> n3
  classDef bad fill:#fde2e1,stroke:#c0392b,color:#7b1d16,stroke-width:2px
  classDef amber fill:#fff3d6,stroke:#b7791f,color:#5c3d0b,stroke-width:2px
  classDef ok fill:#e3f4e8,stroke:#2f855a,color:#1c4532
  classDef ghost fill:#f4f4f4,stroke:#888,color:#555,stroke-dasharray:5 4
  classDef muted fill:#f4f4f4,stroke:#bbb,color:#666
  class n1,n2,n3,n4 ok
  class n5 bad
  class n6 muted
```

### Lente: Recebe «CategoriaSolicitacao» do orquestrador

«Recebe «CategoriaSolicitacao» do orquestrador» — padrão dos especialistas (4 de 5). Fora: Frete.

```mermaid
flowchart LR
  %% title Lente: Recebe «CategoriaSolicitacao» do orquestrador
  %% cast-list 1.11.0
  n1["Cupons<br/><small>cumpre</small>"]
  n2["Devoluções<br/><small>cumpre</small>"]
  n3["Pedidos<br/><small>cumpre</small>"]
  n4["Loja Física<br/><small>cumpre</small>"]
  n5["Frete<br/><small>fora</small>"]
  n6["Orquestrador"]
  n6 --> n1
  n6 --> n2
  n6 --> n5
  n6 --> n4
  n6 --> n3
  classDef bad fill:#fde2e1,stroke:#c0392b,color:#7b1d16,stroke-width:2px
  classDef amber fill:#fff3d6,stroke:#b7791f,color:#5c3d0b,stroke-width:2px
  classDef ok fill:#e3f4e8,stroke:#2f855a,color:#1c4532
  classDef ghost fill:#f4f4f4,stroke:#888,color:#555,stroke-dasharray:5 4
  classDef muted fill:#f4f4f4,stroke:#bbb,color:#666
  class n1,n2,n3,n4 ok
  class n5 bad
  class n6 muted
```

### Lente: Formatação de links

«Formatação de links» — padrão dos especialistas (4 de 5). Variação: Frete.

```mermaid
flowchart LR
  %% title Lente: Formatação de links
  %% cast-list 1.11.0
  n1["Cupons<br/><small>cumpre</small>"]
  n2["Devoluções<br/><small>cumpre</small>"]
  n3["Pedidos<br/><small>cumpre</small>"]
  n4["Loja Física<br/><small>cumpre</small>"]
  n5["Frete<br/><small>para olhar</small>"]
  n6["Orquestrador"]
  n6 --> n1
  n6 --> n2
  n6 --> n5
  n6 --> n4
  n6 --> n3
  classDef bad fill:#fde2e1,stroke:#c0392b,color:#7b1d16,stroke-width:2px
  classDef amber fill:#fff3d6,stroke:#b7791f,color:#5c3d0b,stroke-width:2px
  classDef ok fill:#e3f4e8,stroke:#2f855a,color:#1c4532
  classDef ghost fill:#f4f4f4,stroke:#888,color:#555,stroke-dasharray:5 4
  classDef muted fill:#f4f4f4,stroke:#bbb,color:#666
  class n1,n2,n3,n4 ok
  class n5 amber
  class n6 muted
```

### Lente: Contrato

O que o orquestrador passa, e como encaminha: em vermelho o que falta; em âmbar, uma descrição de roteamento curta ou um fluxo que não devolve nada.

```mermaid
flowchart LR
  %% title Lente: Contrato
  %% cast-list 1.11.0
  n1["Cupons<br/><small>para olhar</small>"]
  n2["Devoluções<br/><small>cumpre</small>"]
  n3["Pedidos<br/><small>cumpre</small>"]
  n4["Loja Física<br/><small>cumpre</small>"]
  n5["Frete<br/><small>fora</small>"]
  n6["Orquestrador"]
  n6 --> n1
  n6 --> n2
  n6 --> n5
  n6 --> n4
  n6 --> n3
  classDef bad fill:#fde2e1,stroke:#c0392b,color:#7b1d16,stroke-width:2px
  classDef amber fill:#fff3d6,stroke:#b7791f,color:#5c3d0b,stroke-width:2px
  classDef ok fill:#e3f4e8,stroke:#2f855a,color:#1c4532
  classDef ghost fill:#f4f4f4,stroke:#888,color:#555,stroke-dasharray:5 4
  classDef muted fill:#f4f4f4,stroke:#bbb,color:#666
  class n2,n3,n4 ok
  class n1 amber
  class n5 bad
  class n6 muted
```

### Lente: Telemetria

Quem registra, e o que dispara: em vermelho quem não registra ou não tem linha; em âmbar um evento escrito de outro jeito, um campo que falta ou um evento que não disparou.

```mermaid
flowchart LR
  %% title Lente: Telemetria
  %% cast-list 1.11.0
  n1["Cupons<br/><small>para olhar</small>"]
  n2["Devoluções<br/><small>cumpre</small>"]
  n3["Pedidos<br/><small>cumpre</small>"]
  n4["Loja Física<br/><small>fora</small>"]
  n5["Frete<br/><small>para olhar</small>"]
  n6["Orquestrador<br/><small>cumpre</small>"]
  n6 --> n1
  n6 --> n2
  n6 --> n5
  n6 --> n4
  n6 --> n3
  classDef bad fill:#fde2e1,stroke:#c0392b,color:#7b1d16,stroke-width:2px
  classDef amber fill:#fff3d6,stroke:#b7791f,color:#5c3d0b,stroke-width:2px
  classDef ok fill:#e3f4e8,stroke:#2f855a,color:#1c4532
  classDef ghost fill:#f4f4f4,stroke:#888,color:#555,stroke-dasharray:5 4
  classDef muted fill:#f4f4f4,stroke:#bbb,color:#666
  class n2,n3,n6 ok
  class n1,n5 amber
  class n4 bad
```

### Lente: Sem uso

O que ninguém usa, ou está desligado: remover ou ligar?

```mermaid
flowchart LR
  %% title Lente: Sem uso
  %% cast-list 1.11.0
  n1["Cupons<br/><small>cumpre</small>"]
  n2["Devoluções<br/><small>cumpre</small>"]
  n3["Pedidos<br/><small>para olhar</small>"]
  n4["Loja Física<br/><small>para olhar</small>"]
  n5["Frete<br/><small>para olhar</small>"]
  n6["Orquestrador<br/><small>cumpre</small>"]
  n6 --> n1
  n6 --> n2
  n6 --> n5
  n6 --> n4
  n6 --> n3
  classDef bad fill:#fde2e1,stroke:#c0392b,color:#7b1d16,stroke-width:2px
  classDef amber fill:#fff3d6,stroke:#b7791f,color:#5c3d0b,stroke-width:2px
  classDef ok fill:#e3f4e8,stroke:#2f855a,color:#1c4532
  classDef ghost fill:#f4f4f4,stroke:#888,color:#555,stroke-dasharray:5 4
  classDef muted fill:#f4f4f4,stroke:#bbb,color:#666
  class n1,n2,n6 ok
  class n3,n4,n5 amber
```

### O tipo «transação»

Os padrões do tipo «transação» (aceitos ou ainda candidatos) e, em vermelho, quem está fora de cada um.

```mermaid
flowchart TD
  %% title O tipo «transação»
  %% cast-list 1.11.0
  t["«transação»<br/><small>3 especialistas: Cupons, Devoluções, Pedidos</small>"]
  %% # Fluxo chama erp.bodega-azul.example
  t --> q1["Fluxo chama erp.bodega-azul.example<br/><small>candidato · 3 de 3</small>"]
  %% # Fluxo Abrir chamado no ERP
  t --> q2["Fluxo Abrir chamado no ERP<br/><small>candidato · 3 de 3</small>"]
  %% # Abre um chamado no ERP quando o cliente…
  t --> q3["Abre um chamado no ERP quando o cliente…<br/><small>candidato · 3 de 3</small>"]
  classDef bad fill:#fde2e1,stroke:#c0392b,color:#7b1d16,stroke-width:2px
  classDef amber fill:#fff3d6,stroke:#b7791f,color:#5c3d0b,stroke-width:2px
  classDef ok fill:#e3f4e8,stroke:#2f855a,color:#1c4532
  classDef ghost fill:#f4f4f4,stroke:#888,color:#555,stroke-dasharray:5 4
  classDef muted fill:#f4f4f4,stroke:#bbb,color:#666
```

### O tipo «orientação»

Os padrões do tipo «orientação» (aceitos ou ainda candidatos) e, em vermelho, quem está fora de cada um.

```mermaid
flowchart TD
  %% title O tipo «orientação»
  %% cast-list 1.11.0
  t["«orientação»<br/><small>2 especialistas: Cupons, Loja Física</small>"]
  %% # Link para ajuda.bodega-azul.example
  t --> q1["Link para ajuda.bodega-azul.example<br/><small>candidato · 2 de 2</small>"]
  %% # Tamanho da resposta = 5 frases
  t --> q2["Tamanho da resposta = 5 frases<br/><small>candidato · 2 de 2</small>"]
  classDef bad fill:#fde2e1,stroke:#c0392b,color:#7b1d16,stroke-width:2px
  classDef amber fill:#fff3d6,stroke:#b7791f,color:#5c3d0b,stroke-width:2px
  classDef ok fill:#e3f4e8,stroke:#2f855a,color:#1c4532
  classDef ghost fill:#f4f4f4,stroke:#888,color:#555,stroke-dasharray:5 4
  classDef muted fill:#f4f4f4,stroke:#bbb,color:#666
```

### O tipo «triagem»

Os padrões do tipo «triagem» (aceitos ou ainda candidatos) e, em vermelho, quem está fora de cada um.

```mermaid
flowchart TD
  %% title O tipo «triagem»
  %% cast-list 1.11.0
  t["«triagem»<br/><small>1 especialista: Frete</small>"]
  t --- none["poucos para comparar: ainda sem padrão próprio"]
  classDef bad fill:#fde2e1,stroke:#c0392b,color:#7b1d16,stroke-width:2px
  classDef amber fill:#fff3d6,stroke:#b7791f,color:#5c3d0b,stroke-width:2px
  classDef ok fill:#e3f4e8,stroke:#2f855a,color:#1c4532
  classDef ghost fill:#f4f4f4,stroke:#888,color:#555,stroke-dasharray:5 4
  classDef muted fill:#f4f4f4,stroke:#bbb,color:#666
```

---

Escrito pelo cast-list 1.11.0.
