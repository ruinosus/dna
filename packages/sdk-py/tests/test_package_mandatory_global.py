"""i-112 catalog ph1 — mandatory + global_scope no GenomeSpec (OQ1)."""
from dna.kernel.models import GenomeSpec

def test_defaults_false():
    s = GenomeSpec()
    assert s.mandatory is False and s.global_scope is False

def test_from_raw_roundtrip():
    s = GenomeSpec.from_raw({"owner": "platform", "mandatory": True, "global_scope": True})
    assert s.mandatory is True and s.global_scope is True

def test_from_raw_absent_defaults_false():
    s = GenomeSpec.from_raw({"owner": "platform"})
    assert s.mandatory is False and s.global_scope is False

def test_not_overlayable():
    from dna.extensions.helix import GenomeKind
    of = GenomeKind.OVERLAYABLE_FIELDS
    assert "mandatory" not in of and "global_scope" not in of
