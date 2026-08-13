"""Navigator — mi.nav.describe() / summary() / inventory() namespace.

Extracts navigation/display logic from ManifestInstance. Both old and
new APIs return identical results.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from dna.kernel.manifest import ManifestInstance

from dna.kernel.preview import PreviewBlock, generic_spec_dump


class Navigator:
    """Namespace for navigation/display — accessed via ``mi.nav``."""

    def __init__(self, host: ManifestInstance) -> None:
        self._host = host
        self._registry: Any = None

    @property
    def registry(self) -> Any:
        """The canonical Kind registry over this host's registered Kinds.

        Lazy: ``_kinds`` is populated as extensions load, so binding at
        ``__init__`` would freeze a partial view.
        """
        if self._registry is None:
            from dna.kernel.kinds.registry import KindRegistry
            self._registry = KindRegistry(self._host._kinds)
        return self._registry

    def describe(self, kind: str, name: str) -> str:
        """Describe a single instance.

        Equivalent to ``mi.describe(kind, name)``.
        """
        doc = self._host._one(kind, name)
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
            docs = self._host._all(k)
            lines.append(f"  {k}: {len(docs)} ({', '.join(d.name for d in docs)})")
        return "\n".join(lines)

    def inventory(self) -> dict[str, Any]:
        """Produce a structured inventory of the manifest.

        Equivalent to ``mi.inventory()``.
        """
        kinds_data: dict[str, Any] = {}

        for kind_name in self._host.list_kinds():
            docs = self._host._all(kind_name)
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
                "instances": doc_entries,
            }

        comp = self._host.composition_result
        return {
            "scope": self._host.scope,
            "total_instances": len(self._host.instances),
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

        ⚠️ Resolution goes through ``KindRegistry.resolve_dep_filter_target``
        — THE canonical dep_filter resolver (s-unify-composition-subsystems),
        the same one ``validate_refs`` / ``mi.composition`` uses. This method
        used to hand-roll an ``kp.alias == target_alias`` loop, which cannot
        read the legacy ``kind=<Name>`` form, so a legacy dep_filter graded
        AMBIGUOUS here while ``composition.validate()`` resolved it happily —
        two live readers disagreeing about the same edge. The convergence
        story unified the (now deleted) ``query/nav.py`` twin and missed this,
        the reader every ``mi.nav.inventory()`` caller actually reaches.
        """
        host = self._host
        kp_target = self.registry.resolve_dep_filter_target(target_alias)
        kind_name: str | None = kp_target.kind if kp_target is not None else None
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
            if host._one(kind_name, n) is None:
                return "AMBIGUOUS"
        return "EXTRACTED"

    def render_doc(self, kind: str, name: str) -> list[PreviewBlock]:
        """Polymorphic per-kind preview.

        Equivalent to ``mi.render_doc(kind, name)``.
        """
        doc = self._host._one(kind, name)
        if doc is None:
            return []
        kp = self._host._kinds.get((doc.api_version, doc.kind))
        # KindPresentation.preview — optional capability member, typed
        # access with default (absence/None result → generic fallback).
        preview_fn = getattr(kp, "preview", None)
        if callable(preview_fn):
            blocks = preview_fn(doc)
            if blocks is not None:
                return blocks
        return generic_spec_dump(doc)
