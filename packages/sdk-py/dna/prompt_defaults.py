"""``dna.prompt_defaults`` — o degrau que faltava na resolução de uma VOZ.

## O defeito que este módulo fecha

A resolução de um `PromptTemplate` tinha dois degraus — overlay do tenant,
depois o doc base do scope — e **um terceiro que ninguém declarava**: o default
que mora no código do SDK e que, na prática, é o que roda em toda instalação
recém-criada.

O terceiro degrau existir sem ser declarado produziu dois defeitos irmãos,
medidos em 06/08/2026 no ambiente do founder:

* **i-101** — `get_template('memory-recall-briefing')` devolvia
  `PromptTemplate ... not found in scope 'dna-cloud'`. Um ERRO vermelho para o
  estado NORMAL de qualquer template cujo default do runtime está valendo: a
  voz sai certa, nada quebrou, e mesmo assim a resposta diz falha. Um erro que
  aparece quando nada quebrou treina a pessoa — e o modelo — a ignorar o
  próximo, inclusive o verdadeiro.
* **i-102** — a voz de MAIOR tráfego do produto (o briefing que o recall injeta
  em todo turno) vivia só como constante de código, enquanto o portal listava
  uma CÓPIA hardcoded do mesmo texto. Duas descrições da mesma coisa, e a
  segunda já nascia condenada a derivar.

## A correção: o default vira DADO, sem virar documento

Um default declarado aqui é servido pelo mesmo catálogo que serve os
documentos, com a ORIGEM DITA — o padrão de honestidade que o `Sourced<T>` do
portal já aplica (`live`/`sample`/`unprovisioned` são estados DITOS, não
falhas). O documento continua VENCENDO quando existe; a ausência dele deixa de
ser erro e passa a ser uma resposta que se explica:

    origin="runtime-default"
    note="nenhum PromptTemplate 'memory-recall-briefing' autorado no scope
          'dna-cloud' — vale o default do runtime (dna.runtime.middleware.recall)."

⚠️ **Por que NÃO materializar os defaults como documentos de verdade.** Era a
direção proposta no i-102 e foi avaliada: escrever os defaults como docs no
scope congela o texto no momento da escrita, e uma melhoria futura do default
do SDK deixa de alcançar quem já tem o doc — exatamente a semântica de fork
que o `memory-template-defaults.ts` do portal documenta como armadilha. Pior:
transformaria "o SDK melhorou a voz" em "todo tenant precisa de uma migração".
Aqui o default continua sendo CÓDIGO (uma melhoria do SDK alcança todo mundo
no próximo release) e ao mesmo tempo é DADO LEGÍVEL pela porta (listável,
buscável, com origem). Materializar continua possível como ato EXPLÍCITO do
tenant — é o que o botão "Personalizar" faz — e essa é a decisão de produto que
fica com o founder, não com este módulo.

## O corpo é lido do próprio código que roda

`body` aceita um *callable*. Isso não é sofisticação: é o que torna a deriva
IMPOSSÍVEL. O registro de `memory-extraction` devolve o texto produzido pela
mesma função que o runtime chama, com as variáveis no lugar — se alguém editar
o default no código, o catálogo passa a servir o texto editado no mesmo commit,
sem ninguém lembrar de atualizar uma segunda cópia. Uma cópia estática aqui
teria reproduzido, dentro do SDK, o defeito que o i-102 aponta no portal.

## Como um pacote de fora registra a sua voz

`dna-cloud` tem quatro vozes próprias no copiloto (`kind-draft-guidance`,
`memory-proposal-guidance`, `extract-prompt`, `spreadsheet-briefing`, …), e
elas têm exatamente o mesmo defeito. A API é pública para que aquele pacote
registre as suas no import do middleware que as usa::

    from dna.prompt_defaults import register_prompt_default

    register_prompt_default(
        "kind-draft-guidance",
        description="A orientação do Kind Studio.",
        body=lambda: GUIDANCE_DEFAULT,
        module=__name__,
    )
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

__all__ = [
    "ORIGIN_DOCUMENT",
    "ORIGIN_RUNTIME_DEFAULT",
    "PromptDefault",
    "prompt_default",
    "prompt_defaults",
    "register_prompt_default",
]

_LOGGER = logging.getLogger(__name__)

#: A origem de uma leitura de catálogo. São os dois estados NORMAIS — nenhum
#: deles é falha, e é por isso que os dois têm nome.
ORIGIN_DOCUMENT = "document"          #: venceu um doc autorado (overlay ou base)
ORIGIN_RUNTIME_DEFAULT = "runtime-default"  #: não há doc; vale o default do código

#: Os módulos do SDK que declaram uma voz. Importados sob demanda (a primeira
#: leitura do catálogo), cada um guardado por si: um extra não instalado tira
#: aquela voz do catálogo, nunca o catálogo inteiro do ar.
_BUILTIN_MODULES = (
    "dna.runtime.middleware.recall",
    "dna.memory.ingestion",
    "dna.extensions.intel.analyzer",
)

_REGISTRY: dict[tuple[str, str], "PromptDefault"] = {}
_WIRED = False


@dataclass(frozen=True)
class PromptDefault:
    """Uma voz que o código traz pronta e que um documento pode sobrescrever."""

    name: str
    description: str
    module: str
    kind: str = "PromptTemplate"
    #: As variáveis OBRIGATÓRIAS — um override que não as carrega é recusado
    #: pelo código que consome a voz (`_template_valido`), e o default volta a
    #: valer. Declaradas aqui para que a tela saiba o que não pode sumir.
    variables: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    _body: "str | Callable[[], str]" = field(default="", repr=False)

    @property
    def body(self) -> str:
        """O texto que roda AGORA. Um callable é chamado a cada leitura, de
        propósito: é o que garante que o catálogo sirva o default vigente e não
        uma fotografia dele."""
        b = self._body
        if callable(b):
            try:
                return str(b() or "")
            except Exception:  # noqa: BLE001 — uma voz quebrada não derruba a listagem
                _LOGGER.warning(
                    "prompt default %r: o corpo não pôde ser produzido", self.name,
                    exc_info=True,
                )
                return ""
        return str(b or "")

    def row(self, scope: str, *, tenant: str | None = None) -> dict[str, Any]:
        """A resposta de catálogo para esta voz, com a ORIGEM dita."""
        return {
            "scope": scope,
            "name": self.name,
            "tenant": tenant,
            "body": self.body,
            "variables": list(self.variables),
            "description": self.description,
            "tags": list(self.tags),
            "origin": ORIGIN_RUNTIME_DEFAULT,
            "module": self.module,
            "overridable": True,
            "note": runtime_default_note(self.name, scope, self.kind, self.module),
        }


def runtime_default_note(name: str, scope: str, kind: str, module: str) -> str:
    """A frase que substitui o erro. Ela diz três coisas, porque as três faltam
    quando a resposta é `not found`: que NADA quebrou, QUEM está falando, e como
    passar a mandar."""
    return (
        f"no {kind} named {name!r} is authored in scope {scope!r} — this is the "
        f"normal state, and the runtime default (from {module}) is what runs. "
        f"Write a {kind} document with this name to override it."
    )


def register_prompt_default(
    name: str,
    *,
    description: str,
    body: "str | Callable[[], str]",
    module: str,
    variables: "Iterable[str]" = (),
    tags: "Iterable[str]" = (),
    kind: str = "PromptTemplate",
) -> None:
    """Declara a voz que o código traz pronta para ``name``.

    Idempotente por (kind, name): reimportar o módulo não duplica nem sobrescreve
    em silêncio — o PRIMEIRO registro vence, para que um host que queira
    substituir uma voz built-in possa registrar a sua ANTES do wiring, do mesmo
    jeito que o registro de runtimes (`dna.runtime.port`) já permite.
    """
    _REGISTRY.setdefault(
        (kind, name),
        PromptDefault(
            name=name,
            description=description,
            module=module,
            kind=kind,
            variables=tuple(variables),
            tags=tuple(tags),
            _body=body,
        ),
    )


def _ensure_wired() -> None:
    global _WIRED
    if _WIRED:
        return
    _WIRED = True
    for mod in _BUILTIN_MODULES:
        try:
            importlib.import_module(mod)
        except Exception:  # noqa: BLE001 — extra ausente tira UMA voz, não o catálogo
            _LOGGER.debug("prompt defaults: %s indisponível", mod, exc_info=True)


def prompt_default(name: str, *, kind: str = "PromptTemplate") -> "PromptDefault | None":
    """A voz built-in de ``name``, ou ``None`` se o código não traz nenhuma."""
    _ensure_wired()
    return _REGISTRY.get((kind, name))


def prompt_defaults(*, kind: str = "PromptTemplate") -> list["PromptDefault"]:
    """Todas as vozes built-in de um Kind, ordenadas por nome.

    É esta função que dá PORTA à capacidade: sem ela o default é conhecível só
    por quem já sabe o nome, e "existe mas não se acha" é o mesmo que não
    existir.
    """
    _ensure_wired()
    return sorted(
        (d for (k, _), d in _REGISTRY.items() if k == kind),
        key=lambda d: d.name,
    )
