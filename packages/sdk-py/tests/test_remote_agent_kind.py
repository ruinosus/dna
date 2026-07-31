"""``RemoteAgent`` — o Agent Card do A2A como documento.

O protocolo A2A não é um Kind (transporte não é documento). O Agent CARD é: um
descritor versionado de identidade e capacidade. Este Kind é ele.

Quatro propriedades carregam o desenho, e cada uma é pinada porque cada uma é
fácil de perder num edit que parece inofensivo:

1. **``data_scope`` é OBRIGATÓRIO.** Um RemoteAgent é, por construção, um canal
   de exfiltração — o DNA manda dado do workspace para uma URL que o tenant
   escolheu. Um escopo implícito significa "tudo".
2. **O schema é FECHADO.** ``additionalProperties: false`` impede que uma
   credencial (um bearer, um api_key) seja anexada ao documento. O
   ``securitySchemes`` diz COMO autenticar; a credencial em si nunca é documento.
3. **``delegation_target_for`` é o campo COMPARTILHADO com ``Agent``** — é o que
   permite ao roster (Task 2) atravessar os dois Kinds sem enumerá-los.
4. **``signature_state`` é tri-estado.** Ausência de verificação fica LEGÍVEL
   em vez de implícita (ver as premissas do plano).
"""
from __future__ import annotations

import pytest

from dna.kernel.kinds.registry import KindRegistry
from dna.kernel.source.descriptor_loader import load_descriptors

_API = "github.com/ruinosus/dna/a2a/v1"
_KIND = "RemoteAgent"


@pytest.fixture
def port():
    """O port registrado, pelo mesmo funil que o kernel usa."""
    registry = KindRegistry()
    registered = [
        registry.register_from_descriptor(raw)
        for raw in load_descriptors("dna.extensions.a2a")
    ]
    assert len(registered) == 1, f"esperava um descritor, veio {len(registered)}"
    return registered[0]


def _spec(**overrides):
    base = {
        "name": "invoice-reader",
        "description": "Reads invoices and returns structured fields",
        # A forma REAL da A2A 1.0: `protocol_binding` (o `transport` que estava
        # aqui não existe na especificação) com o valor em MAIÚSCULAS.
        "supported_interfaces": [
            {
                "url": "https://vendor.example/a2a",
                "protocol_binding": "JSONRPC",
                "protocol_version": "1.0",
            }
        ],
        "data_scope": {"kinds": ["SourceArtifact"]},
    }
    base.update(overrides)
    return base


def _validate(port, spec):
    """Valida pelo seam do PRÓPRIO port — o mesmo ``parse()`` que o caminho de
    escrita alcança. Asserir contra um validador substituto testaria a ideia que
    o teste tem do schema, não a que o kernel aplica."""
    raw = {
        "apiVersion": _API,
        "kind": _KIND,
        "metadata": {"name": "remote-under-test"},
        "spec": spec,
    }
    try:
        port.parse(raw)
    except Exception as exc:  # noqa: BLE001 — a recusa É o resultado
        return exc
    return None


def test_the_kind_registers_under_its_own_namespace(port):
    assert port.kind == _KIND
    assert port.api_version == _API


def test_a_valid_card_parses(port):
    assert _validate(port, _spec()) is None


def test_data_scope_is_required(port):
    """Tire ``data_scope`` do ``required`` e isto morre.

    Sem escopo declarado, aprovar um RemoteAgent seria aprovar "este endpoint
    pode receber qualquer coisa" — e ninguém aprova isso sabendo."""
    bad = _spec()
    del bad["data_scope"]
    assert _validate(port, bad) is not None


@pytest.mark.parametrize("missing", ["name", "description", "supported_interfaces"])
def test_the_a2a_required_fields_are_required(port, missing):
    """O A2A 1.0 exige name/description/supportedInterfaces. Um Card sem eles não
    é um Card."""
    bad = _spec()
    del bad[missing]
    assert _validate(port, bad) is not None


@pytest.mark.parametrize(
    "smuggled", ["bearer", "api_key", "token", "credential", "password"]
)
def test_no_credential_can_be_smuggled_into_the_document(port, smuggled):
    """``securitySchemes`` diz COMO autenticar; a credencial nunca é documento.

    Ponha ``additionalProperties: true`` e isto morre — e o documento passaria a
    carregar o próprio acesso, então quem alcançasse o documento alcançaria o
    endpoint com ele. O mesmo motivo pelo qual o ``SourceArtifact`` é fechado."""
    assert _validate(port, _spec(**{smuggled: "sk-live-abc123"})) is not None


def test_the_delegation_block_is_accepted(port):
    """O campo COMPARTILHADO com ``Agent``. É o que faz o roster (Task 2)
    atravessar os dois Kinds sem enumerá-los — tire-o e o RemoteAgent fica
    inalcançável por delegação."""
    assert (
        _validate(
            port,
            _spec(
                delegation_target_for={
                    "agents": ["supervisor-agent"],
                    "format": "json",
                    "use_when": "the user attached an invoice",
                    "typical_seconds": 12,
                }
            ),
        )
        is None
    )


def test_signature_state_is_tri_state(port):
    """Ausência de verificação tem de ser LEGÍVEL, não implícita."""
    for state in ("unsigned", "present_unverified", "verified"):
        assert _validate(port, _spec(signature_state=state)) is None
    assert _validate(port, _spec(signature_state="probably-fine")) is not None
