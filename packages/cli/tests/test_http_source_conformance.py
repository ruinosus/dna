"""O kit de conformidade de Source, rodado contra o `HttpSource` — ATRAVESSANDO
a face REST real (i-106).

A convenção do repo é que um adaptador novo entra nos kits que já existem, em
vez de ganhar testes próprios. Aqui isso vale duplo: o kit é escrito por quem
NÃO escreveu este adaptador, e as duas primeiras coisas que ele achou foram
defeitos reais e não de teste —

* ``load_layer(scope, "tenant", "__base__")`` devolvia o CONTEÚDO BASE do scope
  sob nome de overlay (o defeito i-006, que já fez `dna source diff/push`
  digerir ``{}`` dos dois lados);
* ``load_layer`` de um plano que esta porta não tem LEVANTAVA, quando o
  contrato do port diz vazio.

Nada é dublado: a fábrica semeia o ``fixture_docs`` canônico no disco, sobe a
face REST de verdade numa porta de verdade, e devolve um `HttpSource` apontado
para ela. Os casos ``writable`` pulam sozinhos — esta porta é de leitura, e o
kit lê isso da declaração, não de um flag escrito à mão.
"""
from __future__ import annotations

import asyncio
import socket
import tempfile
import threading
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi", reason="a face REST precisa do extra 'api'")
uvicorn = pytest.importorskip("uvicorn")

from dna.testing import source_conformance_suite  # noqa: E402
from dna.testing.source_conformance import (  # noqa: E402
    CaseNotApplicable,
    FIXTURE_SCOPE,
    fixture_docs,
)
from dna_cli import _rest_api as R  # noqa: E402

_TOKEN = "conformance-fake-bearer-not-a-secret"


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _semear(raiz: Path) -> None:
    """O fixture canônico no armazenamento NATIVO do servidor (YAML em disco) —
    é o que o kit pede de uma fonte somente-leitura."""
    import json

    scope_dir = raiz / FIXTURE_SCOPE
    for doc in fixture_docs():
        kind = doc["kind"]
        container = {"Genome": ".", "Story": "stories"}.get(kind, kind.lower() + "s")
        destino = scope_dir if container == "." else scope_dir / container
        destino.mkdir(parents=True, exist_ok=True)
        nome = "Genome" if kind == "Genome" else doc["metadata"]["name"]
        (destino / f"{nome}.yaml").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8",
        )


@pytest.fixture(scope="module")
def porta():
    """UMA face REST real para o módulo inteiro; cada caso ganha um
    `HttpSource` novo apontado para ela (o kit constrói por caso)."""
    tmp = tempfile.mkdtemp(prefix="dna-http-conf-")
    raiz = Path(tmp) / ".dna"
    _semear(raiz)

    p = _porta_livre()
    app = R.build_app(
        base_dir=str(raiz), scope=FIXTURE_SCOPE, auth="token", token=_TOKEN,
    )
    servidor = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=p, log_level="error")
    )
    thread = threading.Thread(target=servidor.run, daemon=True)
    thread.start()
    import time

    for _ in range(200):
        if servidor.started:
            break
        time.sleep(0.05)
    assert servidor.started, "a face REST não subiu"
    try:
        yield f"http://127.0.0.1:{p}/v1"
    finally:
        servidor.should_exit = True
        thread.join(timeout=10)
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


def _fabrica(base: str):
    async def build() -> tuple[Any, Any]:
        from dna.adapters.http_source import HttpSource

        src = HttpSource(base, token=_TOKEN, ttl=0)
        return src, src.close

    return build


@pytest.mark.parametrize(
    "nome",
    [c.name for c in source_conformance_suite(_fabrica("http://unused"))],
)
def test_conformidade_do_source(porta, nome):
    casos = {c.name: c for c in source_conformance_suite(_fabrica(porta))}
    caso = casos[nome]
    try:
        asyncio.run(caso.run())
    except CaseNotApplicable as pulo:
        pytest.skip(str(pulo))
