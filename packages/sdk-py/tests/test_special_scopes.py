# packages/sdk-py/tests/test_special_scopes.py
"""i-112 Phase 1 — single source of truth for special-scope names."""
from dna.kernel.protocols import DEFAULT_BASE_SCOPE, SYSTEM_SCOPE

def test_default_base_scope_is_platform():
    assert DEFAULT_BASE_SCOPE == "_lib"

def test_system_scope_is_platform():
    assert SYSTEM_SCOPE == "_lib"

def test_kernel_constants_reference_the_single_source():
    from dna.kernel import Kernel
    from dna.kernel.protocols import DEFAULT_BASE_SCOPE, SYSTEM_SCOPE
    assert Kernel._INHERIT_PARENT_SCOPE == DEFAULT_BASE_SCOPE
    assert Kernel._MODEL_REGISTRY_SCOPE == SYSTEM_SCOPE
    assert Kernel._VOICE_POLICY_SCOPE == SYSTEM_SCOPE

def test_kernel_scope_constants_derive_from_single_source():
    """Guard (positivo, robusto a reformatação): as 3 constantes DERIVAM da fonte única."""
    import inspect
    from dna.kernel import Kernel
    src = inspect.getsource(Kernel)
    assert "_INHERIT_PARENT_SCOPE = DEFAULT_BASE_SCOPE" in src
    assert "_MODEL_REGISTRY_SCOPE = SYSTEM_SCOPE" in src
    assert "_VOICE_POLICY_SCOPE = SYSTEM_SCOPE" in src
