"""A metade de ESCRITA da base de conhecimento: Markdown → trechos → índice.

O que cada bloco aqui existe para provar, e por quê:

* **o NOME é gravável.** O primeiro teste é uma guarda, não um exemplo: o
  formato original — ``<collection>/<sha12>/<ordinal>`` — passou toda a metade
  de LEITURA verde e NÃO PODE SER ESCRITO, porque ``Kernel.write_instance``
  valida todo nome como um único componente de caminho e recusa ``/``. Ler não
  valida nome; foi escrever que cobrou. A guarda pergunta exatamente isso, e
  quebra se alguém trocar o separador por um que o kernel recuse.
* **o prefixo de uma coleção não alcança a vizinha.** O separador tem de estar
  FORA do alfabeto de uma coleção, senão ``handbook`` varre ``handbook-2024``.
* **o corte é do ``chonkie``, e os offsets são exatos.** Sem dublê: um teste de
  corte com dublê mede o dublê. E ``token_count`` fica nulo com o tokenizador
  de caracteres, porque um contador de caracteres reportado como tokens é um
  número que parece conferível e não é.
* **a re-ingestão não deixa órfão.** Cortar o mesmo arquivo mais grosso produz
  menos trechos; os que sobravam sairiam numa busca como texto de uma versão
  morta do documento.
* **o truncamento é DECLARADO, nunca herdado.** Sem teto por padrão; com teto
  pedido, o resultado diz quanto ficou de fora.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.application import knowledge as K
from dna.application.live import LiveDna
from dna.application.runtime import artifact_name
from dna.kernel import Kernel
from dna.kernel.errors import InvalidInstanceName, validate_instance_name

_SCOPE = "corpus"
_TENANT = "acme"
_SHA = "b" * 64
_OTHER_SHA = "c" * 64

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# ── as funções de nome (puras — nenhum kernel) ────────────────────────────────


@pytest.mark.parametrize("collection", ["handbook", "a", "0", "a-b-c", "x" * 63])
def test_chunk_name_e_um_componente_de_caminho_valido(collection: str) -> None:
    """⭐ A GUARDA que a metade de leitura não tinha.

    ``validate_instance_name`` é chamada por ``Kernel.write_instance`` e
    ``Kernel.delete_instance`` ANTES de qualquer adapter. Um nome que ela recusa
    é um trecho que não pode ser gravado nem apagado — e o formato original,
    com ``/``, era exatamente isso. Este teste pergunta a PERGUNTA ("este nome
    é gravável?"), não congela a resposta: trocar o separador por outro
    caractere legal continua passando; trocar por um que o kernel recuse
    quebra."""
    validate_instance_name(K.chunk_name(collection, _SHA, 7))


def test_o_formato_antigo_com_barra_teria_sido_recusado() -> None:
    """A guarda-sobre-a-guarda: prova que o validador de fato ACUSA o caso real.

    Sem isto, o teste acima poderia estar verde porque ``validate_instance_name``
    não valida nada (universo vazio ≠ tudo certo)."""
    antigo = f"handbook/{_SHA[:12]}/00007"
    with pytest.raises(InvalidInstanceName):
        validate_instance_name(antigo)


def test_prefixo_de_colecao_nao_alcanca_a_colecao_vizinha() -> None:
    """``handbook`` e ``handbook-2024`` são duas coleções, e o prefixo de uma
    não pode varrer a outra — a razão de o separador estar fora de
    ``COLLECTION_RE``. Com ``-`` como separador este teste quebra."""
    prefixo = K.collection_prefix("handbook")
    assert K.chunk_name("handbook", _SHA, 0).startswith(prefixo)
    assert not K.chunk_name("handbook-2024", _SHA, 0).startswith(prefixo)
    assert not K.chunk_name("handbookx", _SHA, 0).startswith(prefixo)


def test_source_prefix_isola_um_arquivo_dentro_da_colecao() -> None:
    """A poda age sob o prefixo do ARQUIVO. Se ele alcançasse outro arquivo da
    mesma coleção, re-ingerir um apagaria os trechos do outro."""
    p = K.source_prefix("handbook", _SHA)
    assert K.chunk_name("handbook", _SHA, 3).startswith(p)
    assert not K.chunk_name("handbook", _OTHER_SHA, 3).startswith(p)
    assert p.startswith(K.collection_prefix("handbook"))


def test_ordinal_ordena_lexicograficamente() -> None:
    """O zero-padding é o que faz a ordem do nome ser a ordem de leitura — sem
    ele, o trecho 10 vem antes do 9 em toda listagem ordenada por nome."""
    nomes = [K.chunk_name("h", _SHA, i) for i in (0, 2, 9, 10, 100)]
    assert sorted(nomes) == nomes


# ── o corte (puro, mas com a biblioteca de VERDADE) ───────────────────────────

_MD = """\
# Manual do time

Este é o parágrafo de abertura, e ele existe para ter tamanho suficiente para
que o cortador tenha de decidir alguma coisa em vez de devolver tudo junto.

## Férias

Férias são pedidas com trinta dias de antecedência. O pedido vai para a pessoa
gestora, que aprova ou devolve com um motivo escrito.

## Reembolso

Reembolso de despesa de viagem é pedido em até quinze dias, com nota fiscal
anexada. Sem nota fiscal não há reembolso, e não há exceção discricionária.
"""


def test_o_corte_cobre_o_texto_sem_buraco_e_sem_sobreposicao() -> None:
    """Os offsets são a metade FINA da citação (``start_char``/``end_char``). Se
    eles não recompuserem o documento, a citação aponta para um recorte que não
    existe — e uma citação que não confere é pior que nenhuma, porque parece
    verificável."""
    pedacos = K.chunk_markdown(_MD, chunk_size=200)
    assert len(pedacos) > 1
    recomposto = "".join(_MD[p["start_char"]:p["end_char"]] for p in pedacos)
    assert recomposto == _MD[pedacos[0]["start_char"]:pedacos[-1]["end_char"]]
    for p in pedacos:
        assert _MD[p["start_char"]:p["end_char"]] == p["text"]
    assert [p["start_char"] for p in pedacos] == sorted(
        p["start_char"] for p in pedacos)


def test_token_count_fica_nulo_com_o_tokenizador_de_caracteres() -> None:
    """⚠️ O ``chonkie`` devolve o número de CARACTERES em ``token_count`` quando
    o tokenizador é ``"character"``. Reportá-lo como tokens seria um número que
    parece conferível e não é."""
    for p in K.chunk_markdown(_MD, chunk_size=200):
        assert p["token_count"] is None


@pytest.mark.parametrize(
    ("nome", "texto"),
    [
        # ⚠️ O caso que quase passou calado. Frases mais CURTAS que o
        # `min_characters_per_chunk` fazem o `RecursiveChunker` desistir de
        # cortar e devolver o documento inteiro num trecho — medido: 1280
        # caracteres num teto de 200.
        ("frases curtas sem quebra de linha", "frase de teste. " * 200),
        # Um "token" único maior que o teto: não há limite natural onde cortar.
        ("uma palavra gigante", "abertura.\n\n" + "z" * 5000),
        ("uma linha base64 numa cerca", "# T\n\n```\n" + "QUJD" * 1500 + "\n```\n"),
        ("um parágrafo longo sem pontuação", "palavra " * 900),
        ("uma tabela markdown larga",
         "| a | b |\n|---|---|\n" + "| valor da celula | outro valor |\n" * 200),
    ],
)
def test_o_chunk_size_e_um_TETO_em_todo_formato(nome: str, texto: str) -> None:
    """⭐ A guarda contra a perda SILENCIOSA no embedder.

    Um trecho maior que a janela do all-MiniLM-L6-v2 é truncado por ELE, sem
    aviso: o texto e a citação ficam certos e o vetor representa só o começo.
    Nada na tela distingue isso de um trecho bem cortado, então a única defesa
    é o teto valer SEMPRE — inclusive nos formatos onde o cortador recursivo
    não acha limite natural nenhum.

    A pergunta é "o teto vale?", não "quantos trechos deram": acrescentar um
    nível de regra, ou trocar a versão do chonkie, não quebra isto."""
    teto = 200
    pedacos = K.chunk_markdown(texto, chunk_size=teto)
    assert pedacos, f"{nome}: nada foi cortado"
    maior = max(len(p["text"]) for p in pedacos)
    assert maior <= teto, f"{nome}: um trecho de {maior} caracteres passou do teto {teto}"
    for p in pedacos:
        assert texto[p["start_char"]:p["end_char"]] == p["text"], (
            f"{nome}: offset não bate — a citação apontaria para outro recorte")


def test_o_recorte_de_emergencia_nao_perde_texto() -> None:
    """O ``TokenChunker`` entra onde o recursivo desiste, e a costura entre os
    dois não pode engolir caractere: o corpus tem de conter o documento."""
    texto = "abertura curta.\n\n" + ("z" * 5000) + "\n\nfecho do documento.\n"
    pedacos = K.chunk_markdown(texto, chunk_size=300)
    assert "".join(p["text"] for p in pedacos) == texto
    assert pedacos[0]["start_char"] == 0
    assert pedacos[-1]["end_char"] == len(texto)


def test_texto_vazio_ou_so_espaco_nao_vira_trecho() -> None:
    assert K.chunk_markdown("") == []
    assert K.chunk_markdown("   \n\n \t ") == []


def test_chunk_size_invalido_e_recusado() -> None:
    with pytest.raises(ValueError):
        K.chunk_markdown(_MD, chunk_size=0)


# ── a porta (kernel de verdade, em disco) ─────────────────────────────────────


def _write_yaml(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(doc, default_flow_style=False))


@pytest.fixture()
def live(tmp_path: Path) -> LiveDna:
    base = tmp_path / ".dna"
    _write_yaml(base / _SCOPE / "Genome.yaml", {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Genome",
        "metadata": {"name": _SCOPE}, "spec": {},
    })
    (base / "_lib").mkdir(parents=True, exist_ok=True)
    k = Kernel.auto()
    k.source(FilesystemWritableSource(str(base), kernel=k))
    k.cache(FilesystemCache(str(base)))
    return LiveDna(base_scope=_SCOPE, kernel=k, provider=None,
                   vendor_workspace=None)


async def _seed_artifact(
    live: LiveDna, sha: str = _SHA, *, uri: str = "blob://uploads/manual.md",
    filename: str | None = "manual-do-time.md",
) -> None:
    """O upload que já aconteceu: o host guardou os bytes e registrou o
    ``SourceArtifact``. A ingestão parte DAQUI, nunca dos bytes."""
    spec: dict[str, Any] = {"sha256": sha, "uri": uri, "origin": "uploaded"}
    if filename is not None:
        spec["filename"] = filename
    await live.kernel.with_tenant(_TENANT).write_instance(
        _SCOPE, "SourceArtifact", artifact_name(sha),
        {"apiVersion": "github.com/ruinosus/dna/artifact/v1",
         "kind": "SourceArtifact", "metadata": {"name": artifact_name(sha)},
         "spec": spec},
    )


async def _chunks(live: LiveDna) -> list[dict[str, Any]]:
    out = []
    async for raw in live.kernel.query(_SCOPE, K.KNOWLEDGE_CHUNK_KIND, tenant=_TENANT):
        out.append(raw)
    out.sort(key=lambda r: (r.get("metadata") or {}).get("name") or "")
    return out


@pytest.mark.asyncio
async def test_ingestao_grava_trechos_citaveis(live: LiveDna) -> None:
    """O caminho inteiro: Markdown → instâncias, cada uma sabendo dizer de onde
    veio. A procedência vem do ARTEFATO, não do chamador — ele nunca passou
    ``uri`` nem ``filename``."""
    await _seed_artifact(live)
    out = await K.ingest_knowledge_impl(
        live, tenant=_TENANT, collection="manual", source_sha256=_SHA, text=_MD,
        chunk_size=200, index=False,
    )
    assert out["chunks_written"] > 1
    assert out["source_uri"] == "blob://uploads/manual.md"
    assert out["source_filename"] == "manual-do-time.md"
    assert out["truncated"] is False

    gravados = await _chunks(live)
    assert len(gravados) == out["chunks_written"]
    for ordinal, raw in enumerate(gravados):
        spec = raw["spec"]
        assert (raw["metadata"]["name"]
                == K.chunk_name("manual", _SHA, ordinal))
        assert spec["ordinal"] == ordinal
        assert spec["collection"] == "manual"
        assert spec["source_sha256"] == _SHA
        assert spec["source_uri"] == "blob://uploads/manual.md"
        assert spec["source_filename"] == "manual-do-time.md"
        assert spec["text"].strip()
        assert _MD[spec["start_char"]:spec["end_char"]] == spec["text"]
        assert spec["extracted_at"]


@pytest.mark.asyncio
async def test_o_sha_maiusculo_e_normalizado(live: LiveDna) -> None:
    """O endereço de conteúdo é hex minúsculo (o schema impõe). Um chamador que
    passe maiúsculas não deve descobrir isso como erro de schema no trecho 0."""
    await _seed_artifact(live, sha="a" * 64)
    out = await K.ingest_knowledge_impl(
        live, tenant=_TENANT, collection="manual", source_sha256="A" * 64, text=_MD,
        chunk_size=400, index=False)
    assert out["source_sha256"] == "a" * 64


@pytest.mark.asyncio
async def test_reingestao_identica_nao_duplica(live: LiveDna) -> None:
    """``chunk_name`` é determinístico: a segunda passagem reescreve as mesmas
    instâncias."""
    await _seed_artifact(live)
    primeira = await K.ingest_knowledge_impl(
        live, tenant=_TENANT, collection="manual", source_sha256=_SHA, text=_MD,
        chunk_size=200, index=False)
    segunda = await K.ingest_knowledge_impl(
        live, tenant=_TENANT, collection="manual", source_sha256=_SHA, text=_MD,
        chunk_size=200, index=False)
    assert segunda["chunk_names"] == primeira["chunk_names"]
    assert segunda["pruned"] == []
    assert len(await _chunks(live)) == primeira["chunks_written"]


@pytest.mark.asyncio
async def test_reingestao_com_corte_maior_poda_os_orfaos(live: LiveDna) -> None:
    """⭐ O caso que a determinismo do nome NÃO cobre.

    Trocar o ``chunk_size`` (ou a versão do cortador) muda a QUANTIDADE de
    trechos. Sem poda, os ordinais que sobravam continuariam no store e no
    índice — e voltariam numa busca como texto de uma versão morta do
    documento, sem nada dizendo isso."""
    await _seed_artifact(live)
    fino = await K.ingest_knowledge_impl(
        live, tenant=_TENANT, collection="manual", source_sha256=_SHA, text=_MD,
        chunk_size=120, index=False)
    grosso = await K.ingest_knowledge_impl(
        live, tenant=_TENANT, collection="manual", source_sha256=_SHA, text=_MD,
        chunk_size=100_000, index=False)

    assert grosso["chunks_written"] < fino["chunks_written"]
    assert grosso["pruned"] == sorted(
        set(fino["chunk_names"]) - set(grosso["chunk_names"]))
    restantes = {(r["metadata"] or {}).get("name") for r in await _chunks(live)}
    assert restantes == set(grosso["chunk_names"])


@pytest.mark.asyncio
async def test_a_poda_nao_toca_outro_arquivo_nem_outra_colecao(
    live: LiveDna,
) -> None:
    """A poda age sob o prefixo do ARQUIVO dentro da COLEÇÃO. Um segundo
    arquivo na mesma coleção, e o mesmo arquivo em outra coleção, ficam."""
    await _seed_artifact(live)
    await _seed_artifact(live, sha=_OTHER_SHA, uri="blob://uploads/outro.md",
                         filename="outro.md")
    vizinho = await K.ingest_knowledge_impl(
        live, tenant=_TENANT, collection="manual", source_sha256=_OTHER_SHA, text=_MD,
        chunk_size=120, index=False)
    outra = await K.ingest_knowledge_impl(
        live, tenant=_TENANT, collection="arquivo", source_sha256=_SHA, text=_MD,
        chunk_size=120, index=False)
    await K.ingest_knowledge_impl(
        live, tenant=_TENANT, collection="manual", source_sha256=_SHA, text=_MD,
        chunk_size=120, index=False)

    alvo = await K.ingest_knowledge_impl(
        live, tenant=_TENANT, collection="manual", source_sha256=_SHA, text=_MD,
        chunk_size=100_000, index=False)
    assert alvo["pruned"], "a poda deveria ter removido algo"
    restantes = {(r["metadata"] or {}).get("name") for r in await _chunks(live)}
    assert set(vizinho["chunk_names"]) <= restantes
    assert set(outra["chunk_names"]) <= restantes


@pytest.mark.asyncio
async def test_prune_desligado_deixa_o_orfao_e_o_resultado_admite(
    live: LiveDna,
) -> None:
    """``prune=False`` é reachable, e quando ligado o resultado NÃO finge que
    podou."""
    await _seed_artifact(live)
    fino = await K.ingest_knowledge_impl(
        live, tenant=_TENANT, collection="manual", source_sha256=_SHA, text=_MD,
        chunk_size=120, index=False)
    grosso = await K.ingest_knowledge_impl(
        live, tenant=_TENANT, collection="manual", source_sha256=_SHA, text=_MD,
        chunk_size=100_000, prune=False, index=False)
    assert grosso["pruned"] == []
    restantes = {(r["metadata"] or {}).get("name") for r in await _chunks(live)}
    assert set(fino["chunk_names"]) <= restantes


@pytest.mark.asyncio
async def test_sem_teto_por_padrao_a_cauda_do_documento_entra(
    live: LiveDna,
) -> None:
    """⚠️ O anexo de CONVERSA do host trunca em 200k e descarta a cauda. Uma
    base de conhecimento que herdasse isso perderia o FIM de todo documento
    longo em silêncio. O padrão aqui é SEM teto, e a prova é a última frase do
    documento estar no corpus."""
    await _seed_artifact(live)
    longo = _MD + ("\n\nparágrafo de enchimento. " * 4000) + (
        "\n\nA ÚLTIMA FRASE DO DOCUMENTO É ESTA, E ELA TEM DE ESTAR NO CORPUS.\n")
    out = await K.ingest_knowledge_impl(
        live, tenant=_TENANT, collection="manual", source_sha256=_SHA, text=longo,
        chunk_size=800, index=False)
    assert out["truncated"] is False
    assert out["chunks_dropped"] == 0
    corpus = "".join(r["spec"]["text"] for r in await _chunks(live))
    assert "A ÚLTIMA FRASE DO DOCUMENTO É ESTA" in corpus


@pytest.mark.asyncio
async def test_teto_pedido_e_REPORTADO_nunca_calado(live: LiveDna) -> None:
    """Um chamador pode pedir teto. O que ele não pode é não saber que cortou —
    o resultado carrega quantos trechos e quantos caracteres ficaram fora."""
    await _seed_artifact(live)
    out = await K.ingest_knowledge_impl(
        live, tenant=_TENANT, collection="manual", source_sha256=_SHA, text=_MD,
        chunk_size=120, max_chunks=2, index=False)
    assert out["chunks_written"] == 2
    assert out["truncated"] is True
    assert out["chunks_dropped"] > 0
    assert out["chars_dropped"] > 0


# ── as recusas ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recusa_artefato_nao_registrado(live: LiveDna) -> None:
    """A citação de um trecho tem de apontar para um original que existe. Sem o
    ``SourceArtifact``, a ingestão para ANTES de escrever qualquer coisa."""
    with pytest.raises(ValueError, match="SourceArtifact"):
        await K.ingest_knowledge_impl(
            live, tenant=_TENANT, collection="manual", source_sha256=_SHA, text=_MD)
    assert await _chunks(live) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("ruim", ["Manual", "com espaço", "", "-abre-com-hifen",
                                  "x" * 64, "com/barra", "com.ponto"])
async def test_recusa_nome_de_colecao_fora_do_alfabeto(
    live: LiveDna, ruim: str,
) -> None:
    """O nome da coleção ABRE o nome de cada trecho — ele é identidade. Um
    caractere fora do alfabeto faria o prefixo de uma coleção alcançar outra."""
    await _seed_artifact(live)
    with pytest.raises(ValueError, match="collection"):
        await K.ingest_knowledge_impl(
            live, tenant=_TENANT, collection=ruim, source_sha256=_SHA, text=_MD)


@pytest.mark.asyncio
@pytest.mark.parametrize("ruim", ["", "abc", "z" * 64, _SHA.upper() + "0"])
async def test_recusa_sha_que_nao_e_endereco_de_conteudo(
    live: LiveDna, ruim: str,
) -> None:
    with pytest.raises(ValueError, match="source_sha256"):
        await K.ingest_knowledge_impl(
            live, tenant=_TENANT, collection="manual", source_sha256=ruim, text=_MD)


@pytest.mark.asyncio
async def test_recusa_bytes_com_a_fronteira_na_mensagem(live: LiveDna) -> None:
    """Bytes não entram nesta porta, e a recusa DIZ onde eles param — senão o
    próximo leitor tenta de novo."""
    await _seed_artifact(live)
    with pytest.raises(TypeError, match="Markdown"):
        await K.ingest_knowledge_impl(
            live, tenant=_TENANT, collection="manual", source_sha256=_SHA,
            text=b"%PDF-1.4",  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_artefato_sem_filename_nao_inventa_um(live: LiveDna) -> None:
    """Um campo ausente fica AUSENTE — nunca ``"desconhecido"``, que leria como
    um nome de arquivo.

    E ele fica ausente da CHAVE, não nulo no valor: o caminho de escrita lê um
    ``None`` explícito como "limpe este campo" (``_merged_spec``), então a
    chave nem chega ao YAML. É o mesmo contrato que ``_citation`` já assume do
    lado da leitura — ela projeta só o que o spec carrega."""
    await _seed_artifact(live, filename=None)
    out = await K.ingest_knowledge_impl(
        live, tenant=_TENANT, collection="manual", source_sha256=_SHA, text=_MD,
        chunk_size=400, index=False)
    assert out["source_filename"] is None
    for raw in await _chunks(live):
        assert raw["spec"].get("source_filename") is None
        assert K._citation(raw["spec"]).get("filename") is None
        # e a procedência que EXISTE continua lá — senão este teste passaria
        # com um spec vazio.
        assert K._citation(raw["spec"])["uri"] == "blob://uploads/manual.md"
