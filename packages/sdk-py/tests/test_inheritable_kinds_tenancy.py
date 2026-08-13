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
from dna.kernel.query.resolver import TRAIT_PLATFORM_DEFAULT


def test_inheritable_kinds_never_tenanted():
    """Nenhum Kind herdável (default de _lib) pode declarar TENANTED.

    ⚠️ i-107 — o conjunto vem do trait ``composition.platform-default``, não
    mais do literal ``DEFAULT_INHERITABLE_KINDS_V1``. Duas consequências:

    1. O ``if kp is None: continue`` SUMIU. Ele existia porque três dos oito
       nomes da lista — LottieAsset, HtmlTemplate, ImagePrompt — não são Kind
       registrado neste repo, então esta invariante pulava 37% do próprio
       conjunto e passava verde. Um trait não tem onde ser declarado num Kind
       que não existe, então o pulo não tem mais o que pular.
    2. Um Kind autorado por tenant que declare o trait é verificado aqui como
       qualquer embutido — o que faz disto uma regra da plataforma em vez de
       uma lista de exceções conhecidas.
    """
    k = Kernel.auto()  # entry-point discovery carrega todas as extensões
    ports = k.kind_ports_with_trait(TRAIT_PLATFORM_DEFAULT)
    assert ports, (
        "nenhum Kind declara composition.platform-default — a invariante ficou "
        "cega, que é exatamente o modo de falha desta casa (guarda verde por "
        "conjunto vazio). Ver tests/test_platform_default_is_declared.py."
    )
    offenders = sorted(
        kp.kind for kp in ports
        if getattr(kp, "scope", None) == TenantScope.TENANTED
    )
    assert offenders == [], (
        "Kinds herdáveis declarados TENANTED bloqueiam o default base de "
        f"_lib que a herança exige: {offenders}. Remova "
        "`scope = TenantScope.TENANTED` (vira permissivo) ou, se uniforme, "
        "use TenantScope.GLOBAL — nunca TENANTED num herdável."
    )
