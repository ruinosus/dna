"""Saída grande de tool sai do contexto — e vira arquivo com prévia.

## O defeito, medido três vezes neste produto

Uma tool que devolve muito texto deixa esse texto no estado da conversa **para
sempre**, reenviado a cada turno seguinte. É exatamente o defeito do base64 de
anexo (fechado em 02/08) e o do Base64 de imagem gerada (fechado no mesmo dia),
com outra roupa: agora é JSON.

Medido no mesmo dia: a saída de `analyze_spreadsheet` chega a milhares de
caracteres. Ela não quebra nada — só torna cada turno seguinte mais caro, sem
nada na tela indicando isso.

## A forma: cabeça + cauda, com o endereço

O corte guarda **o começo e o fim**, não só o começo. Numa saída estruturada o
fim costuma carregar o total, a conclusão ou o erro — cortar só a cauda joga
fora justamente o que responde a pergunta.

E o corte é **anunciado**, com o endereço de onde ler o resto. Um corte
silencioso faria o modelo concluir a partir de um recorte acreditando ser o
todo — que é o mesmo modo de falha da planilha truncada em 1.000 linhas, e o
motivo de este produto ter começado a olhar para isto.

## ⚠️ NÃO é compressão, é endereçamento

A alternativa tentadora é resumir com um LLM. Ela custa uma chamada por saída
grande, e o resumo pode estar errado sem ninguém saber. Guardar o original e
mostrar uma janela custa uma escrita e não interpreta nada.

## Puro, com o armazenamento injetado

`store` é do host — é ele que tem o blob, a credencial e o workspace. Sem ele o
middleware **corta mesmo assim** e diz que cortou, sem endereço. Um deployment
sem storage prefere uma janela honesta a um contexto que cresce sem fim.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

_LOGGER = logging.getLogger("dna.runtime.offload")

__all__ = [
    "HEAD_CHARS",
    "TAIL_CHARS",
    "THRESHOLD",
    "DnaToolOffloadMiddleware",
    "preview",
]

#: Acima disto a saída é descarregada. Abaixo, ela passa intacta — a maioria das
#: tools devolve pouco, e mexer nelas seria custo sem ganho.
THRESHOLD = 4000

#: Quanto do começo e do fim sobrevivem. A cauda existe porque numa saída
#: estruturada o fim costuma carregar o total, a conclusão ou o erro.
HEAD_CHARS = 1500
TAIL_CHARS = 500


def preview(text: str, *, address: str | None = None) -> str:
    """A janela que substitui a saída, com o corte ANUNCIADO.

    Sem `address`, ainda corta e ainda avisa — mas diz que não há onde ler o
    resto. É pior que ter endereço e melhor que crescer sem fim ou que cortar em
    silêncio.
    """
    if len(text) <= THRESHOLD:
        return text

    omitidos = len(text) - HEAD_CHARS - TAIL_CHARS
    onde = (
        f"leia o conteúdo completo em {address}"
        if address
        else "o conteúdo completo NÃO foi guardado neste ambiente"
    )
    return (
        text[:HEAD_CHARS]
        + f"\n\n[…{omitidos} caracteres omitidos por dna.runtime.offload — {onde}. "
        f"NÃO conclua a partir deste recorte sem antes buscar o resto se a "
        f"resposta depender do que foi omitido.]\n\n"
        + text[-TAIL_CHARS:]
    )


def _middleware_base():
    from langchain.agents.middleware import AgentMiddleware

    return AgentMiddleware


class DnaToolOffloadMiddleware(_middleware_base()):  # type: ignore[misc]
    """Troca saída grande de tool por uma janela com endereço.

    ``store`` é ``async (text: str, tool: str) -> str | None`` e devolve o
    ENDEREÇO onde o conteúdo ficou. Do host, porque só ele tem storage.
    """

    def __init__(
        self,
        store: Callable[..., Awaitable[str | None]] | None = None,
        *,
        threshold: int = THRESHOLD,
    ) -> None:
        super().__init__()
        self._store = store
        self._threshold = threshold

    async def aafter_model(self, state, runtime=None):  # noqa: D102
        return None

    async def awrap_tool_call(self, request, handler):
        """⚠️ Envolve a EXECUÇÃO da tool, não a mensagem depois.

        Interceptar mais tarde significaria que a saída inteira já entrou no
        estado — e o estado é justamente o que este middleware existe para
        proteger.
        """
        resultado = await handler(request)
        conteudo = getattr(resultado, "content", None)
        if not isinstance(conteudo, str) or len(conteudo) <= self._threshold:
            return resultado

        nome = getattr(getattr(request, "tool_call", None), "get", lambda _k: None)("name")
        endereco = await self._guardar(conteudo, nome or "tool")
        copiar = getattr(resultado, "model_copy", None)
        janela = preview(conteudo, address=endereco)
        return copiar(update={"content": janela}) if copiar else resultado

    async def _guardar(self, conteudo: str, nome: str) -> str | None:
        if self._store is None:
            return None
        try:
            return await self._store(conteudo, nome)
        except Exception:  # noqa: BLE001 — falhar em guardar não pode custar o turno
            _LOGGER.warning("descarga de saída de tool falhou", exc_info=True)
            return None
