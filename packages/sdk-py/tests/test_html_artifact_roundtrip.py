"""s-dx-html-artifact-kind — HtmlArtifact bundle reader/writer round-trip.

The HtmlArtifact Kind stores an HTML page as a first-class work-item output.
Its primary marker (ARTIFACT.html) must round-trip BYTE-FAITHFUL — a design
doc / roteiro is worthless if the writer mangles the markup. artifact.json is
a canonical-JSON metadata companion (like a Soul's soul.json).
"""
from __future__ import annotations

import json
from pathlib import Path

from dna.kernel import Kernel
from dna.kernel.bundle.handle import FilesystemBundleHandle
from dna.extensions.sdlc import HtmlArtifactReader, HtmlArtifactWriter


_HTML = (
    "<!DOCTYPE html>\n"
    "<html lang=\"pt-BR\">\n"
    "<head>\n"
    "  <meta charset=\"utf-8\">\n"
    "  <title>DNA DX — Agora → Depois</title>\n"
    "  <style>body { --bg: #f2f0ea; } /* quotes ' and \" & < > */</style>\n"
    "</head>\n"
    "<body>\n"
    "  <h1>Agora → Depois</h1>\n"
    "  <p>Acentuação: configuração, herança, funções.</p>\n"
    "</body>\n"
    "</html>\n"
)


def _write_read(tmp_path: Path, raw: dict) -> dict:
    dest = FilesystemBundleHandle(tmp_path / raw["metadata"]["name"])
    HtmlArtifactWriter().write(dest, raw)
    return HtmlArtifactReader().read(dest)


def test_html_marker_is_byte_faithful(tmp_path: Path) -> None:
    raw = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "kind": "HtmlArtifact",
        "metadata": {"name": "ha-x"},
        "spec": {"html": _HTML},
    }
    HtmlArtifactWriter().write(FilesystemBundleHandle(tmp_path / "ha-x"), raw)
    on_disk = (tmp_path / "ha-x" / "ARTIFACT.html").read_text(encoding="utf-8")
    # The stored HTML is IDENTICAL to the input — no frontmatter, no re-escaping.
    assert on_disk == _HTML


def test_roundtrip_html_and_metadata(tmp_path: Path) -> None:
    aj = {
        "title": "DNA DX — Agora → Depois",
        "description": "Antes/depois da DX do DNA.",
        "source": "design doc do épico e-dna-dx",
        "created_at": "2026-07-11T00:00:00+00:00",
    }
    raw = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "kind": "HtmlArtifact",
        "metadata": {"name": "ha-e-dna-dx-design"},
        "spec": {"html": _HTML, "artifact_json": aj},
    }
    back = _write_read(tmp_path, raw)

    assert back["kind"] == "HtmlArtifact"
    assert back["metadata"]["name"] == "ha-e-dna-dx-design"
    # description promoted from artifact.json into metadata for search/listing.
    assert back["metadata"]["description"] == "Antes/depois da DX do DNA."
    # HTML preserved verbatim across the round-trip.
    assert back["spec"]["html"] == _HTML
    # Structured metadata preserved.
    assert back["spec"]["artifact_json"] == aj


def test_second_roundtrip_is_stable(tmp_path: Path) -> None:
    """Read → write → read must be a fixed point (idempotent)."""
    aj = {"title": "T", "source": "s", "created_at": "2026-07-11"}
    raw = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "kind": "HtmlArtifact",
        "metadata": {"name": "ha-stable"},
        "spec": {"html": _HTML, "artifact_json": aj},
    }
    first = _write_read(tmp_path, raw)
    # Re-write the parsed doc and read again — bytes must not drift.
    dest2 = FilesystemBundleHandle(tmp_path / "ha-stable-2")
    HtmlArtifactWriter().write(dest2, {**first, "metadata": {"name": "ha-stable-2"}})
    html2 = (tmp_path / "ha-stable-2" / "ARTIFACT.html").read_text(encoding="utf-8")
    json2 = json.loads((tmp_path / "ha-stable-2" / "artifact.json").read_text(encoding="utf-8"))
    assert html2 == _HTML
    assert json2 == aj


def test_html_only_no_metadata(tmp_path: Path) -> None:
    """An HtmlArtifact with no artifact.json still round-trips the HTML."""
    raw = {
        "apiVersion": "github.com/ruinosus/dna/sdlc/v1",
        "kind": "HtmlArtifact",
        "metadata": {"name": "ha-bare"},
        "spec": {"html": _HTML},
    }
    dest = FilesystemBundleHandle(tmp_path / "ha-bare")
    HtmlArtifactWriter().write(dest, raw)
    assert not (tmp_path / "ha-bare" / "artifact.json").exists()
    back = HtmlArtifactReader().read(dest)
    assert back["spec"]["html"] == _HTML
    assert "artifact_json" not in back["spec"]


def test_kernel_registers_html_artifact() -> None:
    """The Kind + reader + writer are wired into the auto kernel."""
    k = Kernel.auto()
    aliases = {kp.alias for kp in k._kinds.values() if getattr(kp, "alias", "")}
    assert "sdlc-html-artifact" in aliases
    assert any(w.can_write({"kind": "HtmlArtifact"}) for w in k._writers)
    assert any(r.__class__.__name__ == "HtmlArtifactReader" for r in k._readers)


def test_typed_parse() -> None:
    from dna.kernel.models import TypedHtmlArtifact
    doc = TypedHtmlArtifact.from_raw({
        "metadata": {"name": "ha-x", "description": "d"},
        "spec": {"html": _HTML, "artifact_json": {"title": "T"}},
    })
    assert doc.spec.html == _HTML
    assert doc.spec.artifact_json == {"title": "T"}
    assert doc.metadata.name == "ha-x"
