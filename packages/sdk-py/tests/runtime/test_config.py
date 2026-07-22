import shutil
from pathlib import Path

from dna.runtime.config import copilot_config

FIXTURE_SRC = Path("/Users/jefferson.barnabe/projects/dna-cloud/.dna/dna-cloud-dev")


def _copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / ".dna" / "dna-cloud-dev"
    dest.mkdir(parents=True)
    for subdir in ("copilots", "agents", "federations", "tools"):
        shutil.copytree(FIXTURE_SRC / subdir, dest / subdir)
    return tmp_path / ".dna"


def test_derives_allowlist_model_confirm_from_def(tmp_path):
    # Uses the committed dna-cloud-dev-shaped fixture (copy the memory-copilot
    # + memory-agent + dna-mcp federation + tool docs into tmp_path/.dna).
    base_dir = _copy_fixture(tmp_path)
    cfg = copilot_config("memory-copilot", base_dir=str(base_dir), scope="dna-cloud-dev")
    assert cfg.model == "gpt-5-mini"
    # `_project_hitl_intent` (dna.emit) returns a set, so `confirm_tools`
    # ordering is not stable across process invocations (hash randomization) —
    # compare sorted to avoid flaking on iteration order.
    assert sorted(cfg.confirm_tools) == ["consolidate", "forget", "remember"]
    # `list` (Tool-doc alias) expands to the runtime name `list_memories`:
    assert cfg.allowed_tools == frozenset(
        {"consolidate", "forget", "list", "list_memories", "recall", "remember"}
    )
    assert "compositor" in cfg.instructions.lower()
