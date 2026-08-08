"""``dna copilot orphans`` — a contagem é derivada, e o vazio é recusa.

``Story/s-orfaos-viram-visiveis``. Tudo aqui atravessa a PORTA (o comando click
real, via ``CliRunner``) e não só a função, pela mesma razão que o irmão
``test_copilot_provenance.py``: o defeito registrado nesta casa é "guard existe,
porta não chama" — um validador certo, testado em unit, que nenhuma rota
invocava. Só a sessão é dublê, pelo port declarado (``SESSION_PROVIDER_KEY``).

⭐ E o dublê inclui o **REGISTRO DE KINDS**, de propósito. A guarda deriva os
campos de ``kind_ports()``, então um teste que só dublasse as instâncias
verificaria a contagem sobre um descritor real e nunca provaria a derivação.
``test_a_guarda_segue_a_relacao_renomeada`` planta um descritor com a relação
chamada ``roda_em`` e prova que a guarda a segue — o análogo do serviço com
dígito no nome que ``guard-app-wiring.mjs`` planta, e o único caso que
distingue derivar de enumerar.

Os mutantes que estes testes matam, cada um verificado revertendo o código:

1. universo vazio devolvendo "0 órfãos, tudo certo" → ``test_universo_vazio_...``;
2. colapsar "aponta um App inexistente" em "órfão" → ``test_apontar_app_...``;
3. o nome do campo escrito à mão → ``test_a_guarda_segue_a_relacao_renomeada``;
4. FALHAR por causa de órfão (órfão é legítimo hoje) → ``test_orfao_reporta_...``;
5. anunciar o dia num scope vazio → coberto por (1), na asserção do ``ready``;
6. imprimir "0 penduradas" quando não havia aresta a olhar →
   ``test_sem_aresta_diz_que_nao_ha_o_que_olhar``;
7. rodar a varredura mesmo com o auto-teste quebrado →
   ``test_auto_teste_quebrado_impede_qualquer_contagem``.
"""
from __future__ import annotations

import json
from contextlib import contextmanager

import pytest
from click.testing import CliRunner

from dna_cli import copilot_orphans
from dna_cli._ctx import SESSION_PROVIDER_KEY
from dna_cli.copilot_kit_cmd import copilot

SCOPE = "dna-development"

#: O registro REAL do repo: `Copilot.runs_in → App` e `App.copilots → Copilot`.
#: Escrito aqui na forma CRUA (o que o descritor traz), para o teste atravessar
#: `normalize_relations` como o kernel atravessa.
REGISTRO = {
    "Copilot": {
        "runs_in": {"to": "App", "cardinality": "one"},
        # a reflexiva convive, e a guarda tem de IGNORÁ-LA: ela não aponta
        # para App, e um copiloto com `created_by` continua órfão.
        "created_by": {"to": "Copilot", "cardinality": "one"},
    },
    "App": {"copilots": {"to": "Copilot", "cardinality": "many"}},
}


class _FakeInstance:
    def __init__(self, name: str, spec: dict):
        self.name = name
        self.spec = spec


class _FakePort:
    def __init__(self, kind: str, relations: dict | None):
        self.kind = kind
        self.relations = relations


class _FakeKernel:
    def __init__(self, registro: dict):
        self._registro = registro

    def kind_ports(self):
        # Um registro de verdade tem dezenas de Kinds irrelevantes; incluir um
        # prova que a guarda seleciona por ALVO e não pela ordem da lista.
        return [
            _FakePort("Agent", {"uses": {"to": "Tool", "cardinality": "many"}}),
            *(_FakePort(k, r) for k, r in self._registro.items()),
        ]


class _FakeSession:
    def __init__(self, copilots, apps, *, registro, explode=False):
        self._copilots = copilots
        self._apps = apps
        self._explode = explode
        self.scope = SCOPE
        self.kernel = _FakeKernel(registro)

    def query_list(self, kind, *, filter=None, tenant=None):
        if self._explode:
            raise RuntimeError("store indisponível")
        fonte = {"Copilot": self._copilots, "App": self._apps}.get(kind, {})
        return [_FakeInstance(n, s) for n, s in fonte.items()]


def _obj(copilots, apps=None, *, registro=None, explode=False) -> dict:
    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession(
            copilots, apps or {},
            registro=registro if registro is not None else REGISTRO,
            explode=explode,
        )

    return {SESSION_PROVIDER_KEY: _fake}


def _run(copilots, apps=None, **kw):
    return CliRunner().invoke(copilot, ["orphans"], obj=_obj(copilots, apps, **kw))


def _json(copilots, apps=None, **kw):
    r = CliRunner().invoke(copilot, ["orphans", "--json"], obj=_obj(copilots, apps, **kw))
    return json.loads(r.output), r


# ── 1. o coração da story: plantar um órfão e provar que ela o enxerga ───────


def test_orfao_plantado_e_enxergado_e_a_guarda_nao_falha():
    """A DoD da story, em uma asserção — e a REGRA 3 na outra.

    Órfão é estado LEGÍTIMO hoje (``runs_in`` é opcional por decisão
    registrada): a guarda REPORTA e sai 0. Falhar aqui quebraria os copilotos
    vivos que funcionam sem o campo.
    """
    rel, r = _json(
        {
            "sem-campo": {"mounts": []},
            "campo-nulo": {"runs_in": None},
            "campo-vazio": {"runs_in": "   "},
            "so-tem-procedencia": {"created_by": "copiloto-criador"},
            "colocado": {"runs_in": "porta"},
        },
        {"porta": {"title": "a porta"}},
    )
    assert rel["orphans"] == [
        "campo-nulo", "campo-vazio", "sem-campo", "so-tem-procedencia",
    ]
    assert rel["placed"] == ["colocado"]
    assert rel["copilots_seen"] == 5
    assert r.exit_code == 0  # ⛔ REGRA 3: ela reporta, não falha


def test_orfao_reporta_e_a_tela_diz_a_contagem_e_o_gatilho():
    r = _run({"solto": {}, "posto": {"runs_in": "porta"}}, {"porta": {}})
    assert r.exit_code == 0
    assert "solto" in r.output
    assert "1/2 copiloto(s) sem `runs_in`" in r.output
    # o dia que a guarda existe para tornar visível é NOMEADO mesmo faltando
    assert "Faltam 1" in r.output
    assert "spec-app-e-o-servico" in r.output


# ── 2. ⛔ REGRA 2 — universo vazio NÃO é "tudo certo" ────────────────────────


def test_universo_vazio_recusa_e_nao_afirma_zero_orfaos():
    """A armadilha que mordeu quatro vezes nesta casa em dois dias.

    Zero ``Copilot`` é NÃO HÁ O QUE OLHAR. Uma guarda que devolvesse "0 órfãos"
    aqui anunciaria — verde, convincente, e por vacuidade — o dia em que
    ``runs_in`` pode virar obrigatório.
    """
    rel, r = _json({}, {"porta": {}})
    assert rel["refusals"], "universo vazio tem de RECUSAR"
    assert rel["ready"] is False
    assert r.exit_code == 1

    t = _run({}, {"porta": {}})
    assert t.exit_code == 1
    assert "NÃO HÁ O QUE OLHAR" in t.output
    # e NENHUMA contagem ao lado: um "0/0" junto do aviso convidaria a ler o
    # zero como resultado, quando não houve varredura.
    assert "copiloto(s) sem" not in t.output


def test_registro_sem_a_relacao_recusa_em_vez_de_contar_zero():
    """Se ``Copilot`` deixar de apontar para ``App``, a guarda perdeu o assunto.

    Sem esta recusa, um rename da relação faria a guarda reportar 0 órfãos de N
    copilotos — a forma mais convincente possível de estar quebrada.
    """
    rel, r = _json(
        {"a": {}, "b": {}},
        {"porta": {}},
        registro={"Copilot": {}, "App": REGISTRO["App"]},
    )
    assert rel["refusals"]
    assert rel["orphans"] == []
    assert r.exit_code == 1


def test_store_ilegivel_recusa_e_nao_conta_ninguem_como_colocado():
    rel, r = _json({"x": {"runs_in": "porta"}}, {"porta": {}}, explode=True)
    assert rel["refusals"] and "não pôde ser lido" in rel["refusals"][0]
    assert rel["placed"] == [] and rel["orphans"] == [] and rel["ready"] is False
    assert r.exit_code == 1


# ── 3. os DONOS diferentes — órfão, pendurado, e a aresta do outro lado ──────


def test_apontar_app_inexistente_e_pendurado_nao_orfao():
    """Quem responde errado não é quem não respondeu.

    ``orphans`` acusa quem nunca preencheu; ``dangling_runs_in`` acusa um nome
    que não existe. É a mesma separação que ``dna graph refs`` já fez para as
    suas arestas e que ``provenance`` mantém entre ``unanswered`` e ``dangling``.
    """
    rel, _ = _json({"aponta": {"runs_in": "porta-fantasma"}}, {"porta": {}})
    assert rel["dangling_runs_in"] == [["aponta", "porta-fantasma"]]
    assert rel["orphans"] == []
    assert rel["placed"] == ["aponta"]
    r = _run({"aponta": {"runs_in": "porta-fantasma"}}, {"porta": {}})
    assert "que não existe" in r.output


def test_aresta_app_para_copilot_pendurada_e_acusada():
    """As "arestas penduradas" da story — medidas em 2 de 4 em 07/08/2026."""
    rel, r = _json(
        {"existente": {}},
        {"quebrado": {"copilots": ["existente", "fantasma-1", "fantasma-2"]}},
    )
    assert rel["dangling_composition"] == [
        ["quebrado", "fantasma-1"], ["quebrado", "fantasma-2"],
    ]
    assert rel["composition_refs"] == 3
    assert r.exit_code == 0
    t = _run(
        {"existente": {}},
        {"quebrado": {"copilots": ["existente", "fantasma-1", "fantasma-2"]}},
    )
    assert "2/3 aresta(s) App→Copilot penduradas" in t.output


def test_sem_aresta_diz_que_nao_ha_o_que_olhar():
    """Zero App NÃO é recusa — mas também não é "0 penduradas".

    Medido em 08/08/2026: o scope ``dna-cloud`` tem 6 ``Copilot`` e 9 ``App``,
    e NENHUM App declara copiloto. A pergunta dos órfãos tem universo; a das
    arestas não tem, e a tela diz isso com todas as letras em vez de um zero
    que se leria como "nenhuma quebrada".
    """
    r = _run({"solto": {}}, {"porta": {}, "outra": {}})
    assert r.exit_code == 0
    assert "não há o que olhar deste lado" in r.output
    assert "penduradas" not in r.output


# ── 4. ⛔ REGRA 1 — DERIVADA, e este é o teste que a prova ───────────────────


def test_a_guarda_segue_a_relacao_renomeada():
    """O campo vem do DESCRITOR. Renomeie-o e a guarda vai junto.

    Se qualquer linha da guarda tivesse a string ``"runs_in"``, este teste
    quebraria. É o análogo exato do serviço com dígito no nome que a irmã
    ``guard-app-wiring.mjs`` planta — o caso contra a classe de erro que a
    enumeração causa, e que lá custou justamente o serviço que motivou a
    guarda.
    """
    registro = {
        "Copilot": {"roda_em": {"to": "App", "cardinality": "one"}},
        "App": {"contem": {"to": "Copilot", "cardinality": "many"}},
    }
    rel, _ = _json(
        {"solto": {}, "posto": {"roda_em": "porta"}, "velho": {"runs_in": "porta"}},
        {"porta": {"contem": ["posto", "sumido"]}},
        registro=registro,
    )
    assert rel["to_app_fields"] == ["roda_em"]
    assert rel["to_copilot_fields"] == ["contem"]
    assert rel["placed"] == ["posto"]
    # ⭐ `velho` preenche o campo ANTIGO: para o registro de hoje ele está mudo,
    # e a guarda o diz. Uma guarda enumerada diria o contrário.
    assert rel["orphans"] == ["solto", "velho"]
    assert rel["dangling_composition"] == [["porta", "sumido"]]
    # e o nome derivado aparece na TELA, para se conferir sem ler o código
    r = CliRunner().invoke(
        copilot, ["orphans"], obj=_obj({"solto": {}}, {}, registro=registro)
    )
    assert "sem `roda_em`" in r.output


def test_mais_de_uma_relacao_para_app_conta_todas():
    """Um Kind pode declarar duas relações para o mesmo alvo.

    A guarda que assumisse "uma" seria uma lista à mão de tamanho 1. Órfão é
    quem não preenche NENHUMA.
    """
    registro = {
        "Copilot": {
            "runs_in": {"to": "App", "cardinality": "one"},
            "fallback_app": {"to": "App", "cardinality": "one"},
        },
        "App": REGISTRO["App"],
    }
    rel, _ = _json(
        {"so-fallback": {"fallback_app": "porta"}, "nenhum": {}},
        {"porta": {}},
        registro=registro,
    )
    assert rel["to_app_fields"] == ["fallback_app", "runs_in"]
    assert rel["placed"] == ["so-fallback"]
    assert rel["orphans"] == ["nenhum"]


# ── 5. o DIA ────────────────────────────────────────────────────────────────


def test_zero_orfaos_anuncia_o_dia():
    """O AC que a guarda existe para cumprir: quando zerar, ela GRITA."""
    rel, _ = _json(
        {"a": {"runs_in": "porta"}, "b": {"runs_in": "porta"}},
        {"porta": {"copilots": ["a", "b"]}},
    )
    assert rel["orphans"] == [] and rel["ready"] is True
    r = _run(
        {"a": {"runs_in": "porta"}, "b": {"runs_in": "porta"}},
        {"porta": {"copilots": ["a", "b"]}},
    )
    assert r.exit_code == 0
    assert "A CONTAGEM CHEGOU A ZERO" in r.output
    assert "OBRIGATÓRIO" in r.output


def test_zero_orfaos_com_referencia_pendurada_avisa_a_ressalva():
    """Obrigatório exige PRESENÇA, não resolução — e a tela não deixa passar."""
    r = _run({"a": {"runs_in": "porta-fantasma"}}, {"porta": {}})
    assert "A CONTAGEM CHEGOU A ZERO" in r.output
    assert "continuariam" in r.output


# ── 6. o auto-teste roda ANTES da guarda ────────────────────────────────────


def test_auto_teste_atravessa_a_porta_sozinho():
    r = CliRunner().invoke(copilot, ["orphans", "--self-test"])
    assert r.exit_code == 0, r.output
    assert "a guarda ainda sabe olhar" in r.output
    # e ele NÃO leu store nenhum: nenhuma sessão foi injetada e mesmo assim
    # passou — é o que o torna rodável em CI, sem banco.
    assert "self-test:" in r.output


def test_auto_teste_quebrado_impede_qualquer_contagem(monkeypatch):
    """Uma guarda cujo auto-teste falhou não pode imprimir número nenhum.

    O relatório verde de uma guarda que não sabe mais olhar é indistinguível do
    relatório verde de uma que sabe — e é a razão de o auto-teste rodar antes
    da varredura em TODA invocação, não só sob a flag.
    """
    monkeypatch.setattr(
        copilot_orphans, "self_test", lambda: [("um caso inventado", False)]
    )
    r = _run({"solto": {}}, {"porta": {}})
    assert r.exit_code != 0
    assert "NÃO é confiável" in r.output
    assert "copiloto(s) sem" not in r.output


def test_o_auto_teste_real_passa_inteiro():
    casos = copilot_orphans.self_test()
    assert casos, "um auto-teste sem casos passaria por vacuidade"
    assert [n for n, ok in casos if not ok] == []


# ── 7. as duas irmãs se apontam ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("cmd", "esperado"),
    [("orphans", "dna copilot provenance"), ("provenance", "dna copilot orphans")],
)
def test_as_duas_perguntas_se_apontam(cmd, esperado):
    """``created_by`` responde DE ONDE VEIO; ``runs_in``, ONDE RODA.

    Comandos separados porque os contratos de saída se contradizem (universo
    vazio: 0 lá, 1 aqui) — e cross-linkados porque quem faz uma pergunta
    costuma querer a outra.
    """
    r = CliRunner().invoke(copilot, [cmd], obj=_obj({"a": {}}, {"porta": {}}))
    assert esperado in r.output
