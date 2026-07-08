"""s-alias-generated-not-typed — aliases GERADOS de (owner, kind), não digitados.

Aliases são a chave de dep_filters, dos templates Mustache e do LayerPolicy
— e eram strings digitadas à mão em cada classe, com ~46 divergências da
convenção ``<owner>-<kebab(kind)>`` e um bug histórico registrado
("policy-layer" reversed/truncated). Contrato pós-story:

1. Kind SEM ``alias`` declarado ganha um gerado: ``<owner>-<kebab(kind)>``.
   Owner vem de ``alias_owner`` no port, senão do contexto da Extension em
   ``kernel.load()`` (``ext.alias_owner`` / ``ext.name``), senão do 1º token
   do api_version. Ports gerados são estampados ``__alias_generated__``.
2. Aliases legados ficam INTOCADOS (wire format vivo — renomear quebraria
   dep_filters/Mustache/LayerPolicy docs). O ratchet EXPLICIT_ALIAS_ALLOWLIST
   é shrink-only: Kind novo NÃO declara alias na mão.
3. ``kernel.validate_dep_filters()`` roda no fim de ``Kernel.auto()``:
   dep_filter de extension apontando pra alias desconhecido → ERRO de boot
   (era warning silencioso que degradava o prompt). Ports per-scope
   (declarative) continuam warning — docs de usuário não derrubam boot.
4. O formato legado ``kind=<Nome>`` resolve via shim com DeprecationWarning
   no resolver canônico (antes: silenciosamente ignorado pelo kernel).
"""
import warnings as _warnings

import pytest

from dna.kernel import Kernel
from dna.kernel.errors import KindRegistrationError
from dna.kernel.kind_base import KindBase
from dna.kernel.kind_registry import (
    generate_alias,
    kebab_kind_name,
)
from dna.kernel.protocols import StorageDescriptor


# ---------- 1. kebab + generation helpers ----------

@pytest.mark.parametrize("kind,expected", [
    ("EvalCase", "eval-case"),
    ("Agent", "agent"),
    ("ADR", "adr"),
    ("HTMLThing", "html-thing"),
    ("JobType", "job-type"),
    ("Story", "story"),
    ("PreMortem", "pre-mortem"),
])
def test_kebab_kind_name(kind, expected):
    assert kebab_kind_name(kind) == expected


def test_generate_alias():
    assert generate_alias("sdlc", "JobType") == "sdlc-job-type"
    assert generate_alias("eval", "EvalCase") == "eval-eval-case"


# ---------- 2. kind() generates when alias missing ----------

class _NoAliasKind(KindBase):
    api_version = "myext.test/v1"
    kind = "WidgetThing"
    alias = None  # ← não digitado: gerado no registro
    alias_owner = "myext"
    storage = StorageDescriptor.yaml("widget-things")


def test_kind_without_alias_gets_generated():
    k = Kernel()
    port = _NoAliasKind()
    k.kind(port)
    assert port.alias == "myext-widget-thing"
    assert getattr(port, "__alias_generated__", False) is True


def test_generated_alias_falls_back_to_api_version_owner():
    class _NoOwner(KindBase):
        api_version = "fallback.test/v1"
        kind = "GadgetThing"
        alias = None
        storage = StorageDescriptor.yaml("gadget-things")

    k = Kernel()
    port = _NoOwner()
    k.kind(port)
    assert port.alias == "fallback-gadget-thing"


def test_generated_alias_still_subject_to_uniqueness():
    class _A(KindBase):
        api_version = "uniq.test/v1"
        kind = "SameThing"
        alias = None
        storage = StorageDescriptor.yaml("same-a")

    class _B(KindBase):
        api_version = "uniq.test/v2"
        kind = "SameThing"
        alias = None
        storage = StorageDescriptor.yaml("same-b")

    k = Kernel()
    k.kind(_A())
    # mesma geração → colide no H1 alias-uniqueness (e no name-collision i-195)
    with pytest.raises(KindRegistrationError):
        k.kind(_B())


# ---------- 3. load() provides extension owner context ----------

def test_load_provides_owner_context():
    class _ExtKind(KindBase):
        api_version = "weird.namespace.io/v1"
        kind = "ContextThing"
        alias = None
        storage = StorageDescriptor.yaml("context-things")

    class _Ext:
        name = "ctxext"
        version = "0.0.1"

        def register(self, kernel):
            kernel.kind(_ExtKind())

    k = Kernel()
    k.load(_Ext())
    port = k.kind_port_for("ContextThing")
    # owner veio da Extension (ctxext), não do api_version (weird)
    assert port.alias == "ctxext-context-thing"


# ---------- 4. ratchet: Kind novo não digita alias ----------

def test_explicit_alias_ratchet_is_shrink_only():
    """Todo port builtin com alias digitado à mão está no allowlist frozen.
    Kind NOVO deve OMITIR alias (geração) — adicionar nome aqui é proibido;
    a lista só encolhe conforme classes migram pra geração."""
    from dna.kernel.kind_registry import EXPLICIT_ALIAS_ALLOWLIST
    k = Kernel.auto()
    explicit = {
        kp.alias
        for kp in k.kind_ports()
        if getattr(kp, "alias", None)
        and not getattr(kp, "__alias_generated__", False)
        and not getattr(kp, "__declarative__", False)  # descriptors têm alias no YAML (parity-critical)
    }
    stray = explicit - EXPLICIT_ALIAS_ALLOWLIST
    assert not stray, (
        f"Kind(s) novo(s) com alias digitado à mão: {sorted(stray)}. "
        f"Omita o alias (será gerado <owner>-<kebab(kind)>) em vez de "
        f"digitá-lo — s-alias-generated-not-typed."
    )
    # Igualdade nos DOIS sentidos: entrada sem port vivo = classe migrou
    # pra geração/descriptor — REMOVA do allowlist (é assim que ele
    # provadamente encolhe).
    dead = EXPLICIT_ALIAS_ALLOWLIST - explicit
    assert not dead, (
        f"Entrada(s) morta(s) no EXPLICIT_ALIAS_ALLOWLIST: {sorted(dead)} — "
        f"a classe migrou; remova do allowlist (shrink-only)."
    )


# ---------- 5. validate_dep_filters: unknown alias = ERRO de boot ----------

def test_validate_dep_filters_unknown_alias_raises():
    class _Broken(KindBase):
        api_version = "broken.test/v1"
        kind = "BrokenDeps"
        alias = "broken-broken-deps"
        storage = StorageDescriptor.yaml("broken-deps")

        def dep_filters(self):
            return {"things": "no-such-alias"}

    k = Kernel()
    k.kind(_Broken())
    with pytest.raises(KindRegistrationError, match="no-such-alias"):
        k.validate_dep_filters()


def test_validate_dep_filters_kind_eq_format_rejected_for_builtin():
    """Builtins são alias-puros pós-story — kind=X em extension é erro."""
    class _LegacyFmt(KindBase):
        api_version = "legacyfmt.test/v1"
        kind = "LegacyFmt"
        alias = "legacyfmt-legacy-fmt"
        storage = StorageDescriptor.yaml("legacy-fmts")

        def dep_filters(self):
            return {"stories": "kind=Story"}

    k = Kernel()
    k.kind(_LegacyFmt())
    with pytest.raises(KindRegistrationError, match="kind="):
        k.validate_dep_filters()


def test_validate_dep_filters_declarative_only_warns(caplog):
    import logging
    from dna.kernel.kind_base import KindBase as KB

    class _ScopeKind(KB):
        api_version = "scoped.test/v1"
        kind = "ScopedThing"
        alias = "scoped-scoped-thing"
        storage = StorageDescriptor.yaml("scoped-things")
        __declarative__ = True

        def dep_filters(self):
            return {"refs": "missing-alias"}

    k = Kernel()
    k._kinds[("scoped.test/v1", "ScopedThing")] = _ScopeKind()  # funil per-scope
    with caplog.at_level(logging.WARNING):
        k.validate_dep_filters()  # NÃO levanta
    assert any("missing-alias" in r.getMessage() for r in caplog.records)


def test_kernel_auto_passes_validation():
    """Todos os dep_filters builtin resolvem — Kernel.auto() valida no fim."""
    k = Kernel.auto()  # levantaria se algum builtin apontasse pra alias morto
    k.validate_dep_filters()


# ---------- 6. resolver canônico com shim kind= deprecado ----------

def test_resolve_dep_filter_target_alias_and_legacy_shim():
    class _Tgt(KindBase):
        api_version = "tgt.test/v1"
        kind = "TargetThing"
        alias = "tgt-target-thing"
        storage = StorageDescriptor.yaml("target-things")

    k = Kernel()
    k.kind(_Tgt())
    reg = k._kindreg
    assert reg.resolve_dep_filter_target("tgt-target-thing").kind == "TargetThing"
    with _warnings.catch_warnings(record=True) as w:
        _warnings.simplefilter("always")
        port = reg.resolve_dep_filter_target("kind=TargetThing")
        assert port is not None and port.kind == "TargetThing"
        assert any(issubclass(x.category, DeprecationWarning) for x in w)
    assert reg.resolve_dep_filter_target("nope-nothing") is None
