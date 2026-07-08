"""RedisCache — CachePort backed by Redis.

Stores resolved dependency documents in Redis with JSON serialization.
TTL is configurable (default: 1 hour). Scope+key form the Redis key namespace.

Usage:
    from dna.adapters.redis.cache import RedisCache

    cache = RedisCache("redis://localhost:6379/0")
    k = Kernel()
    k.cache(cache)

Requires: redis
    pip install redis
"""
from __future__ import annotations

import json
from typing import Any

from dna.kernel.protocols import CacheItem


class RedisCache:
    """CachePort implementation backed by Redis."""

    def __init__(self, url: str = "redis://localhost:6379/0", ttl: int = 3600, prefix: str = "dna") -> None:
        """Initialize Redis cache.

        Args:
            url: Redis connection URL.
            ttl: Time-to-live in seconds for cached items. Default: 1 hour.
            prefix: Key prefix for all cache entries.
        """
        try:
            import redis
        except ImportError:
            raise ImportError("redis is required. Install with: pip install redis")

        self._client = redis.from_url(url)
        self._ttl = ttl
        self._prefix = prefix

    def _key(self, scope: str, key: str) -> str:
        return f"{self._prefix}:{scope}:{key}"

    def has(self, scope: str, key: str) -> bool:
        return self._client.exists(self._key(scope, key)) > 0

    def store(self, scope: str, key: str, items: list[CacheItem]) -> None:
        """Store resolved items as JSON list in Redis."""
        data = []
        for item in items:
            entry: dict[str, Any] = {"name": item.name, "kind": item.kind}
            if item.raw:
                entry["raw"] = item.raw
            else:
                entry["content"] = item.content_path.read_text(encoding="utf-8")
            data.append(entry)
        self._client.setex(self._key(scope, key), self._ttl, json.dumps(data))

    def load_all(self, scope: str, readers: list | None = None) -> list[dict[str, Any]]:
        """Load all cached documents for a scope.

        Scans all keys matching the scope prefix and aggregates documents.
        """
        pattern = f"{self._prefix}:{scope}:*"
        docs: list[dict[str, Any]] = []
        for redis_key in self._client.scan_iter(match=pattern):
            raw_data = self._client.get(redis_key)
            if not raw_data:
                continue
            items = json.loads(raw_data)
            for item in items:
                if "raw" in item and isinstance(item["raw"], dict):
                    docs.append(item["raw"])
                elif "content" in item:
                    try:
                        docs.append(json.loads(item["content"]))
                    except (json.JSONDecodeError, TypeError):
                        pass
        return docs

    def invalidate(self, scope: str, key: str | None = None) -> int:
        """Invalidate cache entries.

        Args:
            scope: Manifest scope.
            key: Specific key to invalidate. If None, invalidates all keys for scope.

        Returns:
            Number of keys deleted.
        """
        if key:
            return self._client.delete(self._key(scope, key))
        pattern = f"{self._prefix}:{scope}:*"
        keys = list(self._client.scan_iter(match=pattern))
        if keys:
            return self._client.delete(*keys)
        return 0
