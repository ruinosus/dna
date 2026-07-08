from dna.kernel.models import AgentSpec


def test_kind_writer_fields_parsed():
    spec = AgentSpec.from_raw({
        "writes_kind": "StatusReport",
        "creative_slots": ["verdict"],
        "system_slots": {"insight": "input.oracle_id"},
    })
    assert spec.writes_kind == "StatusReport"
    assert spec.creative_slots == ["verdict"]
    assert spec.system_slots == {"insight": "input.oracle_id"}


def test_kind_writer_fields_default_none():
    spec = AgentSpec.from_raw({})
    assert spec.writes_kind is None
    assert spec.creative_slots == []
    assert spec.system_slots == {}
