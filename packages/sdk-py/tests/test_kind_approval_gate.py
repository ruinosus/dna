"""An unapproved Kind never enters the registry — so it has no effect at all.

Registration is what CONFERS behaviour: a registered Kind validates documents
against its schema and routes their storage; an unregistered one does neither
(measured — an unknown Kind's documents are accepted unvalidated). So refusing
registration is not a soft gate, it is the absence of effect.
"""
from __future__ import annotations

from typing import Any

import pytest

from dna.adapters.filesystem import FilesystemCache
from dna.adapters.filesystem.writable import FilesystemWritableSource
from dna.extensions.helix import HelixExtension
from dna.extensions.kinddef import KindDefinitionExtension
from dna.kernel import Kernel


@pytest.fixture
def kernel_with_scope(tmp_path):
    """A writable Kernel over a filesystem scope — the store an authored
    ``KindDefinition`` really arrives from."""
    scope = "test-scope"
    scope_dir = tmp_path / scope
    scope_dir.mkdir(parents=True)
    (scope_dir / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Genome\n"
        f"metadata:\n  name: {scope}\n"
        "spec: {}\n"
    )

    k = Kernel()
    k.load(HelixExtension())
    k.load(KindDefinitionExtension())
    k.source(FilesystemWritableSource(str(tmp_path), kernel=k))
    k.cache(FilesystemCache(str(tmp_path)))
    return k, scope


async def _write_kinddef(
    k: Kernel, scope: str, *, kind: str, approved: bool,
) -> None:
    """Author a ``KindDefinition`` into ``scope``'s store, approved or not.

    Same shape as the descriptors in ``test_kinddef.py``, written through the
    real write path so the document reaches the registration funnel exactly as
    an authored one would."""
    spec: dict[str, Any] = {
        "target_api_version": "example.com/v1",
        "target_kind": kind,
        "alias": f"example-{kind.lower()}",
        "origin": "example.com",
        "schema": {"type": "object", "additionalProperties": True},
        "storage": {
            "type": "bundle",
            "container": f"{kind.lower()}s",
            "marker": f"{kind.upper()}.md",
        },
    }
    if approved:
        spec["approved_by"] = "reviewer@example.com"
        spec["approved_at"] = "2026-07-25T12:00:00Z"
    await k.write_document(
        scope,
        "KindDefinition",
        kind.lower(),
        {
            "apiVersion": "github.com/ruinosus/dna/core/v1",
            "kind": "KindDefinition",
            "metadata": {"name": kind.lower()},
            "spec": spec,
        },
    )


@pytest.mark.asyncio
async def test_an_unapproved_kind_is_not_registered(kernel_with_scope):
    k, scope = kernel_with_scope
    await _write_kinddef(k, scope, kind="Widget", approved=False)
    await k.instance_async(scope)

    assert k.kind_port_for("Widget", scope=scope) is None, (
        "an unapproved KindDefinition must not register: registration is what "
        "gives a Kind schema enforcement and storage routing"
    )


@pytest.mark.asyncio
async def test_approval_is_what_registers_it(kernel_with_scope):
    k, scope = kernel_with_scope
    await _write_kinddef(k, scope, kind="Widget", approved=True)
    await k.instance_async(scope)

    port = k.kind_port_for("Widget", scope=scope)
    assert port is not None, "an approved Kind registers normally"
    assert port.kind == "Widget"


@pytest.mark.asyncio
async def test_the_refusal_is_logged_not_silent(kernel_with_scope, caplog):
    """A Kind that vanishes without a word is a support ticket."""
    k, scope = kernel_with_scope
    await _write_kinddef(k, scope, kind="Widget", approved=False)
    await k.instance_async(scope)

    assert any("Widget" in r.message and "approv" in r.message.lower()
               for r in caplog.records), (
        "the skip must name the Kind and the reason — the author has to be able "
        "to find out why their Kind does nothing"
    )
