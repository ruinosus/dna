"""KindDefinitionExtension — the built-in meta-kind extension.

Ships the ``KindDefinition`` kind itself. KindDefinition documents live
under ``.dna/<scope>/kinds/<name>/KIND.yaml`` (bundle layout so future
per-kind DOCS.md files can live next to the definition). The kernel's
2-phase loader parses these first, then synthesizes a DeclarativeKindPort
for each before parsing the rest of the manifest.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from dna.kernel.models import TypedKindDefinition
from dna.kernel.kinds.base import KindBase
from dna.kernel.preview import PreviewBlock
from dna.kernel.protocols import ExtensionHost, StorageDescriptor, ReaderPort, WriterPort
from dna.kernel.bundle.handle import BundleHandle

from dna.extensions.helix import _schema_from_model


class KindDefinitionKind(KindBase):
    api_version = TypedKindDefinition.API_VERSION
    kind = TypedKindDefinition.KIND
    alias = "kinddef-kinddefinition"
    is_schema_affecting = True
    is_overlayable = False
    scope_inheritable = False
    model = TypedKindDefinition
    origin = "github.com/ruinosus/dna/core"
    storage = StorageDescriptor.bundle("kinds", "KIND.yaml")
    visible_in_backend = True  # explicit: user-authored via wizard, not system-generated
    graph_style = {"fill": "#A855F7", "stroke": "#9333EA", "text_color": "#fff"}
    ascii_icon = "🧬"
    display_label = "KindDefinitions"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False
    docs = (
        "A KindDefinition declaratively defines a brand-new kind without "
        "writing Python code. Its spec carries the target apiVersion, kind "
        "name, alias, JSON Schema for the document spec, storage layout, "
        "and prompt flags. The kernel's 2-phase loader parses KindDefinitions "
        "first, synthesizes a DeclarativeKindPort for each, then parses the "
        "rest of the manifest so regular documents can reference the newly "
        "registered kind."
    )

    def schema(self) -> dict[str, Any] | None:
        return _schema_from_model(self.model)

    def parse(self, raw: dict[str, Any]) -> Any:
        return TypedKindDefinition.from_raw(raw)

    def summary(self, doc: Any) -> dict[str, Any] | None:
        return None

    def preview(self, doc: Any) -> list[PreviewBlock]:
        import json as _json

        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        fields: list[dict[str, str]] = []
        for k in ("target_kind", "target_api_version", "alias", "origin"):
            v = spec_dict.get(k)
            if isinstance(v, str) and v:
                fields.append({"label": k, "value": v})
        for flag in ("is_root", "prompt_target", "flatten_in_context"):
            v = spec_dict.get(flag)
            if v is not None:
                fields.append({"label": flag, "value": str(v)})
        if spec_dict.get("storage"):
            fields.append(
                {
                    "label": "storage",
                    "value": _json.dumps(spec_dict["storage"], indent=2, default=str),
                }
            )
        if spec_dict.get("schema"):
            fields.append(
                {
                    "label": "schema",
                    "value": _json.dumps(spec_dict["schema"], indent=2, default=str),
                }
            )
        docs = spec_dict.get("docs")
        if isinstance(docs, str) and docs:
            fields.append({"label": "docs", "value": docs})
        if not fields:
            return [PreviewBlock(kind="empty", title=f"KindDefinition {doc.name}")]
        return [
            PreviewBlock(
                kind="fields",
                title=f"KindDefinition {doc.name}",
                fields=fields,
            )
        ]


class KindDefinitionReader(ReaderPort):
    """Bundle reader for ``kinds/<name>/KIND.yaml``.

    A tiny dedicated reader keeps KIND.yaml as *plain YAML* (not
    frontmatter+body) so authors can write a normal Kubernetes-style
    apiVersion/kind/metadata/spec document.
    """

    _marker = "KIND.yaml"

    def detect(self, bundle: BundleHandle) -> bool:
        return bundle.exists("KIND.yaml")

    def read(self, bundle: BundleHandle) -> dict[str, Any]:
        doc = yaml.safe_load(bundle.read_text("KIND.yaml"))
        if not isinstance(doc, dict):
            raise ValueError(f"KIND.yaml in bundle '{bundle.name}' did not parse into a mapping")
        doc.setdefault("apiVersion", TypedKindDefinition.API_VERSION)
        doc.setdefault("kind", TypedKindDefinition.KIND)
        meta = doc.setdefault("metadata", {})
        meta.setdefault("name", bundle.name)
        return doc


class KindDefinitionWriter(WriterPort):
    """Writer for KindDefinition bundles — plain YAML, no frontmatter."""

    _kind = TypedKindDefinition.KIND

    def can_write(self, raw: dict) -> bool:
        return raw.get("kind") == TypedKindDefinition.KIND

    def write(self, bundle: BundleHandle, raw: dict) -> None:
        bundle.write_text(
            "KIND.yaml",
            yaml.dump(raw, default_flow_style=False, sort_keys=False, allow_unicode=True),
        )

    def serialize(self, raw: dict) -> list[dict[str, str]]:
        return [
            {
                "relativePath": "KIND.yaml",
                "content": yaml.dump(
                    raw, default_flow_style=False, sort_keys=False, allow_unicode=True
                ),
            }
        ]


class KindDefinitionExtension:
    name = "kinddef"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(KindDefinitionKind())
        kernel.reader(KindDefinitionReader())
        kernel.writer(KindDefinitionWriter())
