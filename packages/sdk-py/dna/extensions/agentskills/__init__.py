"""AgentSkillsExtension — Skill kind + SkillReader + SkillWriter."""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from typing import Any

from dna.kernel.kinds.base import KindBase
from dna.kernel.models import TypedSkill
from dna.kernel.preview import PreviewBlock
from dna.kernel.protocols import ExtensionHost, StorageDescriptor, ReaderPort, WriterPort
from dna.kernel.bundle.handle import BundleHandle

# Reuse the shared schema builder from helix extension
from dna.extensions.helix import _schema_from_model

_BINARY_EXTENSIONS = {".tar", ".gz", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".wasm", ".bin", ".exe", ".so", ".dylib"}


def _read_text_safe(path: Path) -> str | None:
    """Read file as UTF-8, return None for binary files."""
    if any(path.name.endswith(ext) for ext in _BINARY_EXTENSIONS):
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, ValueError):
        return None


class SkillKind(KindBase):
    api_version = "agentskills.io/v1"
    kind = "Skill"
    alias = "agentskills-skill"
    is_schema_affecting = True
    model = TypedSkill
    origin = "agentskills.io"
    storage = StorageDescriptor.bundle("skills", "SKILL.md")
    graph_style = {"fill": "#10B981", "stroke": "#059669", "text_color": "#fff"}
    ascii_icon = "📖"
    display_label = "Skills"
    is_prompt_target = False
    prompt_target_priority = 0
    flatten_in_context = False
    description_fallback_field = "instruction"
    ui_schema = {
        "instruction": {
            "widget": "markdown-toc",
            "label": "SKILL.md",
            "help": "The skill's instruction body (progressive disclosure, ≤500 lines).",
            "height": 520,
            "order": 10,
        },
        "scripts": {
            "widget": "readonly",
            "label": "scripts/",
            "help": "Bundled scripts directory. Edit on disk.",
            "order": 20,
        },
        "references": {
            "widget": "readonly",
            "label": "references/",
            "help": "Bundled reference files. Edit on disk.",
            "order": 30,
        },
        "assets": {
            "widget": "readonly",
            "label": "assets/",
            "help": "Binary/static assets. Edit on disk.",
            "order": 40,
        },
    }
    docs = (
        "A Skill is a reusable capability bundle an agent composes into its "
        "prompt. It follows the agents.md SKILL.md convention: one markdown "
        "file (frontmatter + body instruction) plus optional scripts/, "
        "references/, and assets/ subdirectories. A Skill referenced by an "
        "Agent (spec.skills) has its SKILL.md body inlined into the composed "
        "system prompt — the same way a Soul or Guardrail composes (i-031) — so "
        "it reaches build_prompt and every emitted runtime artifact. A "
        "DeepAgents harness may additionally expose Skills via progressive "
        "disclosure (SkillsMiddleware loads full content on demand). Use a "
        "Skill for reusable procedural know-how shared across agents."
    )

    def schema(self) -> dict[str, Any] | None:
        return _schema_from_model(self.model)

    def parse(self, raw: dict[str, Any]) -> Any:
        return TypedSkill.from_raw(raw)

    def summary(self, doc: Any) -> dict[str, Any] | None:
        return None

    def preview(self, doc: Any) -> list[PreviewBlock]:
        spec = getattr(doc, "spec", None) or {}
        instruction = spec.get("instruction") if hasattr(spec, "get") else None
        if not isinstance(instruction, str) or not instruction:
            return [PreviewBlock(kind="empty", title="Skill (empty)")]
        return [
            PreviewBlock(
                kind="markdown",
                title="SKILL.md",
                body=instruction,
            )
        ]


class SkillReader(ReaderPort):
    """Detects and reads SKILL.md bundles."""

    def detect(self, bundle: BundleHandle) -> bool:
        return bundle.exists("SKILL.md")

    # Known subdirectories that map to named spec fields
    _KNOWN_DIRS = {"scripts", "references", "assets"}

    def read(self, bundle: BundleHandle) -> dict[str, Any]:
        skill_md = bundle.read_text("SKILL.md")
        metadata = self._parse_frontmatter(skill_md)
        name = metadata.get("name", bundle.name)
        description = metadata.get("description", "")
        # Preserve all frontmatter keys (tags, owner, priority, …). SkillWriter
        # already round-trips extras via yaml.safe_dump since 39663a2; this
        # closes the asymmetry on the reader side. name/description are only
        # fed in as defaults when absent from the parsed frontmatter.
        meta_full: dict[str, Any] = dict(metadata)
        meta_full.setdefault("name", name)
        meta_full.setdefault("description", description)
        # Extract body (after frontmatter) — F3 market fidelity: keep the
        # tail byte-exact except the ONE leading newline the writer
        # canonically re-emits ("---\\n\\n"). Trailing newlines and extra
        # blank lines are part of the artifact.
        fm_match = re.match(r"^---\n.*?---(?:\n|$)", skill_md, flags=re.DOTALL)
        tail = skill_md[fm_match.end():] if fm_match else skill_md
        body = tail[1:] if tail.startswith("\n") else tail

        spec: dict[str, Any] = {"instruction": body}

        # Collect known subdirectories (scripts/, references/, assets/)
        for dir_name in self._KNOWN_DIRS:
            if bundle.exists(dir_name):
                files = self._collect_subdir(bundle, dir_name)
                if files:
                    spec[dir_name] = files

        # Collect ALL other subdirectories as extra bundles
        # (agents/, eval-viewer/, etc. — anything not in _KNOWN_DIRS)
        extras: dict[str, dict[str, str]] = {}
        for entry in sorted(bundle.iter_entries()):
            if bundle.is_file(entry) or entry in self._KNOWN_DIRS:
                continue
            files = self._collect_subdir(bundle, entry)
            if files:
                extras[entry] = files
        if extras:
            spec["extras"] = extras

        # Collect root-level extra files (LICENSE.txt, etc. — not SKILL.md)
        root_files: dict[str, str] = {}
        for entry in sorted(bundle.iter_entries()):
            if not bundle.is_file(entry) or entry == "SKILL.md":
                continue
            if any(entry.endswith(ext) for ext in _BINARY_EXTENSIONS):
                continue
            try:
                text = bundle.read_text(entry)
                root_files[entry] = text
            except (UnicodeDecodeError, ValueError):
                pass
        if root_files:
            spec["root_files"] = root_files

        return {
            "apiVersion": "agentskills.io/v1",
            "kind": "Skill",
            "metadata": meta_full,
            "spec": spec,
        }

    def _collect_subdir(self, bundle: BundleHandle, dir_name: str) -> dict[str, str]:
        """Recursively collect all text files in a named subdirectory as {relative_path: content}."""
        files: dict[str, str] = {}
        prefix = dir_name + "/"
        for entry in bundle.iter_entries(recursive=True):
            if not entry.startswith(prefix):
                continue
            rel = entry[len(prefix):]
            fname = entry.split("/")[-1]
            if any(fname.endswith(ext) for ext in _BINARY_EXTENSIONS):
                continue
            try:
                text = bundle.read_text(entry)
                files[rel] = text
            except (UnicodeDecodeError, ValueError):
                pass
        return files

    def _collect_dir(self, directory: Path) -> dict[str, str]:
        """Recursively collect all text files in a directory as {relative_path: content}."""
        files: dict[str, str] = {}
        for f in sorted(directory.rglob("*")):
            if f.is_file():
                text = _read_text_safe(f)
                if text is not None:
                    rel = str(f.relative_to(directory))
                    files[rel] = text
        return files

    def _parse_frontmatter(self, text: str) -> dict[str, Any]:
        """Parse YAML frontmatter preserving native types (int, list, dict).

        Previously coerced every value to str, which broke round-trip for
        lists, numbers, and nested mappings. SkillWriter emits via
        yaml.safe_dump, so the reader must accept whatever YAML can carry.
        """
        match = re.match(r"^---\n(.*?)---\n?", text, re.DOTALL)
        if not match:
            return {}
        try:
            parsed = yaml.safe_load(match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {}


class SkillWriter(WriterPort):
    """Writes a Skill raw dict back to a SKILL.md bundle directory."""

    def can_write(self, raw: dict) -> bool:
        return raw.get("kind") == "Skill"

    def serialize(self, raw: dict) -> list[dict[str, str]]:
        """Return the full file list the writer would emit to disk.

        Mirrors typescript/src/extensions/agentskills.ts SkillWriter.serialize
        so `kernel.serialize_document` picks this up and emits bundle extras
        (scripts/, references/, assets/, extras, root_files) — not just the
        primary SKILL.md. See Plan B2 follow-up on http-virtual-fs.ts.
        """
        files: list[dict[str, str]] = []
        spec = raw.get("spec", {}) or {}
        meta = raw.get("metadata", {}) or {}

        # Build metadata dict for the frontmatter (name/description first, then
        # extras). Dumping via yaml.safe_dump matches the TS writer's
        # yaml.dump(fm, {flowLevel: -1, sortKeys: false}) semantics and is safe
        # for values with YAML-special chars (:, quotes, multiline, lists).
        fm: dict = {"name": meta.get("name", "")}
        desc = meta.get("description", "")
        if desc:
            fm["description"] = desc
        for key, value in meta.items():
            if key in ("name", "description"):
                continue
            if value is None:
                continue
            fm[key] = value

        # F3 market fidelity: metadata.description may have been ENRICHED at
        # parse time (derive_first_line of the body). Persisting it would emit
        # frontmatter the source bundle never had — elide when derivable.
        from dna.kernel._text import derive_first_line
        if fm.get("description") and fm["description"] == derive_first_line(spec.get("instruction", "")):
            fm.pop("description")
        # width: real marketplace skills author description as ONE long
        # line — the default width=80 would wrap it (not byte-faithful).
        frontmatter_body = yaml.safe_dump(
            fm, default_flow_style=False, sort_keys=False, width=100_000
        ).rstrip("\n")
        skill_md = f"---\n{frontmatter_body}\n---\n\n{spec.get('instruction', '')}"
        files.append({"relativePath": "SKILL.md", "content": skill_md})

        # Known subdirs: scripts/, references/, assets/
        for dir_name in ("scripts", "references", "assets"):
            dir_files = spec.get(dir_name, {})
            if isinstance(dir_files, dict):
                for fname, fcontent in dir_files.items():
                    files.append(
                        {"relativePath": f"{dir_name}/{fname}", "content": fcontent}
                    )

        # Extras — arbitrary named subdirs preserved on round-trip
        for dir_name, dir_files in (spec.get("extras", {}) or {}).items():
            if isinstance(dir_files, dict):
                for fname, fcontent in dir_files.items():
                    files.append(
                        {"relativePath": f"{dir_name}/{fname}", "content": fcontent}
                    )

        # Root-level extra files (LICENSE.txt, etc.)
        for fname, fcontent in (spec.get("root_files", {}) or {}).items():
            files.append({"relativePath": fname, "content": fcontent})

        return files

    def write(self, bundle: BundleHandle, raw: dict) -> None:
        # Fill in bundle.name as the default frontmatter name when metadata is
        # missing it — only relevant for the on-disk write path.
        if not (raw.get("metadata") or {}).get("name"):
            raw = {**raw, "metadata": {**(raw.get("metadata") or {}), "name": bundle.name}}
        for f in self.serialize(raw):
            bundle.write_text(f["relativePath"], f["content"])


class AgentSkillsExtension:
    name = "agentskills"
    version = "1.0.0"

    def register(self, kernel: ExtensionHost) -> None:
        kernel.kind(SkillKind())
        kernel.reader(SkillReader())
        kernel.writer(SkillWriter())
