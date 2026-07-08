"""S3Source — Read-only SourcePort backed by AWS S3.

Loads manifest documents from an S3 bucket. Each scope maps to a prefix
in the bucket: `{prefix}/{scope}/manifest.yaml`, `{prefix}/{scope}/documents/*.yaml`.

Usage:
    from dna.adapters.s3.source import S3Source

    source = S3Source(bucket="my-manifests", prefix="dna")
    k = Kernel()
    k.source(source)

Requires: boto3
    pip install boto3
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class S3Source:
    """Read-only SourcePort backed by AWS S3."""

    supports_readers: bool = False

    def __init__(
        self,
        bucket: str,
        prefix: str = "dna",
        region: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        """Initialize S3 source.

        Args:
            bucket: S3 bucket name.
            prefix: Key prefix for manifest files.
            region: AWS region (optional, uses default if not set).
            endpoint_url: Custom endpoint (for MinIO, LocalStack, etc.).
        """
        try:
            import boto3
        except ImportError:
            raise ImportError("boto3 is required. Install with: pip install boto3")

        kwargs: dict[str, Any] = {}
        if region:
            kwargs["region_name"] = region
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url

        self._s3 = boto3.client("s3", **kwargs)
        self._bucket = bucket
        self._prefix = prefix

    def _key(self, scope: str, *parts: str) -> str:
        return "/".join([self._prefix, scope, *parts])

    def _get_json(self, key: str) -> dict[str, Any] | None:
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=key)
            body = resp["Body"].read().decode("utf-8")
            # Support both JSON and YAML
            if key.endswith((".yaml", ".yml")):
                import yaml
                return yaml.safe_load(body)
            return json.loads(body)
        except self._s3.exceptions.NoSuchKey:
            return None
        except Exception as e:
            logger.warning("S3 read error for %s: %s", key, e)
            return None

    def load_bootstrap_docs(
        self, scope: str, *, tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        """Phase 16 — return Genome + KindDefinition + LayerPolicy docs.

        S3 adapter scans the scope prefix and filters by Kind name.
        Tenant overlay is not implemented for S3 today (no
        tenants/<t>/scopes/<s>/ convention exposed).
        """
        from dna.kernel.protocols import BOOTSTRAP_KIND_NAMES
        del tenant  # not implemented on S3
        all_raws = self.load_all(scope)
        return [d for d in all_raws if d.get("kind") in BOOTSTRAP_KIND_NAMES]

    def load_all(self, scope: str, readers: list | None = None) -> list[dict[str, Any]]:
        """Load all documents from the scope prefix."""
        prefix = self._key(scope, "")
        docs: list[dict[str, Any]] = []

        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith((".yaml", ".yml", ".json")):
                    continue
                doc = self._get_json(key)
                if doc and "kind" in doc:
                    docs.append(doc)

        return docs

    def resolve_ref(self, scope: str, ref: str) -> str:
        """Resolve a file reference from S3."""
        key = self._key(scope, ref)
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=key)
            return resp["Body"].read().decode("utf-8")
        except Exception:
            return ref

    def load_layer(
        self, scope: str, layer_id: str, layer_value: str,
        readers: list | None = None,
    ) -> list[dict[str, Any]]:
        """Load layer overlay documents from S3."""
        prefix = self._key(scope, "layers", layer_id, layer_value, "")
        docs: list[dict[str, Any]] = []

        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith((".yaml", ".yml", ".json")):
                    continue
                doc = self._get_json(key)
                if doc and "kind" in doc:
                    docs.append(doc)

        return docs
