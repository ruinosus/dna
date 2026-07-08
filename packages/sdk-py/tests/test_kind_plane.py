"""F1 two-planes (spec 2026-06-09): KindBase.plane default + override."""
from dna.kernel.kind_base import KindBase
from dna.kernel.protocols import StorageDescriptor


class _CompKind(KindBase):
    api_version = "test.io/v1"
    kind = "Comp"
    alias = "test-comp"
    storage = StorageDescriptor.yaml("comps")


class _RecKind(KindBase):
    api_version = "test.io/v1"
    kind = "Rec"
    alias = "test-rec"
    storage = StorageDescriptor.yaml("recs")
    plane = "record"


def test_plane_defaults_to_composition():
    assert _CompKind().plane == "composition"


def test_plane_record_override():
    assert _RecKind().plane == "record"


import pytest
from dna.kernel import Kernel, KindRegistrationError


def _mk(name: str, **attrs):
    """Kind class factory for lint tests."""
    return type(
        f"{name}Kind", (KindBase,),
        {"api_version": "test.io/v1", "kind": name,
         "alias": f"test-{name.lower()}",
         "storage": StorageDescriptor.yaml(name.lower() + "s"), **attrs},
    )()


def test_lint_rejects_record_prompt_target():
    k = Kernel()
    with pytest.raises(KindRegistrationError, match="plane"):
        k.kind(_mk("BadPT", plane="record", is_prompt_target=True))


def test_lint_rejects_record_flatten():
    k = Kernel()
    with pytest.raises(KindRegistrationError, match="plane"):
        k.kind(_mk("BadFl", plane="record", flatten_in_context=True))


def test_lint_rejects_record_schema_affecting():
    k = Kernel()
    with pytest.raises(KindRegistrationError, match="plane"):
        k.kind(_mk("BadSA", plane="record", is_schema_affecting=True))


def test_lint_rejects_record_root():
    from dna.kernel.protocols import StorageDescriptor as SD
    k = Kernel()
    with pytest.raises(KindRegistrationError, match="plane"):
        k.kind(_mk("BadRoot", plane="record", storage=SD.root("BadRoot.yaml")))


def test_lint_rejects_invalid_plane_value():
    k = Kernel()
    with pytest.raises(KindRegistrationError, match="plane"):
        k.kind(_mk("BadVal", plane="cacheless"))


def test_lint_accepts_valid_record_and_composition():
    k = Kernel()
    k.kind(_mk("GoodRec", plane="record", is_runtime_artifact=True))
    k.kind(_mk("GoodComp", is_prompt_target=True))  # default composition


def test_sdlc_kinds_are_records():
    """Every Kind registered by the SDLC extension is a record (F1)."""
    from dna.extensions.sdlc import SdlcExtension
    k = Kernel()
    k.load(SdlcExtension())
    sdlc_kinds = [kp for kp in k._kinds.values() if kp.origin == "github.com/ruinosus/dna/sdlc"]
    assert len(sdlc_kinds) > 10  # sanity: a extensão registra ~34 kinds
    non_records = [kp.kind for kp in sdlc_kinds if getattr(kp, "plane", "") != "record"]
    assert non_records == [], f"SDLC kinds sem plane=record: {non_records}"


def test_runtime_artifacts_are_records():
    """Every is_runtime_artifact Kind across loaded extensions is a record."""
    k = Kernel.auto()  # entry-point discovery carrega todas as extensões
    offenders = [
        kp.kind for kp in k._kinds.values()
        if getattr(kp, "is_runtime_artifact", False)
        and getattr(kp, "plane", "") != "record"
    ]
    assert offenders == [], f"runtime artifacts sem plane=record: {offenders}"
