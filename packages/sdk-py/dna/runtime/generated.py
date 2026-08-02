"""O que o modelo PRODUZ — e a regra de nunca deixar os bytes subirem.

## O caminho de saída é o espelho do de entrada

======================  =====================================================
arquivo do sandbox      anotação ``container_file_citation`` no texto
imagem                  ``image_generation_call`` com **Base64 no corpo**
======================  =====================================================

## ⚠️ A REGRA, e ela é onde é mais fácil errar

O Base64 da imagem chega dentro da resposta do provider. Se ele subir até a
``AIMessage``, vai para o **checkpoint** — e é reenviado em **todo turno
seguinte**. Meio megabyte por turno, e ninguém percebe até a conversa ficar
lenta; aí o sintoma é "o copiloto está devagar", que não aponta para cá.

Por isso este módulo faz duas coisas e nessa ordem:

1. **extrai** os descritores (o que foi gerado, e como buscar), e
2. **limpa** a mensagem, trocando os bytes por uma marca legível.

O host baixa, persiste e entrega por evento. O que sobe é referência.

## O container é EFÊMERO

Um arquivo do sandbox só existe enquanto o container vive. Guardar
``container_id``/``file_id`` para buscar depois é guardar um link morto — por
isso o descritor existe para ser consumido AGORA, na mesma resposta.

## Puro

Nada aqui baixa nada. Extrair e limpar são decisões sobre uma estrutura de
dados; buscar bytes é do host, que tem o cliente e a credencial.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

__all__ = [
    "GeneratedArtifact",
    "ARTIFACT_MARK",
    "extract_artifacts",
    "without_bytes",
]

#: O que fica no lugar do Base64. Legível de propósito: quem lê o histórico
#: precisa ver que houve uma imagem, e não um buraco.
ARTIFACT_MARK = "[imagem gerada — entregue como artefato]"

#: Chaves em que os providers costumam esconder Base64. Varridas por NOME e não
#: por heurística de tamanho: um blob de 400 bytes é tão errado quanto um de
#: 400 KB, só demora mais para doer.
_BYTE_KEYS = ("result", "b64_json", "image_base64", "data")


@dataclass(frozen=True)
class GeneratedArtifact:
    """Um arquivo que o modelo produziu — o descritor, nunca os bytes.

    ``data_b64`` é a exceção deliberada e temporária: para imagem o provider
    devolve o conteúdo inline, então ele passa por aqui a caminho do storage. É
    justamente esse campo que ``without_bytes`` remove da mensagem.
    """

    kind: str  # "sandbox" | "imagem"
    filename: str
    mime: str | None = None
    container_id: str | None = None
    file_id: str | None = None
    data_b64: str | None = None


def _annotations_of(block: Any) -> Iterable[dict]:
    for a in (block.get("annotations") or []) if isinstance(block, dict) else []:
        if isinstance(a, dict):
            yield a


def extract_artifacts(output: Any) -> list[GeneratedArtifact]:
    """Os artefatos desta resposta, na ordem em que aparecem.

    ``saida`` é a lista ``output`` do provider (ou o ``content`` já normalizado
    pelo LangChain). Formato inesperado devolve lista vazia — nunca exceção: um
    provider que muda a forma da resposta não pode derrubar uma execução que já
    produziu texto útil.
    """
    if not isinstance(output, (list, tuple)):
        return []

    found: list[GeneratedArtifact] = []
    for item in output:
        if not isinstance(item, dict):
            continue

        if item.get("type") == "image_generation_call":
            b64 = next(
                (item[c] for c in _BYTE_KEYS if isinstance(item.get(c), str)),
                None,
            )
            found.append(
                GeneratedArtifact(
                    kind="imagem",
                    filename=str(item.get("output_format") and f"imagem.{item['output_format']}" or "imagem.png"),
                    mime="image/png",
                    data_b64=b64,
                )
            )
            continue

        for block in item.get("content") or []:
            for a in _annotations_of(block):
                if a.get("type") != "container_file_citation":
                    continue
                found.append(
                    GeneratedArtifact(
                        kind="sandbox",
                        filename=str(a.get("filename") or "arquivo"),
                        container_id=a.get("container_id"),
                        file_id=a.get("file_id"),
                    )
                )
    return found


def without_bytes(output: Any) -> Any:
    """A mesma saída, sem nenhum Base64 — o que pode subir para o state.

    ⚠️ Esta função é a guarda do checkpoint. O teste que a acompanha busca
    ``iVBORw0KGgo`` (o cabeçalho PNG em Base64) no resultado e exige **zero**;
    se ele cair, a conversa voltou a carregar meio megabyte por turno.

    Substitui em vez de apagar: um bloco que some faria o histórico mentir sobre
    o que aconteceu, e quem lesse depois não saberia que houve uma imagem.
    """
    if not isinstance(output, (list, tuple)):
        return output

    cleaned = []
    for item in output:
        if not isinstance(item, dict):
            cleaned.append(item)
            continue
        if item.get("type") == "image_generation_call":
            copy_ = {k: v for k, v in item.items() if k not in _BYTE_KEYS}
            copy_["marca"] = ARTIFACT_MARK
            cleaned.append(copy_)
            continue
        cleaned.append(item)
    return cleaned
