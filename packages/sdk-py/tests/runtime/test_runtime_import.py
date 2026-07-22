def test_build_copilot_is_importable():
    from dna.runtime import build_copilot
    assert callable(build_copilot)
