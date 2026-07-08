"""i-112 catalog ph2 — capability manifest no GenomeSpec."""
import dataclasses
from dna.kernel.models import GenomeSpec

def test_default_empty():
    assert GenomeSpec().capabilities == []

def test_from_raw_reads_capabilities():
    s = GenomeSpec.from_raw({"owner": "platform", "capabilities": [
        {"kind": "soulspec-soul", "name": "voice-policy", "location": "souls/voice-policy.yaml"},
    ]})
    assert len(s.capabilities) == 1
    assert s.capabilities[0]["kind"] == "soulspec-soul"
    assert s.capabilities[0]["name"] == "voice-policy"

def test_from_raw_absent_defaults_empty():
    assert GenomeSpec.from_raw({"owner": "platform"}).capabilities == []

def test_write_roundtrip_via_asdict():
    # write-path serialization (document.py uses dataclasses.asdict) must carry capabilities
    caps = [{"kind": "modelreg-modelprofile", "name": "gpt-5.4", "location": "model-profiles/gpt-5.4.yaml"}]
    s = GenomeSpec.from_raw({"owner": "platform", "capabilities": caps})
    d = dataclasses.asdict(s)
    assert d["capabilities"] == caps
    # round-trips back through from_raw identically
    assert GenomeSpec.from_raw(d).capabilities == caps

def test_capabilities_not_overlayable():
    from dna.extensions.helix import GenomeKind
    assert "capabilities" not in GenomeKind.OVERLAYABLE_FIELDS
