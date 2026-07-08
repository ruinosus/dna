"""Máxima — herdável ⇒ nunca TENANTED (s-inheritable-kinds-tenancy-invariant).

Um Kind que é um *default de `_lib` consumido por scopes/tenants* — o
conjunto curado ``DEFAULT_INHERITABLE_KINDS_V1`` (Agent, LottieAsset,
Skill, Theme, HtmlTemplate, ImagePrompt, PromptTemplate, JobType) — PRECISA ser
gravável na camada base (`_lib`, tenant=``''``). A leitura (resolver:
inheritance + ``merge_override_full``) promete um default base que scopes/tenants
herdam e podem sobrescrever; a escrita ``TenantScope.TENANTED`` PROÍBE gravar
essa base (``TenantRequired`` sem tenant) — os dois contratos brigam.

Logo a `TenantScope` de um herdável é **permissiva** (scope ausente → base +
override per-tenant) ou **GLOBAL** (base, sem override) — **nunca TENANTED**.
``TENANTED`` é exclusivo de *dados per-tenant sem default de plataforma*
(audit-log, voice-episode, Canvas, UserProfile).

Origem: o avatar ``jarvis-avatar-remembering`` do JARVIS não gravava na base
do ``_lib`` porque ``LottieAsset`` estava declarado TENANTED.
"""
from dna.kernel import Kernel
from dna.kernel.protocols import TenantScope
from dna.kernel.resolver import DEFAULT_INHERITABLE_KINDS_V1


def test_inheritable_kinds_never_tenanted():
    """Nenhum Kind herdável (default de _lib) pode declarar TENANTED."""
    k = Kernel.auto()  # entry-point discovery carrega todas as extensões
    offenders = []
    for kind_name in sorted(DEFAULT_INHERITABLE_KINDS_V1):
        kp = k.kind_port_for(kind_name)
        if kp is None:
            continue  # Kind não registrado neste build — sem violação possível
        if getattr(kp, "scope", None) == TenantScope.TENANTED:
            offenders.append(kind_name)
    assert offenders == [], (
        "Kinds herdáveis declarados TENANTED bloqueiam o default base de "
        f"_lib que a herança exige: {offenders}. Remova "
        "`scope = TenantScope.TENANTED` (vira permissivo) ou, se uniforme, "
        "use TenantScope.GLOBAL — nunca TENANTED num herdável."
    )
