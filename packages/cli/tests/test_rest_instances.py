"""``POST /v1/kinds/{kind}/instances`` — the generic, kubernetes-shaped write.

The gap this closes: only PER-KIND write routes existed (``/v1/memories``,
``/v1/artifacts``, ``/v1/kinds``, ``/v1/projects``, ``/v1/tenants``,
``/v1/workspaces``). An instance of an arbitrary — including tenant-authored —
Kind had no REST door at all, so a proposer (e.g. an instance-converter agent)
that authors a Kind and matches an instance to it had nowhere to write the
instance through the shared REST lane.

The shape follows Kubernetes, deliberately (see the plan): applying a CRD
CREATES an endpoint that serves that type, the ``kind`` is inferred from the
endpoint the client submits to (never re-stated ambiguously), and the API
server validates every write against the registered schema before persisting.

Six properties, each pinned by the test that would actually catch its
regression:

1. **the Kind comes from the PATH** — a body that names a DIFFERENT kind is
   refused (400), never silently obeyed by either source.
2. **the server validates ``spec`` against the registered schema** before
   writing, and the refusal NAMES the field (unknown, or missing required) —
   exactly like the Kubernetes API server.
3. **an authored-but-unapproved Kind refuses** — the SAME gate every other
   surface already has: an authored Kind is inert until a human approves it,
   and this door cannot bypass that.
4. **identity and scope are not caller input** — asserted against the
   PUBLISHED schema (the OpenAPI instance a caller actually reaches), the
   REST analogue of what ``test_tools_bind_their_scope.py`` already asserts
   for the MCP tools.
5. **the provenance edge is real** — citing a ``SourceArtifact`` by
   ``source_sha256`` appends to its ``derived_refs``, and a re-write never
   erases what was already recorded (the write-side twin of the property
   ``register_artifact_impl`` already holds on the artifact's own side).
6. **an unknown Kind is a 404 naming it, never a 500.**

This suite runs on ``--auth none`` (the local/self-host lane), the same lane
``test_kind_authoring_route.py`` runs its core assertions on: the doors this
route depends on (``POST /v1/kinds`` + its ``/approve``) are already proven
mounted there, and nothing about THIS route is auth-lane-conditional.
"""
from __future__ import annotations

import asyncio
import pathlib
import shutil

import pytest

pytest.importorskip("fastapi", reason="the REST read-API needs the optional 'fastapi' extra")

from fastapi.testclient import TestClient  # noqa: E402

from dna_cli import _rest_api as R  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_BASE = _ROOT / "examples" / "emitting-to-a-runtime" / ".dna"
_SCOPE = "concierge"
_WID = "ws-documents000000000001"

_ALICE = {"oid": "oid-alice", "email": "alice@acme.com", "email_verified": True}

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["titulo"],
    "properties": {"titulo": {"type": "string"}},
}


def _store_at(dst: pathlib.Path) -> pathlib.Path:
    """A writable copy of the concierge scope, WITH the ``_lib`` namespace
    registry (author_kind reads it before minting a namespace) — same shape
    ``test_kind_authoring_route.py``'s ``dna_dir`` fixture stands up."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_BASE, dst)
    lib = dst / "_lib"
    lib.mkdir(parents=True, exist_ok=True)
    (lib / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        "metadata:\n  name: _lib\n"
        "spec: {}\n"
    )
    return dst


@pytest.fixture
def dna_dir(tmp_path, monkeypatch):
    dst = _store_at(tmp_path / ".dna")
    monkeypatch.setenv("DNA_BASE_DIR", str(dst))
    monkeypatch.delenv("DNA_SOURCE_URL", raising=False)
    return dst


def _client(dna_dir, **kwargs) -> TestClient:
    return TestClient(R.build_app(base_dir=str(dna_dir), scope=_SCOPE, **kwargs))


def _read(dna_dir, kind, name, *, tenant=None, scope=_SCOPE):
    from dna_cli import _mcp_server as M

    async def go():
        live = await M.boot_live(scope=_SCOPE, base_dir=str(dna_dir))
        return await live.kernel.get_instance(scope, kind, name, tenant=tenant)

    return asyncio.run(go())


def _author_and_approve(c: TestClient, *, kind="Contrato", schema=None, tenant=_WID):
    r = c.post(
        "/v1/kinds", params={"tenant": tenant},
        json={"kind": kind, "schema": schema or _SCHEMA},
    )
    assert r.status_code == 201, r.text
    a = c.post(f"/v1/kinds/{kind}/approve", params={"tenant": tenant})
    assert a.status_code == 200, a.text
    return r.json()


# ── 1. the Kind comes from the PATH ─────────────────────────────────────────


def test_a_divergent_body_kind_is_refused(dna_dir):
    with _client(dna_dir) as c:
        _author_and_approve(c)
        r = c.post(
            "/v1/kinds/Contrato/instances", params={"tenant": _WID},
            json={
                "kind": "OutraCoisa",
                "metadata": {"name": "c1"},
                "spec": {"titulo": "Foo"},
            },
        )
        assert r.status_code == 400, r.text
        assert "Contrato" in r.text and "OutraCoisa" in r.text


def test_a_matching_body_kind_is_accepted(dna_dir):
    """The refusal is about DIVERGENCE, not about the field's mere presence."""
    with _client(dna_dir) as c:
        _author_and_approve(c)
        r = c.post(
            "/v1/kinds/Contrato/instances", params={"tenant": _WID},
            json={
                "kind": "Contrato",
                "metadata": {"name": "c1"},
                "spec": {"titulo": "Foo"},
            },
        )
        assert r.status_code == 201, r.text


# ── 2. the server validates the spec against the registered schema ─────────


def test_the_happy_path_writes_a_conforming_document(dna_dir):
    with _client(dna_dir) as c:
        _author_and_approve(c)
        r = c.post(
            "/v1/kinds/Contrato/instances", params={"tenant": _WID},
            json={"metadata": {"name": "c1"}, "spec": {"titulo": "Foo"}},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["kind"] == "Contrato"
        assert body["name"] == "c1"
        assert body["created"] is True
    stored = _read(dna_dir, "Contrato", "c1", tenant=_WID)
    assert stored is not None, "the instance was not persisted"
    assert stored["spec"]["titulo"] == "Foo"


def test_an_unknown_field_is_refused_by_name(dna_dir):
    with _client(dna_dir) as c:
        _author_and_approve(c)
        r = c.post(
            "/v1/kinds/Contrato/instances", params={"tenant": _WID},
            json={
                "metadata": {"name": "c2"},
                "spec": {"titulo": "Foo", "campo_fantasma": 1},
            },
        )
        assert r.status_code == 400, r.text
        assert "campo_fantasma" in r.text, r.text


def test_a_missing_required_field_is_refused_by_name(dna_dir):
    with _client(dna_dir) as c:
        _author_and_approve(c)
        r = c.post(
            "/v1/kinds/Contrato/instances", params={"tenant": _WID},
            json={"metadata": {"name": "c3"}, "spec": {}},
        )
        assert r.status_code == 400, r.text
        assert "titulo" in r.text, r.text


def test_bootstrap_kinds_stay_refused_through_this_route(dna_dir):
    """The generic write's own refusal (Genome/LayerPolicy/KindDefinition
    declare what a scope IS) must not be reachable through the new route
    either — it is the SAME core, and the new door adds no back way in."""
    with _client(dna_dir) as c:
        r = c.post(
            "/v1/kinds/KindDefinition/instances", params={"tenant": _WID},
            json={"metadata": {"name": "anything"}, "spec": {}},
        )
        assert r.status_code == 403, r.text
        assert "BOOTSTRAP" in r.text


# ── 3. an authored-but-unapproved Kind refuses ──────────────────────────────


def test_writing_under_an_unapproved_kind_refuses(dna_dir):
    with _client(dna_dir) as c:
        r = c.post(
            "/v1/kinds", params={"tenant": _WID},
            json={"kind": "Rascunho", "schema": _SCHEMA},
        )
        assert r.status_code == 201, r.text
        # Never approved.
        w = c.post(
            "/v1/kinds/Rascunho/instances", params={"tenant": _WID},
            json={"metadata": {"name": "d1"}, "spec": {"titulo": "x"}},
        )
        assert w.status_code == 404, w.text
        assert "Rascunho" in w.text


# ── 4. identity and scope are NOT caller input ──────────────────────────────


def test_scope_and_claims_are_absent_from_the_published_route(dna_dir):
    """Asserted against the PUBLISHED OpenAPI schema — the thing a caller
    actually reaches — not against the Python function signature. The REST
    analogue of ``test_tools_bind_their_scope.py``'s source-pattern guard."""
    app = R.build_app(base_dir=str(dna_dir), scope=_SCOPE)
    spec = app.openapi()
    op = spec["paths"]["/v1/kinds/{kind}/instances"]["post"]

    query_names = {
        p["name"] for p in op.get("parameters", []) if p.get("in") == "query"
    }
    assert "scope" not in query_names, query_names
    assert "claims" not in query_names, query_names

    body_ref = op["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    model_name = body_ref.rsplit("/", 1)[-1]
    props = spec["components"]["schemas"][model_name]["properties"]
    assert "scope" not in props, props
    assert "claims" not in props, props


# ── 5. the provenance edge is real ──────────────────────────────────────────

_SHA = "c" * 64


def _register_artifact(c: TestClient, wid: str, sha: str = _SHA) -> None:
    r = c.post("/v1/artifacts", json={
        "workspace_id": wid, "sha256": sha, "uri": f"blob://{wid}/{sha}",
        "claims": _ALICE,
    })
    assert r.status_code == 201, r.text


def test_citing_a_source_artifact_closes_the_derived_refs_edge(dna_dir):
    with _client(dna_dir) as c:
        wid = c.post(
            "/v1/workspaces", json={"name": "Acme", "claims": _ALICE},
        ).json()["workspace_id"]
        _register_artifact(c, wid)
        _author_and_approve(c, tenant=wid)
        r = c.post(
            "/v1/kinds/Contrato/instances", params={"tenant": wid},
            json={
                "metadata": {"name": "c1"}, "spec": {"titulo": "Foo"},
                "source_sha256": _SHA,
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["source_sha256"] == _SHA

    art = _read(dna_dir, "SourceArtifact", f"sha256-{_SHA}", tenant=wid)
    refs = art["spec"]["derived_refs"]
    assert len(refs) == 1, refs
    assert refs[0]["kind"] == "Contrato"
    assert refs[0]["name"] == "c1"


def test_a_second_derivation_preserves_the_first(dna_dir):
    """Two instances citing the SAME artifact — the one-to-many case
    ``derived_refs`` is a list FOR. Writing the second must not erase the
    first's entry."""
    with _client(dna_dir) as c:
        wid = c.post(
            "/v1/workspaces", json={"name": "Acme", "claims": _ALICE},
        ).json()["workspace_id"]
        _register_artifact(c, wid)
        _author_and_approve(c, tenant=wid)
        for doc_name in ("c1", "c2"):
            r = c.post(
                "/v1/kinds/Contrato/instances", params={"tenant": wid},
                json={
                    "metadata": {"name": doc_name}, "spec": {"titulo": "Foo"},
                    "source_sha256": _SHA,
                },
            )
            assert r.status_code == 201, r.text

    art = _read(dna_dir, "SourceArtifact", f"sha256-{_SHA}", tenant=wid)
    names = {ref["name"] for ref in art["spec"]["derived_refs"]}
    assert names == {"c1", "c2"}, names


def test_rewriting_the_same_document_updates_its_own_entry_not_a_duplicate(dna_dir):
    with _client(dna_dir) as c:
        wid = c.post(
            "/v1/workspaces", json={"name": "Acme", "claims": _ALICE},
        ).json()["workspace_id"]
        _register_artifact(c, wid)
        _author_and_approve(c, tenant=wid)
        for _ in range(2):
            r = c.post(
                "/v1/kinds/Contrato/instances", params={"tenant": wid},
                json={
                    "metadata": {"name": "c1"}, "spec": {"titulo": "Foo"},
                    "source_sha256": _SHA,
                },
            )
            assert r.status_code == 201, r.text

    art = _read(dna_dir, "SourceArtifact", f"sha256-{_SHA}", tenant=wid)
    refs = art["spec"]["derived_refs"]
    assert len(refs) == 1, refs


def test_citing_an_unregistered_artifact_is_refused(dna_dir):
    with _client(dna_dir) as c:
        _author_and_approve(c)
        r = c.post(
            "/v1/kinds/Contrato/instances", params={"tenant": _WID},
            json={
                "metadata": {"name": "c1"}, "spec": {"titulo": "Foo"},
                "source_sha256": "d" * 64,
            },
        )
        assert r.status_code == 400, r.text


# ── 6. an unknown Kind is a 404 naming it, never a 500 ──────────────────────


def test_an_unknown_kind_is_a_named_404(dna_dir):
    with _client(dna_dir) as c:
        r = c.post(
            "/v1/kinds/NoSuchKind/instances", params={"tenant": _WID},
            json={"metadata": {"name": "x"}, "spec": {}},
        )
        assert r.status_code == 404, r.text
        assert "NoSuchKind" in r.text


# ── a LEITURA da porta genérica ─────────────────────────────────────────────
#
# A face REST escrevia qualquer instância (`POST /v1/kinds/{kind}/instances`) e
# só LIA os Kinds para os quais alguém escreveu uma rota à mão (`/v1/memories`,
# `/v1/projects`, …). O `list_instances_impl` existia no SDK, completo — com
# projeção, filtro, ordenação e paginação honesta — e não tinha porta.
#
# É a assimetria mais cara que uma API pode ter: quem escreve uma instância por
# esta porta não consegue lê-lo de volta por porta nenhuma, e descobre isso
# depois de já ter gravado.


def test_a_porta_generica_LE_o_que_ela_mesma_escreveu(dna_dir):
    """A propriedade que a rota existe para garantir: escrever e ler pela mesma
    porta, sem precisar de uma rota nova por Kind."""
    with _client(dna_dir) as c:
        _author_and_approve(c)
        for nome in ("c1", "c2"):
            r = c.post(
                "/v1/kinds/Contrato/instances", params={"tenant": _WID},
                json={"metadata": {"name": nome}, "spec": {"titulo": nome.upper()}},
            )
            assert r.status_code == 201, r.text

        r = c.get("/v1/kinds/Contrato/instances", params={"tenant": _WID})
        assert r.status_code == 200, r.text
        nomes = sorted(d["name"] for d in r.json()["instances"])
        assert nomes == ["c1", "c2"], r.json()


def test_a_projecao_evita_o_1_mais_N(dna_dir):
    """Sem `fields`, responder "quais contratos estão abertos" custa 1 + N
    chamadas: listar os nomes e ler cada um. `fields` empurra a projeção para o
    kernel — no Postgres ela vira SELECT, e a linha já viaja aparada."""
    with _client(dna_dir) as c:
        _author_and_approve(c)
        c.post("/v1/kinds/Contrato/instances", params={"tenant": _WID},
               json={"metadata": {"name": "c1"}, "spec": {"titulo": "Alfa"}})

        r = c.get("/v1/kinds/Contrato/instances",
                  params={"tenant": _WID, "fields": "titulo"})
        assert r.status_code == 200, r.text
        doc = r.json()["instances"][0]
        assert doc["name"] == "c1"
        assert doc["spec"]["titulo"] == "Alfa"


def test_um_Kind_desconhecido_e_404_NOMEANDO_o_Kind(dna_dir):
    """A mesma resposta que a escrita dá — um leitor não deve descobrir que o
    Kind não existe por uma lista vazia, que é indistinguível de "existe e está
    vazio"."""
    with _client(dna_dir) as c:
        r = c.get("/v1/kinds/NaoExiste/instances", params={"tenant": _WID})
        assert r.status_code == 404, r.text
        assert "NaoExiste" in r.text


def test_a_lista_de_um_Kind_VAZIO_e_200_e_nao_404(dna_dir):
    """"Existe e não tem nada" é uma resposta, e é diferente de "não existe".
    Confundi-las faria a tela dizer "erro" quando devia dizer "nenhum ainda"."""
    with _client(dna_dir) as c:
        _author_and_approve(c)
        r = c.get("/v1/kinds/Contrato/instances", params={"tenant": _WID})
        assert r.status_code == 200, r.text
        assert r.json()["instances"] == []


# ── 7. GET de UM instância, verbatim — a leitura que a lista projetada não dá


def test_get_one_document_returns_the_spec_verbatim(dna_dir):
    """Quem gravou pelo POST genérico lê DE VOLTA o que gravou — incluindo
    campos que a projeção da lista (vista dos readers) descartaria num Kind
    produzível por bundle (o caso medido: Agent.spec.description e
    tools_requiring_confirmation, 05/08/2026)."""
    with _client(dna_dir) as c:
        _author_and_approve(c)
        c.post(
            "/v1/kinds/Contrato/instances", params={"tenant": _WID},
            json={"metadata": {"name": "c1"}, "spec": {"titulo": "Foo"}},
        )
        r = c.get("/v1/kinds/Contrato/instances/c1", params={"tenant": _WID})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["kind"] == "Contrato" and body["name"] == "c1"
        assert body["instance"]["spec"] == {"titulo": "Foo"}
        assert body["etag"], "o token de concorrência viaja com a leitura"


def test_get_one_document_404s_naming_what_is_missing(dna_dir):
    with _client(dna_dir) as c:
        _author_and_approve(c)
        faltando = c.get("/v1/kinds/Contrato/instances/nao-existe", params={"tenant": _WID})
        assert faltando.status_code == 404
        assert "nao-existe" in faltando.json()["detail"]
        kind_desconhecido = c.get("/v1/kinds/SemKind/instances/x", params={"tenant": _WID})
        assert kind_desconhecido.status_code == 404
