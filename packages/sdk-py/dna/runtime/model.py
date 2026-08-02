"""Como o runtime monta o modelo de chat — um lugar só.

## Por que existe

``init_chat_model(f"openai:{model}")`` aparecia em DOIS pontos: o
``run_local`` do ``builder`` e o ``langchain_rt`` que serve. Duas leituras da
mesma pergunta divergem, e esta em particular divergiria em silêncio — o mesmo
agente responderia diferente conforme fosse executado localmente ou servido.

## ⭐ A Responses API é o default, e isso destrava ARQUIVO

Sem ela, o modelo fala **Chat Completions**, que **não aceita arquivo de
entrada** (a OpenAI removeu em 2025-09). Foi essa limitação que fez o dna-cloud
converter todo anexo para Markdown antes de mandar — e é ela que a Responses
API remove.

MEDIDO em 02/08/2026 contra `oai-dna-cloud-4j22elc7bxjoc`, deployment
`gpt-5-mini` (isto é, um modelo pequeno, não um topo de linha):

* ``input_file`` — leu o segredo plantado num `.txt`, 37 tokens de entrada
* ``code_interpreter`` — rodou o sandbox e devolveu o `sha256` correto

Não veio de documentação: a documentação do Azure afirma que PDF é o único tipo
aceito em ``input_file``, e o `langgraph-file-agent` mediu oito formatos
funcionando.

## ⚠️ A escotilha NÃO é uma preferência

``DNA_MODEL_RESPONSES_API=0`` desliga. Ela existe para um caso concreto e
verificável, não para gosto: ``OPENAI_BASE_URL`` pode apontar para um **gateway
compatível com OpenAI** (LiteLLM e afins — o bicep do dna-cloud tem parâmetros
exatamente para isso), e um gateway pode implementar `/chat/completions` sem
implementar `/responses`. Aí não é o modelo que não suporta; é o endpoint que
não tem a rota.

A distinção importa porque a spec desta mudança recusa uma FLAG de capacidade —
uma chave que fizesse "o PDF funcionar num deployment e não noutro" esconderia
justamente o que precisa aparecer. Isto aqui é outra coisa: compatibilidade de
ENDPOINT, com um sintoma diferente (404 na rota, não formato recusado).

Quem quer saber o que um deployment consegue fazer não pergunta a esta
variável — mede. Ver `dna.runtime.capabilities`.
"""
from __future__ import annotations

import os
from typing import Any

__all__ = ["build_chat_model", "deployment_para", "responses_api_enabled"]


def responses_api_enabled() -> bool:
    """Se este processo monta o modelo sobre a Responses API.

    Default **ligado**. Só ``0``/``false``/``no`` desligam — qualquer outro
    valor mantém o default, porque um typo numa variável de ambiente não pode
    desligar em silêncio a API que carrega o caminho de arquivo.
    """
    bruto = (os.environ.get("DNA_MODEL_RESPONSES_API") or "").strip().lower()
    return bruto not in {"0", "false", "no", "off"}


def deployment_para(model: str) -> str:
    """Qual DEPLOYMENT serve a coordenada que o agente declarou.

    ## A separação que isto torna explícita

    O documento do agente declara ``model: gpt-5-mini`` — uma **coordenada
    portátil**, parte da definição, versionada com ela e igual em todo ambiente.
    Qual *deployment* atende essa coordenada é fato do **ambiente**: o mesmo
    agente roda contra um recurso que tem ``gpt-5-mini`` e outro que só tem
    ``gpt-5.4``.

    Sem essa separação a única saída é editar a definição — que é COMPARTILHADA
    com produção. Foi exatamente o que aconteceu em 02/08/2026: o endpoint local
    passou a apontar para um recurso com ``gpt-5.4``, as definições continuaram
    pedindo ``gpt-5-mini``, e a chamada morreu com ``DeploymentNotFound``. No
    navegador isso chega como ``terminated`` — um erro opaco, no meio do stream.

    ⚠️ O override é REGISTRADO em log quando difere. Uma substituição silenciosa
    de modelo faria alguém depurar comportamento de um modelo que não está
    rodando — e essa é a depuração mais cara que existe.
    """
    alvo = (os.environ.get("DNA_MODEL_DEPLOYMENT") or "").strip()
    if not alvo or alvo == model:
        return model

    import logging

    logging.getLogger("dna.runtime.model").info(
        "deployment sobrepõe a coordenada do agente: %s → %s "
        "(DNA_MODEL_DEPLOYMENT). A definição segue portátil; isto é ambiente.",
        model,
        alvo,
    )
    return alvo


def build_chat_model(model: str, **extras: Any) -> Any:
    """O modelo de chat deste runtime, montado igual em todo lugar.

    ``model`` é a coordenada como o resto do SDK a carrega (``gpt-5-mini``); o
    prefixo de provedor é acrescentado aqui, porque quem chama não deveria
    precisar saber que ``init_chat_model`` usa ``provider:modelo``.
    """
    from langchain.chat_models import init_chat_model

    if responses_api_enabled():
        extras.setdefault("use_responses_api", True)
    return init_chat_model(f"openai:{deployment_para(model)}", **extras)
