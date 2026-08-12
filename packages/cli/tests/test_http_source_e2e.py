"""A PROVA de i-106: um Copilot resolvido PELA REDE, com token e sem DSN.

Um adaptador que passa nos unit tests e não resolve um agente de verdade não
entregou nada. Então este teste não dubla nada do caminho:

* sobe a face REST REAL (``dna api serve`` → ``build_app``) numa PORTA REAL, com
  ``--auth token``, sobre o scope ``concierge`` que já vive em
  ``examples/emitting-to-a-runtime``;
* aponta ``DNA_SOURCE_URL`` para ela e mais nada — nenhuma DSN, nenhum
  ``DNA_BASE_DIR``;
* chama ``DnaClient.from_env()`` e ``resolve_copilot`` com a MESMA forma de
  sempre. Se o consumidor precisasse mudar código, o item teria falhado.

Ele mora neste pacote porque é aqui que a face REST é importável: o `dna-sdk`
não depende do `dna-cli`, e é justamente essa direção que o adaptador preserva —
o consumidor instala só o SDK e fala com a face pela rede.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil
import socket
import threading

import pytest

pytest.importorskip("fastapi", reason="a face REST precisa do extra 'api'")
uvicorn = pytest.importorskip("uvicorn")

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_COPILOT = "memory-copilot"
_TOKEN = "e2e-fake-bearer-not-a-secret"  # um token FALSO, de teste.


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _aquecer(base: str) -> None:
    """Um pedido real, para a face fixar o próprio kernel sobre o DISCO antes de
    a variável do consumidor existir."""
    import json
    import urllib.request

    req = urllib.request.Request(
        f"{base}/kinds/registry", headers={"Authorization": f"Bearer {_TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        corpo = json.loads(resp.read().decode())
    assert corpo["scope"] == _SCOPE, corpo.get("scope")


@pytest.fixture
def porta_hospedada(tmp_path, monkeypatch):
    """A face REST real, no ar, sobre uma cópia do scope concierge."""
    dst = tmp_path / ".dna"
    shutil.copytree(_BASE, dst)

    # ⚠️ A ORDEM importa, e o erro é instrutivo: a face REST resolve a PRÓPRIA
    # fonte por ``DNA_SOURCE_URL`` (que ganha de ``base_dir``) na PRIMEIRA
    # requisição. Apontar a variável para a porta antes de aquecê-la faz o
    # servidor tentar ler de si mesmo. Então: disco primeiro, um pedido real
    # para fixar o kernel do servidor, e só depois a variável do CONSUMIDOR.
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))

    porta = _porta_livre()
    app = R.build_app(
        base_dir=str(dst), scope=_SCOPE, auth="token", token=_TOKEN,
    )
    servidor = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="error")
    )
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    for _ in range(200):
        if servidor.started:
            break
        import time

        time.sleep(0.05)
    assert servidor.started, "a face REST não subiu"

    base = f"http://127.0.0.1:{porta}/v1"
    _aquecer(base)

    # A partir daqui o consumidor NÃO conhece o disco: só a URL e o bearer.
    monkeypatch.delenv("DNA_BASE_DIR", raising=False)
    monkeypatch.setenv("DNA_SOURCE_URL", base)
    monkeypatch.setenv("DNA_API_TOKEN", _TOKEN)
    try:
        yield base
    finally:
        servidor.should_exit = True
        thread.join(timeout=10)


def test_um_copilot_resolve_pela_rede_com_token_e_sem_dsn(porta_hospedada):
    """O alvo inteiro do i-106, numa asserção: a MESMA API de hoje, uma variável
    de ambiente diferente, e nenhuma credencial de banco em lugar nenhum."""
    from dna.adapters.http_source import HttpSource
    from dna.client import DnaClient

    async def go():
        client = await DnaClient.from_env(scope=_SCOPE)
        assert isinstance(client._source, HttpSource), (
            "DNA_SOURCE_URL http(s):// tem de chegar ao adaptador remoto"
        )
        try:
            copilot = await client.resolve_copilot(_COPILOT)
            agent = await client.resolve_agent("memory-agent")
            return copilot, agent
        finally:
            await client.close()

    copilot, agent = asyncio.run(go())

    # O campo que a ficha pede pelo nome: uma lista declarada no YAML, viajada
    # inteira por HTTP, e não um placeholder que um dublê teria produzido.
    assert copilot.knowledge == ("knowledge-base",)
    assert copilot.instructions, "o prompt composto veio vazio"
    assert agent.name == "memory-agent"
    assert agent.tools, "as Tools do agente não foram enriquecidas pela porta"


def test_o_scope_que_esta_porta_nao_serve_e_recusado_e_nao_respondido(porta_hospedada):
    """As rotas de instância NÃO aceitam ``scope``: elas respondem o scope
    DERIVADO da credencial. Medido contra a face real — ``?scope=outro`` devolve
    as instâncias do scope servido. Então o adaptador recusa; responder seria
    entregar o conteúdo de um scope sob o nome de outro, e devolver ``[]`` seria
    afirmar que o outro está vazio."""
    from dna.adapters.http_source import HttpSource, RemoteScopeMismatch

    async def go():
        src = HttpSource(porta_hospedada, token=_TOKEN)
        assert await src.list_scopes() == [_SCOPE]
        with pytest.raises(RemoteScopeMismatch):
            await src.load_all("um-scope-de-outra-pessoa")
        await src.close()

    asyncio.run(go())


def test_sem_o_bearer_a_leitura_levanta_em_vez_de_ler_como_vazia(porta_hospedada):
    """A regra da casa, atravessando a porta de verdade: um 401 é
    ``ResolveAuthError``, nunca uma lista vazia — e a mensagem diz
    ``ausente``/``setado``, jamais o token."""
    from dna.adapters.http_source import HttpSource
    from dna.kernel.protocols import ResolveAuthError

    async def go():
        src = HttpSource(porta_hospedada, token="")
        with pytest.raises(ResolveAuthError) as err:
            await src.load_all(_SCOPE)
        await src.close()
        return str(err.value)

    mensagem = asyncio.run(go())
    assert "ausente" in mensagem
    assert _TOKEN not in mensagem
