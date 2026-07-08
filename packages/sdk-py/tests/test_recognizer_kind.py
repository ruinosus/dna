"""Tests for the Recognizer Kind (presidio/v1)."""
from dna import Kernel


class TestRecognizerKind:
    def test_registered(self):
        k = Kernel.auto()
        found = any(kp.kind == "Recognizer" for kp in k._kinds.values())
        assert found

    def test_metadata(self):
        k = Kernel.auto()
        for kp in k._kinds.values():
            if kp.kind == "Recognizer":
                assert kp.alias == "presidio-recognizer"
                assert kp.api_version == "presidio/v1"
                assert kp.origin == "microsoft.github.io/presidio"
                break
        else:
            raise AssertionError("Recognizer kind not found")

    def test_safety_policy_dep_filters(self):
        k = Kernel.auto()
        for kp in k._kinds.values():
            if kp.kind == "SafetyPolicy":
                deps = kp.dep_filters()
                assert deps is not None
                assert deps.get("recognizers") == "presidio-recognizer"
                break
        else:
            raise AssertionError("SafetyPolicy kind not found")
