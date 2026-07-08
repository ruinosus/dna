"""ExtensionHost — explicit registration-time contract (s-dna-extension-host-contract).

Guards three things:

1. ``kernel.load()`` fail-loud validates the WHOLE Extension contract
   (name: non-empty str, version: str, register: callable) with a clear
   ``ExtensionLoadError`` — not just ``callable(register)``.
2. The real ``Kernel`` structurally satisfies the ``ExtensionHost``
   Protocol (the registration vocabulary extensions are typed against).
3. Every builtin extension declared as an entry point passes the gate.

TS twin: ``tests/extension-host-contract.test.ts``.
"""
from __future__ import annotations

import pytest

from dna.kernel import Kernel
from dna.kernel.errors import ExtensionLoadError
from dna.kernel.protocols import (
    EXTENSIONS_ENTRY_POINT_GROUP,
    Extension,
    ExtensionHost,
    TemplateProvider,
)


# ---------------------------------------------------------------------------
# 1. load() gate — fail-loud on structurally invalid extensions
# ---------------------------------------------------------------------------

class _GoodExt:
    name = "good-ext"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:  # noqa: ARG002
        return None


def test_load_accepts_valid_extension():
    k = Kernel()
    k.load(_GoodExt())
    assert any(getattr(e, "name", None) == "good-ext" for e in k._extensions)


def test_load_rejects_missing_register():
    class NoRegister:
        name = "no-register"
        version = "1.0.0"

    with pytest.raises(ExtensionLoadError, match="no callable register"):
        Kernel().load(NoRegister())  # type: ignore[arg-type]


def test_load_rejects_non_callable_register():
    class BadRegister:
        name = "bad-register"
        version = "1.0.0"
        register = "not-callable"

    with pytest.raises(ExtensionLoadError, match="no callable register"):
        Kernel().load(BadRegister())  # type: ignore[arg-type]


def test_load_rejects_missing_name():
    class NoName:
        version = "1.0.0"

        def register(self, kernel):  # noqa: ARG002
            return None

    with pytest.raises(ExtensionLoadError, match="no valid `name`"):
        Kernel().load(NoName())  # type: ignore[arg-type]


def test_load_rejects_blank_name():
    class BlankName:
        name = "   "
        version = "1.0.0"

        def register(self, kernel):  # noqa: ARG002
            return None

    with pytest.raises(ExtensionLoadError, match="no valid `name`"):
        Kernel().load(BlankName())


def test_load_rejects_non_str_name():
    class IntName:
        name = 42
        version = "1.0.0"

        def register(self, kernel):  # noqa: ARG002
            return None

    with pytest.raises(ExtensionLoadError, match="no valid `name`"):
        Kernel().load(IntName())  # type: ignore[arg-type]


def test_load_rejects_missing_version():
    class NoVersion:
        name = "no-version"

        def register(self, kernel):  # noqa: ARG002
            return None

    with pytest.raises(ExtensionLoadError, match="no valid `version`"):
        Kernel().load(NoVersion())  # type: ignore[arg-type]

    # The error names the extension so the operator can find it.
    with pytest.raises(ExtensionLoadError, match="no-version"):
        Kernel().load(NoVersion())  # type: ignore[arg-type]


def test_load_gate_fires_before_register_runs():
    """A structurally invalid extension must never get to register()."""
    ran = []

    class NoName:
        version = "1.0.0"

        def register(self, kernel):  # noqa: ARG002
            ran.append(True)

    with pytest.raises(ExtensionLoadError):
        Kernel().load(NoName())  # type: ignore[arg-type]
    assert ran == []


# ---------------------------------------------------------------------------
# 2. Kernel satisfies ExtensionHost (structural)
# ---------------------------------------------------------------------------

def test_kernel_satisfies_extension_host():
    k = Kernel()
    assert isinstance(k, ExtensionHost)


def test_extension_host_surface_is_present_and_callable():
    """Belt-and-braces: runtime_checkable only checks *presence*; also
    assert each registration method is callable on the real Kernel."""
    k = Kernel()
    for method in (
        "kind",
        "kind_from_descriptor",
        "reader",
        "writer",
        "on",
        "on_veto",
        "tool",
        "composition_profile",
    ):
        assert callable(getattr(k, method)), f"Kernel.{method} missing"
    # hooks is the HookRegistry attribute, not a method.
    from dna.kernel.hooks import HookRegistry
    assert isinstance(k.hooks, HookRegistry)


def test_good_ext_satisfies_extension_protocol():
    assert isinstance(_GoodExt(), Extension)


# ---------------------------------------------------------------------------
# 3. TemplateProvider — optional capability protocol
# ---------------------------------------------------------------------------

def test_template_provider_protocol():
    class WithTemplates:
        name = "with-templates"
        version = "1.0.0"

        def register(self, kernel):  # noqa: ARG002
            return None

        def templates(self):
            return []

    assert isinstance(WithTemplates(), TemplateProvider)
    assert not isinstance(_GoodExt(), TemplateProvider)


# ---------------------------------------------------------------------------
# 4. Every builtin entry-point extension passes the load() gate
# ---------------------------------------------------------------------------

def test_all_builtin_extensions_pass_load_gate():
    from importlib.metadata import entry_points

    eps = list(entry_points(group=EXTENSIONS_ENTRY_POINT_GROUP))
    assert eps, "no builtin extensions discovered via entry points"
    for ep in eps:
        ext = ep.load()()
        name = getattr(ext, "name", None)
        version = getattr(ext, "version", None)
        assert isinstance(name, str) and name.strip(), (
            f"builtin extension {ep.value} has invalid name {name!r}"
        )
        assert isinstance(version, str) and version.strip(), (
            f"builtin extension {name} has invalid version {version!r}"
        )
        assert callable(getattr(ext, "register", None)), (
            f"builtin extension {name} has no callable register()"
        )
