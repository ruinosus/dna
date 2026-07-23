import asyncio
import shutil
from pathlib import Path

from dna.runtime.builder import build_runtime
from dna.runtime.port import RuntimeHooks

# Committed fixture (this repo), NOT the sibling dna-cloud repo — must pass on
# a fresh clone with no dna-cloud checkout present.
FIXTURE_SRC = Path(__file__).parent / "fixtures" / "dna" / "dna-cloud-dev"


def _copy_fixture(tmp_path: Path, *, copilot_yaml: str | None = None) -> Path:
    """Copy the committed fixture tree; optionally overwrite the copilot doc's
    text (used to inject a ``serving.framework`` the committed fixture doesn't
    declare, proving the Kind change round-trips through the kernel)."""
    dest = tmp_path / ".dna" / "dna-cloud-dev"
    dest.mkdir(parents=True)
    for subdir in ("copilots", "agents", "federations", "tools"):
        shutil.copytree(FIXTURE_SRC / subdir, dest / subdir)
    if copilot_yaml is not None:
        (dest / "copilots" / "memory-copilot.yaml").write_text(copilot_yaml)
    return tmp_path / ".dna"


async def _compose(_headers):
    return "PROMPT"


def _hooks():
    return RuntimeHooks(mcp_auth=lambda: {}, compose=_compose)


def _spy_get_runtime(monkeypatch, sentinel_app):
    calls = []

    class _FakeRt:
        async def build(self, ctx, hooks):
            return sentinel_app

    def fake_get_runtime(framework):
        calls.append(framework)
        return _FakeRt()

    monkeypatch.setattr("dna.runtime.builder.get_runtime", fake_get_runtime)
    return calls


def test_serving_framework_maf_dispatches_to_maf_runtime(tmp_path, monkeypatch):
    # The committed fixture's memory-copilot.yaml declares `serving: {transport:
    # ag-ui}` with no `framework` — inject one to exercise the new Kind field
    # end-to-end (schema → EmitContext.serving.framework → build_runtime dispatch).
    original = (FIXTURE_SRC / "copilots" / "memory-copilot.yaml").read_text()
    assert "serving:\n    transport: ag-ui\n" in original
    maf_yaml = original.replace(
        "serving:\n    transport: ag-ui\n",
        "serving:\n    transport: ag-ui\n    framework: maf\n",
    )
    base_dir = _copy_fixture(tmp_path, copilot_yaml=maf_yaml)

    sentinel_app = object()
    calls = _spy_get_runtime(monkeypatch, sentinel_app)

    app = asyncio.run(
        build_runtime(
            "memory-copilot", base_dir=str(base_dir), scope="dna-cloud-dev", hooks=_hooks()
        )
    )

    assert calls == ["maf"]
    assert app is sentinel_app


def test_no_serving_framework_defaults_to_langchain(tmp_path, monkeypatch):
    # The committed fixture declares no `serving.framework` at all.
    base_dir = _copy_fixture(tmp_path)

    sentinel_app = object()
    calls = _spy_get_runtime(monkeypatch, sentinel_app)

    app = asyncio.run(
        build_runtime(
            "memory-copilot", base_dir=str(base_dir), scope="dna-cloud-dev", hooks=_hooks()
        )
    )

    assert calls == ["langchain"]
    assert app is sentinel_app
