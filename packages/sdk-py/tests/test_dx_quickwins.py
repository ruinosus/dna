"""DX quick-wins (e-dna-dx / f-dna-dx-consume + f-dna-dx-configure).

Covers the four consumer-facing wins as a suite:

  1. s-dx-build-prompt-fail-loud   — build_prompt raises AgentNotFound
  2. s-dx-clean-composition-output — build_prompt output has no trailing newlines
  3. s-dx-load-prompts-helper      — dna.load_prompts collapses the shim
  4. s-dx-kernel-from-config       — Kernel.from_config + dna.config.yaml

Read-path tests run against the real ``scopes/open-swe`` scope (the same one
``test_kernel.py`` uses), so there is no fragile hand-rolled fixture.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dna import AgentNotFound, Kernel, PromptLibrary, Runtime, load_prompts

# scopes/open-swe/.dna — the scopes root that holds open-swe/.
OPEN_SWE_BASE = (
    Path(__file__).parent.parent.parent.parent / "scopes" / "open-swe" / ".dna"
)


@pytest.fixture()
def mi():
    return Kernel.quick("open-swe", base_dir=str(OPEN_SWE_BASE))


# ── 1. fail-loud (s-dx-build-prompt-fail-loud) ──────────────────────────────

def test_missing_agent_raises_agent_not_found(mi):
    with pytest.raises(AgentNotFound) as exc:
        mi.build_prompt(agent="does-not-exist")
    assert exc.value.agent == "does-not-exist"
    assert "does-not-exist" in str(exc.value)


def test_agent_not_found_is_lookup_error(mi):
    # Narrow enough for `except LookupError` without swallowing the world.
    with pytest.raises(LookupError):
        mi.build_prompt(agent="nope")


@pytest.mark.asyncio
async def test_missing_agent_raises_in_async_builder(mi):
    with pytest.raises(AgentNotFound):
        await mi.build_prompt_async(agent="ghost")


# ── 2. clean output (s-dx-clean-composition-output) ─────────────────────────

def test_build_prompt_output_has_no_trailing_newlines(mi):
    text = mi.build_prompt(agent="swe-agent")
    assert text  # non-empty
    assert text == text.rstrip("\n")
    assert not text.endswith("\n")


@pytest.mark.asyncio
async def test_async_build_prompt_output_is_clean(mi):
    text = await mi.build_prompt_async(agent="swe-agent")
    assert text and not text.endswith("\n")


# ── 3. load_prompts (s-dx-load-prompts-helper) ──────────────────────────────

def test_load_prompts_returns_clean_composed_prompt():
    prompts = load_prompts("open-swe", base_dir=str(OPEN_SWE_BASE))
    assert isinstance(prompts, PromptLibrary)
    text = prompts["swe-agent"]
    assert text and not text.endswith("\n")


def test_load_prompts_missing_agent_raises():
    prompts = load_prompts("open-swe", base_dir=str(OPEN_SWE_BASE))
    with pytest.raises(AgentNotFound):
        prompts["ghost"]


def test_load_prompts_mapping_surface():
    prompts = load_prompts("open-swe", base_dir=str(OPEN_SWE_BASE))
    assert "swe-agent" in prompts
    assert "ghost" not in prompts
    names = prompts.names()
    assert "swe-agent" in names
    assert names == sorted(names)
    assert set(prompts) == set(names)
    assert len(prompts) == len(names)
    # cached: second access returns the identical object
    assert prompts["swe-agent"] is prompts["swe-agent"]


def test_load_prompts_defaults_base_dir_to_env(monkeypatch):
    monkeypatch.setenv("DNA_BASE_DIR", str(OPEN_SWE_BASE))
    prompts = load_prompts("open-swe")
    assert prompts["swe-agent"]


def test_mini_consumer_collapses_the_shim():
    """A whole foundry-style prompts module, in two real lines — no kernel boot
    boilerplate, no ``mi.one(...)`` guard, no ``.rstrip("\\n")``. This is the
    166-line shim the win is measured against."""
    prompts = load_prompts("open-swe", base_dir=str(OPEN_SWE_BASE))
    SWE_INSTRUCTIONS = prompts["swe-agent"]

    assert SWE_INSTRUCTIONS
    assert SWE_INSTRUCTIONS == SWE_INSTRUCTIONS.rstrip("\n")


# ── 4. from_config (s-dx-kernel-from-config) ────────────────────────────────

def test_from_config_file_source(tmp_path: Path):
    cfg = tmp_path / "dna.config.yaml"
    cfg.write_text(f"source: file://{OPEN_SWE_BASE}\n")
    kernel = Kernel.from_config(str(cfg))
    mi = kernel.instance("open-swe")
    assert mi.build_prompt(agent="swe-agent")


def test_from_config_plain_path_source(tmp_path: Path):
    cfg = tmp_path / "dna.config.yaml"
    cfg.write_text(f"source: {OPEN_SWE_BASE}\n")  # no scheme → filesystem
    kernel = Kernel.from_config(str(cfg))
    assert kernel.instance("open-swe").build_prompt(agent="swe-agent")


def test_from_config_no_file_falls_back_to_default(monkeypatch, tmp_path: Path):
    # No dna.config.yaml + no path → default filesystem source. Point the
    # default resolver at open-swe via DNA_BASE_DIR and cd somewhere clean.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DNA_BASE_DIR", str(OPEN_SWE_BASE))
    kernel = Kernel.from_config()  # no config present in tmp_path
    assert kernel.instance("open-swe").build_prompt(agent="swe-agent")


def test_from_config_runtime_returns_runtime(tmp_path: Path):
    cfg = tmp_path / "dna.config.yaml"
    cfg.write_text(f"source: file://{OPEN_SWE_BASE}\n")
    rt = Runtime.from_config(str(cfg))
    assert isinstance(rt, Runtime)
    assert rt.manifest("open-swe").build_prompt(agent="swe-agent")


def test_from_config_bad_scheme_fails_loud(tmp_path: Path):
    cfg = tmp_path / "dna.config.yaml"
    cfg.write_text("source: mysql://nope\n")
    with pytest.raises(Exception) as exc:
        Kernel.from_config(str(cfg))
    assert "mysql" in str(exc.value)


def test_from_config_missing_path_is_error(tmp_path: Path):
    with pytest.raises(ValueError):
        Kernel.from_config(str(tmp_path / "nope.yaml"))


def test_from_config_unknown_key_fails_loud(tmp_path: Path):
    cfg = tmp_path / "dna.config.yaml"
    cfg.write_text(f"source: file://{OPEN_SWE_BASE}\nbogus: 1\n")
    with pytest.raises(ValueError) as exc:
        Kernel.from_config(str(cfg))
    assert "bogus" in str(exc.value)


def test_from_config_bad_search_enum_fails_loud(tmp_path: Path):
    cfg = tmp_path / "dna.config.yaml"
    cfg.write_text(f"source: file://{OPEN_SWE_BASE}\nsearch: faiss\n")
    with pytest.raises(ValueError) as exc:
        Kernel.from_config(str(cfg))
    assert "faiss" in str(exc.value)


def test_from_config_auth_section_is_opaque_passthrough(tmp_path: Path):
    # The `auth:` section (the MCP pluggable-IdP layer) is accepted + carried
    # opaquely; the SDK does not interpret it (its consumer, the CLI, does).
    from dna.config import load_config

    cfg = tmp_path / "dna.config.yaml"
    cfg.write_text(
        f"source: file://{OPEN_SWE_BASE}\n"
        "auth:\n  providers:\n    - type: entra\n      issuer: https://i/v2.0\n"
    )
    parsed = load_config(str(cfg))
    assert parsed is not None
    assert isinstance(parsed.auth, dict)
    assert parsed.auth["providers"][0]["type"] == "entra"


def test_from_config_auth_must_be_mapping(tmp_path: Path):
    from dna.config import load_config

    cfg = tmp_path / "dna.config.yaml"
    cfg.write_text(f"source: file://{OPEN_SWE_BASE}\nauth: nope\n")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_config(str(cfg))


# ── product smoke: an external consumer, whole shim in a handful of lines ─────

def test_external_consumer_from_config_plus_prompts(tmp_path: Path):
    """The foundry-style prompts module, rebuilt from OUTSIDE the SDK with the
    two DX entry points working together: declare ports in dna.config.yaml,
    boot with Kernel.from_config, compose the agent constants. No kernel boot
    boilerplate, no per-agent None-guard, no rstrip — the ~166-line shim gone.
    """
    (tmp_path / "dna.config.yaml").write_text(f"source: file://{OPEN_SWE_BASE}\n")

    # --- the entire consumer module ---------------------------------------
    kernel = Kernel.from_config(str(tmp_path / "dna.config.yaml"))
    mi = kernel.instance("open-swe")
    SWE_INSTRUCTIONS = mi.build_prompt(agent="swe-agent")
    REVIEWER_INSTRUCTIONS = mi.build_prompt(agent="reviewer-agent")
    # ----------------------------------------------------------------------

    for text in (SWE_INSTRUCTIONS, REVIEWER_INSTRUCTIONS):
        assert text
        assert text == text.rstrip("\n")  # clean, no hand-rstrip needed

    # and a missing agent is a hard error, not a placeholder that ships.
    with pytest.raises(AgentNotFound):
        mi.build_prompt(agent="agent-that-was-renamed")
