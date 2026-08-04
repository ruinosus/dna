"""s-prompts-reutilizaveis — `promptTemplate` resolve por NOME de catálogo.

O que deixa um end user criar o prompt na tela (doc PromptTemplate) e o agent
referenciá-lo por nome — sem mustache inline e sem arquivo. A regra é
determinística e backward-compatível: slug + doc existente → o body do doc;
slug sem doc → o valor segue sendo template inline, como sempre foi.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from dna.kernel.prompt.builder import PromptBuilder


def _doc(kind, name, spec):
    return SimpleNamespace(kind=kind, name=name, spec=spec,
                           api_version="github.com/ruinosus/dna/v1")


def _host(docs):
    async def all_async(kind, **kw):
        return [d for d in docs if d.kind == kind]

    return SimpleNamespace(documents=docs, _kinds={}, _kernel=None,
                           all_async=all_async)


AGENTE = _doc("Agent", "meu-agente",
              {"promptTemplate": "boas-vindas", "instruction": "fallback"})
CATALOGO = _doc("PromptTemplate", "boas-vindas",
                {"body": "Ola, {{agent.instruction}}!"})


def test_slug_COM_doc_no_catalogo_usa_o_body_do_doc():
    b = PromptBuilder(_host([CATALOGO]))
    out = b._render_prompt({"agent": {"instruction": "fallback"}}, AGENTE)
    assert out == "Ola, fallback!"


def test_slug_SEM_doc_continua_template_inline_nunca_erro():
    """Backward-compat: um template inline de uma palavra era legal e segue."""
    b = PromptBuilder(_host([]))
    out = b._render_prompt({"agent": {"instruction": "fallback"}}, AGENTE)
    assert out == "boas-vindas"


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
