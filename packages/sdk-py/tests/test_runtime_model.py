"""Como o runtime monta o modelo — e por que a Responses API é o default.

O assunto é uma escolha de API que parece detalhe e não é: sem a Responses API o
modelo fala Chat Completions, que **não aceita arquivo de entrada**. Foi essa
limitação que fez o dna-cloud converter todo anexo para Markdown.
"""
from __future__ import annotations

import pytest

from dna.runtime.model import build_chat_model, responses_api_enabled


def test_o_default_e_a_Responses_API(monkeypatch):
    """Ligada sem configurar nada. Um deployment que a suporta é o caso normal —
    MEDIDO em 02/08/2026 até no `gpt-5-mini`, que não é topo de linha."""
    monkeypatch.delenv("DNA_MODEL_RESPONSES_API", raising=False)
    assert responses_api_enabled() is True


@pytest.mark.parametrize("valor", ["0", "false", "no", "off", "FALSE", " 0 "])
def test_a_escotilha_desliga(valor, monkeypatch):
    """Existe para GATEWAY que não implementa a rota `/responses` — não para
    preferência. Ver o docstring do módulo."""
    monkeypatch.setenv("DNA_MODEL_RESPONSES_API", valor)
    assert responses_api_enabled() is False


@pytest.mark.parametrize("valor", ["", "1", "true", "sim", "yes", "talvez", "0.0"])
def test_um_valor_QUALQUER_mantem_o_default(valor, monkeypatch):
    """⚠️ Só os negadores conhecidos desligam.

    Um typo (`DNA_MODEL_RESPONSES_API=flase`) não pode desligar em silêncio a
    API que carrega o caminho de arquivo — o sintoma seria "o PDF parou de
    funcionar" três semanas depois, sem nada apontando para uma variável de
    ambiente escrita errado.
    """
    monkeypatch.setenv("DNA_MODEL_RESPONSES_API", valor)
    assert responses_api_enabled() is True


def test_o_modelo_e_montado_com_use_responses_api(monkeypatch):
    """A prova de que a escolha CHEGA no construtor, e não fica na intenção."""
    monkeypatch.delenv("DNA_MODEL_RESPONSES_API", raising=False)
    capturado: dict = {}

    import langchain.chat_models as cm

    def _falso(coordenada, **kw):
        capturado["coordenada"] = coordenada
        capturado.update(kw)
        return object()

    monkeypatch.setattr(cm, "init_chat_model", _falso)
    build_chat_model("gpt-5-mini")

    assert capturado["coordenada"] == "openai:gpt-5-mini"
    assert capturado["use_responses_api"] is True


def test_desligada_o_construtor_NAO_recebe_a_chave(monkeypatch):
    """Desligar tem de significar ausência, e não `False`.

    Um `use_responses_api=False` explícito é uma afirmação sobre a API; a
    ausência deixa o default do `langchain-openai` valer, que é o que um gateway
    incompatível precisa.
    """
    monkeypatch.setenv("DNA_MODEL_RESPONSES_API", "0")
    capturado: dict = {}

    import langchain.chat_models as cm

    monkeypatch.setattr(cm, "init_chat_model", lambda c, **kw: capturado.update(kw))
    build_chat_model("gpt-5-mini")

    assert "use_responses_api" not in capturado


def test_quem_chama_pode_sobrepor(monkeypatch):
    """`setdefault`, não atribuição: um chamador que sabe o que faz vence."""
    monkeypatch.delenv("DNA_MODEL_RESPONSES_API", raising=False)
    capturado: dict = {}

    import langchain.chat_models as cm

    monkeypatch.setattr(cm, "init_chat_model", lambda c, **kw: capturado.update(kw))
    build_chat_model("gpt-5-mini", use_responses_api=False, temperature=0.2)

    assert capturado["use_responses_api"] is False
    assert capturado["temperature"] == 0.2


def test_os_DOIS_caminhos_do_runtime_usam_este_construtor():
    """A guarda contra a divergência que motivou o módulo.

    `init_chat_model` aparecia em dois lugares — o `run_local` do builder e o
    adapter que SERVE. Duas leituras da mesma pergunta divergem em silêncio, e
    esta divergiria do pior jeito: o mesmo agente responderia diferente conforme
    fosse executado localmente ou servido.
    """
    import pathlib

    import dna.runtime as pacote

    raiz = pathlib.Path(pacote.__file__).parent
    for caminho in (raiz / "builder.py", raiz / "adapters" / "langchain_rt.py"):
        fonte = caminho.read_text()
        assert "build_chat_model(" in fonte, f"{caminho.name} não usa o construtor"
        assert "init_chat_model(f\"openai:" not in fonte, (
            f"{caminho.name} voltou a montar o modelo por conta própria"
        )


# ── a coordenada do agente vs o deployment do ambiente ─────────────────────


def test_sem_override_a_coordenada_do_agente_VENCE(monkeypatch):
    monkeypatch.delenv("DNA_MODEL_DEPLOYMENT", raising=False)
    from dna.runtime.model import deployment_for

    assert deployment_for("gpt-5-mini") == "gpt-5-mini"


def test_o_override_troca_o_deployment_sem_tocar_na_definicao(monkeypatch):
    """⚠️ A separação que este par existe para guardar.

    O documento do agente declara uma COORDENADA portátil, versionada com ele e
    igual em todo ambiente. Qual deployment a atende é fato do AMBIENTE.

    Sem isso a única saída seria editar a definição — que é COMPARTILHADA com
    produção. Foi o que aconteceu em 02/08: o endpoint local passou a apontar
    para um recurso com `gpt-5.4`, as definições seguiram pedindo `gpt-5-mini`,
    e a chamada morreu com `DeploymentNotFound` — que chega ao navegador como
    `terminated`, no meio do stream.
    """
    monkeypatch.setenv("DNA_MODEL_DEPLOYMENT", "gpt-5.4")
    from dna.runtime.model import deployment_for

    assert deployment_for("gpt-5-mini") == "gpt-5.4"


def test_o_override_e_REGISTRADO_quando_difere(monkeypatch, caplog):
    """Substituição silenciosa de modelo faria alguém depurar o comportamento de
    um modelo que não está rodando — a depuração mais cara que existe."""
    import logging

    monkeypatch.setenv("DNA_MODEL_DEPLOYMENT", "gpt-5.4")
    from dna.runtime.model import deployment_for

    with caplog.at_level(logging.INFO, logger="dna.runtime.model"):
        deployment_for("gpt-5-mini")
    assert "gpt-5-mini" in caplog.text and "gpt-5.4" in caplog.text


def test_override_IGUAL_a_coordenada_nao_polui_o_log(monkeypatch, caplog):
    import logging

    monkeypatch.setenv("DNA_MODEL_DEPLOYMENT", "gpt-5-mini")
    from dna.runtime.model import deployment_for

    with caplog.at_level(logging.INFO, logger="dna.runtime.model"):
        assert deployment_for("gpt-5-mini") == "gpt-5-mini"
    assert caplog.text == ""
