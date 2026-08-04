"""`AgentCatalogEntry` — o fallback ROTULADO, e o que o schema impede.

Este Kind é o papel MENOR da identidade do agente. O principal é o CIMD, onde o
nome vem ancorado no domínio que o publica; aqui o nome é digitado por alguém do
workspace, e a tela precisa poder dizer isso.

Quase todo teste deste arquivo é sobre manter essa diferença VISÍVEL — porque
apagá-la é o modo de falha da feature inteira: um nome sem procedência ao lado de
um nome provado ensina o usuário a confiar nos dois igual.
"""
from __future__ import annotations

import pathlib

import yaml
from jsonschema import Draft202012Validator

import dna.extensions.a2a as pacote

_KIND = pathlib.Path(pacote.__file__).parent / "kinds" / "agent-catalog-entry.kind.yaml"


def _schema() -> dict:
    return yaml.safe_load(_KIND.read_text())["spec"]["schema"]


def _spec(**overrides) -> dict:
    base = {
        "client_id": "client_01KYZFRW8W58S5DAHMDS8FA32A",
        "client_name": "Assistente de Sprint",
        "registered_by": "user_01KXV762MWW3J7X90A36PQ5DV0",
    }
    base.update(overrides)
    return base


def _erros(spec: dict) -> list[str]:
    return [
        f"{list(e.path)}: {e.message}"
        for e in Draft202012Validator(_schema()).iter_errors(spec)
    ]


def test_uma_entrada_de_catalogo_e_valida():
    assert not _erros(_spec())


def test_um_client_id_que_e_URL_e_RECUSADO():
    """A regra que carrega o Kind, e ela é estrutural — não convenção.

    Um cliente que publica metadados JÁ TEM identidade ancorada no domínio dele.
    Deixar alguém digitar um nome por cima seria substituir prova por digitação —
    exatamente a troca que a primeira versão da spec fazia sem perceber.
    """
    for url in (
        "https://acme.example/oauth/x",
        "http://acme.example/oauth/x",
        "HTTPS://ACME.EXAMPLE/x",
    ):
        assert _erros(_spec(client_id=url)), f"aceitou {url!r}"


def test_QUEM_cadastrou_e_obrigatorio():
    """É o que torna o rótulo possível.

    "Assistente de Sprint · cadastrado por Maria" é uma frase que o usuário pode
    pesar. "Assistente de Sprint" sozinho, num id opaco, é uma afirmação que
    ninguém sustenta — e ao lado de um nome ancorado, ensina a confiar nos dois
    igual.
    """
    spec = _spec()
    del spec["registered_by"]
    assert _erros(spec)


def test_o_nome_VAZIO_e_recusado():
    assert _erros(_spec(client_name=""))
    assert _erros(_spec(registered_by=""))


def test_o_schema_e_FECHADO():
    """Um campo a mais num documento que a tela de autorização LÊ é a forma mais
    silenciosa de alguém acrescentar significado que ninguém revisou."""
    assert _erros(_spec(trusted=True))
    assert _erros(_spec(verified=True))


def test_NAO_ha_campo_de_permissao():
    """Este Kind NOMEIA, não autoriza. Quem autoriza é o `AgentGrant`.

    São documentos separados de propósito: cadastrar um agente no catálogo não
    pode ser um caminho para conceder acesso a ele — e a ausência destes campos
    é o que garante isso, não a boa intenção de quem escreve o portal.
    """
    propriedades = _schema()["properties"]
    for proibido in ("scope_kinds", "state", "granted_at", "subject", "allow"):
        assert proibido not in propriedades, f"o catálogo abriu {proibido!r}"


def test_nao_ha_campo_para_credencial():
    plano = _KIND.read_text().lower()
    for proibido in ("token:", "secret", "password", "bearer", "api_key"):
        assert proibido not in plano, f"o Kind menciona {proibido!r}"


def test_e_TENANTED_e_do_plano_de_REGISTRO():
    """Um agente cadastrado pela Acme não nomeia nada no workspace da Beta: o
    nome é opinião de quem cadastrou, e opinião não atravessa workspace."""
    spec = yaml.safe_load(_KIND.read_text())["spec"]
    assert spec["tenant_scope"] == "tenanted"
    assert spec["plane"] == "record"
    assert spec["prompt_target"] is False
