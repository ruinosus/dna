"""i-121 — o Kind ``Spec`` datava-se e não dizia o que É.

O sintoma foi medido no portal: as raias do board derivam de
``sdlc.rollup`` / ``sdlc.decision`` / ``sdlc.work-item``, lidos do registry, e
``Spec`` declarava só ``sdlc.dated``. Toda spec caía na quarta raia — "sem
classificação". A tela estava certa (dizia o que sabia); a lacuna era do
VOCABULÁRIO do SDK.

⭐ **Medido antes de declarado**, do descritor e do USO, nunca do nome — que
teria argumentado nos dois sentidos ("spec" soa plano; ``Spec`` mora ao lado de
``ADR``). Este módulo prende a MEDIÇÃO, não a conclusão: cada asserção abaixo é
um dos sinais que decidiram ``sdlc.decision``, de forma que se algum deles virar
(``Spec`` ganhar dono, perder ``supersedes``, trocar o arco de status) a guarda
cai e a classificação volta à mesa em vez de continuar herdada.

O que NÃO se propôs, e o porquê está aqui para o próximo leitor: um nome novo
(``sdlc.design-artifact`` e parentes). Vocabulário é decisão do founder — há
i-128 aberta com quatro propostas — e, pior, um nome novo teria errado o alvo
do i-121: as raias leem os TRÊS nomes acima, então um quarto deixaria toda spec
exatamente onde estava, com um trait declarado para provar que alguém olhou.
"""
from __future__ import annotations

import pytest

from dna.application import sdlc_family as F
from dna.kernel import Kernel


@pytest.fixture(scope="module")
def kernel():
    return Kernel.auto()


@pytest.fixture(scope="module")
def spec_port(kernel):
    return kernel.kind_port_for("Spec")


# ── 1. o defeito, na granularidade em que ele apareceu ──────────────────────


def test_spec_answers_what_kind_of_thing_it_is(kernel, spec_port):
    """A pergunta que o board faz ao registry, feita aqui com o vocabulário do
    próprio SDK em vez de uma lista escrita neste arquivo."""
    classifying = {F.TRAIT_ROLLUP, F.TRAIT_DECISION, F.TRAIT_WORK_ITEM}
    assert set(spec_port.traits) & classifying, sorted(spec_port.traits)
    assert "Spec" in kernel.kinds_with_trait(F.TRAIT_DECISION)


def test_spec_did_not_LOSE_the_date_it_already_declared(spec_port):
    """Aditivo, não substituição: ``sdlc.dated`` continua, e com ele o contrato
    de data que ``dated_spec_fields`` cobra de todo caminho de escrita."""
    assert F.TRAIT_DATED in spec_port.traits


# ── 2. por que DECISION e não WORK-ITEM — os sinais, um a um ────────────────


def test_spec_is_not_ASSIGNED_to_anyone(spec_port):
    """O primeiro sinal, e o mais duro: um work item é *"the thing a person is
    assigned and closes"*. O schema de ``Spec`` não tem onde escrever essa
    pessoa — tem ``authors``, como o ADR tem ``deciders``."""
    props = spec_port.schema()["properties"]
    assert not ({"owner", "assignee", "assigned_to"} & set(props)), sorted(props)
    assert "authors" in props


def test_spec_carries_the_ARTIFACT_arc_and_not_a_work_arc(spec_port):
    """O arco declarado é o do ADR, alargado nas duas pontas terminais — e o
    Kind diz isso com essas palavras no próprio ``docs``."""
    from dna.extensions.sdlc import ARTIFACT_STATUSES

    enum = tuple(spec_port.schema()["properties"]["status"]["enum"])
    assert enum[: len(ARTIFACT_STATUSES)] == ARTIFACT_STATUSES
    assert set(enum) - set(ARTIFACT_STATUSES) == {"executed", "shelved"}
    assert "ADR-style" in (spec_port.docs or "")


def test_spec_is_SUPERSEDED_rather_than_reopened(spec_port):
    """Substituída, não reaberta — a idiomática da supersessão, que o ADR
    carrega e nenhum work item tem."""
    relations = dict(spec_port.relations or {})
    assert relations["supersedes"]["to"] == "Spec"
    assert "superseded" in spec_port.schema()["properties"]["status"]["enum"]


def test_every_terminal_state_of_a_spec_owes_a_WHY(spec_port):
    """``executed`` / ``shelved`` / ``deprecated`` cada um com o seu campo de
    razão — a carga de uma decisão, não a de uma tarefa fechada."""
    props = spec_port.schema()["properties"]
    for field in ("execution_summary", "shelve_reason", "deprecation_reason"):
        assert field in props, field


def test_spec_stays_out_of_the_transitionable_work_set(kernel):
    """A prova de que a declaração não a transformou em trabalho: ``Spec`` não
    entra em ``work_item_kinds`` nem em ``transitionable_kinds``, exatamente
    como ``ADR`` não entra. Os verbos dela continuam sendo os do grupo
    ``dna sdlc spec`` (propose/accept/executed/shelve/…)."""
    assert "Spec" not in F.work_item_kinds(kernel)
    assert "Spec" not in F.transitionable_kinds(kernel)


# ── 3. o que a declaração LIGOU, dito de propósito ──────────────────────────


def test_the_declaration_puts_spec_in_the_digest_and_the_gallery(kernel):
    """Uma consequência, não um efeito colateral: ``sdlc.decision`` é lida por
    ``digest_kinds`` e ``producer_kinds``. Escrita aqui para que ela seja uma
    decisão registrada e não uma surpresa que alguém descobre no relatório.

    O custo é medido e é zero hoje: das 18 Specs gravadas nos escopos ``dna`` e
    ``dna-cloud`` em 06/08/2026, 17 têm ``timeline`` (que é o que o digest
    caminha) e **nenhuma** tem ``produces`` (que é o que a galeria caminha) —
    então a galeria não ganha linha nenhuma e o digest passa a poder reportar um
    movimento que antes ele não via."""
    assert "Spec" in F.digest_kinds(kernel)
    assert "Spec" in F.producer_kinds(kernel)


def test_the_kernel_less_fallback_moved_with_the_declaration():
    """``FALLBACK_FAMILIES`` é a única tabela literal de nomes que
    ``sdlc_family`` guarda, para os consumidores puros (``build_digest`` recebe
    instâncias e uma janela, não um kernel). Ela não pode divergir da declaração
    — e neste caso não divergiu porque uma guarda a pegou."""
    assert F.FALLBACK_FAMILIES[F.TRAIT_DECISION] == ("ADR", "Spec")
