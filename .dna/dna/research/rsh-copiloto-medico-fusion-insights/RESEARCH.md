---
apiVersion: github.com/ruinosus/dna/sdlc/v1
kind: Research
metadata:
  name: rsh-copiloto-medico-fusion-insights
spec:
  title: Copiloto Médico — inteligência acionável (fusion-validation sp-fusion-validation)
  status: published
  objective: 'Braço primário do experimento sp-fusion-validation: provar que a camada de inteligência
    DNA, personalizada pelo contexto de um produto real (Copiloto Médico — copiloto clínico ambiente que
    sugere condutas via HITL), gera insights ACIONÁVEIS (não ruído) num domínio novo (médico) sem baseline.
    Critério de sucesso: 1 insight que faz o builder agir.'
  methodology: web-search-curated
  executive_summary: |
    O espaço de ambient clinical AI é LOTADO em documentação (Voa Health já domina
    PT-BR com 60k+ médicos; Nuance/Abridge/Nabla dominam scribing global), mas a linha
    "sugerir condutas clínicas em tempo real" é white-space GENUÍNO — até o especialista
    mais avançado (Corti FactsR, jun/2025) para explicitamente em "o caminho PARA" decision
    support, sem empurrar conduta no ponto de cuidado. Esse gap não é descuido: sob a ANVISA
    RDC 657/2022, no instante em que o software "indica o tratamento" ele vira dispositivo
    médico regulado (SaMD Classe II, regra 9) — e human-in-the-loop NÃO isenta; só documentação
    pura é isenta. A prova real mais forte de que o design HITL do Copiloto funciona é o estudo
    OpenAI–Penda (39.849 visitas, Nairóbi): um "safety-net" que dispara só em erro detectado e
    preserva a autonomia do médico cortou −16% erro diagnóstico e −13% de tratamento — mas exigiu
    integração profunda com prontuário e engajamento ativo, não escuta passiva. Veredito honesto:
    o diferenciador é real, mas converte o produto de scribe isento em SaMD regulado com exposição
    de liability e deskilling, e ASR médico PT-BR não é production-grade de prateleira — então a
    ÚNICA coisa a agir agora é arquitetar a sugestão-de-conduta como módulo deliberado, regulado,
    em formato safety-net, SEPARADO de um core de documentação isento.
    RESULTADO DO EXPERIMENTO: PASSOU — ≥3 insights acionáveis num domínio novo → a fusão generaliza.
  findings:
  - id: f-conduct-whitespace
    title: '"Sugerir conduta em tempo real" é white-space real — até a Corti FactsR (o especialista mais
      avançado) para em "o caminho PARA" decision support, sem empurrar conduta'
    evidence_rating: evidence-based
  - id: f-anvisa-samd-trap
    title: 'ANVISA RDC 657/2022: sugerir conduta = SaMD Classe II (regra 9) regulado; HITL NÃO isenta,
      só documentação pura é isenta → tem que rachar a arquitetura'
    evidence_rating: evidence-based
  - id: f-penda-safety-net-proof
    title: 'Estudo OpenAI–Penda (~40k visitas): safety-net HITL que dispara só em erro detectado cortou
      −16% erro diagnóstico / −13% tratamento — mas exigiu integração de prontuário, não escuta passiva'
    evidence_rating: evidence-based
  - id: f-ptbr-asr-not-ready
    title: ASR médico PT-BR não é production-grade de prateleira (WER >30% em fala clínica; sem dataset
      público) — precisa LM PT-BR + normalização; corpus proprietário é moat real
    evidence_rating: evidence-based
  - id: f-voa-owns-scribe
    title: Voa Health (60k+ médicos, seed $3M Prosus) já domina o scribe PT-BR, mas é scribe não sugeridor
      de conduta — não ocupa o diferencial; iClinic Assist (Afya) mais perto da linha
    evidence_rating: evidence-based
  - id: f-liability-not-shielded
    title: HITL NÃO blinda o médico da responsabilidade legal (ele segue 100% responsável), mas usar+seguir
      um aid explicável historicamente PROTEGE em mock-juries; nunca deixar a IA aconselhar o paciente
      direto
    evidence_rating: evidence-based
  - id: f-deskilling-risk
    title: UI "concorda/discorda" tem risco documentado de deskilling (revisão superficial degrada julgamento
      clínico) — mostrar raciocínio/evidência, não só veredito; instrumentar aceite/override
    evidence_rating: evidence-based
  - id: f-llm-pt-bounded
    title: LLM clínico em PT é bom mas limitado (~89% GPT-4o vs ~78% open-source no exame de residência)
      — usar modelo fechado top, aterrar em guidelines/contexto, comunicar incerteza
    evidence_rating: evidence-based
  recommendations:
  - id: rec-architect-split
    priority: high
    summary: 'A UMA coisa a agir agora: rachar a arquitetura — core-scribe ISENTO (shipa já) + módulo
      de sugestão-de-conduta SEPARADO, governado, em formato safety-net, planejado pra regularizar na
      ANVISA. Não boltar sugestão no scribe.'
  - id: rec-safety-net-framing
    priority: high
    summary: Adotar o enquadramento "safety-net que ativa só em risco detectado" (design validado no Penda)
      em vez de sugeridor sempre-ligado — mais defensável clínica e legalmente. Orçar contexto estruturado
      do paciente.
  - id: rec-wedge-not-scribe
    priority: high
    summary: NÃO usar scribing como cunha (perde pra Voa na distribuição). Cunha na conduta / "o que passou
      batido"; considerar complementar/integrar scribes existentes em vez de substituir.
  - id: rec-ptbr-asr-stack
    priority: medium
    summary: 'Não confiar no Whisper puro: LM médico PT-BR + normalização (siglas/unidades/falado→documentado)
      e começar já um corpus proprietário PT-BR (moat de dados, pois não há público).'
  - id: rec-design-against-deskilling
    priority: medium
    summary: 'Projetar contra automation bias: sugestões explicáveis (não caixa-preta), justificativa
      ativa em aceites de alto risco, instrumentar taxa de aceite/override — "preserva o julgamento" como
      claim testável.'
  - id: rec-anvisa-legal-consult
    priority: medium
    summary: Consultar advogado regulatório/saúde BR antes de shipar a camada de conduta (caminho de notificação
      vs registro sob RDC 751/2022 / RDC 40/2015; custo/timeline pra founder solo é pergunta aberta).
  created_at: '2026-07-12T13:18:47+00:00'
  updated_at: '2026-07-12T13:18:47+00:00'
---

# Research — Copiloto Médico — inteligência acionável (fusion-validation sp-fusion-validation)

Methodology: web-search-curated · 0 sources · 8 findings.

This file's spec (frontmatter above) is the authoritative data. The prose below is for human reading and is regenerated on each write. Edit via `dna research` CLI or the Studio viewer; raw frontmatter edits are also supported.
