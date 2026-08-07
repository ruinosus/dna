"""App — a composição nomeada de copilotos (spec-app-como-composicao,
decisões do founder de 05/08/2026: Kind NOVO pequeno; kit = pacote, App =
instância; entitlement no doc consultado pelo gate de plano existente)."""
from __future__ import annotations

import pytest


def _load_app_doc(spec: dict):
    """Parseia um doc App pelo MESMO caminho do runtime (descriptor→port)."""
    from dna.kernel import Kernel
    import pathlib, tempfile, yaml

    tmp = pathlib.Path(tempfile.mkdtemp()) / ".dna" / "s"
    (tmp / "apps").mkdir(parents=True)
    (tmp / "Genome.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        "metadata: {name: s}\nspec: {}\n"
    )
    doc = {
        "apiVersion": "github.com/ruinosus/dna/v1",
        "kind": "App",
        "metadata": {"name": "meu-app"},
        "spec": spec,
    }
    (tmp / "apps" / "meu-app.yaml").write_text(yaml.safe_dump(doc))
    mi = Kernel.quick("s", base_dir=str(tmp.parent))
    # Record-plane não flatten-a em mi.instances (de propósito) — a leitura
    # canônica é pelo registro, como toda tela faz.
    return mi._one("App", "meu-app")


def test_app_minimo_valida_e_carrega():
    doc = _load_app_doc({"title": "Estúdio Editorial", "copilots": ["editor"]})
    assert doc is not None
    assert doc.spec["title"] == "Estúdio Editorial"
    assert doc.spec["copilots"] == ["editor"]


def test_app_declara_a_referencia_aos_copilotos():
    """`copilots` é uma RELAÇÃO declarada — o picker do wizard e a validação de
    existência no write nascem DELA (i-040, f-modelagem-das-relacoes).

    A declaração saiu de dentro da propriedade do JSON Schema e virou bloco
    próprio: o schema guarda os DADOS, `relations` guarda o modelo. O nome da
    relação continua sendo o campo, então nenhuma instância de App mudou."""
    from dna.kernel.source.descriptor_loader import load_descriptors

    raws = load_descriptors("dna.extensions.helix")
    app = next(r for r in raws if r["metadata"]["name"] == "app")
    assert app["spec"]["relations"]["copilots"] == {
        "to": "Copilot", "cardinality": "many",
    }
    assert "x-dna-ref" not in app["spec"]["schema"]["properties"]["copilots"]
    assert app["spec"]["schema"]["properties"]["requires_plan"]["enum"] == ["free", "pro"]


def test_app_sem_copilots_e_valido():
    """⚠️ Isto era o OPOSTO até 07/08/2026, e a inversão é a decisão.

    `spec-app-e-o-servico` fez o App SER o serviço, e um serviço gerado pelo
    template não tem copiloto nenhum — é um processo que atende. Enquanto
    `copilots` fosse `required` com `minItems: 1`, o comando não conseguia
    gravar o App do serviço que ele acabara de gerar. Um App sem copiloto é um
    App válido: ou ainda não recebeu nenhum, ou nunca vai receber (o `worker`
    do dna-cloud escala por KEDA e não serve copiloto algum).

    A recusa do `title` ausente é o que impede este teste de virar "o schema
    não exige mais nada" — a forma que um `required` esvaziado por engano
    teria.
    """
    import jsonschema
    from dna.kernel.source.descriptor_loader import load_descriptors

    raws = load_descriptors("dna.extensions.helix")
    schema = next(
        r for r in raws if r["metadata"]["name"] == "app"
    )["spec"]["schema"]

    jsonschema.validate({"title": "worker"}, schema)
    jsonschema.validate({"title": "worker", "copilots": []}, schema)

    with pytest.raises(jsonschema.ValidationError) as exc:
        jsonschema.validate({"copilots": ["editor"]}, schema)
    assert "title" in str(exc.value)
