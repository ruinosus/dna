"""A2AExtension — o Agent Card do A2A como documento.

Registra um Kind de record, ``RemoteAgent``, a partir de um descritor.

O A2A (Agent2Agent, governado pela Linux Foundation) padronizou exatamente a
coisa que o DNA já trata como documento: um descritor auto-descritivo de
capacidade. Então falar A2A não pede modelo novo — pede um Kind para o Card que
chega, e uma projeção para o Card que sai (``dna.emit.agent_card``).

Vendor-neutro de propósito: "existe um agente ali, ele sabe estas coisas, e pode
receber estes dados" é fato sobre capacidade e permissão, não sobre hospedagem.
O Kind mora aqui, no SDK OSS; qual face serve o Card de saída, e onde a
credencial de cada remoto é guardada, são decisões do deployment.
"""
from __future__ import annotations

from dna.kernel.source.descriptor_loader import load_descriptors
from dna.kernel.protocols import ExtensionHost


class A2AExtension:
    """Registra ``RemoteAgent`` (descriptor-backed)."""

    name = "a2a"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        for raw in load_descriptors("dna.extensions.a2a"):
            kernel.kind_from_descriptor(raw)
