"""``dna.load_tools`` — the agent-facing tool surface, as data
(f-dna-tools-as-data).

Three things this pins:

1. **The consumer helper** (s-load-tools-helper): ``load_tools(scope)`` →
   ``ToolLibrary`` maps a tool name to its ``ToolSurface`` ({description,
   parameters}); a miss raises the typed :class:`dna.ToolNotFound`.

2. **The cross-language dogfood** (the point): the SAME Tool document read via
   Python ``load_tools`` produces the surface committed in
   ``examples/tools_as_data/expected-surface.json`` — the identical oracle the
   TypeScript twin (``tools-as-data.test.ts``) asserts against. One document,
   one byte-identical ``Tool`` Kind descriptor, two runtimes.

3. **Tenant overridability** (the SaaS hook): a tenant overlay of a Tool's
   ``metadata.description`` wins for that tenant while the base stays intact —
   for free, because ``Tool`` is an overlayable Kind.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from dna import ToolNotFound, ToolSurface, load_tools

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_EXAMPLE_BASE = str(_ROOT / "examples" / "tools_as_data" / ".dna")
_EXPECTED = _ROOT / "examples" / "tools_as_data" / "expected-surface.json"


@pytest.fixture()
def tools():
    return load_tools("tools-demo", base_dir=_EXAMPLE_BASE)


# ── consumer helper (s-load-tools-helper) ──────────────────────────────────


class TestToolLibrary:
    def test_names_lists_tools(self, tools) -> None:
        assert tools.names() == ["generate-artifact"]

    def test_get_returns_surface(self, tools) -> None:
        surface = tools["generate-artifact"]
        assert isinstance(surface, ToolSurface)
        assert "shareable artifact" in surface.description
        assert surface.parameters["required"] == ["title", "content"]

    def test_missing_tool_raises_typed_error(self, tools) -> None:
        with pytest.raises(ToolNotFound) as ei:
            tools["does-not-exist"]
        # fail-loud + helpful: names the miss, the scope, and what's available.
        assert ei.value.name == "does-not-exist"
        assert "generate-artifact" in ei.value.available

    def test_mapping_protocol(self, tools) -> None:
        assert "generate-artifact" in tools
        assert "nope" not in tools
        assert len(tools) == 1
        assert list(tools) == ["generate-artifact"]

    def test_cached(self, tools) -> None:
        assert tools["generate-artifact"] is tools["generate-artifact"]


# ── cross-language dogfood (the point) ─────────────────────────────────────


def test_python_surface_matches_shared_oracle(tools) -> None:
    """The Python-projected surface equals the committed oracle that the
    TypeScript twin also asserts against — proving both runtimes read the
    SAME Tool document into the SAME agent-facing surface."""
    surface = tools["generate-artifact"]
    actual = {"description": surface.description, "parameters": surface.parameters}
    expected = json.loads(_EXPECTED.read_text(encoding="utf-8"))
    assert actual == expected


# ── tenant overridability (the SaaS hook) ──────────────────────────────────


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


_GENOME = (
    "apiVersion: github.com/ruinosus/dna/v1\n"
    "kind: Genome\n"
    "metadata: {name: shop, description: base}\n"
    "spec: {default_agent: a}\n"
)


def _tool(desc: str) -> str:
    return (
        "apiVersion: github.com/ruinosus/dna/v1\n"
        "kind: Tool\n"
        f"metadata: {{name: search, description: {desc!r}}}\n"
        "spec:\n"
        "  type: builtin\n"
        "  input_schema: {type: object, properties: {q: {type: string}}}\n"
    )


def test_tenant_overlay_overrides_description_base_intact(tmp_path) -> None:
    from dna.adapters.filesystem.source import FilesystemSource
    from dna.kernel import Kernel
    from dna.tools import ToolLibrary

    base_desc = "BASE — search the shared catalog."
    acme_desc = "ACME — search ACME's private index."

    _write(tmp_path / "shop" / "Genome.yaml", _GENOME)
    _write(tmp_path / "shop" / "tools" / "search.yaml", _tool(base_desc))
    _write(
        tmp_path / "tenants" / "acme" / "scopes" / "shop" / "tools" / "search.yaml",
        _tool(acme_desc),
    )

    k = Kernel.auto(source=FilesystemSource(str(tmp_path)))
    base = ToolLibrary(k.instance("shop"))
    acme = ToolLibrary(k.with_tenant("acme").instance("shop"))

    # The overlay wins for the tenant …
    assert acme["search"].description == acme_desc
    # … while the base is untouched (a different tenant / no tenant sees base).
    assert base["search"].description == base_desc
    assert base["search"].description != acme["search"].description
