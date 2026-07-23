"""s-markdown-bundle-reader-helper — MarkdownBundleReader behavior + adoption.

The byte-compat gate (old reader == new helper across an envelope/flat/edge
corpus) was verified before the swap; this is the permanent guard:
  1. MarkdownBundleReader implements the envelope-or-flat contract exactly.
  2. detect() is plain-exists by default, strict (kind/apiVersion) when asked.
  3. Each of the 10 migrated extensions now registers a MarkdownBundleReader
     (no hand-rolled single-marker reader left behind).
"""
from __future__ import annotations

import pytest

from dna.kernel.source.generic_rw import MarkdownBundleReader


class _MemBundle:
    """Minimal in-memory BundleHandle (name / exists / read_text)."""

    def __init__(self, name: str, entries: dict[str, str]):
        self._name = name
        self._entries = entries

    @property
    def name(self) -> str:
        return self._name

    def exists(self, entry: str) -> bool:
        return entry in self._entries

    def read_text(self, entry: str, encoding: str = "utf-8") -> str:
        return self._entries[entry]


def _reader(strict: str | None = None, oc: str | None = None) -> MarkdownBundleReader:
    return MarkdownBundleReader(
        "X.md", "MyKind", "github.com/ruinosus/dna/my/v1", strict_api_prefix=strict, owner_container=oc,
    )


# ── read() — envelope-or-flat ────────────────────────────────────────────


def test_envelope_uses_fm_spec_and_metadata():
    r = _reader()
    b = _MemBundle("doc-a", {"X.md": (
        "---\napiVersion: github.com/ruinosus/dna/my/v1\nkind: MyKind\n"
        "metadata:\n  name: kept\nspec:\n  foo: 1\n  bar: hi\n---\n\nbody\n"
    )})
    assert r.read(b) == {
        "apiVersion": "github.com/ruinosus/dna/my/v1", "kind": "MyKind",
        "metadata": {"name": "kept"}, "spec": {"foo": 1, "bar": "hi"},
    }


def test_envelope_defaults_name_from_bundle_and_apiversion_kind():
    r = _reader()
    b = _MemBundle("bundle-name", {"X.md": "---\nspec:\n  only: 1\n---\n"})
    assert r.read(b) == {
        "apiVersion": "github.com/ruinosus/dna/my/v1", "kind": "MyKind",
        "metadata": {"name": "bundle-name"}, "spec": {"only": 1},
    }


def test_flat_promotes_whole_frontmatter_to_spec():
    r = _reader()
    b = _MemBundle("bn", {"X.md": "---\nfoo: 1\nbar: two\n---\n\nbody\n"})
    assert r.read(b) == {
        "apiVersion": "github.com/ruinosus/dna/my/v1", "kind": "MyKind",
        "metadata": {"name": "bn"}, "spec": {"foo": 1, "bar": "two"},
    }


def test_non_dict_spec_is_treated_as_flat():
    r = _reader()
    b = _MemBundle("bn", {"X.md": "---\nspec: just-a-string\nfoo: 1\n---\n"})
    # spec is not a dict → not an envelope → whole fm becomes spec
    assert r.read(b)["spec"] == {"spec": "just-a-string", "foo": 1}


def test_no_frontmatter_yields_empty_spec():
    r = _reader()
    b = _MemBundle("bn", {"X.md": "plain text, no frontmatter\n"})
    assert r.read(b) == {
        "apiVersion": "github.com/ruinosus/dna/my/v1", "kind": "MyKind",
        "metadata": {"name": "bn"}, "spec": {},
    }


# ── detect() — simple vs strict ──────────────────────────────────────────


def test_detect_simple_is_plain_exists():
    r = _reader()
    assert r.detect(_MemBundle("b", {"X.md": "anything"})) is True
    assert r.detect(_MemBundle("b", {"OTHER.md": "x"})) is False


def test_detect_strict_validates_kind_or_apiversion():
    r = _reader(strict="github.com/ruinosus/dna/my")
    # kind match
    assert r.detect(_MemBundle("b", {"X.md": "---\nkind: MyKind\n---\n"})) is True
    # apiVersion prefix match
    assert r.detect(_MemBundle("b", {"X.md": "---\napiVersion: github.com/ruinosus/dna/my/v1\n---\n"})) is True
    # neither → False (even though the marker exists)
    assert r.detect(_MemBundle("b", {"X.md": "---\nkind: Other\napiVersion: z/v1\n---\n"})) is False
    # marker absent → False
    assert r.detect(_MemBundle("b", {})) is False


def test_owner_container_set_only_when_given():
    assert getattr(_reader(oc="lottie-assets"), "_owner_container", None) == "lottie-assets"
    assert getattr(_reader(), "_owner_container", None) is None


# ── adoption — the 10 extensions register MarkdownBundleReader ────────────


EXPECTED = {
    
    
    
    
}


@pytest.mark.parametrize("ext_mod,marker", sorted(EXPECTED.items()))
def test_extension_registers_markdown_bundle_reader(ext_mod, marker):
    import importlib

    mod = importlib.import_module(f"dna.extensions.{ext_mod}")
    ext_cls = next(
        getattr(mod, n) for n in dir(mod)
        if n.endswith("Extension") and isinstance(getattr(mod, n), type)
    )
    readers: list = []

    class _K:
        def kind(self, *a, **k): pass
        def reader(self, r): readers.append(r)
        def writer(self, *a, **k): pass
        def template(self, *a, **k): pass

    ext_cls().register(_K())
    mbrs = [r for r in readers if isinstance(r, MarkdownBundleReader)]
    assert any(r._marker == marker for r in mbrs), (
        f"{ext_mod} should register a MarkdownBundleReader for {marker}; "
        f"got markers {[getattr(r, '_marker', '?') for r in readers]}"
    )
