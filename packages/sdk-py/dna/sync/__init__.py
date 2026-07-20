# python/dna/sync/__init__.py
"""Content hashing for manifest documents.

Formerly also hosted a bi-directional SyncEngine (engine/diff/snapshot/apply);
it was removed as dead scaffolding — no `dna sync` command ever shipped and the
kernel's own source-sync engine (``dna/kernel/source_sync.py``) is the live path.
``document_hash`` stays: it backs prompt_builder + kind_registry.
"""
from dna.sync.hash import document_hash

__all__ = ["document_hash"]
