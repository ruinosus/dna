"""Test-double bases for SDK ports (s-dna-source-conformance-kit)."""
from __future__ import annotations

from typing import Any


class CoreSourceStub:
    """Minimal test double that satisfies the ``kernel.source()`` boot gate.

    Carries the CORE SourcePort surface as harmless no-ops — subclass it
    and override only what your test exercises:

        class _FakeSource(CoreSourceStub):
            async def load_layer(self, scope, layer_id, layer_value, readers=None):
                return my_docs

    The boot gate (``validate_source_port``) requires the core members BY
    NAME on anything handed to ``kernel.source()``; ad-hoc fakes with a
    single method no longer pass. Capability-mediated members
    (``list_doc_refs``/``load_one``/``query``/``count``) stay absent on
    purpose: the kernel serves those via fallbacks, and their absence is
    how a stub declares "not granular, no pushdown".
    """

    supports_readers: bool = False

    async def load_bootstrap_docs(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        return []

    async def load_all(
        self, scope: str, readers: list | None = None,
    ) -> list[dict[str, Any]]:
        return []

    async def resolve_ref(self, scope: str, ref: str) -> str:
        return ref

    async def load_layer(
        self, scope: str, layer_id: str, layer_value: str,
        readers: list | None = None,
    ) -> list[dict[str, Any]]:
        return []

    async def close(self) -> None:
        return None
