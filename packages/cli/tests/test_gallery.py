"""Pure-unit coverage for the gallery aggregator.

``dna_cli._gallery`` is kernel-free by design (the CLI command owns the impure
edges), so the whole aggregation contract is testable with plain dicts here —
no source, no session. Covers the reverse index (produces[] ∪ legacy back-refs),
status → bucket classification, PR matching, and the counts rollup.
"""
from __future__ import annotations

from dna_cli._gallery import (
    BUCKET_ORDER,
    build_gallery,
    build_reverse_index,
    bucket_label,
    render_gallery_html,
)


def _art(name, **kw):
    return {
        "name": name,
        "title": kw.get("title"),
        "description": kw.get("description"),
        "source": kw.get("source"),
        "published_url": kw.get("published_url"),
        "html_bytes": kw.get("html_bytes", 100),
    }


def _wi(kind, name, status, *, produces=None, html_artifacts=None, timeline=None):
    spec: dict = {"status": status, "title": f"{name} title"}
    if produces is not None:
        spec["produces"] = produces
    if html_artifacts is not None:
        spec["html_artifacts"] = html_artifacts
    if timeline is not None:
        spec["timeline"] = timeline
    return {"kind": kind, "name": name, "spec": spec}


# ─── reverse index ────────────────────────────────────────────────────

def test_reverse_index_from_explicit_produces():
    wis = [_wi("Story", "s-x", "review",
               produces=[{"kind": "HtmlArtifact", "name": "ha-1"}])]
    idx = build_reverse_index(wis)
    assert idx["ha-1"]["kind"] == "Story"
    assert idx["ha-1"]["name"] == "s-x"
    assert idx["ha-1"]["status"] == "review"
    assert idx["ha-1"]["source"] == "produces"


def test_reverse_index_from_legacy_html_artifacts_backref():
    wis = [_wi("Feature", "f-y", "in-development", html_artifacts=["ha-2"])]
    idx = build_reverse_index(wis)
    assert idx["ha-2"]["kind"] == "Feature"
    assert idx["ha-2"]["source"] == "legacy"


def test_reverse_index_first_producer_wins_on_collision():
    wis = [
        _wi("Story", "s-a", "done", produces=[{"kind": "HtmlArtifact", "name": "ha-c"}]),
        _wi("Story", "s-b", "review", produces=[{"kind": "HtmlArtifact", "name": "ha-c"}]),
    ]
    idx = build_reverse_index(wis)
    assert idx["ha-c"]["name"] == "s-a"


# ─── classification into buckets ──────────────────────────────────────

def test_adr_produced_artifact_is_a_decision():
    g = build_gallery(
        artifacts=[_art("ha-d")],
        work_items=[_wi("ADR", "adr-pivot", "accepted",
                        produces=[{"kind": "HtmlArtifact", "name": "ha-d"}])],
        scope="s",
    )
    assert g["buckets"]["decisions"][0]["name"] == "ha-d"
    assert g["counts"]["decisions"] == 1


def test_story_in_review_needs_review():
    g = build_gallery(
        artifacts=[_art("ha-r")],
        work_items=[_wi("Story", "s-r", "review",
                        produces=[{"kind": "HtmlArtifact", "name": "ha-r"}])],
        scope="s",
    )
    assert g["buckets"]["needs_review"][0]["name"] == "ha-r"


def test_terminal_status_is_shipped():
    g = build_gallery(
        artifacts=[_art("ha-s")],
        work_items=[_wi("Story", "s-s", "done",
                        produces=[{"kind": "HtmlArtifact", "name": "ha-s"}])],
        scope="s",
    )
    assert g["buckets"]["shipped"][0]["name"] == "ha-s"


def test_in_progress_bucket():
    g = build_gallery(
        artifacts=[_art("ha-p")],
        work_items=[_wi("Story", "s-p", "in-progress",
                        produces=[{"kind": "HtmlArtifact", "name": "ha-p"}])],
        scope="s",
    )
    assert g["buckets"]["in_progress"][0]["name"] == "ha-p"


def test_unlinked_artifact_has_no_work_item():
    g = build_gallery(artifacts=[_art("ha-orphan")], work_items=[], scope="s")
    entry = g["buckets"]["unlinked"][0]
    assert entry["name"] == "ha-orphan"
    assert entry["work_item"] is None


# ─── PR matching pushes non-review items into needs_review ─────────────

def test_open_pr_matched_by_branch_forces_needs_review():
    # A Story still 'in-progress' but with an open PR on its branch is
    # awaiting review — the gallery surfaces it in the review queue.
    g = build_gallery(
        artifacts=[_art("ha-pr")],
        work_items=[_wi("Story", "s-pr", "in-progress",
                        produces=[{"kind": "HtmlArtifact", "name": "ha-pr"}])],
        scope="s",
        open_prs=[{"number": 42, "title": "wip", "headRefName": "feat/s-pr",
                   "url": "https://github.com/o/r/pull/42"}],
    )
    entry = g["buckets"]["needs_review"][0]
    assert entry["name"] == "ha-pr"
    assert entry["prs"][0]["number"] == 42


# ─── published_url + metadata surface through ─────────────────────────

def test_published_url_flows_into_entry():
    g = build_gallery(
        artifacts=[_art("ha-u", published_url="https://claude.ai/x", title="T")],
        work_items=[_wi("Story", "s-u", "review",
                        produces=[{"kind": "HtmlArtifact", "name": "ha-u"}])],
        scope="s",
    )
    entry = g["buckets"]["needs_review"][0]
    assert entry["published_url"] == "https://claude.ai/x"
    assert entry["title"] == "T"
    assert entry["work_item"]["name"] == "s-u"


# ─── counts rollup ────────────────────────────────────────────────────

def test_counts_total_is_sum_of_buckets():
    g = build_gallery(
        artifacts=[_art("a1"), _art("a2"), _art("a3")],
        work_items=[
            _wi("ADR", "adr-1", "accepted", produces=[{"kind": "HtmlArtifact", "name": "a1"}]),
            _wi("Story", "s-1", "review", produces=[{"kind": "HtmlArtifact", "name": "a2"}]),
            # a3 unlinked
        ],
        scope="s",
    )
    assert g["counts"]["total"] == 3
    assert g["counts"]["decisions"] == 1
    assert g["counts"]["needs_review"] == 1
    assert g["counts"]["unlinked"] == 1


def test_all_buckets_present_even_when_empty():
    g = build_gallery(artifacts=[], work_items=[], scope="s")
    assert set(g["buckets"]) == set(BUCKET_ORDER)
    assert g["counts"]["total"] == 0


def test_bucket_label_is_human():
    assert bucket_label("needs_review") == "Precisa de avaliação"
    assert bucket_label("decisions") == "Decisões"


# ─── self-contained HTML render ───────────────────────────────────────

def test_render_html_is_self_contained_and_has_content():
    g = build_gallery(
        artifacts=[_art("ha-u", title="Antes → Depois",
                        published_url="https://claude.ai/x", description="d")],
        work_items=[_wi("Story", "s-u", "review",
                        produces=[{"kind": "HtmlArtifact", "name": "ha-u"}])],
        scope="dna-development",
    )
    html = render_gallery_html(g, generated_at="2026-07-11")
    assert html.startswith("<!doctype html>")
    # Self-contained: no external requests (no CDN scripts/styles/fonts).
    assert "http://" not in html.replace("http://www.w3.org", "")  # no http assets
    assert "src=\"http" not in html
    assert "href=\"https://claude.ai/x\"" in html  # the published link is clickable
    assert "Antes → Depois" in html
    assert "Precisa de avaliação" in html  # bucket header rendered


def test_render_html_escapes_untrusted_fields():
    g = build_gallery(
        artifacts=[_art("ha-x", title="<script>alert(1)</script>")],
        work_items=[],
        scope="s",
    )
    html = render_gallery_html(g)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_html_empty_scope():
    g = build_gallery(artifacts=[], work_items=[], scope="s")
    html = render_gallery_html(g)
    assert "Nenhum HtmlArtifact" in html
