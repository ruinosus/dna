"""`App` é o serviço, e o `Copilot` diz onde roda e quanto rende.

`Spec/spec-app-e-o-servico` + `Story/s-kinds-a-conta-declarada` (07/08/2026).

Pela PORTA, como o resto da casa: os campos novos são gravados e relidos pelo
kernel, não inspecionados no YAML. E cada asserção aqui foi escrita para
FALHAR se o campo estivesse ausente — os três schemas envolvidos declaram
`additionalProperties: false`, então uma propriedade não declarada é RECUSADA
na escrita e o round-trip não chega a acontecer. É o que torna o round-trip
uma medição e não uma formalidade.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def kernel(tmp_path):
    from dna.adapters.filesystem import FilesystemCache
    from dna.adapters.filesystem.writable import FilesystemWritableSource
    from dna.extensions.helix import HelixExtension
    from dna.kernel import Kernel

    (tmp_path / "frota").mkdir()
    k = Kernel()
    k.load(HelixExtension())
    k.source(FilesystemWritableSource(tmp_path, kernel=k))
    k.cache(FilesystemCache(tmp_path / ".dna-cache"))
    yield k


def _helix_descriptor(name: str) -> dict:
    from dna.kernel.source.descriptor_loader import load_descriptors

    raws = load_descriptors("dna.extensions.helix")
    return next(r for r in raws if r["metadata"]["name"] == name)


def _app(**extra) -> dict:
    spec = {"title": "Porta Entra", "copilots": ["memory-copilot"]}
    spec.update(extra)
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "App",
        "metadata": {"name": "mcp-entra"},
        "spec": spec,
    }


def _copilot(**extra) -> dict:
    spec = {
        "mounts": [{"id": "principal", "agent": "memory-agent", "path": "/agui"}],
        "serving": {"transport": "ag-ui"},
    }
    spec.update(extra)
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Copilot",
        "metadata": {"name": "memory-copilot"},
        "spec": spec,
    }


# ── App: os campos do serviço ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_app_grava_e_rele_os_campos_do_servico(kernel):
    """Round-trip pela porta. `additionalProperties: false` no schema do App
    significa que este teste NÃO passaria com os campos ausentes: a escrita
    seria recusada antes de haver o que reler.

    ⚠️ `python_module` saiu daqui em 07/08/2026 (`spec-campo-opcional-por-
    evidencia`): ele tem ZERO usos na fiação do template, é resposta de RENDER,
    e mora em `Solution.services[].answers`."""
    await kernel.write_instance(
        "frota", "App", "mcp-entra",
        _app(service_name="mcp", port=8080, can_sleep=True),
    )
    lido = (await kernel.get_instance("frota", "App", "mcp-entra"))["spec"]
    assert lido["service_name"] == "mcp"
    assert lido["port"] == 8080
    assert lido["can_sleep"] is True


@pytest.mark.asyncio
async def test_can_sleep_false_sobrevive_ao_round_trip(kernel):
    """O valor CARO é `false`, e um `false` que virasse ausente na volta seria
    lido como "nunca respondeu" — o mesmo bug com outro nome. Por isso o caso
    testado é o falsy, não o truthy."""
    await kernel.write_instance(
        "frota", "App", "mcp-entra", _app(can_sleep=False),
    )
    lido = (await kernel.get_instance("frota", "App", "mcp-entra"))["spec"]
    assert "can_sleep" in lido
    assert lido["can_sleep"] is False


@pytest.mark.asyncio
async def test_dois_apps_compartilham_um_service_name(kernel):
    """CÓDIGO e DEPLOYMENT são 1:N — medido no dna-cloud (9 serviços sobre 4
    diretórios `apps/`). `apps/mcp/` serve `mcp` e `mcp-entra`, com respostas
    de custo DIFERENTES. Se o schema tratasse `service_name` como identidade,
    este teste não passaria."""
    await kernel.write_instance(
        "frota", "App", "mcp-entra",
        _app(service_name="mcp", can_sleep=False),
    )
    doc = _app(service_name="mcp", can_sleep=True)
    doc["metadata"]["name"] = "mcp-ws"
    await kernel.write_instance("frota", "App", "mcp-ws", doc)

    entra = (await kernel.get_instance("frota", "App", "mcp-entra"))["spec"]
    ws = (await kernel.get_instance("frota", "App", "mcp-ws"))["spec"]
    assert entra["service_name"] == ws["service_name"] == "mcp"
    assert entra["can_sleep"] is False and ws["can_sleep"] is True


def test_os_quatro_campos_do_servico_sao_opcionais():
    """2 instâncias de `App` vivas não responderam nenhuma das quatro
    perguntas. `required` é a única coisa que decide se elas seguem válidas.

    E `copilots` saiu do `required` junto: um serviço gerado pelo template não
    tem copiloto nenhum, então exigir um impedia gravar exatamente o App que
    esta mudança existe para permitir. Só o `title` sobra."""
    app = _helix_descriptor("app")
    assert app["spec"]["schema"]["required"] == ["title"]
    assert "minItems" not in app["spec"]["schema"]["properties"]["copilots"]
    for campo in ("service_name", "port", "can_sleep", "ingress"):
        assert campo in app["spec"]["schema"]["properties"]
    # e `python_module` NÃO é mais um deles — ver
    # `test_campos_opcionais_por_evidencia.py`.
    assert "python_module" not in app["spec"]["schema"]["properties"]


@pytest.mark.asyncio
async def test_o_app_do_servico_gerado_grava_sem_copiloto_nenhum(kernel):
    """O caso que o template produz, pela porta.

    Um serviço recém-gerado é um processo que atende e não serve copiloto
    algum — o `worker` do dna-cloud escala por KEDA e nunca vai servir. Com
    `copilots` obrigatório este write era RECUSADO, e "App = serviço" não
    fechava no único caminho que o cria."""
    doc = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "App",
        "metadata": {"name": "worker"},
        "spec": {
            "title": "worker",
            "service_name": "copilot",
            "port": 8080,
            "can_sleep": True,
        },
    }
    await kernel.write_instance("frota", "App", "worker", doc)
    lido = (await kernel.get_instance("frota", "App", "worker"))["spec"]
    assert "copilots" not in lido
    assert lido["can_sleep"] is True


def test_service_name_recusa_valor_fora_do_padrao():
    """A asserção que prova que o `pattern` é VIVO e não decoração: sem ele o
    caso abaixo passaria, e o erro só apareceria no `azd up`."""
    import jsonschema

    schema = _helix_descriptor("app")["spec"]["schema"]
    base = {"title": "x", "copilots": ["c"]}

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**base, "service_name": "MCP Entra"}, schema)
    # e o valor legítimo continua passando — senão o teste acima mediria só
    # que o schema recusa tudo.
    jsonschema.validate({**base, "service_name": "mcp-entra"}, schema)


def test_can_sleep_documenta_a_conta_de_90_dolares():
    """AC da story: o campo tem de CARREGAR o número. A descrição é o único
    lugar que chega a quem for declarar um App novo, e o portão do dna-cloud
    ("ele pode dormir?") só é respondível se o custo estiver junto."""
    doc = _helix_descriptor("app")["spec"]["schema"]["properties"]["can_sleep"]
    descricao = doc["description"]
    assert "90" in descricao and "US$" in descricao
    assert "94,43" in descricao  # a medição, não só a ordem de grandeza


# ── Copilot: onde roda, e quanto rende ───────────────────────────────────────


@pytest.mark.asyncio
async def test_copilot_grava_e_rele_runs_in_e_value_per_outcome(kernel):
    await kernel.write_instance("frota", "App", "mcp-entra", _app())
    await kernel.write_instance(
        "frota", "Copilot", "memory-copilot",
        _copilot(
            runs_in="mcp-entra",
            value_per_outcome={
                "human_minutes": 45,
                "hourly_cost": 120.5,
                "currency": "BRL",
            },
        ),
    )
    lido = (await kernel.get_instance("frota", "Copilot", "memory-copilot"))["spec"]
    assert lido["runs_in"] == "mcp-entra"
    assert lido["value_per_outcome"] == {
        "human_minutes": 45, "hourly_cost": 120.5, "currency": "BRL",
    }


@pytest.mark.asyncio
async def test_copilot_sem_runs_in_continua_valido(kernel):
    """Cinco dos sete copilotos vivos não estão em App nenhum e funcionam.
    Ausente é ÓRFÃO — um achado a contar — nunca uma recusa."""
    await kernel.write_instance("frota", "Copilot", "memory-copilot", _copilot())
    lido = (await kernel.get_instance("frota", "Copilot", "memory-copilot"))["spec"]
    assert "runs_in" not in lido


def test_value_per_outcome_e_tipado_e_nao_um_mapa_livre():
    """Se fosse `additionalProperties: true` este teste passaria com o objeto
    inteiro por declarar — que é exatamente a forma de erro que ele mede."""
    import jsonschema

    schema = _helix_descriptor("copilot")["spec"]["schema"]
    base = {
        "mounts": [{"id": "p", "agent": "a", "path": "/agui"}],
        "serving": {"transport": "ag-ui"},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {**base, "value_per_outcome": {"valor": 100}}, schema
        )
    jsonschema.validate(
        {**base, "value_per_outcome": {"human_minutes": 45,
                                       "hourly_cost": 120.5,
                                       "currency": "BRL"}},
        schema,
    )


def test_value_per_outcome_documenta_que_e_o_unico_numero_nao_medivel():
    doc = _helix_descriptor("copilot")["spec"]["schema"]["properties"]
    descricao = doc["value_per_outcome"]["description"]
    assert "DECLARED" in descricao or "declared" in descricao
    assert "ROI" in descricao


# ── A relação, e a decisão sobre `inverse_of` ────────────────────────────────


def test_runs_in_e_relacao_declarada_para_app_com_cardinalidade_one():
    copilot = _helix_descriptor("copilot")
    assert copilot["spec"]["relations"]["runs_in"] == {
        "to": "App", "cardinality": "one",
    }


def test_runs_in_nao_declara_inverse_of_e_o_registro_nao_tem_lacuna():
    """A decisão, medida com `dna.kernel.kinds.relations` na frente.

    `inverse_of` IMPÕE a declaração do outro lado (`inverse_gaps`) e só
    REPORTA o dado. O relatório vale quando os dois campos são duas metades
    armazenadas de UM fato; `App.copilots` é COMPOSIÇÃO (o que se vende sob
    uma identidade) e `runs_in` é EXECUÇÃO (o processo que serve), e um
    processo serve legitimamente copilotos de várias identidades.

    A segunda asserção é a que tem valor: se alguém declarar `inverse_of` num
    dos lados sem o outro, `inverse_gaps` acusa — e é assim que este teste
    para de passar por engano."""
    from dna.kernel.kinds.relations import inverse_gaps, normalize_relations

    copilot = _helix_descriptor("copilot")
    app = _helix_descriptor("app")
    assert "inverse_of" not in copilot["spec"]["relations"]["runs_in"]
    assert "inverse_of" not in app["spec"]["relations"]["copilots"]

    por_kind = {
        "Copilot": normalize_relations(copilot["spec"]["relations"]),
        "App": normalize_relations(app["spec"]["relations"]),
    }
    assert inverse_gaps(por_kind) == []
