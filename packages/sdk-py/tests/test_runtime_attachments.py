"""O roteamento de anexo — e a regra que ele existe para impor.

Quase todo teste aqui é sobre a planilha, e é de propósito: ela é o único caso em
que o caminho ERRADO funciona, responde rápido, e mente.
"""
from __future__ import annotations

import pytest

from dna.runtime.attachments import (
    Estrategia,
    bloco_nativo,
    estrategia_para,
    ferramenta_sandbox,
    motivo_da_recusa,
)

CSV = "text/csv"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.mark.parametrize("mime", [CSV, XLSX, "text/tab-separated-values", "application/vnd.ms-excel"])
def test_TABULAR_vai_para_o_SANDBOX_sempre(mime):
    """⚠️ A regra que carrega o módulo.

    O provider ACEITA um CSV dentro da mensagem — e trunca em 1.000 linhas sem
    avisar. MEDIDO em 02/08 com 50.000 linhas: resposta `1000` e 12.056 tokens
    pelo caminho errado; `50000` e 854 tokens pelo sandbox.

    Não é preferência de custo: é que a resposta sai errada e nada acusa.
    """
    assert estrategia_para(mime) is Estrategia.SANDBOX


@pytest.mark.parametrize("mime", ["application/pdf", "text/plain", "text/markdown",
                                  "application/json", "text/html",
                                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document"])
def test_documento_vai_NATIVO(mime):
    assert estrategia_para(mime) is Estrategia.NATIVO


@pytest.mark.parametrize("mime", ["image/png", "image/jpeg", "image/gif", "image/webp"])
def test_imagem_vai_como_IMAGEM(mime):
    assert estrategia_para(mime) is Estrategia.IMAGEM


def test_o_charset_no_mime_nao_muda_a_rota():
    """`text/csv; charset=utf-8` é o que um navegador manda. Uma comparação
    ingênua o classificaria como desconhecido — e desconhecido cai em recusado,
    então a planilha seria RECUSADA em vez de roteada."""
    assert estrategia_para("text/csv; charset=utf-8") is Estrategia.SANDBOX
    assert estrategia_para("TEXT/CSV") is Estrategia.SANDBOX


@pytest.mark.parametrize("mime", ["application/zip", "audio/mpeg", "video/mp4",
                                  "application/octet-stream", "", None])
def test_o_desconhecido_e_RECUSADO_e_nao_tentado_como_texto(mime):
    """Sem caso default otimista.

    "Tenta como texto" transformaria um binário qualquer num preview truncado —
    exatamente o modo de falha que este módulo fecha.
    """
    assert estrategia_para(mime) is Estrategia.RECUSADO


def test_a_recusa_diz_o_QUE_FALTA_e_nao_apenas_que_nao_da():
    """"Não suportado" manda o usuário adivinhar. O motivo nomeado diz o que
    fazer — ou ao menos por que não dá."""
    assert "compactado" in motivo_da_recusa("application/zip")
    assert "transcrição" in motivo_da_recusa("audio/wav")
    assert "quadros" in motivo_da_recusa("video/quicktime")
    # Desconhecido ainda ganha uma frase, e ela NOMEIA o formato.
    assert "application/octet-stream" in motivo_da_recusa("application/octet-stream")


def test_o_bloco_nativo_usa_o_formato_do_LANGCHAIN():
    """⚠️ Não o `input_file` cru da OpenAI.

    Os dois funcionam (medido: ambos devolveram o segredo plantado), e o do
    LangChain é o que ele traduz por provedor. O DNA emite para sete runtimes —
    um bloco cru amarraria a projeção a um deles, e o custo apareceria no dia em
    que alguém trocasse o modelo.
    """
    b = bloco_nativo(base64_data="QUJD", mime="application/pdf", filename="c.pdf")
    assert b["type"] == "file"
    assert b["source_type"] == "base64"
    assert b["mime_type"] == "application/pdf"
    assert b["filename"] == "c.pdf"
    assert "input_file" not in b.values()


def test_a_ferramenta_de_sandbox_monta_os_arquivos_no_container():
    t = ferramenta_sandbox(["file-a", "file-b"])
    assert t["type"] == "code_interpreter"
    assert t["container"]["type"] == "auto"
    assert t["container"]["file_ids"] == ["file-a", "file-b"]


def test_o_modulo_nao_faz_I_O():
    """A decisão é exercitável sem rede — a mesma fronteira de `agent_grant`.

    Uma regra que precisa de cliente HTTP para ser testada é uma regra cujos
    casos difíceis ninguém roda.
    """
    import pathlib

    import dna.runtime.attachments as mod

    fonte = pathlib.Path(mod.__file__).read_text()
    for proibido in ("import httpx", "import requests", "urllib.request", "openai"):
        assert proibido not in fonte, f"o roteamento passou a fazer I/O: {proibido}"


# ── a extensão, que a Files API valida ─────────────────────────────────────


def test_a_extensao_do_XLSX_NAO_sai_de_recortar_o_mime():
    """⚠️ O defeito medido em 02/08, e ele falha só no formato que mais importa.

    `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, cortado,
    vira `vnd.openxmlf` — e a Files API responde `Invalid extension openxmlf`.

    O sintoma é o pior tipo: o upload falha em silêncio, o sandbox fica vazio, e
    o modelo PEDE o arquivo que ele acabou de ver anunciado na mensagem. O
    usuário vê um agente confuso, não um erro.
    """
    from dna.runtime.attachments import extensao_para

    assert extensao_para(XLSX) == ".xlsx"
    assert extensao_para(XLSX) != f".{XLSX.split('/')[-1][:12]}"


@pytest.mark.parametrize("mime,ext", [
    (CSV, ".csv"), ("application/pdf", ".pdf"),
    ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    ("application/vnd.ms-excel", ".xls"), ("image/jpeg", ".jpg"),
])
def test_a_extensao_vem_do_MAPA(mime, ext):
    from dna.runtime.attachments import extensao_para

    assert extensao_para(mime) == ext


def test_mime_desconhecido_degrada_para_txt():
    """O provider trata fluxo desconhecido como texto — degradação segura. O que
    NÃO é seguro é inventar sufixo."""
    from dna.runtime.attachments import extensao_para

    assert extensao_para("x/inexistente") == ".txt"
    assert extensao_para("") == ".txt"


def test_TODO_formato_roteavel_tem_extensao():
    """Guarda contra a lacuna: um MIME que o roteador aceita e o mapa não conhece
    subiria como `.txt` e a Files API o recusaria — o mesmo defeito com outra
    roupa."""
    from dna.runtime.attachments import (
        EXTENSAO_POR_MIME,
        Estrategia,
        estrategia_para,
    )

    for mime in EXTENSAO_POR_MIME:
        assert estrategia_para(mime) is not Estrategia.RECUSADO
