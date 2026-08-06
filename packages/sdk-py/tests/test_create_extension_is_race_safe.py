"""``CREATE EXTENSION`` nunca aparece cru — a corrida é real e já mordeu duas vezes.

``CREATE EXTENSION IF NOT EXISTS`` **não** é seguro sob concorrência, ao
contrário do que o nome sugere e do que dois comentários deste repositório
afirmavam. O Postgres verifica e cria em dois passos, **sem lock entre eles**:
o ``IF NOT EXISTS`` protege contra a extensão JÁ existir, nunca contra alguém
criá-la no intervalo.

Medido duas vezes em 06/08/2026:

* ao aterrissar a migração ``0010`` (``btree_gist``), seis processos do
  ``pytest-xdist`` aplicaram a revisão ao mesmo tempo contra um banco e
  **cinco morreram** em ``duplicate key value violates unique constraint
  "pg_extension_name_index"``;
* reproduzido de propósito contra o Postgres de dev, oito conexões simultâneas
  num banco recém-criado: **2 de 8 falharam** com a forma crua, **0 de 8** com
  o bloco ``DO``.

E não é artefato de teste. O dna-cloud roda migração no ``CMD`` de boot de
**oito** serviços contra um Postgres só; duas réplicas subindo juntas são
exatamente o caso, só mais raro — e mais raro é pior, porque falha em produção
depois de meses de deploy verde.

⚠️ **Por que uma guarda estática e não um teste de concorrência.** O defeito é
probabilístico (2 de 8, não 8 de 8), então um teste que dispara N processos
passa com frequência **sem que o conserto exista** — verde por sorte é o modo
de falha que esta casa mais paga. A afirmação determinística é outra: nenhum
``CREATE EXTENSION`` do fonte está fora de um bloco que engula a corrida.

A guarda é DERIVADA — varre o pacote inteiro, não uma lista de arquivos —
porque as duas ocorrências que existiam nasceram em momentos diferentes, por
pessoas diferentes, e uma lista teria coberto só a que alguém lembrou.

⚠️ **E ela é por AST, não por texto — a primeira versão era por texto e acusou
uma menção em DOCSTRING.** Uma varredura de texto não distingue código de
prosa: este próprio arquivo fala de ``CREATE EXTENSION`` dezenas de vezes, e
sob a regra de texto ele se acusaria. O mesmo erro está documentado do outro
lado da casa (``apps/web/eslint.config.mjs`` no dna-cloud): um teste de texto
foi escrito duas vezes e errou duas vezes, e a segunda foi exatamente marcar
uma frase dentro de um comentário. Aqui só interessam literais que o programa
**executa** — então: constantes de string que não são docstring.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

#: A raiz do pacote de produção. Testes ficam de fora de propósito: um teste
#: que cria a extensão roda sozinho contra o banco dele, e obrigá-lo ao bloco
#: seria burocracia sem defeito por trás.
_SDK = pathlib.Path(__file__).resolve().parents[1] / "dna"

_CREATE_EXTENSION = re.compile(r"CREATE\s+EXTENSION", re.IGNORECASE)

#: As duas formas que a corrida assume quando o perdedor chega tarde. Um bloco
#: que engula ambas torna o resultado do perdedor idêntico ao do vencedor.
_SWALLOWS_THE_RACE = re.compile(
    r"EXCEPTION\s+WHEN[^;]*duplicate_object[^;]*unique_violation",
    re.IGNORECASE | re.DOTALL,
)


def _sources() -> list[pathlib.Path]:
    return sorted(p for p in _SDK.rglob("*.py") if "__pycache__" not in p.parts)


def _docstring_nodes(arvore: ast.AST) -> set[int]:
    """Os ids dos nós de string que são DOCSTRING, e portanto prosa.

    Uma docstring é a primeira instrução de um módulo, classe ou função, e
    aparece como ``Expr(Constant(str))``. Qualquer outra constante de string é
    valor que o programa carrega — é dela que a guarda fala.
    """
    ids: set[int] = set()
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        corpo = getattr(no, "body", None)
        if not corpo:
            continue
        primeiro = corpo[0]
        if (
            isinstance(primeiro, ast.Expr)
            and isinstance(primeiro.value, ast.Constant)
            and isinstance(primeiro.value.value, str)
        ):
            ids.add(id(primeiro.value))
    return ids


def _executed_strings(arquivo: pathlib.Path) -> list[tuple[int, str]]:
    """``(linha, valor)`` de cada literal de string que NÃO é docstring."""
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
    docs = _docstring_nodes(arvore)
    return [
        (no.lineno, no.value)
        for no in ast.walk(arvore)
        if isinstance(no, ast.Constant)
        and isinstance(no.value, str)
        and id(no) not in docs
    ]


def test_the_guard_has_something_to_look_at() -> None:
    """Guarda-sobre-a-guarda: um pacote vazio passaria por vacuidade.

    O número é frouxo de propósito — ele existe para acusar um caminho errado
    ou uma varredura quebrada, não para congelar o tamanho do SDK.
    """
    assert len(_sources()) > 100


def test_no_bare_create_extension_anywhere_in_the_sdk() -> None:
    ofensores: list[str] = []

    for arquivo in _sources():
        for linha, valor in _executed_strings(arquivo):
            if not _CREATE_EXTENSION.search(valor):
                continue
            # O bloco tem de estar no MESMO literal: um `DO $$ … END $$` que
            # engula a corrida é um statement só, e um `EXCEPTION` que estivesse
            # noutra string não protegeria este `CREATE`.
            if _SWALLOWS_THE_RACE.search(valor):
                continue
            ofensores.append(f"{arquivo.relative_to(_SDK.parent)}:{linha}")

    if ofensores:
        pytest.fail(
            "CREATE EXTENSION fora de um bloco que engula a corrida:\n  "
            + "\n  ".join(ofensores)
            + "\n\n`IF NOT EXISTS` NÃO basta — ele protege contra a extensão já "
            "existir, não contra alguém criá-la no intervalo entre o check e o "
            "create. Medido: 2 de 8 conexões simultâneas falham com a forma "
            "crua, 0 de 8 com o bloco.\n\nUse:\n"
            "    DO $$\n"
            "    BEGIN\n"
            "        CREATE EXTENSION IF NOT EXISTS <nome>;\n"
            "    EXCEPTION WHEN duplicate_object OR unique_violation THEN\n"
            "        NULL;\n"
            "    END $$\n"
        )


def test_the_guard_would_actually_catch_a_bare_statement() -> None:
    """O mutante, sem plantá-lo no fonte: a janela crua não passa, a com bloco sim."""
    crua = "op.execute('CREATE EXTENSION IF NOT EXISTS btree_gist')"
    assert _CREATE_EXTENSION.search(crua)
    assert not _SWALLOWS_THE_RACE.search(crua)

    protegida = (
        "DO $$ BEGIN CREATE EXTENSION IF NOT EXISTS btree_gist; "
        "EXCEPTION WHEN duplicate_object OR unique_violation THEN NULL; END $$"
    )
    assert _SWALLOWS_THE_RACE.search(protegida)
