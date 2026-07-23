"""Evidence auto-capture handler for HookRegistry post_save.

The microkernel must work with ZERO extensions loaded, so this module
imports NOTHING from ``dna.extensions`` (boundary ratchet:
``tests/test_kernel_extension_boundary.py``). The three helpers below —
``compute_content_hash``, ``build_evidence`` and ``should_capture`` — are
fully generic (stdlib + plain dicts only), so they live here in the kernel
exactly like the TS twin keeps ``computeContentHash``/``buildEvidenceDoc``/
``shouldCapture`` in ``kernel/evidence-capture.ts`` (s-invert-layer-resolver-dep
pattern; s-invert-evidence-capture-dep). ``EvidenceExtension`` re-exports them
for its public API (the gaia worker + existing callers keep their imports).

Capture is OFF by default: the ``post_save`` handler is only wired when
``EvidenceExtension.register()`` calls ``kernel.on("post_save", ...)``. A
kernel booted without the extension never registers the handler, so nothing
is captured and nothing crashes.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_EVAL_KINDS = {"EvalRun", "EvalBaseline", "Finding"}


# ───────────────────────────────────────────────────────────────────────
# Generic evidence helpers (moved from extensions/evidence — kernel-owned)
# ───────────────────────────────────────────────────────────────────────

def compute_content_hash(content: Any) -> str:
    """Return the SHA-256 hex digest of *content* serialized as canonical JSON.

    Keys are sorted and no extra whitespace is added so that logically
    identical objects always produce the same hash regardless of
    insertion order.
    """
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_evidence(
    event_type: str,
    document_ref: str,
    content: Any,
    *,
    author: str = "system",
    notes: str | None = None,
    suite: str | None = None,
) -> dict[str, Any]:
    """Build an Evidence Kind document dict.

    Parameters
    ----------
    event_type:
        One of the allowed event_type enum values (e.g. ``eval_run_completed``).
    document_ref:
        Reference to the document that triggered the event (e.g. ``eval-evalrun/my-run``).
    content:
        The content to hash — typically the document spec or a serializable snapshot.
    author:
        Who (or what) captured the evidence.  Defaults to ``"system"``.
    notes:
        Optional free-text annotation.

    Returns
    -------
    dict
        A dict with ``api_version``, ``kind``, ``metadata``, and ``spec`` ready
        to be written by the kernel's WriterPort.
    """
    spec: dict[str, Any] = {
        "event_type": event_type,
        "sha256": compute_content_hash(content),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "author": author,
        "document_ref": document_ref,
        "snapshot": content if isinstance(content, dict) else {"value": content},
    }
    if notes is not None:
        spec["notes"] = notes
    if suite is not None:
        spec["suite"] = suite

    return {
        "api_version": "github.com/ruinosus/dna/evidence/v1",
        "kind": "Evidence",
        "metadata": {
            "name": f"ev-{event_type}-{spec['sha256'][:12]}",
        },
        "spec": spec,
    }


def should_capture(policy_spec: dict, event_type: str) -> bool:
    """Check whether *event_type* should be auto-captured per *policy_spec*."""
    if not policy_spec.get("auto_capture", True):
        return False
    return event_type in policy_spec.get("events", [])


def extract_suite(kind: str, spec: dict[str, Any], explicit: str | None) -> str | None:
    """Extract suite name for eval-related Kinds.

    The spec may be flat ({"suite": "x"}) or nested ({"spec": {"suite": "x"}})
    depending on whether the caller passed the raw doc or just the spec field.
    """
    if explicit:
        return explicit
    if kind not in _EVAL_KINDS:
        return None
    # Handle both flat and nested structures
    inner = spec.get("spec", spec) if isinstance(spec.get("spec"), dict) else spec
    return inner.get("suite") or inner.get("source")


def make_evidence_capture_handler(kernel: Any):
    """Create a post_save handler bound to a kernel instance."""
    _policy_cache: dict[str, list] = {}

    async def handler(ctx) -> None:
        data = ctx.data
        event_type = data.get("event_type", "")
        kind = ctx.kind or ""
        name = ctx.name or ""

        if kind == "Evidence":
            return

        scope = ctx.scope
        if kind == "EvidencePolicy" or scope not in _policy_cache:
            # MUST be async — this handler runs from inside post_save
            # emission (which is invoked via `await emit_async` on the
            # caller's event loop). Using sync `kernel.instance(scope)`
            # here drops to `_run_sync_helper`, which spawns a new loop
            # in a ThreadPoolExecutor when `kernel._main_loop` isn't
            # registered (CLI / standalone tests). The new loop then
            # tries to use the asyncpg pool bound to the caller's loop
            # → `RuntimeError: Future attached to a different loop`
            # → `ConnectionDoesNotExistError`. Fixed 2026-05-03.
            _policy_cache[scope] = [
                raw.get("spec") or {}
                async for raw in kernel.query(scope, "EvidencePolicy")
            ]
        if not any(should_capture(p, event_type) for p in _policy_cache.get(scope, [])):
            return

        suite = extract_suite(kind, data.get("spec", {}), data.get("suite"))

        doc = build_evidence(
            event_type,
            f"{kind}:{name}",
            data.get("spec", {}),
            author=data.get("author", "unknown"),
            suite=suite,
        )

        try:
            evidence_name = doc["metadata"]["name"]
            raw_evidence = {
                "apiVersion": doc.get("apiVersion", "github.com/ruinosus/dna/v1"),
                "kind": "Evidence",
                "metadata": doc.get("metadata", {}),
                "spec": doc.get("spec", {}),
            }
            # skip_hooks=True prevents the Evidence write from re-triggering
            # post_save → infinite recursion. Source persists via the registered
            # WriterPort — works for FS, Postgres, SQLite, or any backend.
            await kernel.write_document(
                scope, "Evidence", evidence_name, raw_evidence,
                skip_hooks=True,
            )
            logger.debug("Evidence captured: %s for %s:%s", event_type, kind, name)
        except Exception as e:
            logger.warning("Evidence capture failed for %s:%s: %s", kind, name, e)

    return handler
