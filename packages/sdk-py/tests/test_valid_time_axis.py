"""O eixo de VALIDADE — a coluna, a restrição, a projeção e a recusa.

Fatia 3 de ``spec-topologia-do-grafo``. Cada asserção aqui existe contra um
mutante NOMEADO, porque uma guarda que não sabe o que veria mudar é a guarda
que esta casa já perdeu duas vezes (``guardas-enumeracao-vs-derivacao``).

O mutante principal, e o motivo desta fatia existir:

    **tire a ``EXCLUDE USING gist (id WITH =, valid_at WITH &&)`` e
    ``test_overlapping_windows_for_the_same_id_are_REFUSED`` fica vermelho.**

Os outros, um por teste, ditos no docstring de cada um. Nenhum deles pergunta
"alguém captura isso em algum lugar?" — todos perguntam "ESTA porta captura?".

⚠️ Os testes de Postgres só rodam com ``DATABASE_URL`` setado (o CI sdk-tests
não tem serviço PG). Os de sqlite e os de projeção pura rodam sempre — e são
justamente os que provam a RECUSA, que é a metade que o CI enxerga.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from dna.kernel.capabilities import derive_capabilities
from dna.kernel.valid_time import (
    ValidTimeUnsupported,
    ValidWindow,
    normalize_valid_at,
    valid_window_of,
)

_PG_URL = os.environ.get("DATABASE_URL")
_needs_pg = pytest.mark.skipif(
    not _PG_URL, reason="DATABASE_URL not set — the pg dialect row is skipped",
)


def _envelope(name: str, *, valid_from=None, valid_to=None, instance_id=None):
    spec: dict = {"body": name}
    if valid_from is not None:
        spec["valid_from"] = valid_from
    if valid_to is not None:
        spec["valid_to"] = valid_to
    meta: dict = {"name": name}
    if instance_id is not None:
        meta["id"] = instance_id
    return {
        "apiVersion": "github.com/ruinosus/dna/v1", "kind": "Engram",
        "metadata": meta, "spec": spec,
    }


def _iid() -> str:
    """A well-formed 12-char instance id from the house alphabet."""
    import string
    alphabet = string.ascii_lowercase + "234567"
    n = uuid.uuid4().int
    out = []
    for _ in range(12):
        out.append(alphabet[n % 32])
        n //= 32
    return "".join(out)


# ---------------------------------------------------------------------------
# 1. A projeção — spec → janela. Pura, sem banco.
# ---------------------------------------------------------------------------

def test_an_instance_that_says_nothing_gets_the_UNBOUNDED_window():
    """Mutante: fazer ``valid_window_of`` devolver ``None`` (ou levantar) para
    uma spec sem os campos. As 400 instâncias de 414 que não dizem nada
    passariam a não ter janela, a coluna nasceria NULL nelas, e a ``EXCLUDE``
    (que pula operando NULL) deixaria de valer para 96,6% da tabela."""
    w = valid_window_of(_envelope("nada"))
    assert w == ValidWindow(None, None)
    assert not w.bounded, (
        "'não disse nada' e 'disse sempre' têm o mesmo VALOR e são fatos "
        "diferentes — ``bounded`` é o único jeito de contar um sem o outro"
    )
    assert w.contains(datetime(1999, 1, 1, tzinfo=timezone.utc))


def test_the_projection_reads_the_fields_remember_and_forget_actually_write():
    """Mutante: trocar ``valid_from``/``valid_to`` por qualquer outro nome de
    campo. A coluna existiria, a porta existiria, e ninguém a preencheria —
    "capacidade existe, porta não", que esta casa pagou três vezes. Os nomes
    aqui NÃO são escolha desta fatia: são o que ``dna.memory.verbs.remember``
    semeia e ``forget`` grava, e é por isso que a coluna já nasce com dado."""
    from dna.memory import verbs

    src = verbs.remember.__doc__ or ""
    assert "valid_from" in src
    w = valid_window_of(_envelope(
        "e", valid_from="2026-01-01T00:00:00Z", valid_to="2026-02-01T00:00:00Z",
    ))
    assert w.lower == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert w.upper == datetime(2026, 2, 1, tzinfo=timezone.utc)


def test_the_window_is_HALF_OPEN_so_a_supersession_chain_does_not_overlap():
    """Mutante: fechar o intervalo (``[]`` em vez de ``[)``).

    Não é preciosismo de convenção — foi MEDIDO na base do founder em
    06/08/2026: ``rem-dea6703a48`` fecha em ``2026-08-06T09:12:56Z`` e
    ``rem-fe60fa22ec``, a memória que a substituiu, abre no MESMO instante.
    Com intervalo fechado as duas se sobrepõem em um ponto; se um dia elas
    dividirem um ``id`` (é a mesma coisa, corrigida), a ``EXCLUDE`` recusaria
    a correção — a operação que o eixo existe para permitir."""
    handoff = datetime(2026, 8, 6, 9, 12, 56, tzinfo=timezone.utc)
    old = valid_window_of(_envelope(
        "old", valid_from="2026-08-05T10:19:26Z", valid_to="2026-08-06T09:12:56Z"))
    new = valid_window_of(_envelope("new", valid_from="2026-08-06T09:12:56Z"))
    assert not old.contains(handoff), "o fim é EXCLUSIVO"
    assert new.contains(handoff), "o começo é INCLUSIVO"


def test_a_malformed_stored_timestamp_reads_as_unbounded_not_as_an_error():
    """Mutante: levantar em vez de devolver ``None`` no parse.

    Fail-open é deliberado e assimétrico: aqui o valor é DADO GRAVADO, e um
    ``valid_to`` corrompido meses atrás não pode tornar a instância ilegível
    nem derrubar a escrita — é a mesma escolha de ``currently_valid``. O
    argumento que chega AGORA é outra história: ver o teste seguinte."""
    w = valid_window_of(_envelope("ruim", valid_to="ontem à tarde"))
    assert w == ValidWindow(None, None)


def test_a_caller_typo_is_the_CALLERS_mistake_and_fails_loud():
    """Mutante: fazer ``normalize_valid_at`` fail-open como ``_parse``.

    Um instante inválido viraria "sem filtro", e o leitor receberia a instância
    achando que perguntou pelo tempo. Recusa de capacidade e erro de digitação
    têm remédios diferentes e só a mensagem carrega qual."""
    with pytest.raises(ValueError):
        normalize_valid_at("ontem à tarde")
    assert normalize_valid_at("2026-01-01T00:00:00Z").tzinfo is not None


def test_an_INVERTED_window_keeps_the_well_formed_half_instead_of_failing():
    """Mutante: repassar a janela invertida ao banco.

    ``tstzrange`` recusa ``lower > upper`` levantando — e isso derrubaria a
    ESCRITA INTEIRA da instância por causa de um campo de texto que discorda de
    si mesmo. Um typo de dado viraria indisponibilidade. Mutante espelhado:
    derrubar os DOIS extremos, que apagaria a metade bem formada."""
    w = valid_window_of(_envelope(
        "inv", valid_from="2026-02-01T00:00:00Z", valid_to="2026-01-01T00:00:00Z"))
    assert w.lower == datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert w.upper is None


# ---------------------------------------------------------------------------
# 2. sqlite — a RECUSA. Roda sempre, e é a metade que o CI vê.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def sqlite_source():
    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    fd, path = tempfile.mkstemp(prefix="dna-vt-", suffix=".db")
    os.close(fd)
    src = SqlAlchemySource(f"sqlite+aiosqlite:///{path}")
    await src.connect()
    yield src
    await src.close()
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.mark.asyncio
async def test_sqlite_declares_valid_time_False_and_the_oracle_agrees(sqlite_source):
    """Mutante: declarar ``valid_time=True`` no adapter (uma constante em vez de
    ``self.supports_valid_time``). O oráculo de reflexão pega — e pega porque
    ele lê o ATRIBUTO da instância, não a presença do método. Mutante irmão:
    fazer ``derive_capabilities`` sondar ``load_one_valid_at``; aí ele
    derivaria ``True`` no sqlite (o método existe e recusa) e passaria a
    certificar uma declaração mentirosa."""
    declared = sqlite_source.capabilities()
    assert declared.valid_time is False
    assert declared == derive_capabilities(sqlite_source, label=declared.source)


@pytest.mark.asyncio
async def test_sqlite_REFUSES_a_world_time_read_instead_of_answering(sqlite_source):
    """Mutante: devolver a instância sem filtrar (ou ``None``) em vez de
    levantar. Devolver a linha afirma "sim, era verdade naquele instante" numa
    loja que não tem coluna nenhuma para checar; devolver ``None`` afirma o
    contrário com a mesma ausência de base. As duas são mentiras confiantes, e
    501 é a única resposta honesta."""
    await sqlite_source.save_instance("s", "Engram", "m", _envelope("m"))
    with pytest.raises(ValidTimeUnsupported):
        await sqlite_source.load_one_valid_at(
            "s", "Engram", "m", valid_at="2026-01-01T00:00:00Z")


@pytest.mark.asyncio
async def test_the_refusal_is_catchable_as_the_FAMILY_not_by_name(sqlite_source):
    """Mutante: dar a ``ValidTimeUnsupported`` só ``RuntimeError`` como base.

    Toda face que já captura ``CapabilityRefusal`` passaria a relatar esta
    recusa como um crash — exatamente o defeito que criou a base
    (``recall(as_of=…)`` chegando ao cliente como ``Error calling tool``)."""
    from dna.kernel.errors import CapabilityRefusal, KernelRefusal

    assert issubclass(ValidTimeUnsupported, CapabilityRefusal)
    assert issubclass(ValidTimeUnsupported, RuntimeError), (
        "aditivo, nunca re-parenting: quem já capturava RuntimeError continua"
    )
    assert not issubclass(ValidTimeUnsupported, KernelRefusal), (
        "as duas bases são DISJUNTAS — esta é um fato sobre o DEPLOY, não um "
        "veredito sobre o pedido, e relatar uma como a outra manda o chamador "
        "caçar uma permissão que ele já tem"
    )


@pytest.mark.asyncio
async def test_sqlite_has_no_valid_at_column_at_all(sqlite_source):
    """Mutante: criar duas colunas TEXT no sqlite "para ter paridade".

    Elas carregariam os EXTREMOS e não a INVARIANTE — e um adapter com os
    extremos mas sem a restrição responde com confiança onde não sabe. Meia
    capacidade é pior que nenhuma, porque a nenhuma é sondável."""
    assert "valid_at" not in sqlite_source.instances.c


# ---------------------------------------------------------------------------
# 3. Postgres — a coluna e, sobretudo, a RESTRIÇÃO.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def pg_source():
    """One source per test, in its OWN throwaway schema — the same isolation
    ``test_adapter_conformance_matrix`` uses, for the same reason: the
    revisions run on ``connect()``, and a shared schema has every test
    colliding on ``alembic_version``. Function-scoped and not module-scoped
    because ``pytest-asyncio`` gives each test its own event loop, and an
    asyncpg pool built on one loop cannot be awaited from another."""
    import asyncpg

    from dna.adapters.sqlalchemy_ import SqlAlchemySource

    schema = f"dna_vt_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    conn = await asyncpg.connect(_PG_URL)
    await conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    await conn.execute(f"CREATE SCHEMA {schema}")
    await conn.close()

    src = SqlAlchemySource(
        _PG_URL.replace("postgresql://", "postgresql+asyncpg://", 1), schema=schema)
    await src.connect()
    try:
        yield src
    finally:
        await src.close()
        c = await asyncpg.connect(_PG_URL)
        await c.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        await c.close()


@_needs_pg
@pytest.mark.asyncio
async def test_pg_declares_valid_time_True_and_the_oracle_agrees(pg_source):
    """Mutante: esquecer ``valid_time=`` na declaração do adapter (fica no
    default ``False``). A face recusaria um eixo que a loja TEM — a recusa
    honesta virando uma recusa falsa, que é o outro lado do mesmo defeito."""
    declared = pg_source.capabilities()
    assert declared.valid_time is True
    assert declared == derive_capabilities(pg_source, label=declared.source)


@_needs_pg
@pytest.mark.asyncio
async def test_the_write_path_PROJECTS_the_spec_into_the_column(pg_source):
    """Mutante: não passar ``**valid_at`` no upsert.

    A coluna existiria, com a restrição e o índice, e ficaria ilimitada para
    sempre — o padrão "capacidade existe, porta não" em estado puro: verde no
    esquema, morta no produto. Este teste atravessa a PORTA de escrita, não o
    helper: é ``save_instance`` que tem de carimbar."""
    scope = f"vt-{uuid.uuid4().hex[:8]}"
    await pg_source.save_instance(scope, "Engram", "m", _envelope(
        "m", valid_from="2026-01-01T00:00:00Z", valid_to="2026-02-01T00:00:00Z"))
    assert await pg_source.load_one_valid_at(
        scope, "Engram", "m", valid_at="2026-01-15T00:00:00Z") is not None
    assert await pg_source.load_one_valid_at(
        scope, "Engram", "m", valid_at="2026-03-01T00:00:00Z") is None


@_needs_pg
@pytest.mark.asyncio
async def test_clearing_valid_to_REOPENS_the_window(pg_source):
    """Mutante: ``COALESCE(excluded.valid_at, valid_at)`` no ``ON CONFLICT``,
    copiando o que o ``id`` faz uma linha acima.

    O ``id`` merece COALESCE porque é cunhado uma vez e nunca muda; a janela é
    RE-DERIVADA da spec a cada save. Com COALESCE, um ``forget`` viraria
    irreversível na coluna enquanto o JSON dissesse o contrário — duas fontes
    de verdade para um fato, discordando em silêncio."""
    scope = f"vt-{uuid.uuid4().hex[:8]}"
    await pg_source.save_instance(scope, "Engram", "m", _envelope(
        "m", valid_from="2026-01-01T00:00:00Z", valid_to="2026-02-01T00:00:00Z"))
    await pg_source.save_instance(scope, "Engram", "m", _envelope(
        "m", valid_from="2026-01-01T00:00:00Z"))
    assert await pg_source.load_one_valid_at(
        scope, "Engram", "m", valid_at="2026-03-01T00:00:00Z") is not None


@_needs_pg
@pytest.mark.asyncio
async def test_overlapping_windows_for_the_same_id_are_REFUSED(pg_source):
    """⭐ O MUTANTE PRINCIPAL: apague a ``EXCLUDE USING gist (id WITH =,
    valid_at WITH &&)`` da revisão 0010 e ESTE teste fica vermelho.

    É a invariante inteira da fatia: uma instância tem no máximo UM estado
    verdadeiro em cada instante do mundo. Sem ela, a coluna é decoração —
    carrega os extremos e não promete nada.

    ⚠️ Mutante irmão, e é o que separa esta restrição de um simples
    ``UNIQUE (id)``: o teste seguinte exige que janelas DISJUNTAS sejam
    ACEITAS. Uma restrição que recusa as duas é forte demais e mata a
    correção histórica; uma que aceita as duas é a que não existe."""
    import sqlalchemy.exc

    scope = f"vt-{uuid.uuid4().hex[:8]}"
    shared = _iid()
    await pg_source.save_instance(scope, "Engram", "a", _envelope(
        "a", valid_from="2026-01-01T00:00:00Z", valid_to="2026-02-01T00:00:00Z",
        instance_id=shared))
    with pytest.raises(sqlalchemy.exc.IntegrityError) as exc:
        await pg_source.save_instance(scope, "Engram", "b", _envelope(
            "b", valid_from="2026-01-15T00:00:00Z", valid_to="2026-02-15T00:00:00Z",
            instance_id=shared))
    assert "exclusion" in str(exc.value).lower() or "conflicting" in str(exc.value).lower()


@_needs_pg
@pytest.mark.asyncio
async def test_DISJOINT_windows_for_the_same_id_are_ACCEPTED(pg_source):
    """Mutante: trocar a ``EXCLUDE`` por ``UNIQUE (id)``, ou por
    ``EXCLUDE (id WITH =, valid_at WITH =)``.

    As duas recusariam este caso — e este caso é a razão de o eixo existir: a
    mesma identidade, verdadeira num período e depois noutro. Sem ele a
    restrição só reimplementa unicidade de id, e nada do tempo."""
    scope = f"vt-{uuid.uuid4().hex[:8]}"
    shared = _iid()
    await pg_source.save_instance(scope, "Engram", "a", _envelope(
        "a", valid_from="2026-01-01T00:00:00Z", valid_to="2026-02-01T00:00:00Z",
        instance_id=shared))
    await pg_source.save_instance(scope, "Engram", "b", _envelope(
        "b", valid_from="2026-02-01T00:00:00Z", valid_to="2026-03-01T00:00:00Z",
        instance_id=shared))
    assert await pg_source.load_one_valid_at(
        scope, "Engram", "a", valid_at="2026-01-15T00:00:00Z") is not None
    assert await pg_source.load_one_valid_at(
        scope, "Engram", "b", valid_at="2026-02-15T00:00:00Z") is not None


@_needs_pg
@pytest.mark.asyncio
async def test_two_UNBOUNDED_rows_with_one_id_collide_which_is_the_405_row_case(pg_source):
    """Mutante: deixar a coluna NULLABLE em vez de NOT NULL DEFAULT ilimitado.

    Uma ``EXCLUDE`` PULA qualquer linha com operando NULL. Com a coluna
    nullable, as 405 de 419 instâncias que não dizem nada sobre validade
    (medido 06/08/2026) ficariam fora da restrição — uma guarda verde sobre
    96,6% da tabela, que é exatamente o defeito de "guarda cega e verde". Este
    teste prova que a restrição alcança justamente essas linhas."""
    import sqlalchemy.exc

    scope = f"vt-{uuid.uuid4().hex[:8]}"
    shared = _iid()
    await pg_source.save_instance(
        scope, "Engram", "a", _envelope("a", instance_id=shared))
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        await pg_source.save_instance(
            scope, "Engram", "b", _envelope("b", instance_id=shared))


@_needs_pg
@pytest.mark.asyncio
async def test_the_two_AXES_stay_separate(pg_source):
    """⚠️ O erro clássico do bitemporal, e o único teste desta suíte que existe
    contra um mutante de DESENHO e não de código.

    Uma nota escrita HOJE sobre o ANO PASSADO é válida no ano passado e
    acreditada hoje. Mutante: fazer ``valid_at`` cair no caminho do ``as_of``
    (ou vice-versa) — as duas leituras passariam a concordar, e é a
    DISCORDÂNCIA delas que prova que são dois eixos."""
    scope = f"vt-{uuid.uuid4().hex[:8]}"
    await pg_source.save_instance(scope, "Engram", "m", _envelope(
        "m", valid_from="2025-01-01T00:00:00Z"))
    last_year = "2025-06-01T00:00:00Z"
    # Mundo: era verdade → acha.
    assert await pg_source.load_one_valid_at(
        scope, "Engram", "m", valid_at=last_year) is not None
    # Transação: ninguém acreditava ainda → não acha.
    res = await pg_source.load_one_as_of(scope, "Engram", "m", as_of=last_year)
    assert res["raw"] is None and res["truncated"] is False, (
        "a instância foi GRAVADA agora; nada nela existia no ano passado"
    )
