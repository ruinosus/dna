"""A cadeia de release — a versão que o `dna-cli` PUBLICA tem de casar com a dele.

O `dna-cli` declara `dna-sdk>=X,<Y` para quem instala do PyPI. Neste repo o
`[tool.uv.sources]` substitui isso pelo caminho editável, então **a divergência
é invisível em desenvolvimento**: tudo passa, e o artefato publicado instala o
SDK errado.

Foi por um triz em 31/07/2026: o bump para `0.41.0` teria publicado um
`dna-cli` 0.41.0 exigindo `dna-sdk>=0.40,<0.41` — ou seja, o cli novo puxaria o
SDK **anterior**, sem a face A2A. O usuário instalaria a versão que anuncia a
feature e receberia a que não a tem, com uma mensagem de erro que aponta para o
lugar errado.

Este teste é aritmética, não opinião: a faixa declarada precisa CONTER a própria
versão do cli.
"""
from __future__ import annotations

import pathlib
import tomllib

_RAIZ = pathlib.Path(__file__).resolve().parents[3]


def _manifesto(rel: str) -> dict:
    return tomllib.loads((_RAIZ / rel).read_text(encoding="utf-8"))


def _faixa_do_sdk() -> str:
    deps = _manifesto("packages/cli/pyproject.toml")["project"]["dependencies"]
    achados = [d for d in deps if d.replace(" ", "").startswith("dna-sdk")]
    assert len(achados) == 1, f"esperava UMA declaração de dna-sdk, achei {achados}"
    return achados[0].replace(" ", "")


def _versao(rel: str) -> tuple[int, ...]:
    bruto = _manifesto(rel)["project"]["version"]
    return tuple(int(p) for p in bruto.split(".")[:3])


def test_a_faixa_de_dna_sdk_que_o_cli_publica_contem_a_versao_do_cli():
    faixa = _faixa_do_sdk()
    piso_txt = faixa.split(">=")[1].split(",")[0]
    teto_txt = faixa.split("<")[-1]
    piso = tuple(int(p) for p in piso_txt.split("."))
    teto = tuple(int(p) for p in teto_txt.split("."))
    versao = _versao("packages/cli/pyproject.toml")

    # Compara por (major, minor) — a faixa é pré-1.0 e anda de minor em minor.
    assert piso[:2] <= versao[:2] < teto[:2], (
        f"o dna-cli {'.'.join(map(str, versao))} declara `{faixa}`: a faixa NÃO "
        f"contém a própria versão. Publicado assim, o cli novo instala um "
        f"dna-sdk ANTIGO, e a feature que a versão anuncia não existe no que o "
        f"usuário recebe."
    )


def test_os_dois_pacotes_publicados_sobem_juntos():
    """`sanity` no workflow de release já falha se os manifests divergirem da
    TAG. Isto falha antes, e por outro motivo: os dois têm de estar na mesma
    versão entre si, o que é o que torna a faixa acima verificável."""
    assert _versao("packages/cli/pyproject.toml") == _versao(
        "packages/sdk-py/pyproject.toml"
    ), "dna-cli e dna-sdk saíram de sincronia — a faixa publicada deixa de fazer sentido"
