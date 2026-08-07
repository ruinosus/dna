"""O agente gerado passa a saber de onde veio — `Copilot.created_by`.

`Spec/spec-a-fabrica` + `Story/s-procedencia-do-agente` (07/08/2026).

A story abriu com uma tabela: o código gerado guarda a procedência
(`Solution.services[].answers` verbatim, `services[].name → App` imposta,
`template.ref`) e o agente gerado não guardava nada. A medição que a decidiu
mora no descritor (`copilot.kind.yaml`), e o resumo é: a derivação inversa do
dna-cloud reconstrói o que SOBREVIVEU à materialização, não o que a pessoa
respondeu — cinco respostas medidas se perdem atrás de duas condições. A metade
ANSWERS já está entregue lá (i-137, o `CopilotBlueprint` persistido); a metade
que faltava, e que este arquivo prova, é a LIGAÇÃO.

Tudo aqui atravessa a porta: o kernel grava e relê, o produtor de arestas
desenha, e a travessia responde a profundidade. Nada é lido do YAML a não ser as
duas asserções que são SOBRE a declaração.
"""
from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio

from dna.kernel import Kernel
from tests import _graph_store

SCOPE = "fabrica"
_API = "github.com/ruinosus/dna/v1"


def _copilot(name: str, **spec: Any) -> dict[str, Any]:
    base = {
        "mounts": [{"id": "principal", "agent": f"{name}-agent", "path": "/agui"}],
        "serving": {"transport": "ag-ui"},
    }
    base.update(spec)
    return {
        "apiVersion": _API, "kind": "Copilot",
        "metadata": {"name": name}, "spec": base,
    }


def _helix_descriptor(name: str) -> dict:
    from dna.kernel.source.descriptor_loader import load_descriptors

    raws = load_descriptors("dna.extensions.helix")
    return next(r for r in raws if r["metadata"]["name"] == name)


# ── A DECLARAÇÃO ─────────────────────────────────────────────────────────────


def test_created_by_e_relacao_declarada_reflexiva_e_de_cardinalidade_one():
    """O alvo é o PRÓPRIO Kind, e isso é o desenho, não um descuido.

    `spec-a-fabrica` mediu o laço: o `copiloto-criador` é um `Copilot` cujo
    trabalho é produzir `Copilot`s. Uma relação reflexiva é a forma exata desse
    fato, e é ela que faz a profundidade da cadeia ser uma travessia em vez de
    um mecanismo novo.
    """
    copilot = _helix_descriptor("copilot")
    assert copilot["spec"]["relations"]["created_by"] == {
        "to": "Copilot", "cardinality": "one",
    }


def test_created_by_e_RESOLVIDA_E_IMPOSTA_e_nao_carrega_o_proprio_kind():
    """A asserção que separa esta relação da que foi RECUSADA.

    A primeira tentativa apontava para o `CopilotBlueprint` (Kind do dna-cloud)
    e, na falta dele, para `to: '*'` com `by: "Kind/name"` — a forma composta.
    Ela é ACEITA pelo normalizador e não serve: `carries_kind` implica
    `resolved: False`, ou seja NENHUMA aresta, e o contador de arestas ficaria
    exatamente onde a spec o encontrou. Esta asserção falha no dia em que
    alguém "arrumar" a relação de volta para lá.
    """
    from dna.kernel.kinds.relations import normalize_relations

    rel = normalize_relations(
        _helix_descriptor("copilot")["spec"]["relations"]
    )["created_by"]
    assert rel.resolved is True
    assert rel.enforced is True
    assert rel.carries_kind is False
    assert rel.by_name is True


def test_a_declaracao_nao_contradiz_o_schema():
    """Uma relação que nomeia um campo que o schema não declara não tem onde
    morar — e sob `additionalProperties: false` nunca poderia ser escrita.
    O modo de falhar sem esta guarda é o pior: lint verde, relação declarada,
    resolvendo `[]` para sempre."""
    from dna.kernel.kinds.relations import normalize_relations, schema_contradictions

    spec = _helix_descriptor("copilot")["spec"]
    assert schema_contradictions(
        normalize_relations(spec["relations"]), spec["schema"]
    ) == []


def test_created_by_nao_e_obrigatorio():
    """Obrigatório invalidaria no dia da migração os 7 copilotos vivos medidos
    em 07/08/2026 — que nasceram antes do campo existir."""
    spec = _helix_descriptor("copilot")["spec"]
    assert "created_by" not in spec["schema"].get("required", [])
    assert "created_by" in spec["schema"]["properties"]


# ── O ROUND-TRIP PELA PORTA ──────────────────────────────────────────────────


@pytest.fixture()
def kernel(tmp_path):
    from dna.adapters.filesystem import FilesystemCache
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.extensions.helix import HelixExtension

    (tmp_path / SCOPE).mkdir()
    k = Kernel()
    k.load(HelixExtension())
    k.source(FilesystemWritableSource(tmp_path, kernel=k))
    k.cache(FilesystemCache(tmp_path / ".dna-cache"))
    yield k


@pytest.mark.asyncio
async def test_grava_e_rele_a_procedencia(kernel):
    """`additionalProperties: false` no schema do Copilot torna este round-trip
    uma medição: com o campo ausente do descritor a escrita seria RECUSADA e
    não haveria o que reler."""
    await kernel.write_instance(SCOPE, "Copilot", "copiloto-criador",
                                _copilot("copiloto-criador"))
    await kernel.write_instance(
        SCOPE, "Copilot", "escrita-de-livro",
        _copilot("escrita-de-livro", created_by="copiloto-criador"),
    )
    lido = (await kernel.get_instance(SCOPE, "Copilot", "escrita-de-livro"))["spec"]
    assert lido["created_by"] == "copiloto-criador"


@pytest.mark.asyncio
async def test_copiloto_sem_procedencia_continua_valido_e_a_chave_nao_e_fabricada(
    kernel,
):
    """A AUSÊNCIA volta ausente. Um default aqui — `""`, o nome do próprio
    copiloto, qualquer coisa — seria a fabricação de passado que a i-137 já
    tinha recusado ao não dar blueprint retroativo aos sete."""
    await kernel.write_instance(SCOPE, "Copilot", "a-mao", _copilot("a-mao"))
    lido = (await kernel.get_instance(SCOPE, "Copilot", "a-mao"))["spec"]
    assert "created_by" not in lido


# ── A ARESTA, E A PROFUNDIDADE DA CADEIA ─────────────────────────────────────


@pytest_asyncio.fixture(params=_graph_store.DIALECTS)
async def store(request):
    src, cleanup = await _graph_store.build_store(request.param, "fabrica")
    k = Kernel.auto()
    k.source(src)
    try:
        yield k
    finally:
        await cleanup()


async def _cadeia(kernel) -> None:
    """Um copiloto que criou outro que criou outro — a pergunta da story,
    escrita como dado."""
    await kernel.write_instance(SCOPE, "Copilot", "avo", _copilot("avo"))
    await kernel.write_instance(
        SCOPE, "Copilot", "pai", _copilot("pai", created_by="avo"),
    )
    await kernel.write_instance(
        SCOPE, "Copilot", "neto", _copilot("neto", created_by="pai"),
    )


@pytest.mark.anyio
async def test_a_aresta_sai_do_copilot_onde_havia_ZERO(store):
    """A linha da tabela que faltava. Antes desta relação, `direction=out` a
    partir de um `Copilot` não podia devolver nada — não havia declaração de
    saída que o produtor pudesse ler."""
    await _cadeia(store)
    r = await store.graph_refs(SCOPE, "Copilot", "neto", direction="out")
    assert [(e["source_field"], e["to_kind"], e["to_name"]) for e in r.edges] == [
        ("created_by", "Copilot", "pai"),
    ]


@pytest.mark.anyio
async def test_a_profundidade_da_cadeia_e_uma_TRAVESSIA_nao_um_mecanismo_novo(store):
    """AC 4, respondida sem código novo: `--depth` já caminhava, faltava a
    aresta para caminhar."""
    await _cadeia(store)
    r = await store.graph_refs(SCOPE, "Copilot", "neto", direction="out", depth=3)
    assert {(e["to_name"], e["depth"]) for e in r.edges} == {("pai", 1), ("avo", 2)}


@pytest.mark.anyio
async def test_a_metade_inversa_e_de_graca_e_por_isso_nao_ha_inverse_of(store):
    """"O que este copiloto criou?" sem um campo `creates[]` no criador — que,
    se existisse, obrigaria a reescrever o `copiloto-criador` a cada copiloto
    produzido."""
    await _cadeia(store)
    r = await store.graph_refs(SCOPE, "Copilot", "avo", direction="in", depth=2)
    assert {(e["from_name"], e["depth"]) for e in r.edges} == {("pai", 1), ("neto", 2)}


@pytest.mark.anyio
async def test_procedencia_para_um_criador_inexistente_e_uma_aresta_PENDURADA(store):
    """Reportada, e distinguível — nunca uma aresta ausente.

    "ninguém declarou" e "declarou um nome que não existe" têm donos
    diferentes, e é a mesma separação que `dna copilot provenance` faz em
    `unanswered` versus `dangling`."""
    await store.write_instance(
        SCOPE, "Copilot", "orfao", _copilot("orfao", created_by="nunca-existiu"),
    )
    r = await store.graph_refs(SCOPE, "Copilot", "orfao", direction="out")
    assert [(e["to_name"], e["resolved"]) for e in r.edges] == [
        ("nunca-existiu", False),
    ]
