"""Navigator — mi.nav.describe() / summary() / inventory() namespace.

Extracts navigation/display logic from ManifestInstance. Both old and
new APIs return identical results.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from dna.kernel.instance import ManifestInstance

from dna.kernel.preview import PreviewBlock, generic_spec_dump


class Navigator:
    """Namespace for navigation/display — accessed via ``mi.nav``."""

    def __init__(self, host: ManifestInstance) -> None:
        self._host = host

    def describe(self, kind: str, name: str) -> str:
        """Describe a single document.

        Equivalent to ``mi.describe(kind, name)``.
        """
        doc = self._host.one(kind, name)
        if not doc:
            return f"{kind}/{name} not found"

        kp = self._host._kinds.get((doc.api_version, doc.kind))
        if kp:
            custom = kp.describe(doc)
            if custom:
                return custom

        lines = [
            f"Name:       {doc.name}",
            f"Kind:       {doc.kind}",
            f"ApiVersion: {doc.api_version}",
        ]
        desc = doc.metadata.get("description")
        if desc:
            lines.append(f"Description: {desc}")
        return "\n".join(lines)

    def summary(self) -> str:
        """Produce a text summary of the manifest.

        Equivalent to ``mi.summary()``.
        """
        kinds = self._host.list_kinds()
        lines = [f"Scope: {self._host.scope}", f"Kinds: {len(kinds)}"]
        for k in kinds:
            docs = self._host.all(k)
            lines.append(f"  {k}: {len(docs)} ({', '.join(d.name for d in docs)})")
        return "\n".join(lines)

    def inventory(self) -> dict[str, Any]:
        """Produce a structured inventory of the manifest.

        Equivalent to ``mi.inventory()``.
        """
        kinds_data: dict[str, Any] = {}

        for kind_name in self._host.list_kinds():
            docs = self._host.all(kind_name)
            doc_entries = []

            for doc in docs:
                entry: dict[str, Any] = {
                    "name": doc.name,
                    "description": doc.metadata.get("description", ""),
                }

                kp = self._host._kinds.get((doc.api_version, doc.kind))
                if kp:
                    filters = kp.dep_filters()
                    if filters:
                        # Phase 14s — each ref carries confidence:
                        #   EXTRACTED  — declared and target resolves to a doc
                        #   AMBIGUOUS  — declared but target missing in scope
                        #   INFERRED   — reserved for LLM/heuristic resolution (v2)
                        # Back-compat: refs[field] still holds the raw value;
                        # refs_confidence[field] is the parallel mapping.
                        refs: dict[str, Any] = {}
                        refs_confidence: dict[str, str] = {}
                        for spec_field, alias in filters.items():
                            val = doc.spec.get(spec_field)
                            if val is None:
                                continue
                            refs[spec_field] = val
                            confidence = self._classify_ref_confidence(alias, val)
                            refs_confidence[spec_field] = confidence
                        if refs:
                            entry["refs"] = refs
                            entry["refs_confidence"] = refs_confidence

                    extra = kp.summary(doc)
                    if extra:
                        entry.update(extra)

                doc_entries.append(entry)

            kinds_data[kind_name] = {
                "count": len(docs),
                "documents": doc_entries,
            }

        comp = self._host.composition_result
        return {
            "scope": self._host.scope,
            "total_documents": len(self._host.documents),
            "kinds": kinds_data,
            "composition": {
                "valid": comp.valid,
                "resolved": comp.resolved,
                "missing": comp.missing,
                "warnings": comp.warnings,
                "deferred": comp.deferred,
            },
        }

    def _classify_ref_confidence(self, target_alias: str, value: Any) -> str:
        """Phase 14s — classify a single ref edge as EXTRACTED, AMBIGUOUS,
        or INFERRED.

        - EXTRACTED: target alias resolves to a registered Kind AND
          every referenced name resolves to an existing doc.
        - AMBIGUOUS: target alias unknown OR at least one referenced
          name is missing from the scope.
        - INFERRED: reserved for LLM/heuristic resolution (v2).

        ``value`` may be a string (single ref) or list (multiple).
        """
        host = self._host
        # Resolve alias → kind name (kp.alias is on each KindPort)
        kind_name: str | None = None
        for kn in host.list_kinds():
            kp = host.kind_for(kn)
            if kp and getattr(kp, "alias", None) == target_alias:
                kind_name = kn
                break
        if kind_name is None:
            return "AMBIGUOUS"
        names: list[str] = []
        if isinstance(value, str):
            names = [value]
        elif isinstance(value, list):
            names = [str(v) for v in value if v]
        else:
            return "EXTRACTED"  # opaque value, can't validate but is declared
        for n in names:
            if host.one(kind_name, n) is None:
                return "AMBIGUOUS"
        return "EXTRACTED"

    def render_doc(self, kind: str, name: str) -> list[PreviewBlock]:
        """Polymorphic per-kind preview.

        Equivalent to ``mi.render_doc(kind, name)``.
        """
        doc = self._host.one(kind, name)
        if doc is None:
            return []
        kp = self._host._kinds.get((doc.api_version, doc.kind))
        if kp is not None and hasattr(kp, "preview") and callable(kp.preview):
            return kp.preview(doc)
        return generic_spec_dump(doc)
