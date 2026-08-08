"""O preço do modelo vem do `ModelProfile` — não do código de ninguém.

`Story/s-preco-vem-do-modelprofile` · `Spec/spec-rendimento-do-copiloto`.

O #359 deixou o dinheiro dependendo de um :class:`~dna.runtime.roi.ModelPrice`
que o CHAMADOR montava. Esta story dá endereço ao número: ele já existia como
dado declarado em ``ModelProfile.cost_per_1m_input_usd`` /
``cost_per_1m_output_usd``, e o cabeçalho daquele Kind já tinha escrito a lição
com o incidente que a motivou — *o teto vivia no código de ninguém*.

⭐ **O teste que decide esta story é o da SOMA PARCIAL.** Com dois modelos na
amostra e preço para um só, cobrar só o que tem preço produz um número MENOR
que o real, com cara de medição — e custo subestimado é o erro que mais engana.
`test_o_custo_NUNCA_soma_so_o_que_tem_preco` afirma sobre o valor, não só sobre
o tipo: um mutante que somasse parcialmente tem de deixá-lo vermelho.

⚠️ **Os números desta suíte são medidos, não inventados.** No Postgres de
desenvolvimento, em 08/08/2026: ZERO instância de `ModelProfile`, e o
``dna_turn`` carimbando 74 turnos em ``gpt-5.4``, 1 em
``gpt-5.4-2026-03-05`` (um snapshot datado — daí o alias importar), 1 em
``gpt-5-mini`` e 9 sem modelo nenhum.
"""
from __future__ import annotations

import pathlib
from datetime import datetime, timezone

import pytest
import yaml

from dna.runtime.roi import (
    MEASURED,
    MODEL_PROFILE_KIND,
    NO_MODEL_PRICE,
    PRICE_FIELDS,
    PRICE_FROM_CALLER,
    PRICE_QUOTE_FIELDS,
    PRICE_STALE_AFTER_DAYS,
    PROFILE_PRICE_CURRENCY,
    ModelPrice,
    NotCalculable,
    Number,
    PriceBook,
    as_price_book,
    gather_prices,
    price_age_days,
    price_book,
    read_yield,
    render,
    sample_from_turns,
)

#: O relógio desta suíte. ⚠️ FIXO de propósito: um teste de idade que consulte
#: o relógio real fica verde hoje e vermelho daqui a noventa dias, e ninguém
#: saberia dizer se o que mudou foi o código.
AGORA = datetime(2026, 8, 8, tzinfo=timezone.utc)

COPILOT = {
    "value_per_outcome": {
        "human_minutes": 30,
        "hourly_cost": 60,
        "currency": "USD",
    }
}

ENTRADA, SAIDA = PRICE_FIELDS


def _perfil(model_id: str, *, entrada=0.25, saida=2.0, aliases=None, **extra) -> dict:
    """Uma linha crua de `ModelProfile`, como `kernel.query` a devolve."""
    spec = {
        "model_id": model_id,
        "provider": "test",
        ENTRADA: entrada,
        SAIDA: saida,
        "aliases": aliases or [],
    }
    spec.update(extra)
    return {
        "apiVersion": "github.com/ruinosus/dna/modelreg/v1",
        "kind": MODEL_PROFILE_KIND,
        "metadata": {"name": model_id},
        "spec": spec,
    }


def _turno(**kw) -> dict:
    linha = {
        "model": "gpt-5.4",
        "input_tokens": 1000,
        "output_tokens": 500,
        "tokens_partial": False,
        "outcome": "",
    }
    linha.update(kw)
    return linha


# ── AC 1: com o Kind declarado, o custo sai em dinheiro, apontando o Kind ────


def test_com_o_ModelProfile_declarado_o_custo_sai_em_dinheiro():
    """AC 1. O preço vem do Kind, e a conta é a mesma de sempre."""
    amostra = sample_from_turns([_turno(), _turno()])
    r = read_yield(
        amostra, copilot=COPILOT, prices=price_book([_perfil("gpt-5.4")])
    )

    assert isinstance(r.cost, Number)
    assert r.cost.unit == PROFILE_PRICE_CURRENCY
    assert r.cost.value == pytest.approx(2 * (1000 * 0.25 + 500 * 2.0) / 1e6)
    assert r.cost.basis == MEASURED


def test_a_origem_do_custo_aponta_para_o_KIND_e_nao_para_o_chamador():
    """⭐ Regra 4 da story: o `source` deixa de dizer "o chamador".

    Não é cosmético — é a única coisa que, na tela, distingue um número que
    veio de dado declarado de um que veio de alguém digitando.
    """
    amostra = sample_from_turns([_turno()])
    r = read_yield(
        amostra, copilot=COPILOT, prices=price_book([_perfil("gpt-5.4")])
    )

    assert MODEL_PROFILE_KIND in r.cost.source
    assert "gpt-5.4" in r.cost.source
    assert ENTRADA in r.cost.source and SAIDA in r.cost.source
    assert PRICE_FROM_CALLER not in r.cost.source
    # E na TELA, não só no objeto: a origem é impressa junto do número.
    linhas = render(r)
    i = next(i for i, l in enumerate(linhas) if l.startswith("Custo (tokens):"))
    assert MODEL_PROFILE_KIND in linhas[i + 1]


def test_a_moeda_vem_do_NOME_do_campo_e_nao_de_um_palpite():
    """``cost_per_1m_input_usd`` termina em ``_usd``. Isso é uma declaração."""
    assert ENTRADA.endswith("_usd") and SAIDA.endswith("_usd")
    livro = price_book([_perfil("gpt-5.4")])
    assert livro.prices["gpt-5.4"].currency == PROFILE_PRICE_CURRENCY
    assert PROFILE_PRICE_CURRENCY in livro.prices["gpt-5.4"].source


# ── ⭐ AC 2: um modelo sem preço NÃO vira soma parcial ───────────────────────


def test_o_custo_NUNCA_soma_so_o_que_tem_preco():
    """⭐ **O mutante desta story.** Dois modelos, preço para um só.

    A asserção não é só "é NotCalculable": é que NENHUM número da leitura
    carrega a soma parcial. Um `_cost` que ignorasse o modelo sem preço
    devolveria exatamente ``parcial`` — menor que o real, com cara de medição.
    """
    amostra = sample_from_turns(
        [_turno(), _turno(model="claude-opus-5", input_tokens=4000, output_tokens=9000)]
    )
    livro = price_book([_perfil("gpt-5.4")])
    r = read_yield(amostra, copilot=COPILOT, prices=livro)

    parcial = (1000 * 0.25 + 500 * 2.0) / 1e6
    assert isinstance(r.cost, NotCalculable)
    assert r.cost.reason == NO_MODEL_PRICE
    assert r.cost.missing == ("claude-opus-5",)
    for campo in ("cost", "ratio"):
        resposta = getattr(r, campo)
        assert not isinstance(resposta, Number) or resposta.value != pytest.approx(
            parcial
        ), "a soma PARCIAL vazou para a leitura"


def test_o_modelo_que_falta_sai_pelo_NOME_que_o_dna_turn_carimbou():
    """AC 2/3 — e o ``model_id`` tem de ser o exato, ou ninguém sabe o que
    declarar."""
    amostra = sample_from_turns(
        [_turno(model="gpt-5.4"), _turno(model="gpt-5-mini")]
    )
    r = read_yield(amostra, copilot=COPILOT, prices=price_book([_perfil("gpt-5.4")]))
    assert r.cost.missing == ("gpt-5-mini",)
    assert "gpt-5-mini" in r.cost.detail


# ── ⭐ AC 3: ZERO perfil (o estado medido) → "declare ISTO" ──────────────────


def test_sem_NENHUM_ModelProfile_a_leitura_diz_QUAL_declarar():
    """⭐ O estado do banco de dev em 08/08/2026: zero instância do Kind.

    Não-calculável é a resposta CERTA no dia um. O que ela não pode fazer é
    calar qual modelo declarar — "não sei" tem de virar "declare isto".
    """
    amostra = sample_from_turns(
        [_turno() for _ in range(74)]
        + [_turno(model="gpt-5-mini", input_tokens=0, output_tokens=0)]
        + [_turno(model="", input_tokens=0, output_tokens=0) for _ in range(9)]
    )
    r = read_yield(amostra, copilot=COPILOT, prices=price_book([]))

    assert isinstance(r.cost, NotCalculable)
    assert r.cost.reason == NO_MODEL_PRICE
    # Só o modelo que gastou token precisa de preço; o de zero token e conta
    # FECHADA não entra, e o turno sem modelo tampouco.
    assert r.cost.missing == ("gpt-5.4",)
    assert MODEL_PROFILE_KIND in r.cost.detail
    assert "gpt-5.4" in r.cost.detail
    assert ENTRADA in r.cost.detail and SAIDA in r.cost.detail
    assert "model-profiles/" in r.cost.detail
    # E a instrução chega à TELA, que é onde alguém a lê.
    assert any("gpt-5.4" in l and "falta" in l for l in render(r))


def test_a_instrucao_distingue_CRIAR_de_COMPLETAR():
    """Perfil ausente pede criar; perfil que existe e não cotou pede completar,
    dizendo o campo. Colapsar as duas em "faltou" dá a instrução errada."""
    amostra = sample_from_turns(
        [_turno(model="sem-perfil"), _turno(model="perfil-sem-cotacao")]
    )
    livro = price_book([_perfil("perfil-sem-cotacao", saida=None)])
    r = read_yield(amostra, copilot=COPILOT, prices=livro)

    assert "DECLARE" in r.cost.detail and "sem-perfil" in r.cost.detail
    assert "COMPLETE" in r.cost.detail and SAIDA in r.cost.detail
    assert set(r.cost.missing) == {"sem-perfil", "perfil-sem-cotacao"}


def test_um_turno_SEM_modelo_carimbado_nao_manda_declarar_um_perfil_impossivel():
    """Uso a cobrar num turno sem `model`: não há ``model_id`` a declarar — o
    que está quebrado é o carimbo, e a frase tem de dizer isso."""
    amostra = sample_from_turns(
        [_turno(model="", input_tokens=0, output_tokens=0, tokens_partial=True)]
    )
    r = read_yield(amostra, copilot=COPILOT, prices=price_book([_perfil("gpt-5.4")]))
    assert isinstance(r.cost, NotCalculable)
    assert "carimbo" in r.cost.detail


# ── ⭐ AC 4: `null` é AUSENTE, jamais zero ──────────────────────────────────


def test_um_preco_NULL_e_ausencia_e_NUNCA_zero():
    """⭐ O mutante: ``null`` virando ``0.0``.

    Um custo ZERO para um modelo caro é a pior saída possível — ele não parece
    um erro, parece uma boa notícia.
    """
    livro = price_book([_perfil("gpt-5.4", entrada=None, saida=None)])

    assert livro.prices == {}
    assert livro.incomplete["gpt-5.4"] == PRICE_FIELDS

    amostra = sample_from_turns([_turno()])
    r = read_yield(amostra, copilot=COPILOT, prices=livro)
    assert isinstance(r.cost, NotCalculable), "um `null` virou preço"
    assert not any(
        isinstance(x, Number) and x.unit == PROFILE_PRICE_CURRENCY and x.value == 0.0
        for x in (r.cost, r.value, r.ratio)
    )


def test_meia_cotacao_nao_e_meio_preco():
    """Input declarado, output ``null``: cobrar só o input é um custo menor que
    o real — a mesma recusa de `value_per_outcome`."""
    livro = price_book([_perfil("gpt-5.4", saida=None)])
    assert livro.prices == {}
    assert livro.incomplete["gpt-5.4"] == (SAIDA,)


def test_um_preco_ZERO_DECLARADO_e_uma_declaracao_e_passa():
    """Ausente não é zero; zero declarado é zero — um modelo self-hosted a
    custo marginal nulo é uma cotação legítima."""
    livro = price_book([_perfil("modelo-local", entrada=0, saida=0)])
    assert livro.prices["modelo-local"].input_per_million == 0.0
    assert "modelo-local" not in livro.incomplete


@pytest.mark.parametrize("lixo", [True, False, "0.25", "", [], {}, -1.0])
def test_o_que_NAO_e_numero_nao_e_preco(lixo):
    """``float(True)`` é ``1.0`` — um preço de US$ 1,00/1M inventado a partir de
    um booleano é pior que preço nenhum. Negativo idem."""
    livro = price_book([_perfil("x", entrada=lixo)])
    assert livro.prices == {}
    assert ENTRADA in livro.incomplete["x"]


# ── o alias: medido, e não opcional ─────────────────────────────────────────


def test_um_SNAPSHOT_DATADO_resolve_pelo_alias_do_perfil():
    """⚠️ Medido no dev: 74 turnos em ``gpt-5.4`` e 1 em ``gpt-5.4-2026-03-05``.

    Sem a segunda passada por ``aliases[]`` aquele ÚNICO turno tornaria a conta
    inteira não-calculável — pela regra 1, que é a regra certa. O defeito não
    seria a regra; seria o registro não ter sido consultado como
    `kernel.model_profile()` consulta.
    """
    amostra = sample_from_turns(
        [_turno() for _ in range(74)]
        + [_turno(model="gpt-5.4-2026-03-05", input_tokens=163, output_tokens=20)]
    )
    livro = price_book([_perfil("gpt-5.4", aliases=["gpt-5.4-2026-03-05"])])
    r = read_yield(amostra, copilot=COPILOT, prices=livro)

    assert isinstance(r.cost, Number), "o snapshot datado ficou órfão"
    assert r.cost.value == pytest.approx(
        (74 * 1000 + 163) * 0.25 / 1e6 + (74 * 500 + 20) * 2.0 / 1e6
    )


def test_um_alias_NUNCA_rouba_a_chave_de_um_model_id():
    """As duas passadas na ordem de `kernel.model_profile()`: ``model_id``
    primeiro, ``aliases[]`` depois."""
    livro = price_book(
        [
            _perfil("impostor", entrada=99.0, saida=99.0, aliases=["gpt-5.4"]),
            _perfil("gpt-5.4", entrada=0.25, saida=2.0),
        ]
    )
    assert livro.prices["gpt-5.4"].input_per_million == 0.25


# ── a porta: `gather_prices` atravessando o kernel de verdade ───────────────


@pytest.mark.asyncio
async def test_gather_prices_resolve_pelo_registro_REAL_do_kernel(tmp_path):
    """⭐ A guarda ATRAVESSANDO a porta, com um `Kernel` e o Kind de verdade —
    não um dublê que concorda com o meu palpite sobre o formato da linha."""
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.extensions.modelreg import ModelRegExtension
    from dna.kernel import Kernel

    k = Kernel()
    k.load(ModelRegExtension())
    src = FilesystemWritableSource(str(tmp_path / ".dna"))
    k.source(src)
    src.attach_kernel(k)
    await k.write_instance(
        "_lib", MODEL_PROFILE_KIND, "gpt-5.4",
        _perfil("gpt-5.4", aliases=["gpt-5.4-2026-03-05"]),
    )
    await k.write_instance(
        "_lib", MODEL_PROFILE_KIND, "sem-cotacao",
        _perfil("sem-cotacao", entrada=None, saida=None),
    )

    amostra = sample_from_turns(
        [
            _turno(),
            _turno(model="gpt-5.4-2026-03-05"),
            _turno(model="sem-cotacao"),
            _turno(model="nunca-declarado"),
            _turno(model="", input_tokens=0, output_tokens=0),
        ]
    )
    livro = await gather_prices(k, amostra)

    # ⭐ A chave é o nome que o `dna_turn` CARIMBOU, mesmo casando por alias.
    assert set(livro.prices) == {"gpt-5.4", "gpt-5.4-2026-03-05"}
    assert livro.incomplete == {"sem-cotacao": PRICE_FIELDS}
    assert "nunca-declarado" not in livro.prices

    r = read_yield(amostra, copilot=COPILOT, prices=livro)
    assert isinstance(r.cost, NotCalculable)
    assert set(r.cost.missing) == {"sem-cotacao", "nunca-declarado"}
    assert "COMPLETE" in r.cost.detail and "DECLARE" in r.cost.detail


@pytest.mark.asyncio
async def test_gather_prices_com_ZERO_perfil_devolve_livro_VAZIO_e_nao_zero(tmp_path):
    """O estado de hoje, pela porta: nenhum perfil, livro vazio, custo
    não-calculável — e nada de US$ 0,00."""
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.extensions.modelreg import ModelRegExtension
    from dna.kernel import Kernel

    k = Kernel()
    k.load(ModelRegExtension())
    src = FilesystemWritableSource(str(tmp_path / ".dna"))
    k.source(src)
    src.attach_kernel(k)

    amostra = sample_from_turns([_turno()])
    livro = await gather_prices(k, amostra)
    assert not livro

    r = read_yield(amostra, copilot=COPILOT, prices=livro)
    assert isinstance(r.cost, NotCalculable)
    assert r.cost.missing == ("gpt-5.4",)


@pytest.mark.asyncio
async def test_gather_prices_aceita_uma_lista_de_modelos_alem_da_amostra():
    """A porta serve quem tem a amostra E quem só tem nomes."""

    class _KernelFalso:
        async def model_profile(self, nome):
            return _perfil("gpt-5.4") if nome == "gpt-5.4" else None

    livro = await gather_prices(_KernelFalso(), ["gpt-5.4", "outro", ""])
    assert set(livro.prices) == {"gpt-5.4"}


# ── a guarda contra o descritor: os campos são do KIND, não meus ────────────


def _descritor() -> dict:
    import dna.extensions.modelreg as modelreg

    caminho = (
        pathlib.Path(modelreg.__file__).parent / "kinds" / "model-profile.kind.yaml"
    )
    return yaml.safe_load(caminho.read_text(encoding="utf-8"))


def test_os_campos_de_preco_existem_NO_KIND_com_o_nome_que_o_codigo_usa():
    """⚠️ `PRICE_FIELDS` é enumerado em `roi.py`; esta é a guarda que impede o
    drift — a mesma disciplina de `DECISIONS` contra o middleware do HITL.

    Uma renomeação no descritor sem esta guarda deixaria a resolução lendo
    ``None`` para sempre, e "declare isto" viraria a resposta permanente para
    um perfil que está declarado.
    """
    props = _descritor()["spec"]["schema"]["properties"]
    for campo in PRICE_FIELDS:
        assert campo in props, f"{campo} sumiu do {MODEL_PROFILE_KIND}"


def test_o_schema_do_KIND_admite_null_de_PROPOSITO():
    """A razão da regra 2 está escrita no descritor: ``type: [number, "null"]``.
    Se um dia o Kind exigir o número, esta suíte tem de saber."""
    props = _descritor()["spec"]["schema"]["properties"]
    for campo in PRICE_FIELDS:
        assert "null" in props[campo]["type"]
        assert campo not in _descritor()["spec"]["schema"].get("required", [])


# ── i-101 (decidida em 08/08/2026): de QUANDO é o preço ─────────────────────


def test_os_campos_de_PROCEDENCIA_da_cotacao_existem_no_Kind_e_sao_OPCIONAIS():
    """⚠️ `i-101`. A guarda contra o descritor, e ela afirma as DUAS metades.

    Os campos existem — senão a leitura leria ``None`` para sempre. E NÃO são
    `required` — porque `required` em JSON Schema é incondicional, e este Kind
    serve dois públicos no mesmo objeto: quem registra teto de token e quem
    registra preço. Exigir `cost_quoted_at` de quem só declara
    `instruction_token_cap` empurra a pessoa a INVENTAR uma data, e uma data
    inventada lê como conhecimento.
    """
    schema = _descritor()["spec"]["schema"]
    for campo in PRICE_QUOTE_FIELDS:
        assert campo in schema["properties"], f"{campo} sumiu do Kind"
        assert "null" in schema["properties"][campo]["type"]
        assert campo not in schema.get("required", [])


def test_a_cotacao_DECLARADA_sobe_do_Kind_ate_a_tela():
    """Data e procedência viajam até a linha do número — é lá que alguém lê."""
    livro = price_book(
        [_perfil("gpt-5.4", cost_quoted_at="2026-08-01", cost_source="models.dev")]
    )
    preco = livro.prices["gpt-5.4"]
    assert preco.quoted_at == "2026-08-01"
    assert preco.quote_source == "models.dev"

    r = read_yield(
        sample_from_turns([_turno()]),
        copilot=COPILOT,
        prices=livro,
        now=AGORA,
    )
    assert not r.cost.is_suspect
    assert "models.dev" in r.cost.source
    linha = next(l for l in render(r) if l.startswith("Custo (tokens):"))
    assert "⚠ SUSPEITO" not in linha


def test_um_preco_ACIMA_do_teto_de_idade_marca_o_dinheiro_como_SUSPEITO():
    """⭐ O molde do `is_floor`: o número SAI, com a marca na mesma linha.

    Recusar aqui jogaria fora uma medição por causa de um metadado — a
    diferença entre "não dá para calcular" e "dá, com ressalva".
    """
    livro = price_book([_perfil("gpt-5.4", cost_quoted_at="2026-01-01")])
    r = read_yield(
        sample_from_turns([_turno()]), copilot=COPILOT, prices=livro, now=AGORA
    )

    assert isinstance(r.cost, Number) and r.cost.value > 0
    assert r.cost.is_suspect
    assert "PREÇO VELHO" in r.cost.source
    linha = next(l for l in render(r) if l.startswith("Custo (tokens):"))
    assert "⚠ SUSPEITO" in linha, "a marca ficou guardada onde ninguém olha"
    assert any("SUSPEITO" in n and "teto" in n for n in r.notes)


def test_o_teto_de_idade_e_POLITICA_e_o_chamador_pode_troca_lo():
    """Um teto chumbado tem o mesmo defeito de um preço chumbado. Contrato
    negociado é estável por um ano; página pública não é."""
    livro = price_book([_perfil("gpt-5.4", cost_quoted_at="2026-01-01")])
    amostra = sample_from_turns([_turno()])

    assert read_yield(
        amostra, copilot=COPILOT, prices=livro, now=AGORA
    ).cost.is_suspect
    frouxo = read_yield(
        amostra, copilot=COPILOT, prices=livro, now=AGORA, price_max_age_days=365
    )
    assert not frouxo.cost.is_suspect


def test_o_teto_PADRAO_e_declarado_COM_RAZAO_ESCRITA_E_DATA():
    """⭐ Como os ~US$ 90 do `can_sleep`: uma constante nomeada, com a razão e a
    data ao lado dela — não um número solto dentro de um `if`.

    A asserção é sobre o TEXTO junto da constante, e é de propósito: uma
    política sem razão escrita vira, no leitor seguinte, um número que ninguém
    sabe por que está ali — e ninguém ousa mudar.
    """
    import dna.runtime.roi as roi

    assert PRICE_STALE_AFTER_DAYS == 90.0
    fonte = pathlib.Path(roi.__file__).read_text(encoding="utf-8")
    # As linhas de comentário coladas na constante, remontadas numa frase só —
    # a razão está escrita ali quebrada em várias linhas, e a asserção não pode
    # depender de ONDE a quebra caiu.
    cabecalho = " ".join(
        l.lstrip("#: ").strip()
        for l in fonte.split("PRICE_STALE_AFTER_DAYS = ")[0].splitlines()[-20:]
    )
    assert "POLÍTICA, não medição" in cabecalho
    assert "08/08/2026" in cabecalho
    # E o número não pode estar chumbado num segundo lugar: DEPOIS da
    # declaração, só o NOME circula. (Antes dela mora o `90.0` de
    # `STANDING_REPLICA_USD_MONTH`, que é outra constante e outra razão.)
    depois = fonte.split("PRICE_STALE_AFTER_DAYS = 90.0", 1)[1]
    assert "90" not in depois
    assert "PRICE_STALE_AFTER_DAYS" in depois


def test_IDADE_DESCONHECIDA_e_suspeita_e_NUNCA_lida_como_recente():
    """⭐ A saída fácil que este teste proíbe: ausente = recente.

    É o mesmo erro de presumir `can_sleep: true` — presumir o lado bom esconde
    justamente o que ninguém decidiu.
    """
    livro = price_book([_perfil("gpt-5.4")])  # sem cost_quoted_at
    assert livro.prices["gpt-5.4"].quoted_at is None

    r = read_yield(
        sample_from_turns([_turno()]), copilot=COPILOT, prices=livro, now=AGORA
    )
    assert r.cost.is_suspect, "um preço sem data foi tratado como novo"
    assert "IDADE DESCONHECIDA" in r.cost.source
    assert "NÃO é recente" in r.cost.source
    # ⚠️ E é uma frase DIFERENTE da do preço velho: as duas dividem a marca e
    # afirmam coisas distintas sobre o mundo, como os dois pisos deste módulo.
    assert "PREÇO VELHO" not in r.cost.source


def test_uma_data_ILEGIVEL_e_idade_desconhecida_e_nao_uma_data_adivinhada():
    """`ontem`, `2026`, `""` — nada disso vira data. Adivinhar produziria uma
    idade errada com cara de declaração."""
    for lixo in ("ontem", "2026-13-45", "", "   ", None):
        livro = price_book([_perfil("gpt-5.4", cost_quoted_at=lixo)])
        assert price_age_days(livro.prices["gpt-5.4"], AGORA) is None


def test_uma_cotacao_DATADA_NO_FUTURO_nao_e_escondida():
    """Idade negativa é uma declaração estranha, e um `max(0, …)` apagaria o
    único sinal de que alguém digitou o ano errado."""
    livro = price_book([_perfil("gpt-5.4", cost_quoted_at="2027-01-01")])
    assert price_age_days(livro.prices["gpt-5.4"], AGORA) < 0

    r = read_yield(
        sample_from_turns([_turno()]), copilot=COPILOT, prices=livro, now=AGORA
    )
    assert r.cost.is_suspect
    assert "FUTURO" in r.cost.source


def test_um_preco_de_chamador_TAMBEM_e_de_idade_desconhecida():
    """A pressão que empurra para o Kind: um `ModelPrice` montado à mão não tem
    data, e a leitura não finge que tem."""
    r = read_yield(
        sample_from_turns([_turno()]),
        copilot=COPILOT,
        prices={"gpt-5.4": ModelPrice(0.25, 2.0, "USD")},
        now=AGORA,
    )
    assert r.cost.is_suspect and "IDADE DESCONHECIDA" in r.cost.source


def test_a_marca_de_SUSPEITO_nao_se_confunde_com_a_de_PISO():
    """Dois qualificadores, dois eixos: um diz que o VALOR é limite inferior, o
    outro que a ENTRADA é duvidosa. Colapsá-los perderia informação."""
    livro = price_book([_perfil("gpt-5.4", cost_quoted_at="2026-08-01")])
    r = read_yield(
        sample_from_turns([_turno(tokens_partial=True)]),
        copilot=COPILOT,
        prices=livro,
        now=AGORA,
    )
    assert r.cost.is_floor and not r.cost.is_suspect
    linha = next(l for l in render(r) if l.startswith("Custo (tokens):"))
    assert "≥ PISO" in linha and "⚠ SUSPEITO" not in linha


def test_o_cache_de_prompt_NAO_tem_preco_porque_NAO_tem_CONTADOR():
    """⚠️ MEDIDO em 08/08/2026: `dna_turn` não tem coluna de cache e a telemetria
    não lê atributo de cache. O `models.dev` publica `cache_read`/`cache_write`
    e nós não os importamos — de propósito.

    Preço de uma quantidade que ninguém conta é campo decorativo, e decorativo é
    pior que ausente porque ausente se vê. Esta guarda fica VERMELHA no dia em
    que o contador nascer, que é o dia de acrescentar o preço.
    """
    import dataclasses

    from dna.runtime import telemetry

    # O CONTADOR: os campos do turno gravado, e os atributos de span que a
    # telemetria sabe ler. Nenhum dos dois fala de cache.
    campos = {f.name for f in dataclasses.fields(telemetry.Turn)}
    atributos = {
        a for nome in dir(telemetry) if nome.startswith("ATTR_")
        for a in getattr(telemetry, nome)
    }
    assert not [c for c in campos if "cache" in c], (
        f"`Turn` passou a contar cache ({campos}) — o preço de cache agora TEM "
        "contador e deve entrar no ModelProfile"
    )
    assert not [a for a in atributos if "cache" in a.lower()], (
        "a telemetria passou a LER cache do span — idem"
    )
    # E o PREÇO: enquanto não há contador, não há campo de preço de cache.
    props = _descritor()["spec"]["schema"]["properties"]
    assert not [p for p in props if "cache" in p], (
        "um preço de cache entrou no Kind sem um contador que o alimente"
    )


# ── compatibilidade: o formato anterior a esta story continua válido ────────


def test_um_Mapping_de_ModelPrice_continua_aceito():
    """O painel do dna-cloud está construído contra a forma anterior. Esta
    story ACRESCENTA; não renomeia e não remove."""
    amostra = sample_from_turns([_turno()])
    r = read_yield(
        amostra, copilot=COPILOT, prices={"gpt-5.4": ModelPrice(0.25, 2.0, "USD")}
    )
    assert isinstance(r.cost, Number)
    assert PRICE_FROM_CALLER in r.cost.source


def test_as_price_book_normaliza_as_tres_entradas():
    assert as_price_book(None) == PriceBook()
    livro = PriceBook(prices={"m": ModelPrice(1.0, 2.0, "USD")})
    assert as_price_book(livro) is livro
    assert as_price_book({"m": ModelPrice(1.0, 2.0, "USD")}).prices["m"].currency == "USD"


def test_um_livro_VAZIO_e_falso_e_um_livro_so_com_buracos_NAO_e():
    """⭐ Vazio é achado, e os dois vazios não são o mesmo: "ninguém declarou
    nada" e "declararam e não cotaram" pedem coisas diferentes."""
    assert not PriceBook()
    assert PriceBook(incomplete={"m": PRICE_FIELDS})
