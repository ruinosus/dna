"""AgentsMdExtension — AgentDefinition kind + AgentDefinitionReader + Writer.

The agents.md standard (agents.md/v1) defines an agent archetype via AGENTS.md
prose. This is a full agent definition — identity, conventions, tools, and
behavior specified in Markdown sections. Not just "context".

Is a prompt target with flatten_in_context=True.
Never filtered by dep_filters — always present in all prompts.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from dna.kernel.models import TypedAgentDefinition
from dna.kernel.kinds.base import KindBase
from dna.kernel.preview import PreviewBlock
from dna.kernel.protocols import ExtensionHost, StorageDescriptor, ReaderPort, WriterPort
from dna.kernel.bundle.handle import BundleHandle

from dna.extensions.helix import _schema_from_model


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a markdown doc into (metadata dict, body).

    Returns ({}, text) when no frontmatter is present. Mirrors the SoulSpec
    helper but trims leading blank lines from the body so simple one-liner
    AGENTS.md bodies round-trip cleanly.
    """
    match = re.match(r"^---\n(.*?)---\n?(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    try:
        parsed = yaml.safe_load(match.group(1)) or {}
        if isinstance(parsed, dict):
            return parsed, match.group(2).lstrip("\n")
    except Exception:
        pass
    return {}, text


class AgentDefinitionKind(KindBase):
    api_version = "agents.md/v1"
    kind = "AgentDefinition"
    alias = "agentsmd-agent"
    model = TypedAgentDefinition
    origin = "agents.md"
    storage = StorageDescriptor.standalone("AGENTS.md")
    graph_style = {"fill": "#6366F1", "stroke": "#4F46E5", "text_color": "#fff"}
    ascii_icon = "📝"
    display_label = "AGENTS.md"
    is_prompt_target = True
    prompt_target_priority = 1
    flatten_in_context = True
    description_fallback_field = "content"
    docs = (
        "An AgentDefinition is a standalone AGENTS.md file following the "
        "agents.md/v1 standard — prose that describes an agent's identity, "
        "conventions, tools, and behavior. Unlike a Soul (which is personality "
        "only) or a Skill (which is an on-demand capability), an "
        "AgentDefinition is the full archetype: when present it is flattened "
        "into every prompt (flatten_in_context=True) and is never filtered by "
        "dep_filters. Use it when you want an agent fully described in a "
        "single portable markdown file, independent of the helix module."
    )

    def schema(self) -> dict[str, Any] | None:
        return _schema_from_model(self.model)

    def parse(self, raw: dict[str, Any]) -> Any:
        return TypedAgentDefinition.from_raw(raw)

    def summary(self, doc: Any) -> dict[str, Any] | None:
        return None

    def prompt_template(self) -> str | None:
        # Triple braces disable HTML escaping — content is markdown.
        return "{{{content}}}"

    def preview(self, doc: Any) -> list[PreviewBlock]:
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        content = spec_dict.get("content")
        if not isinstance(content, str) or not content:
            return [PreviewBlock(kind="empty", title="AGENTS.md (empty)")]
        return [PreviewBlock(kind="markdown", title="AGENTS.md", body=content)]


class AgentDefinitionReader(ReaderPort):
    """Detects and reads standalone AGENTS.md files (not inside soul bundles).

    The agents.md standard uses AGENTS.md to define agent archetypes.
    Soul bundles may also contain AGENTS.md, but those are part of the
    soul — not standalone agent definitions. We skip those.
    """

    def detect(self, bundle: BundleHandle) -> bool:
        if not bundle.exists("AGENTS.md"):
            return False
        # Skip if inside a soul bundle
        if bundle.exists("SOUL.md") or bundle.exists("soul.json"):
            return False
        return True

    def read(self, bundle: BundleHandle) -> dict[str, Any]:
        text = bundle.read_text("AGENTS.md")
        fm, body = _parse_frontmatter(text)

        metadata: dict[str, Any] = dict(fm)
        metadata.setdefault("name", bundle.name)

        # When no frontmatter was present, preserve the full original text
        # (including any leading whitespace) so byte-compat is kept. When
        # frontmatter IS present, spec.content is the body after it.
        content = body if fm else text

        return {
            "apiVersion": "agents.md/v1",
            "kind": "AgentDefinition",
            "metadata": metadata,
            "spec": {"content": content},
        }


class AgentDefinitionWriter(WriterPort):
    """Writes an AgentDefinition raw dict back to AGENTS.md (with frontmatter).

    Byte-compat: when metadata contains only ``{name}`` (or is empty), emits
    the plain body — no frontmatter — so existing simple AGENTS.md files do
    not acquire a spurious YAML header on round-trip. As soon as any extra
    key appears (version, tags, owner, …) the writer emits a frontmatter
    block preserving insertion order.
    """

    def can_write(self, raw: dict) -> bool:
        return raw.get("kind") == "AgentDefinition"

    def serialize(self, raw: dict) -> list[dict[str, str]]:
        """Return the full file list the writer would emit to disk.

        Mirrors typescript/src/extensions/agentsmd.ts — keeps
        ``kernel.serialize_document`` on the WRITER path so authored
        frontmatter survives (the generic STANDALONE branch emits the body
        field only, silently dropping authored metadata). Upstreamed from
        the DNA F3 market-fidelity surgery (s-dna-rw-roundtrip-suite)."""
        meta = dict(raw.get("metadata", {}))
        spec = raw.get("spec", {}) or {}
        body = spec.get("content", "") or ""

        # Drop None values before deciding whether to emit frontmatter.
        fm: dict[str, Any] = {k: v for k, v in meta.items() if v is not None}
        # F3 market fidelity: metadata.description may have been ENRICHED at
        # parse time (derive_first_line of the body). Persisting it would emit
        # frontmatter the source bundle never had — elide when derivable.
        from dna.kernel._text import derive_first_line
        if fm.get("description") and fm["description"] == derive_first_line(body):
            fm.pop("description")
        body_has_fm = body.lstrip().startswith("---")
        only_name = set(fm.keys()) <= {"name"}
        needs_fm = bool(fm) and not body_has_fm and not only_name

        if needs_fm:
            fm_body = yaml.safe_dump(
                fm, default_flow_style=False, sort_keys=False, width=100_000
            ).rstrip("\n")
            return [{"relativePath": "AGENTS.md", "content": f"---\n{fm_body}\n---\n{body}"}]
        return [{"relativePath": "AGENTS.md", "content": body}]

    def write(self, bundle: BundleHandle, raw: dict) -> None:
        for f in self.serialize(raw):
            bundle.write_text(f["relativePath"], f["content"])


class AgentsMdExtension:
    name = "agentsmd"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(AgentDefinitionKind())
        kernel.reader(AgentDefinitionReader())
        kernel.writer(AgentDefinitionWriter())
