"""Round-trip test for the safety/ml-privacy-filter scaffold (Phase 7 T8)."""
from __future__ import annotations

from pathlib import Path

import yaml

from dna.extensions.safety import SafetyPolicyExtension


def test_safety_extension_lists_ml_privacy_template() -> None:
    """SafetyPolicyExtension.templates() exposes the ml-privacy-filter scaffold."""
    ext = SafetyPolicyExtension()
    templates = ext.templates()
    assert len(templates) == 1
    tpl = templates[0]
    assert tpl.id == "safety/ml-privacy-filter"
    assert tpl.kind == "SafetyPolicy"
    assert tpl.owner_extension == "safety"


def test_template_files_root_resolves_and_contains_safetypolicy_md() -> None:
    """The bundled template tree is reachable + contains the marker file."""
    ext = SafetyPolicyExtension()
    tpl = ext.templates()[0]
    root = Path(str(tpl.files_root))
    assert root.is_dir(), f"template root not a dir: {root}"
    marker = root / "SAFETYPOLICY.md"
    assert marker.is_file(), f"missing marker: {marker}"
    readme = root / "README.md"
    assert readme.is_file(), f"missing readme: {readme}"


def test_template_safetypolicy_md_frontmatter_uses_locked_categories() -> None:
    """Template YAML frontmatter validates against the T1-locked category enum
    and the new SafetyPolicySpec.engine field round-trips through SDK parser."""
    from dna.kernel.models import TypedSafetyPolicy

    ext = SafetyPolicyExtension()
    tpl = ext.templates()[0]
    marker = Path(str(tpl.files_root)) / "SAFETYPOLICY.md"
    text = marker.read_text(encoding="utf-8")

    # Extract YAML frontmatter (between the first two ``---`` markers)
    parts = text.split("---", 2)
    assert len(parts) >= 3, "missing YAML frontmatter delimiters"
    frontmatter = yaml.safe_load(parts[1])
    spec = frontmatter["spec"]

    # T1-locked engine values
    assert spec["engine"] == "ml-privacy-filter"
    assert spec["model"] == "openai/privacy-filter"

    # T1-locked category enum (subset of the 8)
    valid_categories = {
        "account_number",
        "private_address",
        "private_email",
        "private_person",
        "private_phone",
        "private_url",
        "private_date",
        "secret",
    }
    assert set(spec["categories"]) <= valid_categories

    # Round-trips through the SDK parser
    typed = TypedSafetyPolicy.from_raw(frontmatter)
    assert typed.spec.engine == "ml-privacy-filter"
    assert typed.spec.threshold == 0.8
    assert typed.spec.budget_ms == 1000
