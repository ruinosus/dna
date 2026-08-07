"""``dna copilot provenance`` — a ausência é reportada, jamais presumida.

`Story/s-procedencia-do-agente`. Tudo aqui atravessa a PORTA (o comando click
real, via ``CliRunner``), e não só a função: o defeito registrado nesta casa é
"guard existe, porta não chama" — um validador certo, testado em unit, que
nenhuma rota invocava. Só a sessão é dublê, pelo port declarado
(``SESSION_PROVIDER_KEY``).

Os mutantes que estes testes matam, cada um verificado revertendo o código:

1. tratar ausente como "escrito à mão" (colapsar ``unanswered`` em uma
   afirmação) → ``test_ausencia_e_nao_respondida_nunca_presumida``;
2. colapsar ``dangling`` em ``unanswered`` → ``test_criador_inexistente_...``;
3. store ilegível devolvendo "tudo respondido" → ``test_store_ilegivel_...``;
4. profundidade parando no primeiro elo → ``test_profundidade_da_cadeia``;
5. laço infinito num ciclo → ``test_ciclo_e_achado_nao_travamento``;
6. contar o criador como respondido só porque ele foi NOMEADO, sem existir →
   coberto por (2), do outro lado.
"""
from __future__ import annotations

import json
from contextlib import contextmanager

from click.testing import CliRunner

from dna_cli._ctx import SESSION_PROVIDER_KEY
from dna_cli.copilot_kit_cmd import copilot
from dna_cli.copilot_provenance import chain_depth

SCOPE = "dna-development"


class _FakeInstance:
    def __init__(self, name: str, spec: dict):
        self.name = name
        self.spec = spec


class _FakeSession:
    def __init__(self, copilots: dict[str, dict], *, explode: bool = False):
        self._copilots = copilots
        self._explode = explode
        self.scope = SCOPE

    def query_list(self, kind, *, filter=None, tenant=None):
        if self._explode:
            raise RuntimeError("store indisponível")
        if kind != "Copilot":
            return []
        return [_FakeInstance(n, s) for n, s in self._copilots.items()]


def _obj(copilots: dict[str, dict], *, explode: bool = False) -> dict:
    @contextmanager
    def _fake(scope=None, *, tenant=None, timeout=30.0):
        yield _FakeSession(copilots, explode=explode)

    return {SESSION_PROVIDER_KEY: _fake}


def _json(copilots: dict[str, dict], *, explode: bool = False) -> dict:
    r = CliRunner().invoke(
        copilot, ["provenance", "--json"], obj=_obj(copilots, explode=explode)
    )
    assert r.exit_code == 0, r.output
    return json.loads(r.output)


# ── 1. o coração da story ────────────────────────────────────────────────────


def test_ausencia_e_nao_respondida_nunca_presumida():
    """Um copiloto escrito à mão não afirma nada — ele está MUDO.

    As três formas do silêncio (chave ausente, ``null``, string vazia) são o
    mesmo fato, e nenhuma delas vira "criado por ninguém" nem "escrito à mão".
    """
    rel = _json({
        "sem-campo": {"mounts": [], "serving": {}},
        "campo-nulo": {"created_by": None},
        "campo-vazio": {"created_by": "   "},
    })
    assert rel["unanswered"] == ["campo-nulo", "campo-vazio", "sem-campo"]
    assert rel["answered"] == []
    assert rel["dangling"] == []
    # e a tela DIZ a palavra — "não-respondido", nunca "manual"/"sem criador"
    r = CliRunner().invoke(copilot, ["provenance"], obj=_obj({"solto": {}}))
    assert "não-respondido" in r.output
    assert "à mão" not in r.output


def test_procedencia_declarada_e_respondida():
    rel = _json({
        "copiloto-criador": {},
        "escrita-de-livro": {"created_by": "copiloto-criador"},
    })
    assert rel["answered"] == ["escrita-de-livro"]
    assert rel["unanswered"] == ["copiloto-criador"]
    assert rel["store_readable"] is True


def test_criador_inexistente_e_pendurado_nao_nao_respondido():
    """``dangling`` e ``unanswered`` têm DONOS diferentes.

    Um acusa quem escreveu um nome que nunca existiu; o outro, quem nunca
    escreveu. Colapsá-los é o mesmo erro que ``dna graph refs`` já corrigiu
    para as suas próprias arestas.
    """
    rel = _json({"orfao": {"created_by": "criador-que-nunca-existiu"}})
    assert rel["dangling"] == ["orfao"]
    assert rel["unanswered"] == []
    assert rel["answered"] == []
    r = CliRunner().invoke(
        copilot, ["provenance"], obj=_obj({"orfao": {"created_by": "fantasma"}})
    )
    assert "o criador declarado não existe" in r.output


# ── 2. a cadeia ──────────────────────────────────────────────────────────────


def test_profundidade_da_cadeia():
    """Um copiloto que criou outro que criou outro — a pergunta da story."""
    rel = _json({
        "raiz": {},
        "filho": {"created_by": "raiz"},
        "neto": {"created_by": "filho"},
        "bisneto": {"created_by": "neto"},
    })
    assert rel["depths"] == {"raiz": 0, "filho": 1, "neto": 2, "bisneto": 3}


def test_profundidade_conta_o_elo_pendurado_e_para():
    """O elo até um criador inexistente EXISTE — o que falta é o próximo."""
    assert chain_depth("a", {"a": "sumido"}) == (1, False)


def test_ciclo_e_achado_nao_travamento():
    """Uma cadeia que volta a si mesma é topologia impossível, e é reportada.

    Sem a detecção, este teste não falha — ele PENDURA, que é a pior forma de
    um relatório errar.
    """
    rel = _json({
        "a": {"created_by": "b"},
        "b": {"created_by": "a"},
        "eu-mesmo": {"created_by": "eu-mesmo"},
    })
    assert rel["cycles"] == ["a", "b", "eu-mesmo"]
    r = CliRunner().invoke(
        copilot, ["provenance"], obj=_obj({"eu": {"created_by": "eu"}})
    )
    assert "volta a si mesma" in r.output


# ── 3. o lado ruidoso ────────────────────────────────────────────────────────


def test_store_ilegivel_reporta_o_lado_ruidoso():
    """Não conseguir perguntar NÃO é "tudo respondido".

    Verde por vacuidade é a classe de defeito que já cegou três guardas nesta
    casa; a leitura que falha reporta ``store_readable: False`` e zero
    respondidos.
    """
    rel = _json({"qualquer": {"created_by": "outro"}}, explode=True)
    assert rel["store_readable"] is False
    assert rel["answered"] == []
    r = CliRunner().invoke(
        copilot, ["provenance"], obj=_obj({"x": {}}, explode=True)
    )
    assert "não pôde ser lido" in r.output
    # e NENHUM total é impresso: um "0/0 com procedência" ao lado do aviso
    # convidaria a ler o zero como contagem, quando não houve contagem.
    assert "com procedência declarada" not in r.output


def test_scope_sem_copiloto_nao_afirma_nada():
    r = CliRunner().invoke(copilot, ["provenance"], obj=_obj({}))
    assert r.exit_code == 0
    assert "nada afirmado" in r.output


def test_a_porta_aponta_para_a_travessia_do_grafo():
    """A profundidade tem DOIS leitores de UMA declaração, e a tela diz o outro."""
    r = CliRunner().invoke(copilot, ["provenance"], obj=_obj({"a": {}}))
    assert "dna graph refs Copilot" in r.output
