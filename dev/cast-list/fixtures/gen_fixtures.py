#!/usr/bin/env python3
"""Generate six fictional Copilot Studio agent fixtures (Bodega Azul) as cloned-layout .mcs.yml projects."""
import json
import os
import random
import shutil
import string
import sys
import uuid

# where to write: the folder given, or the skill's examples (dev/cast-list/fixtures -> skills/cast-list/examples/agents)
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../skills/cast-list/examples/agents")
PREFIX = "cr7b2"
rng = random.Random(20261102)


def rid(prefix):
    return prefix + "_" + "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(6))


# wave 2 draws its ids from its own sequence, so the files of the earlier waves keep theirs
rng2 = random.Random("cast-list wave 2")


def rid2(prefix):
    return prefix + "_" + "".join(rng2.choice(string.ascii_letters + string.digits) for _ in range(6))


def guid():
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def q(s):
    """Double-quoted YAML scalar."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def block(text, indent):
    pad = " " * indent
    return "\n".join((pad + line) if line else "" for line in text.strip("\n").split("\n"))


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.rstrip("\n") + "\n")


# ---------------------------------------------------------------------------
# Shared file builders
# ---------------------------------------------------------------------------

def agent_file(component, display, instructions, starters, model_knowledge=None):
    st = "\n\n".join(f"  - title: {q(t)}\n    text: {q(x)}" for t, x in starters)
    mk = f"  useModelKnowledge: {'true' if model_knowledge else 'false'}\n" if model_knowledge is not None else ""
    return f"""mcs.metadata:
  componentName: {component}
kind: GptComponentMetadata
displayName: {display}
instructions: |
{block(instructions, 2)}
conversationStarters:
{st}

aISettings:
{mk}  model:
    modelNameHint: GPT5Chat
"""


def settings_file(display, schema, connectable):
    conn = "  isAgentConnectable: true\n" if connectable else ""
    return f"""displayName: {display}
schemaName: {schema}
accessControlPolicy: ChatbotReaders
authenticationMode: None
configuration:
{conn}  settings:
    GenerativeActionsEnabled: true

  recognizer:
    kind: GenerativeAIRecognizer

language: 1046
"""


def greeting_topic(lines):
    texts = "\n".join(f"          - {q(l)}" for l in lines)
    return f"""mcs.metadata:
  componentName: Saudação
  description: Mensagem de boas-vindas enviada no início da conversa.
kind: AdaptiveDialog
beginDialog:
  kind: OnConversationStart
  id: main
  actions:
    - kind: SendActivity
      id: {rid('sendMessage')}
      activity:
        text:
{texts}
"""


def fallback_topic(schema, escalate):
    if escalate:
        else_actions = f"""        - kind: SendActivity
          id: {rid('sendMessage')}
          activity:
            text:
              - {q('Estou com dificuldade para entender o seu pedido. Vou te encaminhar para alguém da equipe Bodega Azul.')}

        - kind: BeginDialog
          id: {rid('beginDialog')}
          dialog: {schema}.topic.Escalate"""
    else:
        else_actions = f"""        - kind: SendActivity
          id: {rid('sendMessage')}
          activity:
            text:
              - {q('Não consegui entender a sua solicitação. Você pode escrever para atendimento@bodegaazul.example que a nossa equipe responde em até 1 dia útil.')}

        - kind: CancelAllDialogs
          id: {rid('cancelAllDialogs')}"""
    return f"""mcs.metadata:
  componentName: Fallback
  description: Acionado quando nenhum tópico ou ferramenta corresponde à mensagem do cliente.
kind: AdaptiveDialog
beginDialog:
  kind: OnUnknownIntent
  id: main
  priority: -1
  actions:
    - kind: ConditionGroup
      id: {rid('conditionGroup')}
      conditions:
        - id: {rid('conditionItem')}
          condition: =System.FallbackCount < 3
          actions:
            - kind: SendActivity
              id: {rid('sendMessage')}
              activity:
                text:
                  - {q('Desculpe, não entendi. Pode reformular a sua pergunta?')}
                  - {q('Não captei bem. Pode tentar explicar de outro jeito?')}

      elseActions:
{else_actions}
"""


def escalate_topic(contact, disabled=False):
    # wave 2: a message left in the topic, switched off
    off = f"""
    - kind: SendActivity
      id: {rid2('sendMessage')}
      disabled: true
      activity: {q('Aguarde, estamos transferindo você para um atendente.')}
""" if disabled else ""
    return f"""mcs.metadata:
  componentName: Escalar
  description: Acionado quando o cliente pede para falar com uma pessoa.
kind: AdaptiveDialog
beginDialog:
  kind: OnEscalate
  id: main
  intent:
    displayName: Escalar
    includeInOnSelectIntent: false
    triggerQueries:
      - Falar com um atendente
      - Quero falar com uma pessoa
      - Atendimento humano
      - Me transfere para alguém

  actions:
    - kind: SendActivity
      id: {rid('sendMessage')}
      activity: {q('A transferência para um atendente ainda não está disponível neste canal. Fale com a nossa equipe pelo e-mail ' + contact + ', de segunda a sábado, das 9h às 18h.')}
{off}"""


def error_topic(event_name, agent_key, telemetry, conversation_id=True):
    tel = ""
    if telemetry:
        conv = ", ConversationId: System.Conversation.Id" if conversation_id else ""
        tel = f"""
    - kind: LogCustomTelemetryEvent
      id: {rid('logTelemetry')}
      eventName: {event_name}
      properties: "={{Agente: \\"{agent_key}\\", ErrorMessage: System.Error.Message, ErrorCode: System.Error.Code, TimeUTC: Topic.CurrentTime{conv}}}"
"""
    return f"""mcs.metadata:
  componentName: Em caso de erro
  description: Tratamento de erros do agente.
kind: AdaptiveDialog
startBehavior: UseLatestPublishedContentAndCancelOtherTopics
beginDialog:
  kind: OnError
  id: main
  actions:
    - kind: SetVariable
      id: {rid('setVariable')}
      variable: init:Topic.CurrentTime
      value: =Text(Now(), DateTimeFormat.UTC)

    - kind: ConditionGroup
      id: {rid('conditionGroup')}
      conditions:
        - id: {rid('conditionItem')}
          condition: =System.Conversation.InTestMode = true
          actions:
            - kind: SendActivity
              id: {rid('sendMessage')}
              activity: |-
                Mensagem de erro: {{System.Error.Message}}
                Código do erro: {{System.Error.Code}}
                Id da conversa: {{System.Conversation.Id}}
                Horário (UTC): {{Topic.CurrentTime}}

      elseActions:
        - kind: SendActivity
          id: {rid('sendMessage')}
          activity:
            text:
              - |-
                Ocorreu um erro.
                Código do erro: {{System.Error.Code}}
                Id da conversa: {{System.Conversation.Id}}
                Horário (UTC): {{Topic.CurrentTime}}.
            speak:
              - Ocorreu um erro, por favor tente novamente.
{tel}
    - kind: CancelAllDialogs
      id: {rid('cancelAllDialogs')}
"""


def redirect_topic():
    return f"""mcs.metadata:
  componentName: Recebimento do Orquestrador
  description: Ponto de entrada quando o agente é chamado pelo orquestrador Bodega Azul como agente conectado.
kind: AdaptiveDialog
modelDescription: Inicializa o agente quando ele é chamado pelo orquestrador Bodega Azul e recebe a categoria da solicitação.
beginDialog:
  kind: OnRedirect
  id: main
  actions:
    - kind: SetVariable
      id: {rid('setVariable')}
      variable: Global.CategoriaSolicitacao
      value: =System.Activity.Value.CategoriaSolicitacao

inputType: {{}}
outputType: {{}}
"""


def gen_answers_topic(component, desc, model_desc, input_desc, knowledge_ref):
    return f"""mcs.metadata:
  componentName: {component}
  description: {q(desc)}
kind: AdaptiveDialog
inputs:
  - kind: AutomaticTaskInput
    propertyName: PerguntaCliente
    description: {q(input_desc)}
    shouldPromptUser: true

modelDescription: {q(model_desc)}
beginDialog:
  kind: OnRecognizedIntent
  id: main
  intent: {{}}
  actions:
    - kind: CreateSearchQuery
      id: {rid('createSearchQuery')}
      userInput: =Topic.PerguntaCliente
      result: Topic.SearchQuery

    - kind: SearchAndSummarizeContent
      id: {rid('searchContent')}
      autoSend: false
      variable: Topic.SearchResult
      userInput: =Topic.SearchQuery.SearchQuery
      fileSearchDataSource:
        searchFilesMode:
          kind: DoNotSearchFiles

      knowledgeSources:
        kind: SearchSpecificKnowledgeSources
        knowledgeSources:
          - {knowledge_ref}

      applyModelKnowledgeSetting: false
      responseCaptureType: FullResponse

    - kind: SetVariable
      id: {rid('setVariable')}
      variable: Topic.Resposta
      value: =Topic.SearchResult.Text.Content

inputType:
  properties:
    PerguntaCliente:
      displayName: PerguntaCliente
      description: {q(input_desc)}
      type: String

outputType:
  properties:
    Resposta:
      displayName: Resposta
      description: Resposta fundamentada na base de conhecimento do agente.
      type: String
"""


def sharepoint_knowledge(component, desc, site, trigger_condition=None):
    tc = f"  triggerCondition: {trigger_condition}\n" if trigger_condition else ""
    return f"""mcs.metadata:
  componentName: {component}
  description: {q(desc)}
kind: KnowledgeSourceConfiguration
source:
  kind: SharePointSearchSource
{tc}  site: {site}
"""


def outlook_action(component, desc, model_name, model_desc, conn_ref, to_input):
    if to_input[0] == "manual":
        to = f"""  - kind: ManualTaskInput
    propertyName: To
    value: {to_input[1]}"""
    else:
        to = f"""  - kind: AutomaticTaskInput
    propertyName: To
    description: {q(to_input[1])}
    entity: EmailPrebuiltEntity
    shouldPromptUser: true"""
    return f"""mcs.metadata:
  componentName: {component}
  description: {q(desc)}
kind: TaskDialog
inputs:
{to}

  - kind: AutomaticTaskInput
    propertyName: Subject
    description: Assunto do e-mail, curto e em português.
    entity: StringPrebuiltEntity
    shouldPromptUser: false

  - kind: AutomaticTaskInput
    propertyName: Body
    description: Corpo do e-mail em HTML simples, em português, com o resumo do que foi tratado na conversa.
    entity: StringPrebuiltEntity
    shouldPromptUser: false

modelDisplayName: {model_name}
modelDescription: {q(model_desc)}
action:
  kind: InvokeConnectorTaskAction
  connectionReference: {conn_ref}
  connectionProperties:
    mode: Maker

  operationId: SendEmailV2

outputMode: All
"""


def variable_file(schema, external, default):
    ext = "isExternalInitializationAllowed: true\n" if external else ""
    return f"""# Name: Categoria da Solicitação
# Categoria da solicitação do cliente definida pelo orquestrador Bodega Azul (Pedidos, Devolucoes, Frete, Cupons, LojaFisica, Outro).
name: CategoriaSolicitacao
aIVisibility: UseInAIContext
scope: Conversation
description: Categoria da solicitação do cliente definida pelo orquestrador Bodega Azul (Pedidos, Devolucoes, Frete, Cupons, LojaFisica, Outro).
schemaName: {schema}.globalvariable.CategoriaSolicitacao
kind: GlobalVariableComponent
{ext}defaultValue: {default}
"""


def conn_refs_file(refs):
    items = "\n\n".join(
        f"""  - id: {r['id']}
    connectionReferenceLogicalName: {r['name']}
    connectorId: {r['connectorId']}
    displayName: {r['display']}""" + (f"\n    customConnectorId: {r['custom']}" if r.get("custom") else "")
        for r in refs
    )
    return f"""kind: ConnectionReferencesSourceFile
connectionReferences:
{items}
"""


def outlook_ref(schema):
    g = guid()
    return {
        "id": guid(),
        "name": f"{schema}.shared_office365.shared-office365-{g}",
        "connectorId": "/providers/Microsoft.PowerApps/apis/shared_office365",
        "display": "Office 365 Outlook",
    }


# ---------------------------------------------------------------------------
# Specialists
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Wave 1 (cast-list 1.3): the text of the instructions, the types of agent
# ---------------------------------------------------------------------------

# the shared block of links, pasted in four specialists; frete has a variation (one line less, 5 links)
LINKS = """Links:
- Formate links assim: [título](url), nunca a URL crua.
- Um link de ação vai no topo; o link da base de ajuda vai no fim.
- Nunca escreva as palavras «clique aqui».
- No máximo 3 links por resposta."""
LINKS_VARIANT = """Links:
- Formate links assim: [título](url), nunca a URL crua.
- Nunca escreva as palavras «clique aqui».
- No máximo 5 links por resposta."""
SIZE3 = "Responda em no máximo 3 bullets."
SIZE5 = "Use no máximo 5 frases por resposta."
NO_EMOJI = "Não use emojis."
KNOWLEDGE_ONLY = "Responda somente com base no conhecimento publicado."
HELP_LINK = "Para dúvidas gerais, indique https://ajuda.bodega-azul.example/atendimento."
# one flow in the solution, shared by the three transaction specialists
FLOW_ID = "7d1c2a4e-3b5f-4c6d-8e9f-0a1b2c3d4e5f"
WAVE1 = {
    "bodega-pedidos": {"text": [LINKS, SIZE3, NO_EMOJI], "flow": True, "copy": True},
    "bodega-devolucoes": {"text": [LINKS, SIZE3, NO_EMOJI, KNOWLEDGE_ONLY], "flow": True, "model_knowledge": True},
    "bodega-frete": {"text": [LINKS_VARIANT, NO_EMOJI], "triage": True},
    "bodega-cupons": {"text": [LINKS, SIZE5, NO_EMOJI, HELP_LINK], "flow": True},
    "bodega-loja-fisica": {"text": [LINKS, SIZE3, HELP_LINK, SIZE5]},
}


def flow_action():
    return f"""mcs.metadata:
  componentName: Abrir chamado no ERP
  description: Abre um chamado no ERP da Bodega Azul pelo fluxo da solução.
kind: TaskDialog
inputs:
  - kind: AutomaticTaskInput
    propertyName: resumo
    description: Resumo do pedido do cliente, em uma frase.
    shouldPromptUser: false

modelDisplayName: Abrir chamado no ERP
modelDescription: Abre um chamado no ERP quando o cliente pede uma ação que a loja precisa executar (troca, cancelamento, reembolso).
action:
  kind: InvokeFlowTaskAction
  flowId: {FLOW_ID}
"""


def triage_topic():
    return """mcs.metadata:
  componentName: Desambiguar
  description: Pergunta ao cliente qual assunto ele quis dizer quando mais de um tópico serve.
kind: AdaptiveDialog
beginDialog:
  kind: OnSelectIntent
  id: main
  actions:
    - kind: SendActivity
      id: sendMessage_tRiAg3
      activity: Sobre qual destes assuntos você quer falar?
"""


# ---------------------------------------------------------------------------
# Wave 2 (cast-list 1.4): the orchestrator's contract, the flows, what nobody uses
# ---------------------------------------------------------------------------

LISTAR_LOJAS_ID = "3f2a9c1d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
WAVE2 = {
    "bodega-pedidos": {"flow": "returns", "disabled_node": True},
    "bodega-devolucoes": {"flow": "returns"},
    "bodega-cupons": {"flow": "silent"},       # the flow answers nothing to the agent
    "bodega-loja-fisica": {"orphan_flow": True, "orphan_topic": True},
    "bodega-frete": {"orphan_variable": True},
}


# wave 3: the cupons writes its event another way, and leaves the conversation id out
WAVE3 = {
    "bodega-cupons": {"event": "bodega_cupons_onerror", "no_conversation_id": True},
}

# wave 3, outside the agents' folder: what a person exports — the query of the telemetry (references/telemetry.md), the
# Power Platform admin center's inventory, and the team's own spreadsheet (with «;», as Excel saves it in Portuguese)
TELEMETRY_CSV = """agente,evento,vezes
Bodega Azul - Orquestrador,TopicStart,1840
Bodega Azul - Orquestrador,BodegaOrquestrador_OnError,12
Bodega Azul - Pedidos,TopicStart,610
Bodega Azul - Pedidos,BodegaPedidos_OnError,7
Bodega Azul - Devoluções,TopicStart,402
Bodega Azul - Devoluções,BodegaDevolucoes_OnError,3
Bodega Azul - Frete,TopicStart,355
Bodega Azul - Cupons,TopicStart,290
Bodega Azul - Cupons,bodega_cupons_onerror,5
"""

INVENTORY_CSV = """Item name,Item type,Schema name,Owner,Environment,Created on,Last published
Bodega Azul - Orquestrador,Agent,cr7b2_bodegaOrquestrador,atendimento@bodegaazul.example,Bodega Azul (Produção),2026-03-02,2026-10-28
Bodega Azul - Pedidos,Agent,cr7b2_bodegaPedidos,pedidos@bodegaazul.example,Bodega Azul (Produção),2026-03-05,2026-10-21
Bodega Azul - Devoluções,Agent,cr7b2_bodegaDevolucoes,trocas@bodegaazul.example,Bodega Azul (Produção),2026-03-05,2026-10-14
Bodega Azul - Frete,Agent,cr7b2_bodegaFrete,frete@bodegaazul.example,Bodega Azul (Produção),2026-03-09,2026-09-30
Bodega Azul - Cupons,Agent,cr7b2_bodegaCupons,,Bodega Azul (Produção),2026-03-12,2026-10-02
Bodega Azul - Loja Física,Agent,cr7b2_bodegaLojaFisica,loja@bodegaazul.example,Bodega Azul (Produção),2026-04-01,
Bodega Azul - Fidelidade,Agent,cr7b2_bodegaFidelidade,fidelidade@bodegaazul.example,Bodega Azul (Testes),2026-08-20,
Painel de Pedidos,Canvas app,,pedidos@bodegaazul.example,Bodega Azul (Produção),2026-02-11,
Abrir chamado no ERP,Agent flow,,pedidos@bodegaazul.example,Bodega Azul (Produção),2026-03-05,
"""

TEAM_CSV = """Agente;KPI;Dono
Bodega Azul - Pedidos;pedido localizado em até 2 trocas de mensagem;Squad Pedidos
Bodega Azul - Devoluções;troca aberta sem atendente em 80% dos casos;Squad Pós-venda
Bodega Azul - Frete;cotação em menos de 5 s;Squad Logística
Bodega Azul - Cupons;cupom validado na primeira tentativa;Squad Promoções
Bodega Azul - Loja Física;;Squad Lojas
Sobre a Bodega Azul;respostas gerais sem encaminhar;Squad Atendimento
"""


def flow_folder(d, name, folder, workflow_id, actions, returns=True):
    write(f"{d}/workflows/{folder}/metadata.yml", f"""displayName: {name}
workflowId: {workflow_id}
jsonFileName: workflow.json
""")
    if returns:
        actions = {**actions, "Responder": {"type": "Response", "kind": "Skills", "runAfter": {next(iter(actions)): ["Succeeded"]},
                                           "inputs": {"statusCode": 200, "body": {"resultado": "@outputs('Resultado')"}}}}
    flow = {"properties": {"displayName": name, "connectionReferences": {}, "definition": {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "contentVersion": "1.0.0.0",
        "triggers": {"manual": {"type": "Request", "kind": "Skills", "inputs": {"schema": {"type": "object", "properties": {"resumo": {"type": "string"}}}}}},
        "actions": actions}}}
    write(f"{d}/workflows/{folder}/workflow.json", json.dumps(flow, ensure_ascii=False, indent=2) + "\n")


def erp_flow(d, returns):
    flow_folder(d, "Abrir chamado no ERP", "AbrirChamadoERP-7d1c2a4e", FLOW_ID, {
        "Abrir_chamado": {"type": "Scope", "actions": {
            "Chamar_ERP": {"type": "Http", "inputs": {"method": "POST", "uri": "https://erp.bodega-azul.example/chamados", "body": "@triggerBody()"}}}}}, returns)


def stores_flow(d):
    flow_folder(d, "Listar lojas", "ListarLojas-3f2a9c1d", LISTAR_LOJAS_ID, {
        "Listar": {"type": "OpenApiConnection", "inputs": {"host": {
            "apiId": "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps",
            "connectionName": "shared_commondataserviceforapps", "operationId": "ListRecords"}, "parameters": {"entityName": "lojas"}}}})


def old_notice_topic():
    return f"""mcs.metadata:
  componentName: Aviso antigo
  description: Aviso de horário especial de um feriado que já passou.
kind: AdaptiveDialog
beginDialog:
  kind: OnRecognizedIntent
  id: main
  intent: {{}}
  actions:
    - kind: SendActivity
      id: {rid2('sendMessage')}
      activity: {q('No feriado de carnaval a loja fecha às 14h.')}
"""


def unused_variable(schema):
    return f"""# Name: Preferência antiga
# Preferência de contato que ninguém usa mais.
name: PreferenciaAntiga
aIVisibility: UseInAIContext
scope: Conversation
description: Preferência de contato que ninguém usa mais.
schemaName: {schema}.globalvariable.PreferenciaAntiga
kind: GlobalVariableComponent
defaultValue: =Blank()
"""


SPECIALISTS = [
    {
        "key": "bodega-pedidos",
        "schema": f"{PREFIX}_bodegaPedidos",
        "component": "Bodega Azul - Pedidos",
        "display": "Bodega Azul - Pedidos",
        "instructions": """
Você é o especialista em pedidos da Bodega Azul, uma loja online.

Responsabilidades:
- Explicar status de pedido, prazos de processamento e formas de pagamento aceitas
- Usar a base "Políticas de Pedidos" para responder dúvidas sobre regras de compra
- Enviar ao cliente, quando ele pedir, um e-mail com o resumo do atendimento

Regras:
- Responda sempre em português do Brasil, de forma curta e cordial
- Nunca invente números de pedido, valores ou prazos
- Se a dúvida for sobre devolução, frete, cupom ou loja física, diga que é outro especialista que cuida disso
""",
        "starters": [("Status do pedido", "Como acompanho o meu pedido?"), ("Pagamento", "Quais formas de pagamento vocês aceitam?")],
        "greeting": [
            "Olá! Eu sou o {System.Bot.Name}. Posso te ajudar com o seu pedido na Bodega Azul?",
            "Oi! Aqui é o especialista em pedidos da Bodega Azul. Em que posso ajudar?",
        ],
        "contact": "pedidos@bodegaazul.example",
        "escalate": True,
        "telemetry": True,
        "topic": ("ConsultarPoliticasPedidos", "Consultar Políticas de Pedidos",
                  "Responde dúvidas sobre pedidos com base nas políticas publicadas no SharePoint.",
                  "Responde perguntas sobre status de pedido, prazos de processamento, cancelamento antes do envio e formas de pagamento da Bodega Azul.",
                  "A pergunta do cliente sobre pedidos, status, cancelamento ou pagamento."),
        "knowledge": ("PoliticasPedidos", "Políticas de Pedidos",
                      "Políticas de compra, status de pedido, cancelamento e formas de pagamento da Bodega Azul.",
                      "https://bodegaazul.sharepoint.com/sites/Atendimento/Shared%20Documents/Pedidos", None),
        "email": ("EnviarResumoPedido", "Enviar resumo do pedido por e-mail",
                  "Envia ao cliente um e-mail com o resumo do atendimento sobre o pedido.",
                  "Enviar resumo do pedido por e-mail",
                  "Envia ao cliente, pelo Outlook, um e-mail com o resumo do atendimento sobre o pedido. Use somente quando o cliente pedir o resumo por e-mail.",
                  ("auto", "Endereço de e-mail do cliente que vai receber o resumo do pedido.")),
    },
    {
        "key": "bodega-devolucoes",
        "schema": f"{PREFIX}_bodegaDevolucoes",
        "component": "Bodega Azul - Devoluções",
        "display": "Bodega Azul - Devoluções",
        "instructions": """
Você é o especialista em trocas e devoluções da Bodega Azul, uma loja online.

Responsabilidades:
- Explicar prazos de arrependimento, condições do produto e como gerar a etiqueta de devolução
- Usar a base "Política de Trocas e Devoluções" para responder
- Abrir uma solicitação de devolução enviando um e-mail para a equipe de logística reversa

Regras:
- Responda sempre em português do Brasil, com empatia e objetividade
- Confirme o número do pedido e o motivo antes de abrir a solicitação
- Não prometa reembolso antes da análise do produto
""",
        "starters": [("Trocar produto", "Quero trocar um produto que comprei"), ("Prazo de devolução", "Qual o prazo para devolver uma compra?")],
        "greeting": [
            "Olá! Eu sou o {System.Bot.Name}. Vamos resolver a sua troca ou devolução?",
            "Oi! Aqui é o especialista em trocas e devoluções da Bodega Azul. Como posso ajudar?",
        ],
        "contact": "devolucoes@bodegaazul.example",
        "escalate": True,
        "telemetry": True,
        "topic": ("ConsultarPoliticaDevolucoes", "Consultar Política de Devoluções",
                  "Responde dúvidas sobre trocas e devoluções com base na política publicada no SharePoint.",
                  "Responde perguntas sobre prazo de arrependimento, condições para troca, etiqueta de devolução e reembolso na Bodega Azul.",
                  "A pergunta do cliente sobre troca, devolução ou reembolso."),
        "knowledge": ("PoliticaTrocasDevolucoes", "Política de Trocas e Devoluções",
                      "Regras de troca, devolução, arrependimento e reembolso da Bodega Azul.",
                      "https://bodegaazul.sharepoint.com/sites/Atendimento/Shared%20Documents/Devolucoes", None),
        "email": ("AbrirSolicitacaoDevolucao", "Abrir solicitação de devolução",
                  "Envia à equipe de logística reversa um e-mail abrindo a solicitação de devolução.",
                  "Abrir solicitação de devolução",
                  "Envia pelo Outlook um e-mail para a equipe de logística reversa com número do pedido, produto e motivo da devolução. Use depois de confirmar esses dados com o cliente.",
                  ("manual", "logistica.reversa@bodegaazul.example")),
    },
    {
        "key": "bodega-frete",
        "schema": f"{PREFIX}_bodegaFrete",
        "component": "Bodega Azul - Frete",
        "display": "Bodega Azul - Frete",
        "instructions": """
Você é o especialista em frete e entregas da Bodega Azul, uma loja online.

Responsabilidades:
- Explicar modalidades de envio, prazos por região e regras de frete grátis
- Usar a base "Tabela de Frete e Entregas" para responder
- Enviar ao cliente, quando ele pedir, um e-mail com as opções de frete consultadas

Regras:
- Responda sempre em português do Brasil
- Prazos são sempre em dias úteis; deixe isso claro
- Não calcule valores de frete de cabeça: use apenas o que está na base
""",
        "starters": [("Prazo de entrega", "Quanto tempo demora a entrega para o Nordeste?"), ("Frete grátis", "A partir de qual valor o frete é grátis?")],
        "greeting": [
            "Olá! Eu sou o {System.Bot.Name}. Quer saber sobre prazos e valores de entrega?",
            "Oi! Aqui é o especialista em frete da Bodega Azul. Em que posso ajudar?",
        ],
        "contact": "entregas@bodegaazul.example",
        "escalate": False,
        "telemetry": True,
        "topic": ("ConsultarTabelaFrete", "Consultar Tabela de Frete",
                  "Responde dúvidas sobre frete e entregas com base na tabela publicada no SharePoint.",
                  "Responde perguntas sobre modalidades de envio, prazos de entrega por região e regras de frete grátis da Bodega Azul.",
                  "A pergunta do cliente sobre frete, prazo ou modalidade de entrega."),
        "knowledge": ("TabelaFreteEntregas", "Tabela de Frete e Entregas",
                      "Modalidades de envio, prazos por região e regras de frete grátis da Bodega Azul.",
                      "https://bodegaazul.sharepoint.com/sites/Logistica/Shared%20Documents/Frete", None),
        "email": ("EnviarOpcoesFrete", "Enviar opções de frete por e-mail",
                  "Envia ao cliente um e-mail com as opções de frete consultadas.",
                  "Enviar opções de frete por e-mail",
                  "Envia ao cliente, pelo Outlook, um e-mail com as modalidades e prazos de frete consultados na conversa. Use somente quando o cliente pedir.",
                  ("auto", "Endereço de e-mail do cliente que vai receber as opções de frete.")),
    },
    {
        "key": "bodega-cupons",
        "schema": f"{PREFIX}_bodegaCupons",
        "component": "Bodega Azul - Cupons",
        "display": "Bodega Azul - Cupons",
        "instructions": """
Você é o especialista em cupons e promoções da Bodega Azul, uma loja online.

Responsabilidades:
- Explicar as regras de uso de cupons com base no "Regulamento de Cupons"
- Consultar a lista de cupons ativos no SharePoint para verificar se um código existe e está válido
- Usar o servidor MCP de promoções para buscar as campanhas vigentes
- Enviar ao cliente, quando ele pedir, um e-mail com o cupom e as regras de uso

Regras:
- Responda sempre em português do Brasil
- Nunca crie, invente ou altere códigos de cupom
- Cupons não são cumulativos, salvo quando o regulamento disser o contrário
""",
        "starters": [("Cupom não funciona", "Meu cupom não está funcionando"), ("Promoções", "Quais promoções estão ativas hoje?")],
        "greeting": [
            "Olá! Eu sou o {System.Bot.Name}. Quer validar um cupom ou ver as promoções da semana?",
            "Oi! Aqui é o especialista em cupons da Bodega Azul. Como posso ajudar?",
        ],
        "contact": "promocoes@bodegaazul.example",
        "escalate": True,
        "telemetry": True,
        "topic": ("ConsultarRegulamentoCupons", "Consultar Regulamento de Cupons",
                  "Responde dúvidas sobre regras de cupons com base no regulamento publicado no SharePoint.",
                  "Responde perguntas sobre regras de uso de cupons, validade, valor mínimo de compra e acúmulo de descontos na Bodega Azul.",
                  "A pergunta do cliente sobre regras de cupom ou desconto."),
        "knowledge": ("RegulamentoCupons", "Regulamento de Cupons",
                      "Regras de uso, validade e acúmulo de cupons de desconto da Bodega Azul.",
                      "https://bodegaazul.sharepoint.com/sites/Marketing/Shared%20Documents/Cupons", None),
        "email": ("EnviarCupomEmail", "Enviar cupom por e-mail",
                  "Envia ao cliente um e-mail com o código do cupom e as regras de uso.",
                  "Enviar cupom por e-mail",
                  "Envia ao cliente, pelo Outlook, um e-mail com um código de cupom já validado e as regras de uso. Use somente quando o cliente pedir.",
                  ("auto", "Endereço de e-mail do cliente que vai receber o cupom.")),
    },
    {
        "key": "bodega-loja-fisica",
        "schema": f"{PREFIX}_bodegaLojaFisica",
        "component": "Bodega Azul - Loja Física",
        "display": "Bodega Azul - Loja Física",
        "instructions": """
Você é o especialista em loja física e retirada da Bodega Azul.

Responsabilidades:
- Informar endereço, horário de funcionamento e serviços da loja física
- Explicar como funciona a retirada na loja de compras feitas no site
- Usar a base "Guia da Loja Física" para responder
- Enviar ao cliente, quando ele pedir, um e-mail com as instruções de retirada

Regras:
- Responda sempre em português do Brasil
- Confirme o número do pedido antes de dar instruções de retirada
- Horários especiais de feriado só valem se estiverem no guia
""",
        "starters": [("Horário da loja", "Qual o horário de funcionamento da loja física?"), ("Retirada", "Como faço para retirar meu pedido na loja?")],
        "greeting": [
            "Olá! Eu sou o {System.Bot.Name}. Quer saber sobre a nossa loja física ou retirada de pedidos?",
            "Oi! Aqui é o especialista em loja física da Bodega Azul. Como posso ajudar?",
        ],
        "contact": "loja@bodegaazul.example",
        "escalate": True,
        "telemetry": False,
        "topic": ("ConsultarGuiaLojaFisica", "Consultar Guia da Loja Física",
                  "Responde dúvidas sobre a loja física com base no guia publicado no SharePoint.",
                  "Responde perguntas sobre endereço, horário de funcionamento, serviços e retirada de pedidos na loja física da Bodega Azul.",
                  "A pergunta do cliente sobre a loja física ou a retirada de um pedido."),
        "knowledge": ("GuiaLojaFisica", "Guia da Loja Física",
                      "Endereço, horários, serviços e regras de retirada na loja física da Bodega Azul.",
                      "https://bodegaazul.sharepoint.com/sites/Varejo/Shared%20Documents/LojaFisica",
                      '=Or(IsBlank(Global.CategoriaSolicitacao), Global.CategoriaSolicitacao = "LojaFisica")'),
        "email": ("EnviarInstrucoesRetirada", "Enviar instruções de retirada por e-mail",
                  "Envia ao cliente um e-mail com as instruções de retirada na loja.",
                  "Enviar instruções de retirada por e-mail",
                  "Envia ao cliente, pelo Outlook, um e-mail com endereço, horário e documentos necessários para retirar o pedido na loja física. Use somente quando o cliente pedir.",
                  ("auto", "Endereço de e-mail do cliente que vai receber as instruções de retirada.")),
    },
]


def build_specialist(a):
    d = os.path.join(ROOT, a["key"])
    s = a["schema"]
    w1 = WAVE1[a["key"]]
    text = a["instructions"].rstrip("\n") + "\n\n" + "\n\n".join(w1["text"]) + "\n"
    write(f"{d}/agent.mcs.yml", agent_file(a["component"], a["display"], text, a["starters"], w1.get("model_knowledge")))
    write(f"{d}/settings.mcs.yml", settings_file(a["display"], s, connectable=True))
    if w1.get("flow"):
        write(f"{d}/actions/AbrirChamadoERP.mcs.yml", flow_action())
    if w1.get("triage"):
        write(f"{d}/topics/Desambiguar.topic.mcs.yml", triage_topic())

    # topics
    write(f"{d}/topics/Greeting.topic.mcs.yml", greeting_topic(a["greeting"]))
    write(f"{d}/topics/Fallback.topic.mcs.yml", fallback_topic(s, a["escalate"]))
    w2 = WAVE2[a["key"]]
    if a["escalate"]:
        write(f"{d}/topics/Escalate.topic.mcs.yml", escalate_topic(a["contact"], w2.get("disabled_node", False)))
    if w2.get("flow"):
        erp_flow(d, w2["flow"] == "returns")
    if w2.get("orphan_flow"):
        stores_flow(d)
    if w2.get("orphan_topic"):
        write(f"{d}/topics/AvisoAntigo.topic.mcs.yml", old_notice_topic())
    if w2.get("orphan_variable"):
        write(f"{d}/variables/PreferenciaAntiga.mcs.yml", unused_variable(s))
    w3 = WAVE3.get(a["key"], {})
    event = w3.get("event") or "".join(p.capitalize() for p in a["key"].split("-")) + "_OnError"
    write(f"{d}/topics/OnError.topic.mcs.yml", error_topic(event, a["key"], a["telemetry"], conversation_id=not w3.get("no_conversation_id")))
    write(f"{d}/topics/RecebimentoOrquestrador.topic.mcs.yml", redirect_topic())
    kfile, kname, kdesc, ksite, ktc = a["knowledge"]
    tfile, tname, tdesc, tmodel, tinput = a["topic"]
    write(f"{d}/topics/{tfile}.topic.mcs.yml",
          gen_answers_topic(tname, tdesc, tmodel, tinput, f"{s}.knowledge.{kfile}"))
    # a copy left behind in the editor: the analysis leaves its text out
    if w1.get("copy"):
        write(f"{d}/topics/{tfile} Copy.topic.mcs.yml",
              gen_answers_topic(f"{tname} Copy", tdesc, tmodel, tinput, f"{s}.knowledge.{kfile}"))

    # knowledge
    write(f"{d}/knowledge/{kfile}.knowledge.mcs.yml", sharepoint_knowledge(kname, kdesc, ksite, ktc))

    # variables
    write(f"{d}/variables/CategoriaSolicitacao.mcs.yml", variable_file(s, external=True, default="=Blank()"))

    # actions + connection references
    refs = []
    o = outlook_ref(s)
    refs.append(o)
    efile, ecomp, edesc, emodel, emodeldesc, eto = a["email"]
    write(f"{d}/actions/{efile}.mcs.yml", outlook_action(ecomp, edesc, emodel, emodeldesc, o["name"], eto))

    if a["key"] == "bodega-cupons":
        sp = {
            "id": guid(),
            "name": f"{s}.shared_sharepointonline.shared-sharepointonline-{guid()}",
            "connectorId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
            "display": "SharePoint",
        }
        refs.append(sp)
        write(f"{d}/actions/ConsultarCuponsAtivos.mcs.yml", f"""mcs.metadata:
  componentName: Consultar cupons ativos
  description: Consulta a lista de cupons ativos no SharePoint de Marketing.
kind: TaskDialog
inputs:
  - kind: ManualTaskInput
    propertyName: dataset
    value: https://bodegaazul.sharepoint.com/sites/Marketing

  - kind: ManualTaskInput
    propertyName: table
    value: Cupons

  - kind: AutomaticTaskInput
    propertyName: "'$filter'"
    description: "Filtro OData pela coluna Codigo com o código informado pelo cliente, em maiúsculas. Exemplo: Codigo eq 'AZUL10'"
    entity: StringPrebuiltEntity
    shouldPromptUser: false

  - kind: ManualTaskInput
    propertyName: "'$top'"
    value: "10"

modelDisplayName: Consultar cupons ativos
modelDescription: Verifica na lista Cupons do SharePoint se um código de cupom existe, se está ativo e qual a validade. Use quando o cliente informar um código de cupom.
action:
  kind: InvokeConnectorTaskAction
  connectionReference: {sp['name']}
  connectionProperties:
    mode: Maker

  operationId: GetItems

outputMode: All
""")
        mcp = {
            "id": guid(),
            "name": f"{s}.shared_bodegapromocoesmcp.{rid('mcp').split('_')[1].lower()}",
            "connectorId": "/providers/Microsoft.PowerApps/apis/shared_bodegapromocoesmcp",
            "display": "Bodega Azul Promocoes MCP",
            "custom": guid(),
        }
        refs.append(mcp)
        write(f"{d}/actions/PromocoesMCP.mcs.yml", f"""mcs.metadata:
  componentName: Servidor MCP de Promoções
  description: Servidor MCP interno com as campanhas promocionais vigentes da Bodega Azul.
kind: TaskDialog
inputs:
  - kind: ManualTaskInput
    propertyName: canal
    value: =System.Activity.ChannelId

modelDisplayName: Servidor MCP de Promoções
modelDescription: Servidor MCP que lista as campanhas promocionais e os cupons vigentes da Bodega Azul.
action:
  kind: InvokeExternalAgentTaskAction
  connectionReference: {mcp['name']}
  connectionProperties:
    mode: Maker

  operationDetails:
    kind: ModelContextProtocolMetadata
    operationId: InvokeMCP
""")

    write(f"{d}/connectionreferences.mcs.yml", conn_refs_file(refs))


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def build_orchestrator():
    key = "bodega-orquestrador"
    s = f"{PREFIX}_bodegaOrquestrador"
    d = os.path.join(ROOT, key)
    display = "Bodega Azul - Orquestrador"
    instructions = """
Você é o assistente virtual da Bodega Azul, uma loja online. Você não responde sozinho às dúvidas
de atendimento: o seu papel é entender a solicitação e encaminhá-la ao especialista certo.

Como trabalhar:
1. Antes de acionar um especialista, use o tópico "Classificar Solicitação" para definir a categoria.
2. Encaminhe conforme a categoria:
   - Pedidos: agente "Bodega Azul - Pedidos"
   - Devolucoes: agente "Bodega Azul - Devoluções"
   - Frete: agente "Bodega Azul - Frete"
   - Cupons: agente "Bodega Azul - Cupons"
   - LojaFisica: agente "Bodega Azul - Loja Física"
   - Outro: se for uma pergunta geral sobre a empresa, use o agente "Sobre a Bodega Azul"
3. Repasse a resposta do especialista ao cliente sem inventar informações.

Regras:
- Responda sempre em português do Brasil, de forma cordial e objetiva
- Se o cliente pedir para falar com uma pessoa, use o tópico de escalonamento

Não use emojis.
"""
    starters = [("Meu pedido", "Onde está o meu pedido?"), ("Trocas", "Quero devolver um produto"), ("Cupons", "Tenho um cupom de desconto")]
    write(f"{d}/agent.mcs.yml", agent_file(display, display, instructions, starters))
    write(f"{d}/settings.mcs.yml", settings_file(display, s, connectable=False))

    write(f"{d}/topics/Greeting.topic.mcs.yml", greeting_topic([
        "Olá! Eu sou o {System.Bot.Name}, o assistente virtual da Bodega Azul. Como posso ajudar hoje?",
        "Oi! Bem-vindo à Bodega Azul. Posso ajudar com pedidos, trocas, frete, cupons ou a nossa loja física.",
    ]))
    write(f"{d}/topics/Fallback.topic.mcs.yml", fallback_topic(s, escalate=True))
    write(f"{d}/topics/Escalate.topic.mcs.yml", escalate_topic("atendimento@bodegaazul.example"))
    write(f"{d}/topics/OnError.topic.mcs.yml", error_topic("BodegaOrquestrador_OnError", key, telemetry=True))

    desc = """Classifique a solicitação do cliente em exatamente uma destas categorias:
Pedidos, Devolucoes, Frete, Cupons, LojaFisica, Outro
Use Outro quando nenhuma das demais se aplicar."""
    write(f"{d}/topics/ClassificarSolicitacao.topic.mcs.yml", f"""mcs.metadata:
  componentName: Classificar Solicitação
  description: Define a categoria da solicitação do cliente para encaminhar ao especialista certo.
kind: AdaptiveDialog
inputs:
  - kind: AutomaticTaskInput
    propertyName: CategoriaSolicitacao
    description: |-
{block(desc, 6)}
    shouldPromptUser: false

modelDescription: Classifica a solicitação do cliente (pedidos, devoluções, frete, cupons, loja física ou outro) antes de acionar um agente especialista. Use sempre antes de chamar um especialista.
beginDialog:
  kind: OnRecognizedIntent
  id: main
  intent: {{}}
  actions:
    - kind: SetVariable
      id: {rid('setVariable')}
      variable: Global.CategoriaSolicitacao
      value: =Topic.CategoriaSolicitacao

inputType:
  properties:
    CategoriaSolicitacao:
      displayName: CategoriaSolicitacao
      description: |-
{block(desc, 8)}
      type: String

outputType: {{}}
""")

    write(f"{d}/variables/CategoriaSolicitacao.mcs.yml", variable_file(s, external=False, default="Outro"))

    connected = [
        ("AgentePedidos", "Agente Pedidos", "Bodega Azul - Pedidos", f"{PREFIX}_bodegaPedidos",
         "Agente especialista em pedidos: status, prazos de processamento, cancelamento antes do envio e formas de pagamento. Use quando a categoria for Pedidos."),
        ("AgenteDevolucoes", "Agente Devoluções", "Bodega Azul - Devoluções", f"{PREFIX}_bodegaDevolucoes",
         "Agente especialista em trocas e devoluções: prazo de arrependimento, etiqueta de devolução e reembolso. Use quando a categoria for Devolucoes."),
        ("AgenteFrete", "Agente Frete", "Bodega Azul - Frete", f"{PREFIX}_bodegaFrete",
         "Agente especialista em frete e entregas: modalidades, prazos por região e frete grátis. Use quando a categoria for Frete."),
        # wave 2: a routing description too short to route by
        ("AgenteCupons", "Agente Cupons", "Bodega Azul - Cupons", f"{PREFIX}_bodegaCupons", "Cupons."),
        ("AgenteLojaFisica", "Agente Loja Física", "Bodega Azul - Loja Física", f"{PREFIX}_bodegaLojaFisica",
         "Agente especialista na loja física: endereço, horário, serviços e retirada de pedidos. Use quando a categoria for LojaFisica."),
        # wave 2: an agent of the solution that is not in the folder
        ("AgenteFidelidade", "Agente Fidelidade", "Bodega Azul - Fidelidade", f"{PREFIX}_bodegaFidelidade",
         "Agente especialista no programa de fidelidade: pontos, níveis e resgates. Use quando a categoria for Fidelidade."),
    ]
    for fname, comp, model_name, bot, mdesc in connected:
        # wave 2: frete is called with no history and without the category
        bare = fname == "AgenteFrete"
        inputs = "" if bare else """inputs:
  - kind: ManualTaskInput
    propertyName: CategoriaSolicitacao
    value: =Global.CategoriaSolicitacao

"""
        input_type = "  inputType: {}\n" if bare else """  inputType:
    properties:
      CategoriaSolicitacao:
        displayName: CategoriaSolicitacao
        description: Categoria da solicitação definida pelo orquestrador.
        isRequired: true
        type: String

"""
        write(f"{d}/actions/{fname}.mcs.yml", f"""mcs.metadata:
  componentName: {comp}
  description: Agente conectado {model_name}.
kind: TaskDialog
{inputs}modelDisplayName: {model_name}
modelDescription: {q(mdesc)}
action:
  kind: InvokeConnectedAgentTaskAction
{input_type}  botSchemaName: {bot}
  historyType:
    kind: {"NoHistory" if bare else "ConversationHistory"}
""")

    write(f"{d}/agents/SobreBodegaAzul/agent.mcs.yml", """# Name: Sobre a Bodega Azul
# SobreBodegaAzul
kind: AgentDialog

beginDialog:
  kind: OnToolSelected
  id: main
  description: Responde perguntas gerais sobre a Bodega Azul que não são de pedidos, devoluções, frete, cupons ou loja física, como canais de contato, horário do atendimento online e quem somos. Exemplos "Qual o telefone de vocês?", "A Bodega Azul tem aplicativo?".

settings:
  instructions: |
    Você responde perguntas gerais e institucionais sobre a Bodega Azul, uma loja online fictícia.

    Regras:
    - Responda em português do Brasil, em no máximo três frases
    - Canais oficiais: site, e-mail atendimento@bodegaazul.example e chat
    - Atendimento online: de segunda a sábado, das 9h às 18h
    - Se a pergunta for sobre pedidos, devoluções, frete, cupons ou loja física, diga que outro especialista cuida disso

inputs:
  - kind: AutomaticTaskInput
    propertyName: PerguntaGeral
    description: A pergunta geral do cliente sobre a Bodega Azul.

inputType:
  properties:
    PerguntaGeral:
      displayName: Pergunta Geral
      description: A pergunta geral do cliente sobre a Bodega Azul.
      type: String

outputType: {}
""")


if __name__ == "__main__":
    if os.path.isdir(ROOT):
        shutil.rmtree(ROOT)
    build_orchestrator()
    for a in SPECIALISTS:
        build_specialist(a)
    examples = os.path.dirname(os.path.normpath(ROOT))
    write(os.path.join(examples, "telemetria.csv"), TELEMETRY_CSV)
    write(os.path.join(examples, "inventario.csv"), INVENTORY_CSV)
    write(os.path.join(examples, "equipe.csv"), TEAM_CSV)
    print("done")
