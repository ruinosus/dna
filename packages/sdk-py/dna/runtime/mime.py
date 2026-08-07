"""O que o arquivo É — pelos bytes, não pelo que o cliente disse.

## Por que não confiar no declarado

O `Content-Type` e a extensão vêm do cliente. Os dois erram por acidente (um
navegador que manda ``application/octet-stream``) e podem mentir de propósito.
E o roteamento deste produto DEPENDE do MIME: ele decide se um arquivo vai
nativo, vira imagem, ou vai para o sandbox — então um MIME errado não dá erro,
dá **caminho errado**.

O caso concreto que motiva o módulo: uma planilha declarada como
``application/octet-stream`` cairia em `Strategy.REFUSED` e viraria uma tentativa
de MarkItDown, em vez de ir ao Code Interpreter. O usuário receberia um texto
truncado no lugar de um cálculo — e nada falharia.

## A divergência é INFORMAÇÃO, não erro

`mismatch` não recusa nada. Ele responde *"o que chegou bate com o que disseram
que é?"*, e quem chama decide. Um `.pdf` que na verdade é um ZIP pode ser um
engano inocente ou uma tentativa; em ambos os casos o registro precisa dizer as
duas coisas — o que foi declarado e o que era.

⚠️ Por isso `SourceArtifact` guarda `mime` **e** `detected_mime`. Sobrescrever o
declarado apagaria a evidência de que houve divergência, e a evidência é o valor.

## Texto não tem magic bytes

`filetype` cobre binário (PDF, imagens, Office, zip, áudio, vídeo) e **não**
reconhece texto puro — não há assinatura para reconhecer. Então há um segundo
passo explícito: se os bytes decodificam como UTF-8, é texto, e só aí a extensão
refina o subtipo. É a única situação em que a extensão vale, e ela vale porque
já sabemos que o conteúdo é texto.

## OOXML é ZIP por dentro

Um `.docx` é um ZIP, e `filetype` reporta o container. Tratar isso como
divergência marcaria toda instância do Office — então `mismatch` conhece essa
equivalência. Sem ela, o sinal viraria ruído e ninguém olharia mais para ele.
"""
from __future__ import annotations

__all__ = [
    "EXTENSION_MIME",
    "SNIFF_BYTES",
    "TEXT_EXTENSION_MIME",
    "detect_mime",
    "mismatch",
]

#: Quanto do arquivo basta ler. Magic bytes vivem no começo, e um teto evita
#: carregar um arquivo grande na memória só para descobrir o que ele é.
SNIFF_BYTES = 8192

#: Extensão → MIME de TEXTO. Só consultado depois de confirmar que o conteúdo
#: realmente decodifica como UTF-8 — a extensão sozinha nunca decide.
TEXT_EXTENSION_MIME = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".json": "application/json",
    ".xml": "text/xml",
    ".html": "text/html",
    ".htm": "text/html",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".log": "text/plain",
}

#: Extensão → MIME esperado. Usado APENAS para detectar divergência, nunca para
#: decidir o que o arquivo é.
EXTENSION_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".zip": "application/zip",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    **TEXT_EXTENSION_MIME,
}

#: Formatos OOXML são ZIP por dentro; o detector reporta o container.
_OOXML_CONTAINERS = {"application/zip", "application/x-zip-compressed"}

_TEXTUAIS = {"application/json", "application/xml", "application/yaml"}

#: Fallback quando nem os magic bytes nem o teste de texto decidem. Honesto: é o
#: que o próprio HTTP usa para "não sei".
UNKNOWN = "application/octet-stream"


def _extension(filename: str | None) -> str:
    nome = (filename or "").strip().lower()
    ponto = nome.rfind(".")
    return nome[ponto:] if ponto > 0 else ""


def _parece_texto(trecho: bytes) -> bool:
    """UTF-8 válido e sem bytes de controle — o teste que sobra sem assinatura.

    ⚠️ O corte em `SNIFF_BYTES` pode cair no MEIO de um caractere multibyte, e
    aí um arquivo de texto legítimo falharia o `decode`. Por isso o erro é
    tolerado nos últimos bytes: sem isso, um `.md` com acento na posição errada
    viraria `application/octet-stream`.
    """
    if not trecho:
        return False
    try:
        texto = trecho.decode("utf-8")
    except UnicodeDecodeError as e:
        if e.start < len(trecho) - 4:
            return False
        texto = trecho[: e.start].decode("utf-8", "ignore")
    # NUL é a marca prática de binário; tab/CR/LF são texto.
    return "\x00" not in texto


def detect_mime(content: bytes, filename: str | None = None) -> str:
    """O MIME real, dos BYTES. A extensão só refina texto.

    Sem o `filetype` instalado, degrada para o teste de texto — pior, e ainda
    melhor que confiar no declarado. Nunca levanta: um detector que derruba o
    upload transforma uma dúvida sobre formato numa falha de produto.
    """
    trecho = content[:SNIFF_BYTES]
    try:
        import filetype

        achado = filetype.guess(trecho)
        if achado is not None:
            return achado.mime
    except ImportError:
        pass
    except Exception:  # noqa: BLE001 — detector de terceiro não derruba o caminho
        pass

    if _parece_texto(trecho):
        return TEXT_EXTENSION_MIME.get(_extension(filename), "text/plain")
    return UNKNOWN


def _compativel(detectado: str, candidato: str) -> bool:
    if detectado == candidato:
        return True
    if _e_texto(detectado) and _e_texto(candidato):
        # Variação DENTRO de texto (`text/plain` vs `text/markdown`) não é
        # divergência: as duas são tratadas do mesmo jeito, e marcá-las
        # afogaria o sinal que importa.
        return True
    return detectado in _OOXML_CONTAINERS and candidato.startswith(
        "application/vnd.openxmlformats-officedocument"
    )


def _e_texto(mime: str) -> bool:
    return mime.startswith("text/") or mime in _TEXTUAIS


def mismatch(
    *, detected: str, declared: str | None = None, filename: str | None = None
) -> bool:
    """O que chegou bate com o que disseram que é?

    NÃO recusa nada — responde. Quem chama decide: um `.pdf` que é um ZIP pode
    ser engano inocente ou tentativa, e nos dois casos o registro precisa dizer
    as duas coisas.

    ``application/octet-stream`` declarado é IGNORADO como candidato: é o valor
    que um cliente manda quando não sabe, e tratá-lo como afirmação marcaria
    metade dos uploads de navegador como divergentes.
    """
    candidatos = []
    if declared and declared != UNKNOWN:
        candidatos.append(declared)
    esperado = EXTENSION_MIME.get(_extension(filename))
    if esperado:
        candidatos.append(esperado)
    return any(not _compativel(detected, c) for c in candidatos)
