"""s-prompts-reutilizaveis — `promptTemplate` resolve por NOME de catálogo.

O que deixa um end user criar o prompt na tela (doc PromptTemplate) e o agent
referenciá-lo por nome — sem mustache inline e sem arquivo. A regra é
determinística e backward-compatível: slug + doc existente → o body do doc;
slug sem doc → o valor segue sendo template inline, como sempre foi.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from dna.kernel.kinds.base import KindBase
from dna.kernel.prompt.builder import TRAIT_NAMED_TEMPLATE, PromptBuilder
from dna.kernel.protocols import StorageDescriptor


def _doc(kind, name, spec):
    return SimpleNamespace(kind=kind, name=name, spec=spec,
                           api_version="github.com/ruinosus/dna/v1")


class _PromptLibraryKind(KindBase):
    """⭐ i-107 — a Kind is a prompt library because it DECLARES it, not because
    it is spelled "PromptTemplate".

    The builder used to match ``d.kind == "PromptTemplate"`` and read
    ``spec["body"]``, both hardcoded. It now reads the ``prompt.named-template``
    trait and the Kind's own ``storage.body_field`` — so this fixture, named
    nothing like the built-in and keeping its body under ``texto``, gets exactly
    the behaviour the built-in gets. Which is the point: a tenant can ship its
    own prompt library and an agent can reference it by name.
    """
    api_version = "market.example/v1"
    kind = "TenantPromptLibrary"
    alias = "market-tenantpromptlibrary"
    storage = StorageDescriptor.bundle("prompts", "PROMPT.md", body_field="texto")
    traits = frozenset({TRAIT_NAMED_TEMPLATE})


_LIB_PORT = _PromptLibraryKind()
_LIB_KEY = (_PromptLibraryKind.api_version, _PromptLibraryKind.kind)


def _host(docs, *, kinds=(_LIB_KEY,)):
    async def all_async(kind, **kw):
        return [d for d in docs if d.kind == kind]

    return SimpleNamespace(
        instances=docs, _kinds={key: _LIB_PORT for key in kinds},
        _kernel=None, all_async=all_async,
    )


AGENTE = _doc("Agent", "meu-agente",
              {"promptTemplate": "boas-vindas", "instruction": "fallback"})
CATALOGO = _doc(_PromptLibraryKind.kind, "boas-vindas",
                {"texto": "Ola, {{agent.instruction}}!"})


def test_slug_COM_doc_no_catalogo_usa_o_body_do_doc():
    b = PromptBuilder(_host([CATALOGO]))
    out = b._render_prompt({"agent": {"instruction": "fallback"}}, AGENTE)
    assert out == "Ola, fallback!"


def test_slug_SEM_doc_continua_template_inline_nunca_erro():
    """Backward-compat: um template inline de uma palavra era legal e segue."""
    b = PromptBuilder(_host([]))
    out = b._render_prompt({"agent": {"instruction": "fallback"}}, AGENTE)
    assert out == "boas-vindas"


def test_um_Kind_que_NAO_declara_o_trait_e_invisivel_para_o_agent():
    """A metade negativa, sem a qual a derivação seria decorativa: as MESMAS
    instâncias, um MI que não conhece Kind nenhum declarando
    ``prompt.named-template``, e o slug volta a ser template inline. Antes da
    i-107 o builder varria o nome ``"PromptTemplate"``, então um MI com
    ``_kinds={}`` resolvia por um Kind que ninguém havia declarado."""
    b = PromptBuilder(_host([CATALOGO], kinds=()))
    out = b._render_prompt({"agent": {"instruction": "fallback"}}, AGENTE)
    assert out == "boas-vindas"


def test_o_corpo_vem_do_body_field_declarado_nao_de_body_fixo():
    """``storage.body_field`` já era declarado por cada Kind e este código o
    ignorava, lendo ``spec["body"]`` fixo. A fixture guarda o corpo em
    ``texto``; se isto passar, o builder está lendo a declaração."""
    assert _LIB_PORT.storage.body_field == "texto"
    b = PromptBuilder(_host([CATALOGO]))
    assert b._named_template_body("boas-vindas") == "Ola, {{agent.instruction}}!"
    # e um doc cujo corpo está no campo ERRADO não resolve
    errado = _doc(_PromptLibraryKind.kind, "outro", {"body": "nao devia valer"})
    assert PromptBuilder(_host([errado]))._named_template_body("outro") is None


def test_texto_com_espacos_ou_chaves_NUNCA_e_tratado_como_nome():
    ag = _doc("Agent", "a", {"promptTemplate": "Voce e {{agent.instruction}}",
                             "instruction": "x"})
    b = PromptBuilder(_host([CATALOGO]))
    assert b._render_prompt({"agent": {"instruction": "x"}}, ag) == "Voce e x"


def test_o_caminho_async_resolve_igual_e_lazy_safe():
    b = PromptBuilder(_host([CATALOGO]))
    corpo = asyncio.run(b._named_template_body_async("boas-vindas"))
    assert corpo == "Ola, {{agent.instruction}}!"
    assert asyncio.run(b._named_template_body_async("nao-existe")) is None
