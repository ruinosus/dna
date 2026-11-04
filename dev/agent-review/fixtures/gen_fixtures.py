#!/usr/bin/env python3
"""Generate six fictional Copilot Studio agent fixtures — an HR self-service, after Microsoft's Employee Self-Service sample — as cloned-layout .mcs.yml projects."""
import json
import os
import random
import shutil
import string
import sys
import uuid

# where to write: the folder given, or the skill's examples (dev/agent-review/fixtures -> skills/agent-review/examples/agents)
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../skills/agent-review/examples/agents")
PREFIX = "cr7b2"
rng = random.Random(20261102)


def rid(prefix):
    return prefix + "_" + "".join(rng.choice(string.ascii_letters + string.digits) for _ in range(6))


# wave 2 draws its ids from its own sequence, so the files of the earlier waves keep theirs
rng2 = random.Random("agent-review wave 2")


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


def write(path, content, bom=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # the extension saves a flow's workflow.json with a byte-order mark on Windows
    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8") as f:
        f.write(content.rstrip("\n") + "\n")


def write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


# what the extension clones beside the YAML: the agent's icon (uploaded knowledge is in checks/extract.check.ts)
ICON_PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                         "1f15c4890000000d49444154789c63f8cf50ef0f0004ff01ff9d1ca3a30000000049454e44ae426082")


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
              - {q('Estou com dificuldade para entender a sua solicitação. Vou te encaminhar para alguém do RH.')}

        - kind: BeginDialog
          id: {rid('beginDialog')}
          dialog: {schema}.topic.Escalate"""
    else:
        else_actions = f"""        - kind: SendActivity
          id: {rid('sendMessage')}
          activity:
            text:
              - {q('Não consegui entender a sua solicitação. Você pode escrever para rh@empresa.example que o RH responde em até 1 dia útil.')}

        - kind: CancelAllDialogs
          id: {rid('cancelAllDialogs')}"""
    return f"""mcs.metadata:
  componentName: Fallback
  description: Acionado quando nenhum tópico ou ferramenta corresponde à mensagem do colaborador.
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
  description: Acionado quando o colaborador pede para falar com uma pessoa.
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
  description: Ponto de entrada quando o agente é chamado pelo orquestrador do RH como agente conectado.
kind: AdaptiveDialog
modelDescription: Inicializa o agente quando ele é chamado pelo orquestrador do RH e recebe a categoria da solicitação.
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
    propertyName: PerguntaColaborador
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
      userInput: =Topic.PerguntaColaborador
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
    PerguntaColaborador:
      displayName: PerguntaColaborador
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
# Categoria da solicitação do colaborador definida pelo orquestrador do RH (Ferias, Beneficios, Folha, Admissao, Facilities, Outro).
name: CategoriaSolicitacao
aIVisibility: UseInAIContext
scope: Conversation
description: Categoria da solicitação do colaborador definida pelo orquestrador do RH (Ferias, Beneficios, Folha, Admissao, Facilities, Outro).
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
    # as the extension clones it: no kind
    return f"""connectionReferences:
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
# Wave 1 (agent-review 1.3): the text of the instructions, the types of agent
# ---------------------------------------------------------------------------

# the shared block of links, pasted in four specialists; folha has a variation (one line less, 5 links)
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
HELP_LINK = "Para dúvidas gerais, indique https://portal.empresa.example/rh/ajuda."
# one flow in the solution, shared by the three transaction specialists
FLOW_ID = "7d1c2a4e-3b5f-4c6d-8e9f-0a1b2c3d4e5f"
WAVE1 = {
    "rh-ferias": {"text": [LINKS, SIZE3, NO_EMOJI], "flow": True, "copy": True},
    "rh-beneficios": {"text": [LINKS, SIZE3, NO_EMOJI, KNOWLEDGE_ONLY], "flow": True, "model_knowledge": True},
    "rh-folha": {"text": [LINKS_VARIANT, NO_EMOJI], "triage": True},
    "rh-admissao": {"text": [LINKS, SIZE5, NO_EMOJI, HELP_LINK], "flow": True},
    "rh-facilities": {"text": [LINKS, SIZE3, HELP_LINK, SIZE5]},
}


def flow_action():
    return f"""mcs.metadata:
  componentName: Abrir caso no Workday
  description: Abre um caso de atendimento no Workday pelo fluxo da solução.
kind: TaskDialog
inputs:
  - kind: AutomaticTaskInput
    propertyName: resumo
    description: Resumo da solicitação do colaborador, em uma frase.
    shouldPromptUser: false

modelDisplayName: Abrir caso no Workday
modelDescription: Abre um caso no Workday quando o colaborador pede uma ação que o RH precisa executar (ajuste de férias, inclusão de dependente, correção de dados).
action:
  kind: InvokeFlowTaskAction
  flowId: {FLOW_ID}
"""


def triage_topic():
    return """mcs.metadata:
  componentName: Desambiguar
  description: Pergunta ao colaborador qual assunto ele quis dizer quando mais de um tópico serve.
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
# Wave 2 (agent-review 1.4): the orchestrator's contract, the flows, what nobody uses
# ---------------------------------------------------------------------------

LISTAR_LOJAS_ID = "3f2a9c1d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
WAVE2 = {
    "rh-ferias": {"flow": "returns", "disabled_node": True},
    "rh-beneficios": {"flow": "returns"},
    "rh-admissao": {"flow": "silent"},       # the flow answers nothing to the agent
    "rh-facilities": {"orphan_flow": True, "orphan_topic": True},
    "rh-folha": {"orphan_variable": True},
}


# wave 3: admissao writes its event another way, and leaves the conversation id out
WAVE3 = {
    "rh-admissao": {"event": "rh_admissao_onerror", "no_conversation_id": True},
}

# wave 3, outside the agents' folder: what a person exports — the query of the telemetry (references/telemetry.md), the
# Power Platform admin center's inventory, and the team's own spreadsheet (with «;», as Excel saves it in Portuguese)
TELEMETRY_CSV = """agente,evento,vezes
RH - Orquestrador,TopicStart,1840
RH - Orquestrador,RhOrquestrador_OnError,12
RH - Férias,TopicStart,610
RH - Férias,RhFerias_OnError,7
RH - Benefícios,TopicStart,402
RH - Benefícios,RhBeneficios_OnError,3
RH - Folha,TopicStart,355
RH - Admissão,TopicStart,290
RH - Admissão,rh_admissao_onerror,5
"""

# wave 4c, outside the agents' folder: two exports of Copilot Studio's Evaluate tab, in its columns. The product names
# them «Evaluate <agent name> <date>.csv»; here in kebab-case, which the skill reads the same. Férias passes all; Folha fails one, on a second method too.
EVALS = {
    "evaluate-rh-ferias-2026-10-30.csv": """question,expectedResponse,actualResponse,testMethodType_1,result_1,passingScore_1,explanation_1
Quantos dias de férias eu tenho?,,"Você tem 18 dias de saldo no período atual.",GeneralQuality,Pass,,Seems relevant; Seems complete
Posso dividir as férias em três períodos?,,"Sim: em até três períodos, um deles com pelo menos 14 dias.",GeneralQuality,Pass,,Seems relevant; Seems complete
Quanto tempo o gestor tem para aprovar?,,"O gestor aprova em até 2 dias úteis no Workday.",GeneralQuality,Pass,,Seems relevant
Quero falar com uma pessoa,,"Vou te passar para alguém do RH agora.",GeneralQuality,Pass,,Seems relevant
""",
    "evaluate-rh-folha-2026-10-30.csv": """question,expectedResponse,actualResponse,testMethodType_1,result_1,passingScore_1,explanation_1,testMethodType_2,result_2,passingScore_2,explanation_2
Quando cai o salário deste mês?,"No quinto dia útil","O salário é pago no quinto dia útil do mês.",GeneralQuality,Pass,,Seems relevant,CompareMeaning,Pass,70,Same meaning
O adiantamento é automático?,"Sim, no dia 20","Sim: o adiantamento cai todo dia 20.",GeneralQuality,Pass,,Seems relevant,CompareMeaning,Pass,70,Same meaning
Quando sai a primeira parcela do 13º?,"Até 30 de novembro","Sai em breve.",GeneralQuality,Fail,,Seems incomplete,CompareMeaning,Fail,70,Different meaning
Quero falar com uma pessoa,"Encaminhar para uma pessoa","Posso te ajudar com a folha por aqui.",GeneralQuality,Pass,,Seems relevant,CompareMeaning,Fail,70,Question not answered
""",
}

INVENTORY_CSV = """Item name,Item type,Schema name,Owner,Environment,Created on,Last published
RH - Orquestrador,Agent,cr7b2_rhOrquestrador,rh@empresa.example,RH (Produção),2026-03-02,2026-10-28
RH - Férias,Agent,cr7b2_rhFerias,ferias@empresa.example,RH (Produção),2026-03-05,2026-10-21
RH - Benefícios,Agent,cr7b2_rhBeneficios,beneficios@empresa.example,RH (Produção),2026-03-05,2026-10-14
RH - Folha,Agent,cr7b2_rhFolha,folha@empresa.example,RH (Produção),2026-03-09,2026-09-30
RH - Admissão,Agent,cr7b2_rhAdmissao,,RH (Produção),2026-03-12,2026-10-02
RH - Facilities,Agent,cr7b2_rhFacilities,facilities@empresa.example,RH (Produção),2026-04-01,
RH - Mobilidade,Agent,cr7b2_rhMobilidade,mobilidade@empresa.example,RH (Testes),2026-08-20,
Painel de Férias,Canvas app,,ferias@empresa.example,RH (Produção),2026-02-11,
Abrir caso no Workday,Agent flow,,ferias@empresa.example,RH (Produção),2026-03-05,
"""

TEAM_CSV = """Agente;KPI;Dono
RH - Férias;saldo informado em até 2 trocas de mensagem;Squad Férias
RH - Benefícios;inclusão aberta sem atendente em 80% dos casos;Squad Benefícios
RH - Folha;resposta sobre o holerite em menos de 5 s;Squad Folha
RH - Admissão;documentos pendentes listados na primeira tentativa;Squad Admissão
RH - Facilities;;Squad Facilities
Sobre o RH;respostas gerais sem encaminhar;Squad Atendimento RH
"""


def flow_folder(d, name, folder, workflow_id, actions, returns=True):
    # the extension's metadata.yml: the name in `name`, among other fields of the flow
    write(f"{d}/workflows/{folder}/metadata.yml", f"""jsonFileName: workflow.json
workflowId: {workflow_id}
name: {name}
type: 1
category: 5
mode: 0
scope: 4
statecode: 1
statuscode: 2
runAs: 1
modernFlowType: 1
""")
    if returns:
        actions = {**actions, "Responder": {"type": "Response", "kind": "Skills", "runAfter": {next(iter(actions)): ["Succeeded"]},
                                           "inputs": {"statusCode": 200, "body": {"resultado": "@outputs('Resultado')"}}}}
    flow = {"schemaVersion": "1.0.0.0", "properties": {"connectionReferences": {}, "definition": {
        "$schema": "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#",
        "contentVersion": "1.0.0.0",
        "triggers": {"manual": {"type": "Request", "kind": "Skills", "inputs": {"schema": {"type": "object", "properties": {"resumo": {"type": "string"}}}}}},
        "actions": actions}}}
    write(f"{d}/workflows/{folder}/workflow.json", json.dumps(flow, ensure_ascii=False, indent=2) + "\n", bom=True)


def erp_flow(d, returns):
    flow_folder(d, "Abrir caso no Workday", f"AbrirCasoWorkday-{FLOW_ID}", FLOW_ID, {
        "Abrir_caso": {"type": "Scope", "actions": {
            "Chamar_Workday": {"type": "Http", "inputs": {"method": "POST", "uri": "https://workday.empresa.example/casos", "body": "@triggerBody()"}}}}}, returns)


def stores_flow(d):
    flow_folder(d, "Listar unidades", f"ListarUnidades-{LISTAR_LOJAS_ID}", LISTAR_LOJAS_ID, {
        "Listar": {"type": "OpenApiConnection", "inputs": {"host": {
            "apiId": "/providers/Microsoft.PowerApps/apis/shared_commondataserviceforapps",
            "connectionName": "shared_commondataserviceforapps", "operationId": "ListRecords"}, "parameters": {"entityName": "unidades"}}}})


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
      activity: {q('No feriado de carnaval as unidades fecham às 14h.')}
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
        "key": "rh-ferias",
        "schema": f"{PREFIX}_rhFerias",
        "component": "RH - Férias",
        "display": "RH - Férias",
        "instructions": """
Você é o especialista em férias e ausências do autoatendimento de RH da empresa.

Responsabilidades:
- Informar o saldo de férias e explicar como pedir férias, folgas e licenças
- Usar a base "Política de Férias e Ausências" para responder dúvidas sobre regras e prazos
- Enviar ao colaborador, quando ele pedir, um e-mail com o resumo da solicitação

Regras:
- Responda sempre em português do Brasil, de forma curta e cordial
- Nunca invente saldos, datas ou números de solicitação
- Se a dúvida for sobre benefícios, folha, admissão ou facilities, diga que é outro especialista que cuida disso
""",
        "starters": [("Saldo de férias", "Quantos dias de férias eu tenho?"), ("Pedir férias", "Como peço férias para o mês que vem?")],
        "greeting": [
            "Olá! Eu sou o {System.Bot.Name}. Posso te ajudar com as suas férias ou ausências?",
            "Oi! Aqui é o especialista em férias do RH. Em que posso ajudar?",
        ],
        "contact": "ferias@empresa.example",
        "escalate": True,
        "telemetry": True,
        "topic": ("ConsultarPoliticaFerias", "Consultar Política de Férias",
                  "Responde dúvidas sobre férias e ausências com base na política publicada no SharePoint.",
                  "Responde perguntas sobre saldo de férias, períodos aquisitivos, como pedir férias e licenças e o prazo de aprovação do gestor.",
                  "A pergunta do colaborador sobre férias, folgas, licenças ou o saldo."),
        "knowledge": ("PoliticaFeriasAusencias", "Política de Férias e Ausências",
                      "Regras de férias, folgas, licenças e prazos de aprovação da empresa.",
                      "https://empresa.sharepoint.com/sites/RH/Shared%20Documents/Ferias", None),
        "email": ("EnviarResumoFerias", "Enviar resumo da solicitação por e-mail",
                  "Envia ao colaborador um e-mail com o resumo da solicitação de férias.",
                  "Enviar resumo da solicitação por e-mail",
                  "Envia ao colaborador, pelo Outlook, um e-mail com o resumo da solicitação de férias. Use somente quando o colaborador pedir o resumo por e-mail.",
                  ("auto", "Endereço de e-mail do colaborador que vai receber o resumo da solicitação.")),
    },
    {
        "key": "rh-beneficios",
        "schema": f"{PREFIX}_rhBeneficios",
        "component": "RH - Benefícios",
        "display": "RH - Benefícios",
        "instructions": """
Você é o especialista em benefícios do autoatendimento de RH da empresa.

Responsabilidades:
- Explicar o plano de saúde, o plano odontológico, o vale-refeição e as regras de reembolso
- Usar a base "Guia de Benefícios" para responder
- Abrir uma solicitação de inclusão de dependente enviando um e-mail para a equipe de benefícios

Regras:
- Responda sempre em português do Brasil, com empatia e objetividade
- Confirme o nome do dependente e o grau de parentesco antes de abrir a solicitação
- Não prometa reembolso antes da análise da equipe de benefícios
""",
        "starters": [("Incluir dependente", "Quero incluir minha filha no plano de saúde"), ("Reembolso", "Como peço reembolso de uma consulta?")],
        "greeting": [
            "Olá! Eu sou o {System.Bot.Name}. Vamos ver os seus benefícios?",
            "Oi! Aqui é o especialista em benefícios do RH. Como posso ajudar?",
        ],
        "contact": "beneficios@empresa.example",
        "escalate": True,
        "telemetry": True,
        "topic": ("ConsultarGuiaBeneficios", "Consultar Guia de Benefícios",
                  "Responde dúvidas sobre benefícios com base no guia publicado no SharePoint.",
                  "Responde perguntas sobre plano de saúde, plano odontológico, inclusão de dependentes, vale-refeição e reembolso.",
                  "A pergunta do colaborador sobre benefícios, dependentes ou reembolso."),
        "knowledge": ("GuiaBeneficios", "Guia de Benefícios",
                      "Planos, inclusão de dependentes, vale-refeição e regras de reembolso da empresa.",
                      "https://empresa.sharepoint.com/sites/RH/Shared%20Documents/Beneficios", None),
        "email": ("AbrirInclusaoDependente", "Abrir inclusão de dependente",
                  "Envia à equipe de benefícios um e-mail abrindo a inclusão de um dependente.",
                  "Abrir inclusão de dependente",
                  "Envia pelo Outlook um e-mail para a equipe de benefícios com o nome do dependente, o grau de parentesco e o plano. Use depois de confirmar esses dados com o colaborador.",
                  ("manual", "equipe.beneficios@empresa.example")),
    },
    {
        "key": "rh-folha",
        "schema": f"{PREFIX}_rhFolha",
        "component": "RH - Folha",
        "display": "RH - Folha",
        "instructions": """
Você é o especialista em folha de pagamento do autoatendimento de RH da empresa.

Responsabilidades:
- Explicar o holerite, os descontos e o calendário de pagamento
- Usar a base "Calendário e Regras da Folha" para responder
- Enviar ao colaborador, quando ele pedir, um e-mail com o calendário de pagamento

Regras:
- Responda sempre em português do Brasil
- Datas de pagamento são sempre em dias úteis; deixe isso claro
- Não calcule descontos de cabeça: use apenas o que está na base
""",
        "starters": [("Data do pagamento", "Quando cai o salário deste mês?"), ("Holerite", "Onde vejo o meu holerite?")],
        "greeting": [
            "Olá! Eu sou o {System.Bot.Name}. Quer saber sobre o seu holerite ou o calendário de pagamento?",
            "Oi! Aqui é o especialista em folha do RH. Em que posso ajudar?",
        ],
        "contact": "folha@empresa.example",
        "escalate": False,
        "telemetry": True,
        "topic": ("ConsultarCalendarioFolha", "Consultar Calendário da Folha",
                  "Responde dúvidas sobre a folha de pagamento com base no calendário publicado no SharePoint.",
                  "Responde perguntas sobre o holerite, os descontos, o adiantamento e as datas de pagamento.",
                  "A pergunta do colaborador sobre holerite, descontos ou data de pagamento."),
        "knowledge": ("CalendarioRegrasFolha", "Calendário e Regras da Folha",
                      "Datas de pagamento, descontos e regras do holerite da empresa.",
                      "https://empresa.sharepoint.com/sites/Folha/Shared%20Documents/Calendario", None),
        "email": ("EnviarCalendarioFolha", "Enviar calendário da folha por e-mail",
                  "Envia ao colaborador um e-mail com o calendário de pagamento.",
                  "Enviar calendário da folha por e-mail",
                  "Envia ao colaborador, pelo Outlook, um e-mail com as datas de pagamento consultadas na conversa. Use somente quando o colaborador pedir.",
                  ("auto", "Endereço de e-mail do colaborador que vai receber o calendário.")),
    },
    {
        "key": "rh-admissao",
        "schema": f"{PREFIX}_rhAdmissao",
        "component": "RH - Admissão",
        "display": "RH - Admissão",
        "instructions": """
Você é o especialista em admissão do autoatendimento de RH da empresa.

Responsabilidades:
- Explicar as etapas da admissão com base no "Guia de Admissão"
- Consultar a lista de documentos de admissão no SharePoint para dizer o que ainda falta entregar
- Usar o servidor MCP de admissão para buscar o checklist do primeiro dia
- Enviar ao colaborador, quando ele pedir, um e-mail com o checklist de admissão

Regras:
- Responda sempre em português do Brasil
- Nunca peça documentos fora da lista oficial de admissão
- Documentos digitais só valem quando o guia disser que valem
""",
        "starters": [("Documentos", "Quais documentos ainda faltam para a minha admissão?"), ("Primeiro dia", "O que acontece no meu primeiro dia?")],
        "greeting": [
            "Olá! Eu sou o {System.Bot.Name}. Quer ver o que falta para a sua admissão ou o seu primeiro dia?",
            "Oi! Aqui é o especialista em admissão do RH. Como posso ajudar?",
        ],
        "contact": "admissao@empresa.example",
        "escalate": True,
        "telemetry": True,
        "topic": ("ConsultarGuiaAdmissao", "Consultar Guia de Admissão",
                  "Responde dúvidas sobre a admissão com base no guia publicado no SharePoint.",
                  "Responde perguntas sobre as etapas da admissão, os documentos, o exame admissional e o primeiro dia.",
                  "A pergunta do colaborador sobre admissão, documentos ou primeiro dia."),
        "knowledge": ("GuiaAdmissao", "Guia de Admissão",
                      "Etapas, documentos, exame admissional e primeiro dia de quem entra na empresa.",
                      "https://empresa.sharepoint.com/sites/RH/Shared%20Documents/Admissao", None),
        "email": ("EnviarChecklistAdmissao", "Enviar checklist de admissão por e-mail",
                  "Envia ao colaborador um e-mail com o checklist de admissão.",
                  "Enviar checklist de admissão por e-mail",
                  "Envia ao colaborador, pelo Outlook, um e-mail com o checklist de admissão e os documentos que faltam. Use somente quando o colaborador pedir.",
                  ("auto", "Endereço de e-mail do colaborador que vai receber o checklist.")),
    },
    {
        "key": "rh-facilities",
        "schema": f"{PREFIX}_rhFacilities",
        "component": "RH - Facilities",
        "display": "RH - Facilities",
        "instructions": """
Você é o especialista em facilities do autoatendimento de RH da empresa.

Responsabilidades:
- Informar endereço, horário de funcionamento e serviços de cada unidade
- Explicar como reservar sala, cadastrar visitante e abrir um chamado de manutenção
- Usar a base "Guia das Unidades" para responder
- Enviar ao colaborador, quando ele pedir, um e-mail com as instruções de acesso à unidade

Regras:
- Responda sempre em português do Brasil
- Confirme a unidade antes de dar instruções de acesso
- Horários especiais de feriado só valem se estiverem no guia
""",
        "starters": [("Horário da unidade", "Qual o horário de funcionamento da unidade de São Paulo?"), ("Visitante", "Como cadastro um visitante?")],
        "greeting": [
            "Olá! Eu sou o {System.Bot.Name}. Quer saber sobre as unidades, salas ou visitantes?",
            "Oi! Aqui é o especialista em facilities do RH. Como posso ajudar?",
        ],
        "contact": "facilities@empresa.example",
        "escalate": True,
        "telemetry": False,
        "topic": ("ConsultarGuiaUnidades", "Consultar Guia das Unidades",
                  "Responde dúvidas sobre as unidades com base no guia publicado no SharePoint.",
                  "Responde perguntas sobre endereço, horário de funcionamento, reserva de sala, visitantes e manutenção nas unidades.",
                  "A pergunta do colaborador sobre uma unidade, sala, visitante ou manutenção."),
        "knowledge": ("GuiaUnidades", "Guia das Unidades",
                      "Endereços, horários, serviços, salas e regras de acesso das unidades da empresa.",
                      "https://empresa.sharepoint.com/sites/Facilities/Shared%20Documents/Unidades",
                      '=Or(IsBlank(Global.CategoriaSolicitacao), Global.CategoriaSolicitacao = "Facilities")'),
        "email": ("EnviarInstrucoesAcesso", "Enviar instruções de acesso por e-mail",
                  "Envia ao colaborador um e-mail com as instruções de acesso à unidade.",
                  "Enviar instruções de acesso por e-mail",
                  "Envia ao colaborador, pelo Outlook, um e-mail com endereço, horário e documentos necessários para entrar na unidade. Use somente quando o colaborador pedir.",
                  ("auto", "Endereço de e-mail do colaborador que vai receber as instruções de acesso.")),
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
        write(f"{d}/actions/AbrirCasoWorkday.mcs.yml", flow_action())
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
    write_bytes(f"{d}/icon.png", ICON_PNG)

    # variables
    write(f"{d}/variables/CategoriaSolicitacao.mcs.yml", variable_file(s, external=True, default="=Blank()"))

    # actions + connection references
    refs = []
    o = outlook_ref(s)
    refs.append(o)
    efile, ecomp, edesc, emodel, emodeldesc, eto = a["email"]
    write(f"{d}/actions/{efile}.mcs.yml", outlook_action(ecomp, edesc, emodel, emodeldesc, o["name"], eto))

    if a["key"] == "rh-admissao":
        sp = {
            "id": guid(),
            "name": f"{s}.shared_sharepointonline.shared-sharepointonline-{guid()}",
            "connectorId": "/providers/Microsoft.PowerApps/apis/shared_sharepointonline",
            "display": "SharePoint",
        }
        refs.append(sp)
        write(f"{d}/actions/ConsultarDocumentosAdmissao.mcs.yml", f"""mcs.metadata:
  componentName: Consultar documentos de admissão
  description: Consulta a lista de documentos de admissão no SharePoint de RH.
kind: TaskDialog
inputs:
  - kind: ManualTaskInput
    propertyName: dataset
    value: https://empresa.sharepoint.com/sites/RH

  - kind: ManualTaskInput
    propertyName: table
    value: DocumentosAdmissao

  - kind: AutomaticTaskInput
    propertyName: "'$filter'"
    description: "Filtro OData pela coluna Matricula com a matrícula informada pelo colaborador. Exemplo: Matricula eq '104233'"
    entity: StringPrebuiltEntity
    shouldPromptUser: false

  - kind: ManualTaskInput
    propertyName: "'$top'"
    value: "10"

modelDisplayName: Consultar documentos de admissão
modelDescription: Verifica na lista DocumentosAdmissao do SharePoint quais documentos o colaborador já entregou e quais faltam. Use quando o colaborador perguntar o que falta para a admissão.
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
            "name": f"{s}.shared_rhadmissaomcp.{rid('mcp').split('_')[1].lower()}",
            "connectorId": "/providers/Microsoft.PowerApps/apis/shared_rhadmissaomcp",
            "display": "RH Admissao MCP",
            "custom": guid(),
        }
        refs.append(mcp)
        write(f"{d}/actions/AdmissaoMCP.mcs.yml", f"""mcs.metadata:
  componentName: Servidor MCP de Admissão
  description: Servidor MCP interno com o checklist de admissão e do primeiro dia.
kind: TaskDialog
inputs:
  - kind: ManualTaskInput
    propertyName: canal
    value: =System.Activity.ChannelId

modelDisplayName: Servidor MCP de Admissão
modelDescription: Servidor MCP que lista as etapas da admissão e o checklist do primeiro dia de um colaborador.
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
    key = "rh-orquestrador"
    s = f"{PREFIX}_rhOrquestrador"
    d = os.path.join(ROOT, key)
    display = "RH - Orquestrador"
    instructions = """
Você é o assistente de autoatendimento do RH da empresa. Você não responde sozinho às dúvidas
dos colaboradores: o seu papel é entender a solicitação e encaminhá-la ao especialista certo.

Como trabalhar:
1. Antes de acionar um especialista, use o tópico "Classificar Solicitação" para definir a categoria.
2. Encaminhe conforme a categoria:
   - Ferias: agente "RH - Férias"
   - Beneficios: agente "RH - Benefícios"
   - Folha: agente "RH - Folha"
   - Admissao: agente "RH - Admissão"
   - Facilities: agente "RH - Facilities"
   - Outro: se for uma pergunta geral sobre o RH, use o agente "Sobre o RH"
3. Repasse a resposta do especialista ao colaborador sem inventar informações.

Regras:
- Responda sempre em português do Brasil, de forma cordial e objetiva
- Se o colaborador pedir para falar com uma pessoa, use o tópico de escalonamento

Não use emojis.
"""
    starters = [("Minhas férias", "Quantos dias de férias eu tenho?"), ("Dependentes", "Quero incluir um dependente no plano"), ("Admissão", "Quais documentos faltam na minha admissão?")]
    write(f"{d}/agent.mcs.yml", agent_file(display, display, instructions, starters))
    write(f"{d}/settings.mcs.yml", settings_file(display, s, connectable=False))
    write_bytes(f"{d}/icon.png", ICON_PNG)

    write(f"{d}/topics/Greeting.topic.mcs.yml", greeting_topic([
        "Olá! Eu sou o {System.Bot.Name}, o autoatendimento do RH. Como posso ajudar hoje?",
        "Oi! Posso ajudar com férias, benefícios, folha, admissão ou facilities.",
    ]))
    write(f"{d}/topics/Fallback.topic.mcs.yml", fallback_topic(s, escalate=True))
    write(f"{d}/topics/Escalate.topic.mcs.yml", escalate_topic("rh@empresa.example"))
    write(f"{d}/topics/OnError.topic.mcs.yml", error_topic("RhOrquestrador_OnError", key, telemetry=True))

    desc = """Classifique a solicitação do colaborador em exatamente uma destas categorias:
Ferias, Beneficios, Folha, Admissao, Facilities, Outro
Use Outro quando nenhuma das demais se aplicar."""
    write(f"{d}/topics/ClassificarSolicitacao.topic.mcs.yml", f"""mcs.metadata:
  componentName: Classificar Solicitação
  description: Define a categoria da solicitação do colaborador para encaminhar ao especialista certo.
kind: AdaptiveDialog
inputs:
  - kind: AutomaticTaskInput
    propertyName: CategoriaSolicitacao
    description: |-
{block(desc, 6)}
    shouldPromptUser: false

modelDescription: Classifica a solicitação do colaborador (férias, benefícios, folha, admissão, facilities ou outro) antes de acionar um agente especialista. Use sempre antes de chamar um especialista.
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
        ("AgenteFerias", "Agente Férias", "RH - Férias", f"{PREFIX}_rhFerias",
         "Agente especialista em férias e ausências: saldo, pedido de férias, folgas, licenças e aprovação do gestor. Use quando a categoria for Ferias."),
        ("AgenteBeneficios", "Agente Benefícios", "RH - Benefícios", f"{PREFIX}_rhBeneficios",
         "Agente especialista em benefícios: plano de saúde, dependentes, vale-refeição e reembolso. Use quando a categoria for Beneficios."),
        ("AgenteFolha", "Agente Folha", "RH - Folha", f"{PREFIX}_rhFolha",
         "Agente especialista em folha de pagamento: holerite, descontos e calendário de pagamento. Use quando a categoria for Folha."),
        # wave 2: a routing description too short to route by
        ("AgenteAdmissao", "Agente Admissão", "RH - Admissão", f"{PREFIX}_rhAdmissao", "Admissão."),
        ("AgenteFacilities", "Agente Facilities", "RH - Facilities", f"{PREFIX}_rhFacilities",
         "Agente especialista em facilities: endereço e horário das unidades, salas, visitantes e manutenção. Use quando a categoria for Facilities."),
        # wave 2: an agent of the solution that is not in the folder
        ("AgenteMobilidade", "Agente Mobilidade", "RH - Mobilidade", f"{PREFIX}_rhMobilidade",
         "Agente especialista em mobilidade interna: vagas internas, transferências e movimentações. Use quando a categoria for Mobilidade."),
    ]
    for fname, comp, model_name, bot, mdesc in connected:
        # wave 2: folha is called with no history and without the category
        bare = fname == "AgenteFolha"
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

    write(f"{d}/agents/SobreRH/agent.mcs.yml", """# Name: Sobre o RH
# SobreRH
kind: AgentDialog

beginDialog:
  kind: OnToolSelected
  id: main
  description: Responde perguntas gerais sobre o RH que não são de férias, benefícios, folha, admissão ou facilities, como canais de contato, horário de atendimento e a quem recorrer. Exemplos "Qual o telefone do RH?", "O RH atende no sábado?".

settings:
  instructions: |
    Você responde perguntas gerais sobre o atendimento do RH da empresa.

    Regras:
    - Responda em português do Brasil, em no máximo três frases
    - Canais oficiais: portal do colaborador, e-mail rh@empresa.example e o chat do Teams
    - Atendimento do RH: de segunda a sexta, das 8h às 18h
    - Se a pergunta for sobre férias, benefícios, folha, admissão ou facilities, diga que outro especialista cuida disso

inputs:
  - kind: AutomaticTaskInput
    propertyName: PerguntaGeral
    description: A pergunta geral do colaborador sobre o RH.

inputType:
  properties:
    PerguntaGeral:
      displayName: Pergunta Geral
      description: A pergunta geral do colaborador sobre o RH.
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
    for name, body in EVALS.items():
        write(os.path.join(examples, "avaliacoes", name), body)
    print("done")
