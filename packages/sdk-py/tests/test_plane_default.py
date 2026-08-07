"""i-123 — o default de ``plane`` de um Kind AUTORADO por tenant é ``record``.

A decisão do fundador (07/08/2026) e a medição que a sustenta estão escritas em
:func:`dna.kernel.kinds.base.default_plane`. Este arquivo guarda o que, mudado,
a reverteria em silêncio.

⚠️ **O mutante principal: o default voltando a ``composition``.** Ele não
quebraria nada visível — instâncias continuariam sendo gravadas e lidas, só que
cada uma pagando a invalidação de escopo e a materialização na MI. É por isso
que a asserção não é sobre um comportamento derivado, e sim sobre o valor: o
defeito é INVISÍVEL por construção, então a guarda tem de olhar direto para ele.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.helix import HelixExtension
from dna.extensions.kinddef import KindDefinitionExtension
from dna.kernel import Kernel
from dna.kernel.kinds import registry as registry_mod
from dna.kernel.kinds.base import COMPOSITION_SIGNALS, KindBase, default_plane
from dna.kernel.models import KindDefinitionSpec


def _raw(**over: Any) -> dict[str, Any]:
    base = {
        "target_api_version": "example.com/v1",
        "target_kind": "Widget",
        "alias": "example-widget",
        "origin": "example.com",
        "schema": {"type": "object", "additionalProperties": True},
        "storage": {"type": "yaml", "container": "widgets"},
    }
    base.update(over)
    return base


class TestODefault:
    """O valor em si — a asserção que o mutante principal derruba."""

    def test_um_descritor_sem_plane_nasce_record(self):
        assert KindDefinitionSpec.from_raw(_raw()).plane == "record", (
            "i-123: o default do Kind de tenant é `record`. 48 de 49 autores "
            "escolheram `record` quando puderam; o default estava servindo aos "
            "2% e cobrando dos 98% a invalidação de escopo por escrita"
        )

    def test_plane_null_explicito_conta_como_nao_declarado(self):
        # `author_kind` grava a chave SÓ quando declarada, justamente para
        # manter "escolheu" distinguível de "nunca foi perguntado". Um `null`
        # que chegasse pela porta tem de cair no mesmo lado.
        assert KindDefinitionSpec.from_raw(_raw(plane=None)).plane == "record"

    @pytest.mark.parametrize("declarado", ["composition", "record"])
    def test_um_plane_DECLARADO_nunca_e_derivado(self, declarado):
        assert KindDefinitionSpec.from_raw(_raw(plane=declarado)).plane == declarado, (
            "o default responde só quando ninguém declarou nada — a regra "
            "'plane é explícito, nunca derivado' continua valendo para um "
            "valor declarado"
        )

    def test_o_default_da_CLASSE_segue_composition(self):
        # ⚠️ A decisão do i-123 foi sobre o Kind de TENANT, que sempre chega por
        # descritor. ~26 Kinds internos escritos como classe dependem deste
        # default; trocá-lo junto seria uma segunda mudança de comportamento
        # pegando carona numa decisão que não a autorizou.
        assert KindBase.plane == "composition"

    def test_o_literal_do_dataclass_concorda_com_o_default_computado(self):
        # Dois defaults para a mesma pergunta é a forma clássica de divergir.
        # `from_raw` é o único construtor de produção, mas um spec construído à
        # mão não pode responder outra coisa no caso comum.
        assert KindDefinitionSpec.plane == default_plane({})


class TestOsSinaisDeComposicao:
    """A ressalva — e a guarda derivada que a mantém alinhada com o lint."""

    @pytest.mark.parametrize("chave", sorted(COMPOSITION_SIGNALS.values()))
    def test_um_descritor_que_ja_diz_que_compoe_nao_e_rebaixado(self, chave):
        assert KindDefinitionSpec.from_raw(_raw(**{chave: True})).plane == (
            "composition"
        ), (
            f"um descritor com {chave}=True e sem `plane` REGISTRAVA antes do "
            f"i-123; um default cego de `record` o tornaria irregistrável — "
            f"`_lint_plane` recusa `record` ao lado deste sinal — e a troca do "
            f"default quebraria um Kind que ninguém tocou"
        )

    def test_a_lista_de_sinais_e_A_MESMA_que_o_lint_recusa(self):
        """⭐ A guarda DERIVADA, na granularidade exata do defeito.

        O defeito que ela vê: alguém acrescenta um quinto sinal de composição a
        ``_lint_plane`` e não a ``default_plane``. Nada fica vermelho — até um
        tenant autorar um Kind com aquele sinal e sem `plane`, quando o default
        devolve `record`, o lint recusa `record`, e o erro aponta um campo que o
        autor nunca escreveu.

        Ela é derivada de duas fontes independentes: a lista que o lint de fato
        LÊ (por comportamento, um port de mentira por sinal) e o mapa que
        ``default_plane`` consulta. Comparar o mapa com uma cópia dele não veria
        nada.
        """
        recusados: set[str] = set()
        for attr in (
            "is_prompt_target", "flatten_in_context", "is_schema_affecting",
            "is_root", "is_runtime_artifact", "scope_inheritable",
            "is_overlayable", "is_catalog_identity",
        ):
            port = type("P", (), {
                "plane": "record", "kind": "Probe", attr: True,
            })()
            try:
                registry_mod.KindRegistry._lint_plane(port)
            except registry_mod.KindRegistrationError:
                recusados.add(attr)
        assert recusados == set(COMPOSITION_SIGNALS), (
            f"`_lint_plane` recusa {sorted(recusados)} ao lado de "
            f"plane='record', mas `default_plane` consulta "
            f"{sorted(COMPOSITION_SIGNALS)}. Os dois têm de ser a MESMA lista, "
            f"ou o default produz um Kind que o registro recusa em seguida"
        )

    def test_a_mensagem_de_erro_do_lint_nao_mudou(self):
        """A ordem dos sinais sai na mensagem, e ela é o que o autor lê."""
        port = type("P", (), {
            "plane": "record", "kind": "Probe",
            "is_prompt_target": True, "flatten_in_context": True,
            "is_schema_affecting": True, "is_root": True,
        })()
        with pytest.raises(registry_mod.KindRegistrationError) as exc:
            registry_mod.KindRegistry._lint_plane(port)
        assert (
            "is_prompt_target=True, flatten_in_context=True, "
            "is_schema_affecting=True, storage.pattern==ROOT"
        ) in str(exc.value)


class TestOsDescritoresQueNOSPublicamos:
    """A guarda que faz a frase 'o default só alcança Kind de tenant' ser VERDADE."""

    def test_todo_kind_yaml_do_pacote_declara_plane(self):
        """⚠️ Sem isto, a troca do default é uma mudança silenciosa nos NOSSOS
        Kinds também.

        Hoje 47 de 47 declaram, e é por isso que o i-123 não move nenhum deles.
        Mas "hoje declaram" é um fato, não uma garantia: o próximo descritor
        acrescentado sem `plane` passaria a nascer `record` sem que ninguém
        tivesse decidido isso por ele.

        DERIVADA dos arquivos, nunca de uma contagem escrita à mão — uma lista
        de 47 nomes estaria errada no dia em que o 48º entrasse, que é
        exatamente o dia em que ela precisaria estar certa.
        """
        raiz = Path(__file__).resolve().parents[1] / "dna"
        descritores = sorted(raiz.rglob("*.kind.yaml"))
        assert descritores, "nenhum descritor encontrado — o glob está errado"
        mudos = [
            p.relative_to(raiz)
            for p in descritores
            if "plane" not in (
                (yaml.safe_load(p.read_text(encoding="utf-8")) or {})
                .get("spec") or {}
            )
        ]
        assert not mudos, (
            f"{len(mudos)} descritor(es) do pacote não declaram `plane` e "
            f"passariam a herdar o default de TENANT: {mudos}. Declare o plano "
            f"no descritor — um Kind nosso não deve depender de uma decisão "
            f"que foi tomada sobre o Kind de outra pessoa"
        )


# ── o caminho inteiro, com store de verdade ─────────────────────────────────


@pytest.fixture(autouse=True)
def _limpa_caches_de_warn():
    registry_mod._GLOBAL_UNAPPROVED_KIND_WARNED.clear()
    registry_mod._GLOBAL_KINDDEF_CONFLICT_WARNED.clear()
    registry_mod._AMBIGUOUS_LOOKUP_WARNED.clear()
    yield
    registry_mod._GLOBAL_UNAPPROVED_KIND_WARNED.clear()
    registry_mod._GLOBAL_KINDDEF_CONFLICT_WARNED.clear()
    registry_mod._AMBIGUOUS_LOOKUP_WARNED.clear()


@pytest.fixture
def kernel_com_escopo(tmp_path):
    scope = "test-scope"
    d = tmp_path / scope
    d.mkdir(parents=True)
    (d / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\nkind: Genome\n"
        f"metadata:\n  name: {scope}\nspec: {{}}\n"
    )
    k = Kernel()
    k.load(HelixExtension())
    k.load(KindDefinitionExtension())
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    k.cache(FilesystemCache(str(tmp_path)))
    return k, scope


async def _autora_kind(k: Kernel, scope: str, *, kind: str, **spec_over: Any):
    """Um Kind autorado e aprovado, SEM declarar `plane` — o caso do i-123."""
    spec: dict[str, Any] = {
        "target_api_version": "example.com/v1",
        "target_kind": kind,
        "alias": f"example-{kind.lower()}",
        "origin": "example.com",
        "schema": {"type": "object", "additionalProperties": True},
        "storage": {"type": "yaml", "container": f"{kind.lower()}s"},
        "approved_by": "reviewer@example.com",
        "approved_at": "2026-08-07T12:00:00Z",
    }
    spec.update(spec_over)
    await k.write_instance(
        scope, "KindDefinition", kind.lower(),
        {
            "apiVersion": "github.com/ruinosus/dna/core/v1",
            "kind": "KindDefinition",
            "metadata": {"name": kind.lower()},
            "spec": spec,
        },
    )
    await k.instance_async(scope)


class TestOCaminhoInteiro:

    @pytest.mark.asyncio
    async def test_um_kind_autorado_registra_no_plano_record(
        self, kernel_com_escopo,
    ):
        k, scope = kernel_com_escopo
        await _autora_kind(k, scope, kind="Widget")
        port = k.kind_port_for("Widget", scope=scope)
        assert port is not None and port.plane == "record"

    @pytest.mark.asyncio
    async def test_uma_escrita_dele_NAO_derruba_mais_o_escopo(
        self, kernel_com_escopo, monkeypatch,
    ):
        """O que a decisão COMPRA, medido no comportamento e não no valor.

        `Kernel.write_instance` rebaixa `scope` → `doc` quando o Kind está no
        plano `record`. Com o default antigo esta escrita chegaria em `scope` e
        dispararia `invalidate` — o drop do cache base, o reload dos holders e o
        fan-out. A asserção é sobre a CHAMADA, porque é ela que custa.
        """
        k, scope = kernel_com_escopo
        await _autora_kind(k, scope, kind="Widget")

        chamadas: list[dict] = []
        monkeypatch.setattr(
            k, "invalidate", lambda **kw: chamadas.append(kw),
        )
        await k.write_instance(
            scope, "Widget", "w1",
            {"apiVersion": "example.com/v1", "kind": "Widget",
             "metadata": {"name": "w1"}, "spec": {"a": 1}},
        )
        assert chamadas == [], (
            "uma instância de Kind de tenant não pode mais derrubar o cache do "
            "escopo inteiro a cada gravação — era essa a conta que o default "
            "antigo cobrava de 98% dos autores"
        )

    @pytest.mark.asyncio
    async def test_as_instancias_dele_CONTINUAM_legiveis(
        self, kernel_com_escopo,
    ):
        """⚠️ A regressão que o rebaixamento de plano pode causar, e que quase
        aconteceu.

        Um Kind no plano `record` é PULADO na materialização da MI: a leitura
        passa a ser delegada ao plano record do kernel. Para um Kind de tenant
        — sempre registrado POR ESCOPO — havia a hipótese de que
        ``ManifestInstance._is_record_kind`` (que consulta ``kind_plane`` SEM
        escopo) devolvesse o fail-safe `composition`, mandando a MI procurar na
        materialização de onde o builder já tinha excluído a instância, e
        devolvendo VAZIO. Instância gravada, leitura muda.

        **Medido: não acontece** — ``kind_port_for`` sem escopo alcança os
        ports por-escopo, então os dois lados concordam. Esta guarda fixa isso,
        porque é uma coincidência de comportamento entre dois pontos que não se
        citam: o dia em que a resolução sem escopo passar a ignorar ports
        por-escopo, o sintoma é uma lista vazia, sem erro nenhum.

        Antes do i-123 nada disto era alcançável — Kind de tenant era
        `composition` dos dois lados. Trocar o default é o que o torna
        alcançável, então a guarda entra junto com a troca.
        """
        k, scope = kernel_com_escopo
        await _autora_kind(k, scope, kind="Widget")
        await k.write_instance(
            scope, "Widget", "w1",
            {"apiVersion": "example.com/v1", "kind": "Widget",
             "metadata": {"name": "w1"}, "spec": {"a": 1}},
        )
        mi = await k.instance_async(scope)
        assert mi._is_record_kind("Widget"), (
            "a MI tem de RECONHECER o Kind como record. Se ela ler "
            "`composition` enquanto o builder leu `record`, a instância some da "
            "materialização e da delegação ao mesmo tempo — e o sintoma é uma "
            "lista vazia, não um erro"
        )
        lidos = [
            (d.get("metadata") or {}).get("name")
            async for d in k.query(scope, "Widget")
        ]
        assert lidos == ["w1"], (
            "a leitura pelo plano record do kernel é o caminho que o "
            "rebaixamento de plano exige — se ela não devolver a instância, o "
            "i-123 tornou dado gravado invisível"
        )
        assert await k.get_instance(scope, "Widget", "w1") is not None
