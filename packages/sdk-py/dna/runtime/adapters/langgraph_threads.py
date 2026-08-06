"""``LangGraphTranscriptStore`` — a metade de LEITURA da
:mod:`dna.runtime.thread_store` sobre o checkpoint do LangGraph.

Uma **projeção**, não um armazenamento. O grafo já grava tudo o que uma conversa
tem: o snapshot de state guarda as mensagens, e o mecanismo de checkpoint guarda
o run. Este adapter não escreve NADA — ele lê o snapshot (``aget_state``) e o
converte com o **conversor oficial do bridge AG-UI do LangGraph**
(``ag_ui_langgraph.utils.langchain_messages_to_agui``), que é exatamente o mesmo
que o caminho de streaming usa para produzir o snapshot de mensagens.

## Por que o conversor oficial, e não um nosso

Porque conformidade é o produto. Um conversor à mão herda a nossa leitura da
spec, e a divergência só aparece quando um cliente externo real conversa — o
pior momento possível para descobrir. O mesmo conversor no streaming e na
releitura também é o que garante que reabrir uma conversa mostre o que o usuário
viu ao vivo, byte a byte.

## O que fica de fora, de propósito

* **``state`` só por allowlist.** O state de um grafo carrega chaves internas do
  framework que não são contrato de ninguém. Sem ``state_keys``, a projeção
  devolve ``{}``.
* **Posse.** O checkpoint é chaveado só por ``thread_id`` — ele não sabe de quem
  é a conversa, e por isso este adapter cumpre :class:`~dna.runtime.thread_store.
  ThreadTranscriptPort`, não a porta inteira. Quem lê tem de checar
  :func:`~dna.runtime.thread_store.can_read_thread` contra o índice ANTES de
  chamar aqui; esta classe devolve o que o checkpoint tem, sem opinião.
* **Escrita.** Não há ``import_transcript``: importar significaria fabricar
  checkpoints, e é aí que a dupla escrita entraria pela porta dos fundos.

## E o APAGAR mora numa classe à parte

:class:`LangGraphTranscriptPurge` cumpre a metade de expurgo
(:class:`~dna.runtime.thread_store.TranscriptPurgePort`), e é uma classe
separada de propósito: a projeção acima promete não escrever nada, e uma
promessa dessas não sobrevive a um método que apaga. Quem só lê nunca recebe o
apagador.

Ela também não escreve DELETE nenhum — delega ao ``adelete_thread`` do
checkpointer, o apagador **oficial** do framework (parte do contrato
``BaseCheckpointSaver``, implementado por cada backend de checkpoint). A regra
da casa vale para o apagar como vale para o ler: existindo a implementação
oficial, ela é obrigatória — e ela sabe de tabelas (blobs, writes) que uma
varredura nossa esqueceria.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from dna.runtime.thread_store import Transcript, TranscriptExport


def _dump(message: Any) -> Mapping[str, Any]:
    """Uma mensagem AG-UI em forma JSON. O conversor oficial devolve modelos
    tipados; a fronteira da porta é dict — ``by_alias`` porque os nomes do
    protocolo (``toolCallId``…) são os aliases, e ``exclude_none`` porque um
    campo ausente é ausente, não ``null``."""
    dump = getattr(message, "model_dump", None)
    if callable(dump):
        return dump(by_alias=True, exclude_none=True)
    return message if isinstance(message, Mapping) else {"content": str(message)}


class LangGraphTranscriptStore:
    """Lê conversas de um grafo LangGraph compilado (o mesmo objeto que serve o
    ``/agui``). ``state_keys`` é a allowlist PADRÃO de state — o chamador pode
    estreitar/ampliar por chamada, o que é o que um host cujas surfaces são
    declarativas precisa (a allowlist muda por workspace)."""

    source = "langchain"

    def __init__(self, graph: Any, *, state_keys: Sequence[str] = ()) -> None:
        self._graph = graph
        self._state_keys = tuple(state_keys)

    async def _snapshot(self, thread_id: str) -> Any:
        return await self._graph.aget_state({"configurable": {"thread_id": thread_id}})

    async def fetch_transcript(
        self, thread_id: str, *, state_keys: Sequence[str] | None = None
    ) -> Transcript:
        # Import tardio: construir este handle nunca deve exigir que o pacote do
        # bridge esteja importável (a mesma disciplina do `attach` do adapter).
        from ag_ui_langgraph.utils import langchain_messages_to_agui

        snapshot = await self._snapshot(thread_id)
        values = (getattr(snapshot, "values", None) or {}) if snapshot else {}
        messages = tuple(
            _dump(m) for m in langchain_messages_to_agui(list(values.get("messages") or []))
        )
        allowed = tuple(self._state_keys if state_keys is None else state_keys)
        state = {k: values[k] for k in allowed if values.get(k)}
        # `next` não-vazio = o grafo parou no meio (tipicamente um interrupt
        # esperando um humano). O transcript continua válido; quem exporta é que
        # precisa saber que existe um run que não atravessa.
        pending = bool(getattr(snapshot, "next", None)) if snapshot else False
        return Transcript(
            thread_id=thread_id, messages=messages, state=state, pending=pending
        )

    async def export_transcript(
        self, thread_id: str, *, state_keys: Sequence[str] | None = None
    ) -> TranscriptExport:
        transcript = await self.fetch_transcript(thread_id, state_keys=state_keys)
        return TranscriptExport(
            thread_id=thread_id,
            messages=transcript.messages,
            state=transcript.state,
            source=self.source,
            exported_at=datetime.now(timezone.utc).isoformat(),
            # A promessa honesta: o histórico visível atravessa; o run pendente
            # fica. Nenhum formato de transcript reconstrói uma aprovação em
            # curso — e dizer isso por thread é melhor do que uma nota de rodapé.
            pending_state_dropped=transcript.pending,
        )


class LangGraphTranscriptPurge:
    """Apaga o que o LangGraph guarda de um thread, pelo caminho oficial.

    Aceita o grafo compilado (de onde tira o ``checkpointer``) ou o checkpointer
    direto — quem varre num job normalmente tem o segundo, sem grafo montado.

    Sem checkpointer não há o que apagar, e isso é um caso NORMAL (um copiloto
    em memória), não um erro: a chamada vira no-op. Recusar ali transformaria
    "este copiloto não persiste" numa exceção no meio de uma varredura.
    """

    def __init__(self, graph_or_checkpointer: Any) -> None:
        self._alvo = graph_or_checkpointer

    def _checkpointer(self) -> Any:
        alvo = self._alvo
        # Um grafo compilado expõe `.checkpointer`; um checkpointer expõe
        # `adelete_thread`. Perguntar pelo MÉTODO (e não pelo tipo) é o que
        # deixa um backend de terceiro servir sem herdar nada nosso.
        if hasattr(alvo, "adelete_thread"):
            return alvo
        return getattr(alvo, "checkpointer", None)

    async def delete_transcript(self, thread_id: str) -> None:
        checkpointer = self._checkpointer()
        apagar = getattr(checkpointer, "adelete_thread", None)
        if apagar is None:
            return
        await apagar(thread_id)


__all__ = ["LangGraphTranscriptStore", "LangGraphTranscriptPurge"]
