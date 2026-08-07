"""O MIME vem dos BYTES — e a divergência é informação, não erro."""
from __future__ import annotations

import io
import zipfile

from dna.runtime.mime import UNKNOWN, detect_mime, mismatch

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n" + b"conteudo do contrato\n" * 20


def _xlsx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", "<workbook/>")
    return buf.getvalue()


# ── os bytes mandam ─────────────────────────────────────────────────────────


def test_o_MIME_vem_dos_bytes_e_nao_do_nome():
    """⚠️ O caso que motiva o módulo: o roteamento DEPENDE do MIME.

    Um arquivo com nome mentiroso não daria erro — daria caminho errado, em
    silêncio, e o usuário receberia um texto truncado no lugar de um cálculo.
    """
    assert detect_mime(PNG, "contrato.pdf") == "image/png"
    assert detect_mime(PDF, "foto.png") == "application/pdf"


def test_TEXTO_nao_tem_magic_bytes_entao_a_extensao_refina():
    """A única situação em que a extensão vale — e ela vale porque já sabemos,
    pelo conteúdo, que é texto."""
    assert detect_mime(b"a,b\n1,2\n", "dados.csv") == "text/csv"
    assert detect_mime(b"# titulo\n", "nota.md") == "text/markdown"
    assert detect_mime(b"linha solta", "sem-extensao") == "text/plain"


def test_binario_desconhecido_admite_que_NAO_SABE():
    """`application/octet-stream` é honesto. Chutar `text/plain` faria o
    roteamento tentar ler bytes como texto."""
    assert detect_mime(b"\x00\x01\x02\xff" * 40, "coisa.bin") == UNKNOWN


def test_o_corte_no_MEIO_de_um_caractere_nao_vira_binario():
    """⚠️ `SNIFF_BYTES` pode cair no meio de um multibyte. Sem tolerância, um
    `.md` com acento na posição errada viraria `octet-stream` — e o arquivo
    inteiro tomaria o caminho de recusa por causa de um byte."""
    texto = ("á" * 6000).encode()  # o corte cai no meio de um par UTF-8
    assert detect_mime(texto, "nota.md") == "text/markdown"


# ── a divergência ───────────────────────────────────────────────────────────


def test_divergencia_de_FAMILIA_e_apontada():
    assert mismatch(detected="image/png", declared="application/pdf") is True
    assert mismatch(detected="application/pdf", filename="foto.png") is True


def test_octet_stream_DECLARADO_nao_conta_como_afirmacao():
    """⚠️ É o valor que um navegador manda quando não sabe. Tratá-lo como
    afirmação marcaria metade dos uploads como divergentes — e um sinal que
    dispara sempre é um sinal que ninguém olha."""
    assert mismatch(detected="application/pdf", declared="application/octet-stream") is False


def test_OOXML_detectado_como_ZIP_nao_e_divergencia():
    """Um `.docx` É um zip por dentro. Marcar isso reprovaria toda instância do
    Office, e o ruído mataria o sinal."""
    assert mismatch(
        detected="application/zip",
        declared="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="relatorio.docx",
    ) is False


def test_variacao_DENTRO_de_texto_nao_e_divergencia():
    """`text/plain` e `text/markdown` são tratados igual pelo roteamento."""
    assert mismatch(detected="text/plain", declared="text/markdown") is False
    assert mismatch(detected="application/json", declared="text/plain") is False


def test_um_xlsx_de_verdade_e_reconhecido_ou_como_zip_ou_como_xlsx():
    """Os dois são aceitáveis e nenhum é divergência — depende da versão do
    detector, e o teste afirma a PROPRIEDADE, não a implementação dele."""
    detectado = detect_mime(_xlsx(), "planilha.xlsx")
    assert mismatch(detected=detectado, filename="planilha.xlsx") is False


def test_sem_nada_declarado_nao_ha_divergencia():
    """Nenhum candidato = nada a comparar. Inventar uma divergência aqui seria
    afirmar sobre o que ninguém disse."""
    assert mismatch(detected="application/pdf") is False


# ── o que o REGISTRO precisa guardar ────────────────────────────────────────


def test_o_par_declarado_MAIS_detectado_e_a_evidencia():
    """⚠️ `SourceArtifact` guarda os DOIS, e isto documenta por quê.

    Sobrescrever `mime` com o detectado apagaria a informação de que houve
    divergência — e a divergência é a única coisa que qualquer um dos dois
    campos é capaz de dizer sozinho.

    O teste não toca no banco: ele afirma a REGRA que o registro implementa.
    """
    declarado, conteudo, nome = "application/pdf", PNG, "contrato.pdf"
    detectado = detect_mime(conteudo, nome)

    assert detectado == "image/png"
    assert declarado != detectado, "sem divergência não haveria o que registrar"
    assert mismatch(detected=detectado, declared=declarado, filename=nome) is True
