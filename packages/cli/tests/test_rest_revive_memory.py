"""i-139 — ``POST /v1/memories/{name}/revive``: a memória volta, e o esquecimento fica.

``dna.memory.forget`` promete três palavras no próprio docstring desde que
existe: *auditable, point-in-time reconstructable, **revivable***. A primeira
caiu no i-130 (o delete genérico levava a linha e o histórico). Esta é a
terceira, e o grep que a mediu — ``unforget|restore|revive|undelete|recover``
sobre ``dna/`` e ``dna_cli/`` — devolveu **zero**. Capacidade prometida, porta
nenhuma; o padrão de sempre desta casa, duas vezes no mesmo docstring na mesma
semana.

⚠️ **O mutante principal, e ele é o motivo deste arquivo existir: reviver
apagando o registro do esquecimento tem de ficar VERMELHO.** É a saída (a) que a
decisão do i-139 recusou — limpar o ``valid_to`` e pronto. Ela funciona, a
memória volta, o recall responde de novo, e nenhum teste de "a memória voltou"
percebe que a data em que ela deixou de valer sumiu junto.

O que cada propriedade fixa:

* reviver reabre a janela E arquiva o intervalo fechado, **verbatim**;
* ``superseded_by_memory`` vai junto para a entrada — uma memória em vigor não
  está substituída;
* ciclos repetidos EMPILHAM entradas (os múltiplos intervalos que a coluna
  ``valid_at`` não comporta, guardados como dado);
* reviver duas vezes não empilha nem reescreve, e **não escreve nada**;
* ``revived_by`` vem do request verificado, nunca do corpo — a rota nem aceita um;
* o ``response_model`` declara toda chave que o núcleo devolve;
* um nome que esta camada não tem é 404, nunca um 200 confiante;
* outro tenant não revive a sua memória.

Tudo atravessando a porta REAL (``TestClient``). Um teste na função teria ficado
verde durante o ano inteiro em que a promessa não tinha nada atrás.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.delenv("DNA_PERSONAL_ID", raising=False)
    return dst


@pytest.fixture
def relogio(monkeypatch):
    """Um relógio FALSO, e ele não é conforto — é a diferença entre uma
    asserção que passa e uma que mede.

    ``valid_to`` / ``revived_at`` são carimbados com ``timespec="seconds"``, e
    dois eventos no mesmo teste caem na MESMA string. Medido no i-136: o mutante
    "re-carimbar a data no retry" passou VERDE por isso — a asserção era
    verdadeira independente do código. Aqui os instantes são distintos por
    construção, então "a data foi preservada" e "a data foi reescrita" produzem
    strings diferentes e só uma delas passa."""
    import dna.memory.verbs as V

    ticks = iter([f"2026-08-07T1{h}:00:00+00:00" for h in range(0, 9)])
    monkeypatch.setattr(V, "_now_iso", lambda now=None: next(ticks))
    return ticks


def _client(dna_dir, **kwargs) -> TestClient:
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE, **kwargs))


def _seed_memory(dna_dir, summary: str, *, tenant: str | None = None) -> dict:
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        return await M.remember_impl(live, summary, scope=_SCOPE, tenant=tenant)

    return asyncio.run(go())


def _names(c: TestClient, tenant: str) -> set[str]:
    r = c.get("/v1/memories", params={"scope": _SCOPE, "tenant": tenant})
    assert r.status_code == 200, r.text
    return {m["name"] for m in r.json()["memories"]}


def _spec(c: TestClient, name: str, tenant: str) -> dict:
    """A instância CRUA, pela porta genérica — a prova de que o registro ficou
    não vale nada se vier da mesma rota que afirma tê-lo guardado."""
    r = c.get(f"/v1/kinds/Engram/instances/{name}",
              params={"scope": _SCOPE, "tenant": tenant})
    assert r.status_code == 200, r.text
    body = r.json()
    return body.get("instance", body).get("spec", {})


def _forget(c: TestClient, name: str, tenant: str, **body):
    return c.post(f"/v1/memories/{name}/forget",
                  params={"scope": _SCOPE, "tenant": tenant}, json=body)


def _revive(c: TestClient, name: str, tenant: str):
    return c.post(f"/v1/memories/{name}/revive",
                  params={"scope": _SCOPE, "tenant": tenant})


# ── ⚠️ O MUTANTE PRINCIPAL ─────────────────────────────────────────────────


def test_reviver_NAO_apaga_o_registro_do_esquecimento(dna_dir, relogio):
    """⚠️ A asserção que a opção (a) — limpar o ``valid_to`` e pronto — mata.

    Aquela saída funciona: a memória volta, o recall responde, e a tela fica
    certa. O que ela perde é a data em que a memória deixou de valer, e a perda
    é invisível para qualquer teste que pergunte "voltou?". Por isso a pergunta
    aqui é a outra: **o intervalo fechado ainda está lá, com a data original?**

    Verbatim é a palavra que importa. A entrada não carrega "uma data
    plausível": carrega o MESMO ``valid_to`` que a aposentadoria tinha, que é o
    único jeito de o histórico continuar auditável depois de a memória voltar."""
    seeded = _seed_memory(dna_dir, "o deploy é às sextas", tenant="acme")
    name = seeded["name"]
    with _client(dna_dir) as c:
        assert _forget(c, name, "acme").status_code == 200
        esquecida_em = _spec(c, name, "acme")["valid_to"]

        r = _revive(c, name, "acme")
        assert r.status_code == 200, r.text
        assert r.json()["revived"] is True
        assert r.json()["outcome"] == "revived"

        spec = _spec(c, name, "acme")
        # 1. voltou a vigorar — a janela reabriu REMOVENDO o limite.
        assert "valid_to" not in spec or not spec["valid_to"]
        assert name in _names(c, "acme")

        # 2. ⚠️ e o esquecimento CONTINUA REGISTRADO, com a data original.
        revivals = spec.get("revivals") or []
        assert len(revivals) == 1, (
            "a memória voltou e o período em que ela esteve fora não ficou "
            "registrado em lugar nenhum — reviver virou apagar o esquecimento, "
            "que é exatamente a saída (a) recusada no i-139"
        )
        assert revivals[0]["valid_to"] == esquecida_em, (
            f"a entrada diz {revivals[0]['valid_to']!r} e a memória foi "
            f"esquecida em {esquecida_em!r} — uma data plausível no lugar da "
            f"verdadeira é pior que nenhuma, porque parece auditoria"
        )
        assert revivals[0]["revived_at"] > esquecida_em


def test_a_resposta_devolve_o_intervalo_e_o_response_model_nao_o_come(dna_dir, relogio):
    """Dois saltos, e cada um já comeu campo nesta casa.

    **O fio.** O ``response_model`` do FastAPI DESCARTA em silêncio o que não
    declara — foi assim que três campos sumiram num dia só. Então o intervalo é
    lido da RESPOSTA HTTP, não do retorno de ``revive_impl``.

    **A leitura.** Devolver a janela é o que faz a limitação aceita no i-139 ser
    utilizável: o eixo de MUNDO não consulta buracos passados, então quem
    precisa do buraco precisa recebê-lo. Aqui ele chega inteiro.

    Mutante: tirar ``revival`` (ou qualquer campo de ``MemoryRevival``) do
    modelo. Nada levanta, nada avisa, e isto fica vermelho."""
    seeded = _seed_memory(dna_dir, "o preço sobe em março", tenant="acme")
    name = seeded["name"]
    with _client(dna_dir) as c:
        nova = c.post("/v1/memories", params={"scope": _SCOPE, "tenant": "acme"},
                      json={"summary": "o preço sobe em abril"}).json()["name"]
        _forget(c, name, "acme", superseded_by=nova)
        esquecida_em = _spec(c, name, "acme")["valid_to"]

        r = _revive(c, name, "acme")
        assert r.status_code == 200, r.text
        rev = r.json()["revival"]
        assert rev is not None, "a resposta não devolveu o intervalo que fechou"
        assert rev["valid_to"] == esquecida_em
        assert rev["superseded_by"] == nova
        assert rev["revived_at"]
        # E o WHO chegou — resolvido no servidor, não pedido ao chamador.
        assert rev["revived_by"], (
            "sem quem reviveu, a entrada é um evento sem autor — e um audit "
            "trail sem autor é uma linha do tempo, não uma auditoria"
        )


def test_a_supersessao_vai_junto_para_a_entrada(dna_dir, relogio):
    """Uma memória de volta ao vigor NÃO está substituída, e o ponteiro tem de
    ir com o intervalo.

    Deixar ``superseded_by_memory`` para trás seria a aposentadoria continuando
    sob outro nome: a memória voltaria à lista e seguiria marcada como
    substituída para toda superfície que honra o ponteiro. Não se perde nada —
    ele está na entrada, que é onde ele descreve algo verdadeiro (*durante
    aquele intervalo*, aquela outra a substituía).

    Mutante: parar de fazer ``pop`` do ``superseded_by_memory``."""
    seeded = _seed_memory(dna_dir, "usamos yarn", tenant="acme")
    name = seeded["name"]
    with _client(dna_dir) as c:
        nova = c.post("/v1/memories", params={"scope": _SCOPE, "tenant": "acme"},
                      json={"summary": "usamos npm"}).json()["name"]
        _forget(c, name, "acme", superseded_by=nova)
        assert _spec(c, name, "acme")["superseded_by_memory"] == nova

        _revive(c, name, "acme")
        spec = _spec(c, name, "acme")
        assert not spec.get("superseded_by_memory"), (
            "a memória voltou marcada como substituída — meia revivida"
        )
        assert spec["revivals"][0]["superseded_by"] == nova, (
            "e o ponteiro não foi para lugar nenhum: sumiu"
        )


def test_ciclos_repetidos_empilham_um_intervalo_por_vez(dna_dir, relogio):
    """Os múltiplos intervalos de validade que a COLUNA não comporta, guardados
    como dado — que é a decisão inteira do i-139 em uma asserção.

    ``dna_instances`` tem uma linha por instância (PK
    scope+kind+api_version+name+tenant), então ``valid_at`` conhece só a janela
    corrente, embora a ``EXCLUDE`` aceitasse várias disjuntas por ``id``. A
    restrição permite a segunda linha; a chave primária proíbe. Aqui os
    intervalos se acumulam em ``spec.revivals``, em ordem, sem se sobrescrever.

    ⚠️ E o segundo ``forget`` carimba data NOVA — a idempotência do ``forget``
    (preservar o ``valid_to`` original) não pode disparar depois de um revive,
    porque não há mais nada ali para preservar. Se disparasse, o segundo
    intervalo nasceria com a data do primeiro."""
    seeded = _seed_memory(dna_dir, "a stand-up é às nove", tenant="acme")
    name = seeded["name"]
    with _client(dna_dir) as c:
        _forget(c, name, "acme")
        primeira = _spec(c, name, "acme")["valid_to"]
        _revive(c, name, "acme")
        _forget(c, name, "acme")
        segunda = _spec(c, name, "acme")["valid_to"]
        _revive(c, name, "acme")

        revivals = _spec(c, name, "acme")["revivals"]
        assert len(revivals) == 2, f"esperava dois intervalos, veio {revivals}"
        assert segunda > primeira, (
            "o segundo esquecimento reusou a data do primeiro — a idempotência "
            "do forget disparou onde não devia, e o histórico passa a dizer que "
            "a memória saiu de vigor duas vezes no mesmo instante"
        )
        assert [e["valid_to"] for e in revivals] == [primeira, segunda]
        # append-only: a primeira entrada é byte a byte a mesma de antes.
        assert revivals[0]["valid_to"] == primeira


# ── idempotência ───────────────────────────────────────────────────────────


def test_reviver_duas_vezes_nao_empilha_nem_escreve(dna_dir, relogio):
    """Espelho do cuidado que o ``forget`` já tem, e um passo além dele.

    Reviver o que já está em vigor não é erro (200, não 409): um cliente que
    ouve "não" ao repetir um passo que talvez tenha completado desiste ou
    começa a adivinhar. Mas também não é evento — então **nada é escrito**. Um
    no-op que ainda assim gravasse acrescentaria uma versão em ``dna_versions``
    para algo que não aconteceu, e o eixo de transação passaria a registrar
    revivals que ninguém fez. É a auditoria mentindo baixinho.

    Mutante A: empilhar uma segunda entrada. Mutante B: reescrever a primeira.
    Mutante C: gravar assim mesmo (a contagem de versões sobe)."""
    seeded = _seed_memory(dna_dir, "o time usa linear", tenant="acme")
    name = seeded["name"]
    with _client(dna_dir) as c:
        _forget(c, name, "acme")
        _revive(c, name, "acme")
        antes = _spec(c, name, "acme")["revivals"]

        r = _revive(c, name, "acme")
        assert r.status_code == 200, r.text
        assert r.json()["outcome"] == "already_in_force"
        assert r.json()["revived"] is False
        assert r.json()["revival"] is None, (
            "a repetição devolveu um intervalo, e não fechou nenhum"
        )

        depois = _spec(c, name, "acme")["revivals"]
        assert depois == antes, (
            "reviver de novo mexeu no que já estava arquivado — a data em que a "
            "memória foi esquecida É a auditoria, e um retry não é um evento"
        )


def test_reviver_o_que_nunca_foi_esquecido_e_um_no_op_limpo(dna_dir, relogio):
    """Uma memória que sempre esteve em vigor não tem intervalo para fechar.
    ``already_in_force``, lista vazia, e nenhuma entrada inventada."""
    seeded = _seed_memory(dna_dir, "nada aconteceu com esta", tenant="acme")
    with _client(dna_dir) as c:
        r = _revive(c, seeded["name"], "acme")
        assert r.status_code == 200
        assert r.json()["outcome"] == "already_in_force"
        assert not (_spec(c, seeded["name"], "acme").get("revivals") or [])


# ── identidade: do request verificado, nunca do corpo ──────────────────────


def test_quem_reviveu_vem_do_SERVIDOR_e_a_rota_nao_aceita_corpo(dna_dir, relogio):
    """Atribuição que o chamador pode forjar não é atribuição.

    A rota não declara corpo nenhum, então não há onde um cliente escrever
    ``revived_by``. O valor sai de ``_actor_from_state`` — o MESMO resolvedor
    que todo outro campo de auditoria desta face usa — e na lane sem credencial
    isso é o sentinela honesto ``rest:local``, que nomeia o CANAL e o estado de
    atestação, nunca uma pessoa que ninguém verificou.

    Duas asserções, e a segunda é a que importa: mandar um ``revived_by`` no
    corpo **não muda nada**. Um teste que só verificasse "o campo veio
    preenchido" ficaria verde com a rota lendo o corpo."""
    seeded = _seed_memory(dna_dir, "quem foi que reviveu isto", tenant="acme")
    name = seeded["name"]
    with _client(dna_dir) as c:
        _forget(c, name, "acme")
        r = c.post(f"/v1/memories/{name}/revive",
                   params={"scope": _SCOPE, "tenant": "acme"},
                   json={"revived_by": "eu-mesmo-decidi-que-sou-o-ceo"})
        assert r.status_code == 200, r.text
        quem = r.json()["revival"]["revived_by"]
        assert quem == R._UNIDENTIFIED_LOCAL_ACTOR, (
            f"a lane sem credencial tem de gravar o sentinela do CANAL; veio {quem!r}"
        )
        assert "ceo" not in (quem or "").lower(), (
            "a rota leu a identidade do CORPO — atribuição forjável não é "
            "atribuição, e este é o campo que uma auditoria vai ler"
        )


def test_o_operador_que_se_declarou_vence_o_sentinela(dna_dir, relogio, monkeypatch):
    """``DNA_PERSONAL_ID`` é o nome que o operador offline JÁ declarou para a
    memória pessoal, e ele diz mais que um sentinela. A regra não é nova nem
    minha: é a que ``_actor_from_state`` aplica em toda esta face — reusada, não
    reimplementada, que é o ponto de a rota chamar aquele resolvedor."""
    monkeypatch.setenv("DNA_PERSONAL_ID", "barna@dna.dev")
    seeded = _seed_memory(dna_dir, "o operador tem nome", tenant="acme")
    name = seeded["name"]
    with _client(dna_dir) as c:
        _forget(c, name, "acme")
        r = _revive(c, name, "acme")
        assert r.json()["revival"]["revived_by"] == "barna@dna.dev"


# ── o envelope, derivado ───────────────────────────────────────────────────


def test_o_response_model_declara_toda_chave_que_o_nucleo_devolve(dna_dir, relogio):
    """A armadilha do descarte silencioso como guarda DERIVADA, nos DOIS níveis
    (o envelope e a entrada aninhada).

    O erro real nunca é "faltou ``revived_by``": é "o núcleo cresceu e o modelo
    não". Então os conjuntos de chaves vêm do ``revive_impl`` rodando de
    verdade, não de uma lista escrita à mão que envelhece junto com o bug."""
    from dna_cli import _mcp_server as M
    from dna_cli import _rest_models as m

    seeded = _seed_memory(dna_dir, "medindo o envelope", tenant="acme")

    async def go():
        live = await M.boot_live(base_dir=str(dna_dir))
        await M.forget_impl(live, seeded["name"], scope=_SCOPE, tenant="acme",
                            superseded_by="rem-outra")
        return await M.revive_impl(live, seeded["name"], scope=_SCOPE,
                                   tenant="acme", revived_by="quem@exemplo.dev")

    out = asyncio.run(go())

    faltando = set(out) - set(m.ReviveMemoryResponse.model_fields)
    assert not faltando, (
        f"{sorted(faltando)} sairiam da resposta em silêncio — o FastAPI não "
        f"avisa, e o chamador não distingue um campo nunca enviado de um filtrado"
    )
    faltando_entrada = set(out["revival"]) - set(m.MemoryRevival.model_fields)
    assert not faltando_entrada, (
        f"{sorted(faltando_entrada)} sairiam da ENTRADA em silêncio — e é a "
        f"entrada que carrega o intervalo inteiro"
    )


# ── as duas formas de dizer não ────────────────────────────────────────────


def test_reviver_um_nome_desconhecido_e_404_com_a_particao_nomeada(dna_dir):
    """``not_found`` é 404, não um 200 dizendo que nada aconteceu — e a causa
    mais provável não é erro de digitação, é a PARTIÇÃO."""
    with _client(dna_dir) as c:
        r = c.post("/v1/memories/rem-nao-existe-00000/revive",
                   params={"scope": _SCOPE, "tenant": "acme"})
        assert r.status_code == 404, r.text
        assert "personal" in r.json()["detail"]


def test_outro_tenant_nao_revive_a_sua_memoria(dna_dir, relogio):
    """#83 na porta nova, dita pelo que NÃO pode acontecer: globex pedindo o
    revive de uma memória da acme não muda nada que a acme veja — e o 404 é o
    MESMO de um nome desconhecido, porque da camada da globex é isso que ele é.
    Um 403 confirmaria que a memória existe, e essa confirmação é o vazamento."""
    acme = _seed_memory(dna_dir, "roteiro privado da acme", tenant="acme")
    name = acme["name"]
    with _client(dna_dir) as c:
        _forget(c, name, "acme")
        esquecida_em = _spec(c, name, "acme")["valid_to"]

        r = _revive(c, name, "globex")
        assert r.status_code == 404, r.text

        spec = _spec(c, name, "acme")
        assert spec["valid_to"] == esquecida_em, "outro tenant reviveu a memória"
        assert not (spec.get("revivals") or [])
