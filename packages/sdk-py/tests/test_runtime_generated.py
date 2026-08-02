"""O que o modelo produz — e a guarda que impede os bytes de subirem.

O teste que mais importa aqui não prova uma funcionalidade: prova uma AUSÊNCIA.
Se `test_o_base64_NUNCA_sobrevive` cair, a conversa volta a carregar meio
megabyte por turno, e o sintoma ("o copiloto está devagar") não aponta para cá.
"""
from __future__ import annotations

from dna.runtime.generated import (
    ARTIFACT_MARK,
    GeneratedArtifact,
    extract_artifacts,
    without_bytes,
)

#: O cabeçalho de um PNG em Base64 — a assinatura que a guarda procura.
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

SAIDA_IMAGEM = [{"type": "image_generation_call", "result": PNG, "output_format": "png"}]
SAIDA_SANDBOX = [{
    "type": "message",
    "content": [{
        "type": "output_text",
        "text": "Pronto, o grafico esta salvo.",
        "annotations": [{
            "type": "container_file_citation",
            "container_id": "cntr_1", "file_id": "cfile_1", "filename": "grafico.png",
        }],
    }],
}]


def test_a_imagem_gerada_e_extraida_com_os_bytes():
    """Os bytes passam por AQUI a caminho do storage — é a exceção deliberada.
    O que não pode é eles continuarem na mensagem."""
    [a] = extract_artifacts(SAIDA_IMAGEM)
    assert a.kind == "imagem"
    assert a.data_b64 == PNG
    assert a.filename.endswith(".png")


def test_o_base64_NUNCA_sobrevive_ao_que_sobe():
    """⚠️ A guarda do checkpoint, e ela prova uma AUSÊNCIA.

    Se o Base64 subir até a AIMessage, vai para o checkpoint e é reenviado em
    TODO turno seguinte. Meio megabyte por turno, e ninguém percebe até a
    conversa ficar lenta.
    """
    limpa = without_bytes(SAIDA_IMAGEM)
    assert PNG not in repr(limpa)
    assert "iVBORw0KGgo" not in repr(limpa), "o cabeçalho PNG sobreviveu"


def test_a_limpeza_SUBSTITUI_em_vez_de_apagar():
    """Um bloco que some faria o histórico mentir sobre o que aconteceu — quem
    lesse depois não saberia que houve uma imagem."""
    [bloco] = without_bytes(SAIDA_IMAGEM)
    assert bloco["type"] == "image_generation_call"
    assert bloco["marca"] == ARTIFACT_MARK


def test_o_arquivo_do_sandbox_e_extraido_da_ANOTACAO():
    [a] = extract_artifacts(SAIDA_SANDBOX)
    assert a.kind == "sandbox"
    assert (a.container_id, a.file_id, a.filename) == ("cntr_1", "cfile_1", "grafico.png")
    assert a.data_b64 is None, "arquivo de sandbox não vem inline"


def test_texto_sem_artefato_devolve_lista_vazia():
    assert extract_artifacts([{"type": "message", "content": [{"type": "output_text", "text": "oi"}]}]) == []


def test_formato_inesperado_NAO_derruba():
    """Um provider que muda a forma da resposta não pode derrubar uma execução
    que já produziu texto útil."""
    for entrada in (None, "texto", 42, {}, [None, 1, "x"], [{"type": "message"}]):
        assert extract_artifacts(entrada) == []
        without_bytes(entrada)  # não levanta


def test_a_limpeza_preserva_o_resto_da_conversa():
    saida = SAIDA_SANDBOX + SAIDA_IMAGEM
    limpa = without_bytes(saida)
    assert len(limpa) == 2
    assert "grafico esta salvo" in repr(limpa)
    assert PNG not in repr(limpa)


def test_varias_chaves_de_bytes_sao_varridas():
    """Providers escondem Base64 em nomes diferentes (`result`, `b64_json`…).
    A varredura é por NOME, e não por tamanho: um blob de 400 bytes é tão errado
    quanto um de 400 KB — só demora mais para doer."""
    for chave in ("result", "b64_json", "image_base64", "data"):
        limpa = without_bytes([{"type": "image_generation_call", chave: PNG}])
        assert PNG not in repr(limpa), f"sobreviveu em {chave!r}"


def test_o_modulo_nao_baixa_nada():
    import pathlib

    import dna.runtime.generated as mod

    fonte = pathlib.Path(mod.__file__).read_text()
    for proibido in ("import httpx", "import requests", "urllib.request"):
        assert proibido not in fonte
