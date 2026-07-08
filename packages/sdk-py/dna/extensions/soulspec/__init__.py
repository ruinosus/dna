"""SoulSpecExtension — Soul kind + SoulReader + SoulWriter."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from dna.kernel.kind_base import KindBase
from dna.kernel.models import TypedSoul
from dna.kernel.preview import PreviewBlock
from dna.kernel.protocols import StorageDescriptor
from dna.kernel.bundle_handle import BundleHandle

from dna.extensions.helix import _schema_from_model


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a markdown doc into (metadata dict, body).

    Returns ({}, text) when no frontmatter is present.
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


from dna.kernel.studio_ui import docs_ui


class SoulKind(KindBase):
    api_version = "soulspec.org/v1"
    kind = "Soul"
    alias = "soulspec-soul"
    is_schema_affecting = True
    ui = docs_ui("Soul", mode="build", label_en="Souls", label_pt="Almas", display_order=50, description_en="An agent's declarative soul/persona (identity, voice, values).", description_pt="A alma/persona declarativa de um agente (identidade, voz, valores).")
    model = TypedSoul
    origin = "soulspec.org"
    storage = StorageDescriptor.bundle("souls", "SOUL.md")
    graph_style = {"fill": "#8B5CF6", "stroke": "#7C3AED", "text_color": "#fff"}
    ascii_icon = "🧠"
    display_label = "Souls"
    is_prompt_target = True
    prompt_target_priority = 1
    flatten_in_context = True
    description_fallback_field = "soul_content"
    ui_schema = {
        "soul_content": {
            "widget": "markdown-toc",
            "label": "SOUL.md",
            "help": "Main prose describing the agent's personality, voice, and principles.",
            "height": 480,
            "order": 10,
        },
        "style_content": {
            "widget": "markdown",
            "label": "STYLE.md",
            "help": "Communication style, formatting conventions, tone.",
            "height": 260,
            "order": 20,
        },
        "soul_json": {
            "widget": "code",
            "language": "json",
            "label": "soul.json",
            "help": "Structured soulspec.org metadata (specVersion, tags, etc.).",
            "height": 220,
            "order": 30,
        },
        "agents_content": {
            "widget": "markdown",
            "label": "AGENTS.md (companion)",
            "help": "Optional agents.md-style workflow description.",
            "height": 220,
            "order": 40,
        },
        "identity_content": {
            "widget": "markdown",
            "label": "IDENTITY.md",
            "help": "Who the agent is — role, background, expertise.",
            "height": 220,
            "order": 50,
        },
        "heartbeat_content": {
            "widget": "markdown",
            "label": "HEARTBEAT.md",
            "help": "Autonomous scheduled tasks — cron for the agent, in plain language.",
            "height": 220,
            "order": 60,
        },
    }
    docs = (
        "A Soul defines an agent's personality, voice, and guiding principles as "
        "prose (not code). It is stored as a bundle — SOUL.md plus optional "
        "IDENTITY.md, STYLE.md, HEARTBEAT.md, AGENTS.md and soul.json — "
        "following the soulspec.org open standard. When an agent references a "
        "Soul via its dep_filters, the Soul content is flattened directly into "
        "the agent's system prompt (flatten_in_context=True). Use a Soul when "
        "multiple agents should share the same character or ethos."
    )

    def schema(self) -> dict[str, Any] | None:
        return _schema_from_model(self.model)

    def parse(self, raw: dict[str, Any]) -> Any:
        return TypedSoul.from_raw(raw)

    def summary(self, doc: Any) -> dict[str, Any] | None:
        return None

    def prompt_template(self) -> str | None:
        # Use {{{...}}} (triple braces) to disable HTML escaping —
        # soul_content is markdown/text, not HTML, so quotes/&/<>
        # should be passed through verbatim.
        return "{{{soul_content}}}"

    def preview(self, doc: Any) -> list[PreviewBlock]:
        spec = getattr(doc, "spec", None) or {}
        spec_dict = dict(spec) if hasattr(spec, "items") else {}
        blocks: list[PreviewBlock] = []
        soul_content = spec_dict.get("soul_content")
        if isinstance(soul_content, str) and soul_content:
            blocks.append(PreviewBlock(kind="markdown", title="SOUL.md", body=soul_content))
        style_content = spec_dict.get("style_content")
        if isinstance(style_content, str) and style_content:
            blocks.append(PreviewBlock(kind="markdown", title="STYLE.md", body=style_content))
        soul_json = spec_dict.get("soul_json")
        if soul_json and isinstance(soul_json, (dict, list)):
            blocks.append(
                PreviewBlock(
                    kind="code",
                    title="soul.json",
                    body=json.dumps(soul_json, indent=2, default=str),
                    language="json",
                )
            )
        agents_content = spec_dict.get("agents_content")
        if isinstance(agents_content, str) and agents_content:
            blocks.append(
                PreviewBlock(
                    kind="markdown",
                    title="AGENTS.md (companion)",
                    body=agents_content,
                )
            )
        identity_content = spec_dict.get("identity_content")
        if isinstance(identity_content, str) and identity_content:
            blocks.append(PreviewBlock(kind="markdown", title="IDENTITY.md", body=identity_content))
        heartbeat_content = spec_dict.get("heartbeat_content")
        if isinstance(heartbeat_content, str) and heartbeat_content:
            blocks.append(PreviewBlock(kind="markdown", title="HEARTBEAT.md", body=heartbeat_content))
        if not blocks:
            return [PreviewBlock(kind="empty", title="Soul (empty)")]
        return blocks


class SoulReader:
    """Detects and reads SOUL.md or soul.json bundles."""

    def detect(self, bundle: BundleHandle) -> bool:
        return bundle.exists("SOUL.md") or bundle.exists("soul.json")

    def read(self, bundle: BundleHandle) -> dict[str, Any]:
        name = bundle.name
        spec: dict[str, Any] = {}
        metadata: dict[str, Any] = {}

        # Read SOUL.md — parse frontmatter if present
        if bundle.exists("SOUL.md"):
            text = bundle.read_text("SOUL.md")
            fm, body = _parse_frontmatter(text)
            if fm:
                metadata.update(fm)
                spec["soul_content"] = body
            else:
                spec["soul_content"] = text

        # Read soul.json
        if bundle.exists("soul.json"):
            spec["soul_json"] = json.loads(bundle.read_text("soul.json"))
            if not spec.get("soul_content"):
                spec["soul_content"] = json.dumps(spec["soul_json"], indent=2)

        # Companion files — soulspec.org standard
        for field, fname in (
            ("style_content", "STYLE.md"),
            ("agents_content", "AGENTS.md"),
            ("identity_content", "IDENTITY.md"),
            ("heartbeat_content", "HEARTBEAT.md"),
        ):
            if bundle.exists(fname):
                spec[field] = bundle.read_text(fname)

        # name fallback — always ensure metadata has a name
        metadata.setdefault("name", name)

        return {
            "apiVersion": "soulspec.org/v1",
            "kind": "Soul",
            "metadata": metadata,
            "spec": spec,
        }


class SoulWriter:
    """Writes a Soul raw dict back to a bundle directory."""

    def can_write(self, raw: dict) -> bool:
        return raw.get("kind") == "Soul"

    def serialize(self, raw: dict) -> list[dict[str, str]]:
        """Return the full file list the writer would emit to disk.

        Mirrors typescript/src/extensions/soulspec.ts SoulWriter.serialize so
        `kernel.serialize_document` emits SOUL.md + soul.json + companion
        markdown files (STYLE.md / AGENTS.md / IDENTITY.md / HEARTBEAT.md),
        not just the primary marker.
        """
        files: list[dict[str, str]] = []
        spec = raw.get("spec", {}) or {}
        meta = dict(raw.get("metadata", {}) or {})

        # Build frontmatter dict — all non-None meta keys, insertion order.
        fm: dict[str, Any] = {k: v for k, v in meta.items() if v is not None}

        soul_body = spec.get("soul_content", "") or ""
        # F3 market fidelity: metadata.description may have been ENRICHED at
        # parse time (derive_first_line of the body). Persisting it would emit
        # frontmatter the source bundle never had — elide when derivable.
        from dna.kernel._text import derive_first_line
        if fm.get("description") and fm["description"] == derive_first_line(soul_body):
            fm.pop("description")
        body_has_fm = soul_body.lstrip().startswith("---")
        # Byte-compat for the "only name" case — previous writer emitted just
        # the body. Keeps existing fixture SOUL.md files from diffing.
        only_name = set(fm.keys()) <= {"name"}
        needs_fm = bool(fm) and not body_has_fm and not only_name
        if needs_fm:
            fm_body = yaml.safe_dump(
                fm, default_flow_style=False, sort_keys=False, width=100_000
            ).rstrip("\n")
            files.append(
                {"relativePath": "SOUL.md", "content": f"---\n{fm_body}\n---\n{soul_body}"}
            )
        else:
            files.append({"relativePath": "SOUL.md", "content": soul_body})

        soul_json = spec.get("soul_json")
        if soul_json:
            import json as _json
            files.append(
                # ensure_ascii=False — TS JSON.stringify parity (unicode
                # passthrough); soul.json re-emit is canonical, not byte-
                # faithful (documented in test_market_conformance).
                {"relativePath": "soul.json", "content": _json.dumps(soul_json, indent=2, ensure_ascii=False)}
            )

        # Companion files (soulspec.org standard)
        companions = [
            ("style_content", "STYLE.md"),
            ("agents_content", "AGENTS.md"),
            ("identity_content", "IDENTITY.md"),
            ("heartbeat_content", "HEARTBEAT.md"),
        ]
        for spec_key, filename in companions:
            content = spec.get(spec_key)
            if content:
                files.append({"relativePath": filename, "content": content})

        return files

    def write(self, bundle: BundleHandle, raw: dict) -> None:
        for f in self.serialize(raw):
            content = f["content"]
            # The serialize() contract emits an empty SOUL.md when the Soul
            # has no body and no frontmatter — preserve the pre-refactor
            # behaviour of skipping the write in that case.
            if f["relativePath"] == "SOUL.md" and not content:
                continue
            bundle.write_text(f["relativePath"], content)


class SoulSpecExtension:
    name = "soulspec"
    version = "1.0.0"

    def register(self, kernel: Any) -> None:
        kernel.kind(SoulKind())
        kernel.reader(SoulReader())
        kernel.writer(SoulWriter())
