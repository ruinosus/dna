from dna.runtime.port import register_runtime, get_runtime, available_runtimes, UnknownRuntime, RuntimePort
import pytest


class _FakeRt:
    target = "fake"
    async def build(self, ctx, hooks): return object()


def test_register_get_available():
    register_runtime(_FakeRt())
    assert "fake" in available_runtimes()
    assert isinstance(get_runtime("fake"), RuntimePort)


def test_unknown_runtime_names_available():
    with pytest.raises(UnknownRuntime) as e:
        get_runtime("nope")
    assert "nope" in str(e.value)


def test_builtins_langchain_and_maf_register():
    # _ensure_runtimes registers the two built-ins lazily
    assert "langchain" in available_runtimes()
    assert "maf" in available_runtimes()
