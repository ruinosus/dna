# python/dna/sync/hash.py
"""Content-hash computation for sync — compatible with lockfile SHA-256."""
import hashlib
import json
import math


def _normalize_floats(obj):
    """Normalize whole-number floats to ints for cross-language parity.

    Python's YAML loader preserves float (25.0), but JavaScript only has
    'number' (25.0 === 25). JSON.stringify(25.0) in Python produces "25.0",
    in JS produces "25". This normalization ensures identical JSON output.
    """
    if isinstance(obj, float):
        if math.isfinite(obj) and obj == int(obj):
            return int(obj)
        return obj
    if isinstance(obj, dict):
        return {k: _normalize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_floats(v) for v in obj]
    return obj


def document_hash(raw: dict) -> str:
    """Compute SHA-256 of a document's raw dict.

    Uses json.dumps with sort_keys=True, ensure_ascii=False.
    Normalizes whole-number floats to ints for TypeScript parity.
    """
    normalized = _normalize_floats(raw)
    canonical = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()
