"""``graph_refs`` — the traversal, THROUGH the MCP door, measured against REST.

The defect this closes is the one this house keeps re-finding under the name
*capability exists, port does not*: the derived reference graph was reachable
from the CLI (``dna graph refs``) and from REST
(``GET /v1/kinds/{kind}/instances/{name}/refs``) and from nowhere an agent could
speak to. The console copilot dials the broker MCP door, so "what points at this
Feature" was a question it could not ask at all — while the walk itself sat in
the kernel, wired, tested and serving two other faces.

**THE ASSERTION IS A COMPARISON, NOT A LITERAL.** Every interesting test here
calls the REST route and the MCP tool against THE SAME STORE and requires the
same edges back. A hand-written expected list would pass on a tool that had
quietly grown its own shape — a different default direction, an edge dict with
different keys, a depth that means something else — which is precisely the debt
a third face of one verb is at risk of creating. Comparing the faces cannot: it
is red the moment they disagree, whichever one is wrong.

Two stores, deliberately, exactly like the REST suite next door:

* the **filesystem** store, which records no edges and must therefore REFUSE.
  ``{"edges": []}`` would tell an agent nothing points at this instance, and the
  filesystem adapter has no idea whether that is true;
* a **SQLite** store, where a real write through the real producer makes a real
  edge, so the walk has something to return.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_SDLC_API = "github.com/ruinosus/dna/sdlc/v1"

_SQL_SKIP = (
    "the SQL adapter's async driver stack is an SDK extra the CLI does not "
    "pull; the refusal lane — the one only this suite can prove — still runs."
)


@pytest.fixture
def fs_dir(tmp_path, monkeypatch):
    """A filesystem store — the adapter that keeps no edges."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")
    return dst


@pytest.fixture
def sql_dir(tmp_path, monkeypatch):
    """A SQLite store seeded through the REAL write path.

    Seeded by the kernel rather than by inserting edge rows: an edge exists in
    this product because somebody wrote an instance whose reference resolved,
    and a fixture that forged the row would let both faces pass with no producer
    behind either — the exact failure that left the first edge table empty for
    fourteen months.

    ``s-x`` and ``s-z`` both point at ``f-y``; ``s-x`` also points at a Feature
    that does not exist, so the DANGLING half of the answer is real too.
    """
    for _module in ("aiosqlite", "greenlet", "alembic"):
        pytest.importorskip(_module, reason=_SQL_SKIP)
    url = f"sqlite+aiosqlite:///{tmp_path / 'graph.db'}"
    monkeypatch.setenv("DNA_SOURCE_URL", url)
    monkeypatch.delenv("DNA_BASE_DIR", raising=False)
    monkeypatch.setenv("DNA_WRITE_VALIDATION", "off")
    monkeypatch.delenv("DNA_REF_VALIDATION", raising=False)

    def _doc(kind, name, **spec):
        base = {"description": "d", "status": "todo"}
        base.update(spec)
        return {
            "apiVersion": _SDLC_API, "kind": kind,
            "metadata": {"name": name}, "spec": base,
        }

    async def seed():
        from dna.adapters.sqlalchemy_ import SqlAlchemySource
        from dna.kernel import Kernel

        src = SqlAlchemySource(url)
        await src.connect()
        k = Kernel.auto()
        k.source(src)
        await k.write_instance(_SCOPE, "Epic", "e-1", _doc("Epic", "e-1"))
        await k.write_instance(
            _SCOPE, "Feature", "f-y", _doc("Feature", "f-y", epic="e-1"))
        await k.write_instance(
            _SCOPE, "Story", "s-x", _doc("Story", "s-x", feature="f-y"))
        await k.write_instance(
            _SCOPE, "Story", "s-z", _doc("Story", "s-z", feature="f-y"))
        await src.close()

    asyncio.run(seed())
    return url


# ── the two faces, side by side ─────────────────────────────────────────────


def _mcp(args, **build):
    """Call the ``graph_refs`` TOOL over a real ``fastmcp.Client``.

    Through the door, never through ``graph_refs_impl``: the whole defect was
    the boundary. A test that called the use-case would have been green on every
    build that had no tool at all.
    """
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, **build)

    async def go():
        async with Client(server) as client:
            return await client.call_tool("graph_refs", args)

    return asyncio.run(go()).structured_content


def _mcp_refused(args, **build) -> str:
    with pytest.raises(Exception) as ei:  # noqa: PT011 — FastMCP ToolError
        _mcp(args, **build)
    return str(ei.value)


def _rest(path, params=None, **build):
    pytest.importorskip(
        "fastapi", reason="the REST read-API needs the optional 'fastapi' extra")
    from fastapi.testclient import TestClient

    from dna_cli import _rest_api as R

    with TestClient(R.build_app(scope=_SCOPE, **build)) as c:
        return c.get(path, params=params or {})


def _rest_refs(kind, name, params=None, **build):
    return _rest(
        f"/v1/kinds/{kind}/instances/{name}/refs", params=params, **build)


def _amanha() -> str:
    """Um instante seguramente depois de tudo que a fixture escreveu.

    Deliberadamente NÃO "agora": a fixture acabou de gravar e ``created_at`` tem
    resolução de microssegundo, então "agora" é ambíguo por um fio — e um teste
    de comparação que ficasse verde por não achar nada dos DOIS lados seria pior
    que teste nenhum."""
    from datetime import datetime, timedelta, timezone

    from dna.memory.as_of import normalize_as_of

    return normalize_as_of(datetime.now(timezone.utc) + timedelta(days=1))


class TestTheTwoFacesAgree:
    """AC 1, and it is stated as a comparison because that is the only form
    that can catch a third shape of the same verb being invented here."""

    def test_the_default_walk_is_the_same_answer_on_both_faces(self, sql_dir):
        """No parameters at all: both faces must default to the same question.

        ``direction`` and ``depth`` have defaults on both sides, and a default
        that drifted would be invisible to any test that passed them explicitly.
        """
        rest = _rest_refs("Feature", "f-y").json()
        mcp = _mcp({"kind": "Feature", "name": "f-y"})

        assert mcp["edges"], "the walk found nothing — the fixture, not the faces"
        assert mcp == rest, (
            "the MCP tool and the REST route disagree about the same instance "
            "in the same store — a third shape of one verb is exactly what this "
            "tool exists not to create"
        )

    @pytest.mark.parametrize("direction", ["in", "out", "both"])
    @pytest.mark.parametrize("depth", [1, 2, 3])
    def test_every_direction_and_depth_agrees(self, sql_dir, direction, depth):
        """The two coordinate parameters, across their whole range.

        ``out`` at depth 3 from ``s-x`` walks Story → Feature → Epic, so this
        also proves the depth means HOPS on both faces and not something else.
        """
        rest = _rest_refs(
            "Story", "s-x", {"direction": direction, "depth": depth}).json()
        mcp = _mcp({
            "kind": "Story", "name": "s-x",
            "direction": direction, "depth": depth,
        })
        assert mcp == rest, f"{direction}/{depth}: the faces disagree"

    def test_the_honesty_fields_travel_over_MCP_too(self, sql_dir):
        """``stop`` / ``graph_producer`` / ``resolved`` are not decoration.

        Asserted here as well as in the comparison because a face that dropped
        all three would still be EQUAL to a REST face that dropped them — the
        comparison is a strong test of drift and a weak one of content.
        """
        mcp = _mcp({"kind": "Feature", "name": "f-y"})
        assert mcp["stop"] in ("complete", "depth_reached", "truncated")
        assert mcp["graph_producer"] == "warn"
        assert sorted(
            (e["from_kind"], e["from_name"], e["field"]) for e in mcp["edges"]
        ) == [("Story", "s-x", "feature"), ("Story", "s-z", "feature")]
        assert all(e["resolved"] is True for e in mcp["edges"])


class TestTheTwoFacesAgreeAboutThePast:
    """``as_of`` — the fourth coordinate — has to cross BOTH doors identically.

    The measured reason this is not paranoia: this very axis reached the generic
    REST route once before and was ACCEPTED AND IGNORED (i-106) — a caller
    asking what an instance looked like yesterday got today's, under a 200, with
    nothing in the response to say so. A parameter only one face honours is that
    defect wearing the other face's clothes.
    """

    @pytest.mark.parametrize("direction", ["in", "out", "both"])
    @pytest.mark.parametrize("depth", [1, 2, 3])
    def test_o_grafo_historico_e_o_mesmo_nas_duas_faces(
        self, sql_dir, direction, depth,
    ):
        instant = _amanha()
        rest = _rest_refs("Story", "s-x", {
            "direction": direction, "depth": depth, "as_of": instant,
        }).json()
        mcp = _mcp({
            "kind": "Story", "name": "s-x",
            "direction": direction, "depth": depth, "as_of": instant,
        })
        assert mcp == rest, f"{direction}/{depth}: as faces discordam do passado"
        assert mcp["as_of"] == instant, (
            "o instante não voltou ecoado — quem só olha `edges` não consegue "
            "distinguir uma resposta histórica de uma atual"
        )

    def test_o_as_of_e_NORMALIZADO_igual_nas_duas(self, sql_dir):
        """``2026-08-06`` e ``2026-08-06T00:00:00Z`` são o mesmo instante, e as
        duas faces têm de concordar sobre isso — a normalização mora numa função
        só (``normalize_as_of``) exatamente para não haver duas leituras de uma
        palavra. (O instante é anterior à fixture, então as duas RECUSAM com
        404; o que se compara aqui é a leitura do parâmetro.)"""
        for escrito in ("2026-01-02", "2026-01-02T00:00:00Z",
                        "2026-01-02T00:00:00+00:00"):
            rest = _rest_refs("Story", "s-x", {"as_of": escrito})
            msg = _mcp_refused({
                "kind": "Story", "name": "s-x", "as_of": escrito})
            assert rest.status_code == 404, escrito
            assert "2026-01-02T00:00:00+00:00" in rest.json()["detail"], escrito
            assert "2026-01-02T00:00:00+00:00" in msg, escrito

    def test_uma_resposta_VIVA_diz_as_of_nulo_e_nao_omite_o_campo(self, sql_dir):
        """Omitir o campo faria "esta resposta é do presente" e "esta face não
        conhece o eixo" se lerem igual do lado do cliente."""
        rest = _rest_refs("Story", "s-x").json()
        mcp = _mcp({"kind": "Story", "name": "s-x"})
        assert "as_of" in rest and rest["as_of"] is None
        assert "as_of" in mcp and mcp["as_of"] is None
        assert rest["as_of_truncated"] == mcp["as_of_truncated"] == []


# ── the refusals ────────────────────────────────────────────────────────────


class TestTheRefusals:
    def test_a_store_without_edges_is_refused_by_name_not_answered_empty(
        self, fs_dir,
    ):
        """⚠️ AC 3, and the assertion that matters most on this whole tool.

        ``{"edges": []}`` would tell an agent that NOTHING points at this
        instance. The filesystem adapter has no idea whether that is true, and
        an agent handed a confident empty list will act on it — which is worse
        than being told the deployment cannot answer.

        The NAME travels because an agent acts on it: ``GraphUnsupported`` means
        "stop asking this deployment about the graph", a different remedy from
        every other way this call can fail.
        """
        msg = _mcp_refused(
            {"kind": "Agent", "name": "concierge"}, base_dir=str(fs_dir))
        assert "GraphUnsupported" in msg, msg
        assert "not the same as" in msg, msg

        # ...and REST refuses the SAME call with its own 501, so the two faces
        # agree about the refusal exactly as they agree about the answer.
        assert _rest_refs(
            "Agent", "concierge", base_dir=str(fs_dir)).status_code == 501

    def test_the_refusal_survives_mask_error_details(self, fs_dir, monkeypatch):
        """The setting an operator is invited to turn on erases the message of
        anything that is not a ``ToolError``. Under it, an untranslated refusal
        reaches the agent as ``Error calling tool 'graph_refs'`` — no name, no
        reason, indistinguishable from a crash."""
        pytest.importorskip("fastmcp")
        import fastmcp

        monkeypatch.setattr(fastmcp.settings, "mask_error_details", True)
        msg = _mcp_refused(
            {"kind": "Agent", "name": "concierge"}, base_dir=str(fs_dir))
        assert "GraphUnsupported" in msg, msg
        assert "edge_graph" in msg, msg

    def test_a_nonsense_direction_is_refused_on_both_faces(self, sql_dir):
        msg = _mcp_refused({
            "kind": "Feature", "name": "f-y", "direction": "sideways"})
        assert "sideways" in msg, msg
        assert _rest_refs(
            "Feature", "f-y", {"direction": "sideways"}).status_code == 400

    def test_an_unknown_kind_is_refused_naming_it(self, sql_dir):
        msg = _mcp_refused({"kind": "NaoExiste", "name": "x"})
        assert "NaoExiste" in msg, msg
        assert _rest_refs("NaoExiste", "x").status_code == 404

    def test_um_as_of_que_nao_e_instante_e_recusado_nas_duas(self, sql_dir):
        """"o seu timestamp não é um timestamp" tem remédio diferente de "esta
        implantação não lê o passado", e só a mensagem carrega qual."""
        msg = _mcp_refused({
            "kind": "Feature", "name": "f-y", "as_of": "ontem de manhã"})
        assert "ontem de manhã" in msg, msg
        r = _rest_refs("Feature", "f-y", {"as_of": "ontem de manhã"})
        assert r.status_code == 400, r.text

    def test_404_para_um_instante_anterior_a_instancia_nas_duas(self, sql_dir):
        """"não existia ainda" é uma RESPOSTA. O 410 do irmão é uma recusa, e o
        que separa os dois é o fato inteiro — a única distinção que uma leitura
        histórica não pode errar."""
        antigo = "2020-01-01T00:00:00+00:00"
        assert _rest_refs(
            "Feature", "f-y", {"as_of": antigo}).status_code == 404
        assert "2020-01-01" in _mcp_refused({
            "kind": "Feature", "name": "f-y", "as_of": antigo})

    def test_um_store_sem_historia_recusa_o_as_of_e_nao_devolve_hoje(
        self, fs_dir,
    ):
        """⚠️ No filesystem a recusa que chega primeiro é a de ARESTAS, e isso é
        certo: sem tabela de arestas não há grafo nenhum a responder, com ou sem
        eixo de tempo. O que este teste prende é que o caminho ``as_of`` **não
        abre uma porta nova** naquele adapter — não há forma de pedir o passado
        e receber o presente.
        """
        msg = _mcp_refused(
            {"kind": "Agent", "name": "concierge", "as_of": "2026-01-01"},
            base_dir=str(fs_dir))
        assert "GraphUnsupported" in msg, msg
        r = _rest_refs(
            "Agent", "concierge", {"as_of": "2026-01-01"},
            base_dir=str(fs_dir))
        assert r.status_code == 501, r.text

    def test_410_a_historia_PODADA_nao_pode_sair_como_o_404_de_nao_existia(
        self, sql_dir,
    ):
        """⚠️ A ordem dos ``except`` É o contrato, e é por isso que este teste
        atravessa a porta em vez de chamar o impl.

        ``AsOfTruncated`` **É um ``LookupError``** — de propósito, para que a
        família "não veio nada" continue uma só. O preço é que um ``except
        LookupError`` colocado antes dele o relata como *"não existia ainda"*,
        que é o fato OPOSTO. Nenhuma inspeção de assinatura pega isso; só uma
        chamada real, com a história de fato podada.
        """
        import sqlite3

        caminho = sql_dir.split("///", 1)[1]
        with sqlite3.connect(caminho) as conn:
            # Poda: a instância continua com história, e nenhuma dela alcança
            # 2020 — a forma que ``VERSION_CHURN_RETENTION`` produz num Engram.
            # ⚠️ ``versions`` sem prefixo: as tabelas são ``dna_``-prefixadas no
            # Postgres e nuas no SQLite (``schema.py``), e este atalho de
            # fixture é a única linha da suíte que fala SQL cru.
            conn.execute(
                "UPDATE versions SET version = 42 WHERE name = 'f-y'")

        r = _rest_refs("Feature", "f-y", {"as_of": "2020-01-01"})
        assert r.status_code == 410, (
            f"{r.status_code}: 'o registro daquela época foi podado' saiu como "
            f"outra coisa — 404 seria o fato oposto, com a mesma cara"
        )
        assert "pruned" in r.json()["detail"]

        msg = _mcp_refused({
            "kind": "Feature", "name": "f-y", "as_of": "2020-01-01"})
        assert "AsOfTruncated" in msg, (
            f"{msg}: o NOME não viajou. Sem ele um agente lê 'não existia' e "
            f"age sobre um grafo que nunca existiu"
        )

    def test_depth_below_one_is_refused_rather_than_clamped(self, sql_dir):
        """REST answers 422 (``ge=1``); the kernel would CLAMP to 1.

        Clamping is fine for a CLI flag and wrong here: the answer carries a
        ``depth`` field, so a silently-corrected request comes back looking like
        the request that was made.
        """
        msg = _mcp_refused({"kind": "Feature", "name": "f-y", "depth": 0})
        assert "depth" in msg, msg
        assert _rest_refs(
            "Feature", "f-y", {"depth": 0}).status_code == 422


# ── the tool is REGISTERED, which is what makes it reachable ────────────────


def test_the_tool_is_listed_on_the_face(fs_dir):
    """i-106's lesson generalised: a capability nobody can DISCOVER is not a
    port. The tool list is where an agent learns this exists at all."""
    pytest.importorskip("fastmcp")
    from fastmcp import Client

    from dna_cli import _mcp_server as M

    server = M.build_server(scope=_SCOPE, base_dir=str(fs_dir))

    async def go():
        async with Client(server) as client:
            return await client.list_tools()

    tools = {t.name: t for t in asyncio.run(go())}
    assert "graph_refs" in tools, sorted(tools)
    described = (tools["graph_refs"].description or "")
    # The refusal is part of the contract an agent reads BEFORE calling.
    assert "never" in described.lower()


# ── o response_model não pode DESCARTAR campo em silêncio ───────────────────


def test_the_rest_model_declares_every_key_the_impl_produces(sql_dir):
    """O ``response_model`` do FastAPI FILTRA — e filtrar é indistinguível de
    "o campo não existe" para quem lê a resposta.

    Medido em 06/08/2026: a rota REST vinha descartando **três** campos que o
    impl produzia — ``from_api_version`` e ``to_api_version`` (fatia 1) e
    ``to_deleted_at`` (i-131). O último é o pior: ele nasceu exatamente para o
    grafo parar de dizer ``resolved: true`` sobre um alvo apagado, e a face que
    mais gente consome o apagava de volta.

    ⚠️ Isto só foi notado porque a face MCP existe e um teste as compara. Antes
    dela, o campo sumia sem nada ficar vermelho — e esse é o ponto desta guarda:
    ela pergunta ao IMPL o que ele produz, então uma quarta chave nasce coberta,
    e continua coberta no dia em que alguém apagar a tool MCP.

    O ``==`` é deliberado. ``<=`` deixaria o modelo declarar campo que o impl
    não produz, que é a mesma desonestidade no sentido inverso.
    """
    from dna_cli._rest_models import GraphRefEdge

    produzidas = _rest_refs("Story", "s-x", {"depth": 3, "direction": "both"}).json()
    assert produzidas["edges"], "a travessia não achou nada — a fixture, não a guarda"

    declaradas = set(GraphRefEdge.model_fields)
    for aresta in produzidas["edges"]:
        assert set(aresta) == declaradas, (
            "o modelo REST e o impl discordam sobre as chaves de uma aresta.\n"
            f"  só no impl:   {sorted(set(aresta) - declaradas)}\n"
            f"  só no modelo: {sorted(declaradas - set(aresta))}\n"
            "Um campo que o impl produz e o modelo não declara é DESCARTADO "
            "pelo FastAPI, em silêncio — o cliente não distingue isso de "
            "'o campo não existe'."
        )


@pytest.mark.parametrize("params", [
    {},
    {"as_of": "2099-01-01"},
])
def test_o_modelo_REST_declara_toda_chave_de_TOPO_que_o_impl_produz(
    sql_dir, params,
):
    """⚠️ A metade que a guarda de cima NÃO cobria — e a fatia 4 escreve nela.

    A guarda irmã compara as chaves de uma ARESTA. O envelope de topo passava
    livre, e é exatamente onde ``as_of`` e ``as_of_truncated`` nasceram: uma
    resposta histórica cujo ``as_of`` fosse descartado pelo ``response_model``
    voltaria indistinguível de uma resposta do PRESENTE, sob um 200. É o i-106
    de novo, um nível acima.

    Os dois parâmetros rodam de propósito: o envelope vivo e o histórico têm de
    declarar o MESMO conjunto de chaves, senão "o campo não veio" e "o campo não
    se aplica" se leem igual.
    """
    from dna_cli._rest_models import GraphRefsResponse

    corpo = _rest_refs("Story", "s-x", params).json()
    declaradas = set(GraphRefsResponse.model_fields)
    assert set(corpo) == declaradas, (
        "o modelo REST e o impl discordam sobre as chaves do ENVELOPE.\n"
        f"  só no impl:   {sorted(set(corpo) - declaradas)}\n"
        f"  só no modelo: {sorted(declaradas - set(corpo))}"
    )
