"""Por onde cada arquivo chega ao modelo — o roteamento, puro.

## Três caminhos, e só três

Na Responses API existem três formas de um arquivo alcançar o modelo, e a
escolha entre elas não é preferência:

======================  ====================================================
``NATIVO``              o documento vai INTEIRO dentro da mensagem
``IMAGEM``              a imagem vai como imagem
``SANDBOX``             o tabular vai para o Code Interpreter, nunca na mensagem
======================  ====================================================

## ⚠️ A regra que carrega o módulo: planilha NUNCA vai na mensagem

O provider ACEITA um CSV em ``input_file`` — e é exatamente por isso que é
perigoso. Ele converte a planilha num preview das primeiras 1.000 linhas e o
modelo responde sobre o recorte com a mesma confiança de uma resposta correta.

MEDIDO em 02/08/2026, mesmo arquivo de 50.000 linhas (1,1 MB) subido pela Files
API, mesma pergunta ("quantas linhas de dados?"):

=========================  ===========  ===================
caminho                    resposta     tokens de entrada
=========================  ===========  ===================
dentro da mensagem         **1000**     12.056
``code_interpreter``       **50000**    854
=========================  ===========  ===================

Resposta certa com 14× menos tokens. Não há flag no retorno, não há aviso: o
erro chega parecendo acerto.

## O que NÃO entra, e por que dizer o motivo importa

Compactado, áudio e vídeo são RECONHECIDOS e recusados com o motivo nomeado.
Reconhecer um formato e dizer por que ele não passa é diferente de não saber o
que ele é — o segundo vira "falhou" na tela do usuário.

## Puro de propósito

Nada aqui faz I/O. Subir bytes para a Files API é do host (é ele que tem o
cliente e a credencial); o que mora aqui é a DECISÃO, exercitável sem rede — a
mesma fronteira de ``agent_grant`` e ``capabilities``.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

__all__ = [
    "EXTENSAO_POR_MIME",
    "Estrategia",
    "extensao_para",
    "MOTIVOS_DE_RECUSA",
    "bloco_nativo",
    "estrategia_para",
    "ferramenta_sandbox",
]


class Estrategia(str, Enum):
    """Por onde este arquivo alcança o modelo."""

    NATIVO = "nativo"
    IMAGEM = "imagem"
    SANDBOX = "sandbox"
    #: Reconhecido e recusado. Ver ``MOTIVOS_DE_RECUSA``.
    RECUSADO = "recusado"


#: Documentos que o provider lê por completo dentro da mensagem. Medidos um a
#: um pelo `langgraph-file-agent` contra o Azure real; a documentação da
#: Microsoft afirma que PDF é o único, e isso é falso.
_NATIVOS = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/html",
    "text/xml",
    "application/xml",
    "application/json",
    "application/rtf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

_IMAGENS = {"image/png", "image/jpeg", "image/gif", "image/webp"}

#: Tabulares. Ver o aviso do cabeçalho — este conjunto é a razão de o módulo
#: existir.
_TABULARES = {
    "text/csv",
    "text/tab-separated-values",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

#: Formato reconhecido → por que ele não entra. A mensagem é para o usuário, e
#: por isso diz o que FALTA, não que "não é suportado".
MOTIVOS_DE_RECUSA: Mapping[str, str] = {
    "application/zip": "arquivo compactado precisa ser aberto antes de ser lido",
    "application/x-7z-compressed": "arquivo compactado precisa ser aberto antes de ser lido",
    "application/x-rar-compressed": "arquivo compactado precisa ser aberto antes de ser lido",
    "application/gzip": "arquivo compactado precisa ser aberto antes de ser lido",
    "audio": "áudio precisa de transcrição, que é outro endpoint",
    "video": "vídeo precisa de extração de áudio e amostragem de quadros",
}


#: MIME → extensão. Não é conveniência: a Files API valida a EXTENSÃO do nome
#: do arquivo, e recusa o que não conhece.
#:
#: ⚠️ Derivar o sufixo cortando o MIME não funciona, e falha exatamente nos
#: formatos que mais importam. MEDIDO em 02/08/2026: um XLSX
#: (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`) vira
#: `anexo.vnd.openxmlf`, e a API responde
#: `Invalid extension openxmlf`. O upload falha, o sandbox não recebe nada, e o
#: modelo — que já viu a nota dizendo que a planilha está lá — PEDE o arquivo de
#: novo. O usuário vê um agente confuso, não um erro.
EXTENSAO_POR_MIME: Mapping[str, str] = {
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/html": ".html",
    "text/xml": ".xml",
    "application/xml": ".xml",
    "application/json": ".json",
    "application/rtf": ".rtf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "text/csv": ".csv",
    "text/tab-separated-values": ".tsv",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def extensao_para(mime: str) -> str:
    """A extensão que a Files API aceita para este MIME.

    Default `.txt` — o provider trata fluxo desconhecido como texto, que é a
    degradação segura. O que NÃO é seguro é inventar sufixo a partir do MIME:
    ver o aviso em `EXTENSAO_POR_MIME`.
    """
    m = (mime or "").split(";")[0].strip().lower()
    return EXTENSAO_POR_MIME.get(m, ".txt")


def estrategia_para(mime: str) -> Estrategia:
    """Por onde este MIME entra — determinístico, e sem caso default silencioso.

    Um MIME desconhecido cai em ``RECUSADO``, e não em "tenta como texto": o
    caminho otimista transformaria um binário qualquer num preview truncado, que
    é o modo de falha que este módulo existe para fechar.
    """
    m = (mime or "").split(";")[0].strip().lower()
    if m in _TABULARES:
        return Estrategia.SANDBOX
    if m in _IMAGENS:
        return Estrategia.IMAGEM
    if m in _NATIVOS:
        return Estrategia.NATIVO
    return Estrategia.RECUSADO


def motivo_da_recusa(mime: str) -> str:
    """A frase que o usuário lê. Nunca "não suportado" — sempre o que falta."""
    m = (mime or "").split(";")[0].strip().lower()
    if m in MOTIVOS_DE_RECUSA:
        return MOTIVOS_DE_RECUSA[m]
    familia = m.split("/")[0]
    if familia in MOTIVOS_DE_RECUSA:
        return MOTIVOS_DE_RECUSA[familia]
    return f"o formato {m or '(desconhecido)'} não é lido por este agente"


def bloco_nativo(*, base64_data: str, mime: str, filename: str) -> dict[str, Any]:
    """O content block de ARQUIVO, no formato padrão do LangChain.

    ⚠️ ``{"type": "file", "source_type": "base64"}``, e **não** o
    ``{"type": "input_file"}`` cru da OpenAI. Os dois funcionam — MEDIDO em
    02/08/2026, ambos devolveram o segredo plantado — e o primeiro é o que o
    LangChain traduz por provedor.

    O DNA emite para sete runtimes. Um bloco cru de um provedor amarraria a
    projeção a ele, e o custo apareceria no dia em que alguém trocasse o modelo.
    """
    return {
        "type": "file",
        "source_type": "base64",
        "data": base64_data,
        "mime_type": mime,
        "filename": filename,
    }


def ferramenta_sandbox(file_ids: list[str]) -> dict[str, Any]:
    """A tool nativa do Code Interpreter, com os arquivos montados no container.

    ``container.type = "auto"`` deixa o provider criar o sandbox; os ``file_ids``
    são os que o HOST subiu pela Files API — este módulo não sobe nada.

    ⚠️ O container é EFÊMERO. O que ele produzir precisa ser baixado durante a
    resposta; guardar um ponteiro para depois seria guardar um link morto.
    """
    return {
        "type": "code_interpreter",
        "container": {"type": "auto", "file_ids": list(file_ids)},
    }
