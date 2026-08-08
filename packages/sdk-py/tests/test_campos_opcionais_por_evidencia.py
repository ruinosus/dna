"""A régua fiação-vs-render, e um campo opcional por EVIDÊNCIA.

`Spec/spec-campo-opcional-por-evidencia` + `Story/s-campos-opcionais-por-evidencia`
(07/08/2026), depois de o dogfood do dna-cloud (`ruinosus/dna-cloud#370`) medir
os nove serviços reais contra os descritores.

Duas coisas se provam aqui, e a primeira é a que apaga uma lacuna em vez de
tolerá-la:

1. **O `App` carrega o que a FIAÇÃO precisa; o `answers` carrega o que o
   TEMPLATE precisa.** `python_module` tem ZERO usos nos três fragmentos de
   fiação do `templates/app-container` — é resposta de render, saiu do `App` e
   mora em `Solution.services[].answers`. É o que faz o `portal` (Next.js)
   caber **sem exceção nenhuma**.
2. Um campo vira opcional quando a REALIDADE apresenta um caso legítimo —
   `port` pelo `worker`, `Solution.services` pelo dna-cloud inteiro.

⚠️ Cada teste de "passa" carrega o CASO REAL que o comprou, e tem a metade
contrária no mesmo arquivo: sem ela a suíte passaria com o schema tendo virado
"não exige mais nada" e ninguém notaria.
"""

from __future__ import annotations

import pathlib

import pytest

TEMPLATE = (
    pathlib.Path(__file__).resolve().parents[3] / "templates" / "app-container"
)


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


def _schema(name: str) -> dict:
    from dna.kernel.source.descriptor_loader import load_descriptors

    raws = load_descriptors("dna.extensions.helix")
    return next(r for r in raws if r["metadata"]["name"] == name)["spec"]["schema"]


def _app(name: str, **spec) -> dict:
    s = {"title": name}
    s.update(spec)
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "App",
        "metadata": {"name": name},
        "spec": s,
    }


def _solution(name: str, **spec) -> dict:
    s = {"title": "dna-cloud"}
    s.update(spec)
    return {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "Solution",
        "metadata": {"name": name},
        "spec": s,
    }


# ── A régua: fiação mora no App, render mora no answers ─────────────────────


def test_python_module_nao_aparece_em_nenhum_fragmento_de_fiacao():
    """A MEDIÇÃO que decidiu a casa do campo, contra o template real.

    Se `python_module` aparecesse em qualquer um dos três fragmentos, ele
    seria fato de deployment e teria de voltar para o `App`. Este teste é o que
    diz isso em voz alta se o template mudar.

    ⚠️ `service_name` está aqui como controle: sem ele, a asserção passaria com
    o glob de fiação apontando para lugar nenhum — verde por vacuidade, que é a
    forma de defeito que esta casa já pagou três vezes.

    ⚠️ O controle da porta é **`port`**, não `container_port`. A pergunta foi
    renomeada no #353 justamente para as perguntas do template e os campos do
    `App` serem UM vocabulário; este teste nasceu no #355 lendo o template de
    antes e por isso entrou vermelho na `main` (b592dc90). O controle que
    importa é que a porta ESTEJA na fiação — e ela está, com o nome de hoje.
    """
    fiacao = sorted(TEMPLATE.glob("apps/*/wiring/*.jinja"))
    assert len(fiacao) == 3, f"fragmentos de fiação encontrados: {fiacao}"

    texto = "\n".join(p.read_text() for p in fiacao)
    assert "python_module" not in texto
    # o controle: um fato de deployment de verdade ESTÁ lá
    assert "service_name" in texto
    assert "port" in texto
    assert "container_port" not in texto, (
        "o nome antigo não pode voltar por descuido — o `App` declara `port`"
    )
    assert "ingress" in texto


def test_o_app_nao_declara_mais_python_module():
    """Ele desceu para `Solution.services[].answers`, onde o vocabulário do
    template mora livre. Com `additionalProperties: false` no App, "não
    declarado" significa RECUSADO — que é o que a régua quer dizer."""
    import jsonschema

    app = _schema("app")
    assert "python_module" not in app["properties"]
    assert app["additionalProperties"] is False

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"title": "mcp", "python_module": "dna_mcp"}, app)


@pytest.mark.asyncio
async def test_o_portal_next_js_grava_sem_exececao_nenhuma(kernel):
    """⭐ O ganho da régua, no caso que a motivou.

    O `portal` do dna-cloud é Next.js. Ele não declara "não se aplica", não
    ganha exceção e não fica devendo nada: ele simplesmente não responde uma
    pergunta que o Kind deixou de fazer."""
    await kernel.write_instance(
        "frota", "App", "portal",
        _app("portal", service_name="web", port=3000,
             ingress="external", can_sleep=True),
    )
    lido = (await kernel.get_instance("frota", "App", "portal"))["spec"]
    assert lido["port"] == 3000
    assert "python_module" not in lido


@pytest.mark.asyncio
async def test_o_python_module_do_mcp_cabe_no_answers_da_solution(kernel):
    """A outra ponta da mudança de casa: o campo não sumiu, mudou de lugar.

    `answers` é mapa livre (`additionalProperties: true`), então isto grava sem
    o schema precisar conhecer o vocabulário do template — que é exatamente por
    que ele é a casa certa."""
    await kernel.write_instance(
        "frota", "Solution", "dna-cloud",
        _solution("dna-cloud", services=[{
            "name": "mcp",
            "answers_file": ".copier-answers.mcp.yml",
            "template": {"src": "gh:ruinosus/dna", "ref": "v0.74.0"},
            "answers": {"python_module": "dna_mcp", "identity": "workos"},
        }]),
    )
    lido = (await kernel.get_instance("frota", "Solution", "dna-cloud"))["spec"]
    assert lido["services"][0]["answers"]["python_module"] == "dna_mcp"


# ── Um campo opcional por evidência, com o caso real ────────────────────────


@pytest.mark.asyncio
async def test_o_worker_grava_sem_port_porque_nao_atende(kernel):
    """O `worker` do dna-cloud escala por KEDA sobre a fila e NÃO ATENDE.

    ⭐ E o fato declarado é esse — `ingress: none` —, não "a porta não se
    aplica". A porta ausente é consequência dele, por definição, já que `port`
    É o `targetPort` do ingress."""
    await kernel.write_instance(
        "frota", "App", "worker",
        _app("worker", service_name="copilot", ingress="none", can_sleep=True),
    )
    lido = (await kernel.get_instance("frota", "App", "worker"))["spec"]
    assert "port" not in lido
    assert lido["ingress"] == "none"


@pytest.mark.asyncio
async def test_o_dna_cloud_grava_como_solution_sem_services(kernel):
    """O dna-cloud **nunca foi gerado por template** — não há `.copier-answers`
    porque não houve render. Era a única coisa que o dogfood dos nove serviços
    ainda recusava: os nove Apps passavam, e a `Solution` ficava."""
    await kernel.write_instance(
        "frota", "Solution", "dna-cloud",
        _solution("dna-cloud", repo="github.com/ruinosus/dna-cloud"),
    )
    lido = (await kernel.get_instance("frota", "Solution", "dna-cloud"))["spec"]
    assert "services" not in lido
    assert lido["title"] == "dna-cloud"


# ── "Não atende" é RESPOSTA, e é imposta nos dois sentidos ──────────────────


@pytest.mark.asyncio
async def test_nao_atender_e_nao_ter_respondido_sao_distinguiveis(kernel):
    """⭐ A condição da spec, no único caso que sobrou depois da régua.

    Os dois Apps abaixo têm `port` AUSENTE e dizem coisas opostas: o `worker`
    respondeu (não atende) e o `mcp` não respondeu. Se um consumidor não
    conseguisse separá-los, o relatório falaria de tudo — e um relatório que
    fala de tudo é PIOR que a recusa, porque dá a sensação de que alguém está
    olhando."""
    await kernel.write_instance(
        "frota", "App", "worker",
        _app("worker", service_name="copilot", ingress="none"),
    )
    await kernel.write_instance(
        "frota", "App", "mcp", _app("mcp", service_name="mcp"),
    )

    worker = (await kernel.get_instance("frota", "App", "worker"))["spec"]
    mcp = (await kernel.get_instance("frota", "App", "mcp"))["spec"]

    # a metade que já era verdade: os dois estão sem porta
    assert "port" not in worker and "port" not in mcp
    # a metade nova: e MESMO ASSIM eles se distinguem
    assert worker["ingress"] == "none"
    assert "ingress" not in mcp


def test_declarar_que_nao_atende_e_dar_uma_porta_e_recusado():
    """⛔ "Não atende" e "atende na 8080" não podem ser ambas verdade.

    Sem esta recusa `ingress: none` seria DECORAÇÃO: daria para declarar as
    duas coisas no mesmo doc, e o relatório teria de escolher em qual
    acreditar."""
    import jsonschema

    schema = _schema("app")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {"title": "worker", "ingress": "none", "port": 8080}, schema,
        )
    # cada metade sozinha é legítima — senão a recusa acima seria do doc, não
    # da contradição. E `internal`/`external` COM porta é o caso comum.
    jsonschema.validate({"title": "worker", "ingress": "none"}, schema)
    jsonschema.validate({"title": "mcp", "port": 8080}, schema)
    jsonschema.validate({"title": "mcp", "ingress": "internal", "port": 8080}, schema)


@pytest.mark.asyncio
async def test_a_contradicao_e_recusada_pela_porta_e_nao_so_no_unit(kernel):
    """⚠️ Guarda que existe e porta que não chama é um defeito conhecido desta
    casa. O teste acima mede o schema; este mede a GRAVAÇÃO, que é por onde a
    contradição chegaria de verdade."""
    from dna.kernel.protocols import SpecValidationError

    with pytest.raises(SpecValidationError):
        await kernel.write_instance(
            "frota", "App", "contraditorio",
            _app("contraditorio", ingress="none", port=8080),
        )


def test_ingress_recusa_um_valor_fora_do_conjunto():
    """`none` é o valor que torna o `worker` representável — e, desde i-099
    (08/08/2026), GERÁVEL: o template passou a oferecer os três. O `enum` é o
    que impede um `nenhum`/`false` de silenciar a pergunta por engano."""
    import jsonschema

    schema = _schema("app")
    for ruim in ("nenhum", "None", "false", "off"):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"title": "x", "ingress": ruim}, schema)
    for bom in ("external", "internal", "none"):
        jsonschema.validate({"title": "x", "ingress": bom}, schema)


# ── A metade contrária: o schema não virou "não exige nada" ─────────────────


def test_service_name_nao_foi_afrouxado_nem_apertado():
    """⛔ `service_name` tem 3 usos na fiação — o maior de todos — e saiu limpo
    nos NOVE serviços medidos. Nenhuma evidência pediu para afrouxá-lo.

    ⚠️ Ele também NÃO virou `required`, e a story pedia isso ("service_name
    CONTINUA obrigatório"). Ele nunca foi: `spec-app-e-o-servico` o fez nascer
    opcional porque as 2 instâncias de `App` vivas são ANTERIORES ao campo, e
    exigi-lo agora as invalidaria — a forma de erro que esta casa mais caro
    paga, e o oposto do que uma spec sobre AFROUXAR por evidência autoriza.
    """
    schema = _schema("app")
    assert schema["required"] == ["title"]
    assert "service_name" in schema["properties"]


def test_app_sem_title_ainda_e_recusado():
    """A metade sem a qual as de cima passariam com o schema tendo virado "não
    exige mais nada". `title` é o único `required` do App, e é ele que prova
    que ainda existe um."""
    import jsonschema

    schema = _schema("app")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"service_name": "web", "port": 3000}, schema)
    jsonschema.validate({"title": "portal"}, schema)


def test_solution_sem_title_e_com_services_vazio_ainda_e_recusada():
    """Duas recusas, e a segunda é a que a decisão exigia manter.

    `minItems: 1` FICA: opcional dá conta do repo que nunca foi renderizado;
    `services: []` não afirma nem uma coisa nem outra, e segue recusado. O
    schema impede besteira — é a completude que virou relatório, não a forma.
    """
    import jsonschema

    schema = _schema("solution")
    assert schema["required"] == ["title"]

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"repo": "x"}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"title": "dna-cloud", "services": []}, schema)
    jsonschema.validate({"title": "dna-cloud"}, schema)


# ── A evidência escrita, que é o que impede alguém de "arrumar" de volta ────


def test_cada_decisao_carrega_a_evidencia_na_description():
    """AC da story: um `optional` sem o caso real que o justificou é convite
    para alguém desfazer, ou para o próximo campo virar opcional sem evidência
    nenhuma. A `description` é o único lugar que chega a quem for declarar."""
    app = _schema("app")["properties"]
    solution = _schema("solution")["properties"]

    # port: opcional pelo worker, e o fato que o responde é o ingress
    assert "worker" in app["port"]["description"]
    assert "ingress" in app["port"]["description"]

    # ingress: o campo que substituiu o mecanismo genérico
    assert "worker" in app["ingress"]["description"]
    assert "KEDA" in app["ingress"]["description"]

    # services: opcional pelo dna-cloud inteiro
    assert "template" in solution["services"]["description"]
    assert "dna-cloud" in solution["services"]["description"]

    # service_name: por que NÃO foi afrouxado
    assert "NOVE" in app["service_name"]["description"]

    # e o answers diz que é a casa do vocabulário de render
    answers = solution["services"]["items"]["properties"]["answers"]
    assert "python_module" in answers["description"]
