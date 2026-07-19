"""Círculo B — a Claude memory export lands in DNA and is recallable by
PARAPHRASE (s-roundtrip-proof).

Two layers, deliberately separated:

* the **adapter** tests are pure and always run — segmentation, deterministic
  ids, no prose loss, quoted dates;
* the **paraphrase recall** test needs the ``embed-onnx`` extra and downloads
  a model, so it carries ``requires_network`` + ``importorskip`` exactly like
  ``test_embedding_onnx_parity.py``. It is the one that proves the fact went
  through the SEMANTIC plane rather than merely being stored.

The fixture below is SYNTHETIC but mirrors the shape of a real export,
verified against one: a JSON list with a single entry holding
``account_uuid``, ``conversations_memory`` (one markdown string) and
``project_memories`` (``project_uuid -> markdown string``). Real exports are
personal data and never enter the repo.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from dna.memory.claude_export import (
    from_claude_export,
    read_claude_export,
    write_mif_dir,
)

_CREATED = "2026-07-19T00:00:00Z"

#: The fact the paraphrase must reach. Its content words are disjoint from the
#: query's — asserted programmatically below, never by eye.
_TARGET_FACT = (
    "The team migrated the billing service from MySQL to PostgreSQL last quarter."
)
_PARAPHRASE = "database platform switch for payments"

#: Unrelated memories so "in the top-3" is a real bar. With only a handful of
#: documents everything is in the top-3 and the test proves nothing.
_DISTRACTORS = [
    "Coffee is brewed with a V60 pour-over every morning.",
    "The office moved to a new building near the harbour.",
    "Weekly retrospectives happen on Friday afternoons.",
    "The mobile app targets iOS first, Android later.",
    "Documentation is written in MkDocs with the Material theme.",
    "Onboarding takes roughly two weeks for a new engineer.",
    "The logo was redesigned by a freelance illustrator.",
    "Standing desks were purchased for the whole floor.",
    "The vacation policy allows thirty days per year.",
    "The mascot is a rescued greyhound named Pixel.",
]

_EXPORT = [
    {
        "account_uuid": "acct-0001",
        "conversations_memory": (
            "**Work context**\n\n"
            "Barna is a solutions architect shipping an agent orchestration "
            "platform.\n\n"
            f"{_TARGET_FACT}\n\n"
            + "\n\n".join(_DISTRACTORS)
            + "\n\n**Personal context**\n\n"
            "Barna reads science fiction on the train.\n"
        ),
        "project_memories": {
            "proj-a": "**Tools & resources**\n\nThe crew relies on Terraform for infra.\n"
        },
    }
]


def _content_words(text: str) -> set[str]:
    stop = {
        "the", "a", "an", "for", "from", "to", "of", "in", "on", "and", "is",
        "was", "it", "he", "she", "they", "last", "by", "with", "at",
    }
    return {w for w in re.findall(r"[a-z]+", text.lower()) if w not in stop}


# ─────────────────────────────── the adapter ───────────────────────────────


def test_segments_into_one_unit_per_paragraph_carrying_its_heading():
    units = from_claude_export(_EXPORT, created=_CREATED)
    assert len(units) == 4 + len(_DISTRACTORS), [u.get("title") for u in units]
    titles = {u.get("title") for u in units}
    assert titles == {"Work context", "Personal context", "Tools & resources"}
    assert any(u["content"] == _TARGET_FACT for u in units)
    # the project blob is attributed to its project, not merged into the
    # conversation memory
    proj = [u for u in units if u["source"]["ref"] == "project:proj-a"]
    assert len(proj) == 1 and proj[0]["title"] == "Tools & resources"


def test_ids_are_deterministic_and_unique_so_reimport_is_idempotent():
    a = from_claude_export(_EXPORT, created=_CREATED)
    b = from_claude_export(_EXPORT, created=_CREATED)
    assert [u["id"] for u in a] == [u["id"] for u in b], "ids must not depend on run order"
    assert len({u["id"] for u in a}) == len(a), "colliding ids would silently overwrite"
    # A different `created` must NOT change identity — the id is content-derived,
    # so re-importing a later export of the same memory dedupes instead of forking.
    c = from_claude_export(_EXPORT, created="2027-01-01T00:00:00Z")
    assert [u["id"] for u in c] == [u["id"] for u in a]


def test_no_prose_is_lost_in_segmentation():
    units = from_claude_export(_EXPORT, created=_CREATED)
    source = _EXPORT[0]["conversations_memory"] + "".join(
        _EXPORT[0]["project_memories"].values()
    )
    emitted = " ".join(u["content"] + " " + u.get("title", "") for u in units)
    lost = _content_words(source) - _content_words(emitted)
    assert not lost, f"prose lost in segmentation: {sorted(lost)}"


def test_written_mif_quotes_dates_so_yaml_keeps_them_strings(tmp_path):
    units = from_claude_export(_EXPORT, created=_CREATED)
    written = write_mif_dir(units, tmp_path / "mif")
    assert len(written) == len(units)
    text = written[0].read_text(encoding="utf-8")
    assert f'created: "{_CREATED}"' in text, (
        "an unquoted ISO date is resolved to a datetime by YAML and then fails "
        "MIF's string-typed temporal fields"
    )


def test_read_accepts_the_export_directory_or_the_file(tmp_path):
    d = tmp_path / "export"
    d.mkdir()
    (d / "memories.json").write_text(json.dumps(_EXPORT), encoding="utf-8")
    assert read_claude_export(d, created=_CREATED) == read_claude_export(
        d / "memories.json", created=_CREATED
    )


def test_the_paraphrase_shares_no_content_word_with_the_fact():
    """Guards the recall test below: if the query and the fact overlap, a hit
    proves lexical matching, not semantic recall."""
    overlap = _content_words(_TARGET_FACT) & _content_words(_PARAPHRASE)
    assert not overlap, f"query would match lexically on {sorted(overlap)}"


def test_adapter_stays_under_the_loc_budget():
    """AC: '< ~150 LOC' — the 'a new format costs little' metric."""
    src = (Path(__file__).resolve().parents[1] / "dna" / "memory" / "claude_export.py")
    assert src.read_text(encoding="utf-8").count("\n") < 150


# ──────────────────── the proof: recall by paraphrase ─────────────────────


@pytest.mark.requires_network
def test_imported_claude_fact_is_recallable_by_paraphrase(tmp_path, monkeypatch):
    """The money case: a fact that came from Claude is reachable in DNA by a
    paraphrase sharing no content word with it — proving it went through the
    semantic plane, not just storage."""
    pytest.importorskip("fastembed", reason="`embed-onnx` extra not installed")
    click_testing = pytest.importorskip("click.testing")
    dna_cli = pytest.importorskip("dna_cli", reason="the CLI is not installed here")

    src = tmp_path / "src" / "demo"
    src.mkdir(parents=True)
    (src / "manifest.yaml").write_text(
        "apiVersion: github.com/ruinosus/dna/core/v1\n"
        "kind: Package\nmetadata:\n  name: demo\nspec:\n  title: demo\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DNA_BASE_DIR", str(tmp_path / "src"))
    monkeypatch.setenv("DNA_SEARCH_DIR", str(tmp_path / "search"))
    monkeypatch.setenv("DNA_PERSONAL_ID", "acct-0001")

    mif_dir = tmp_path / "mif"
    write_mif_dir(from_claude_export(_EXPORT, created=_CREATED), mif_dir)

    runner = click_testing.CliRunner()
    imported = runner.invoke(dna_cli.main, [
        "memory", "import", str(mif_dir), "--scope", "demo",
        "--as", "both", "--personal", "--json",
    ])
    assert imported.exit_code == 0, imported.output
    assert json.loads(imported.output)["imported"] == 4 + len(_DISTRACTORS)

    recalled = runner.invoke(dna_cli.main, [
        "memory", "recall", _PARAPHRASE, "--scope", "demo",
        "--personal", "--limit", "3", "--json",
    ])
    assert recalled.exit_code == 0, recalled.output
    # the kernel may prefix a scope warning; the JSON payload starts at the brace
    out = recalled.output
    result = json.loads(out[out.index("{"):])

    # Without this guard a purely LEXICAL hit would pass and we would be
    # claiming semantic recall we never exercised.
    assert result["semantic"] is True, "the semantic plane did not engage"
    assert result["degraded"] is False, "recall fell back to the degraded branch"

    hits = result["hits"][:3]
    found = [
        i for i, h in enumerate(hits, 1)
        if _TARGET_FACT in (h.get("snippet") or "") or _TARGET_FACT in (h.get("title") or "")
    ]
    assert found, (
        "the Claude-imported fact must surface in the top-3 for a paraphrase "
        f"sharing no content word with it; got: {[h.get('snippet') for h in hits]}"
    )
    # The AC asks for top-3, but MEASURED, top-3 alone does not discriminate:
    # with --no-semantic the fact still lands at rank 2 — not because BM25
    # matched (it shares no content word) but because, with nothing matching,
    # the order falls to retention/confidence tie-breaks. Rank 1 is what the
    # semantic plane actually buys, so that is what is asserted.
    assert found[0] == 1, (
        f"semantic recall must rank the paraphrased fact first, got rank {found[0]}"
    )
