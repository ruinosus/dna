"""A política de delegação — quem pode pedir trabalho a quem, e com quais dados.

PURA de propósito: nenhum transporte, nenhum parse, nenhum timeout. Esta é a
fronteira de autorização da feature, e ela merece ser lida e revisada sozinha.
(Em 29/07 o dna-cloud teve treze defeitos de identidade; em TODOS a política pura
estava certa e o erro estava na montagem em volta. Manter a parte correta pequena
é o que torna isso possível.)

── As duas regras ───────────────────────────────────────────────────────────

1. **A allowlist é DUPLA.** O delegador declara o alvo (`AgentSpec.team_members`)
   E o alvo aceita o delegador (`delegation_target_for.agents`). As duas, sempre.
   Uma ponta só seria autorização unilateral: com só a primeira, qualquer agente
   puxaria trabalho de qualquer outro por listá-lo; com só a segunda, um alvo que
   aceita `"*"` seria alvo de quem nunca o quis.

2. **O roster é DERIVADO.** "Todo documento que declara `delegation_target_for` e
   cuja allowlist me inclui" — não uma lista de Kinds. `Agent` e `RemoteAgent`
   entram pelo mesmo caminho porque declaram o mesmo bloco, e um terceiro tipo de
   alvo, depois, entra sem uma linha de mudança aqui. Toda lista mantida à mão
   neste projeto ficou cega e verde; esta consulta não pode ficar.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

#: O default que o kernel documenta para `format` ("free-form narrative").
DEFAULT_FORMAT = "text"


@dataclass(frozen=True)
class DelegationTarget:
    """Um alvo de delegação, já autorizado pelas duas pontas.

    `data_scope_kinds` é `None` para um alvo LOCAL — "não se aplica", que é
    diferente de "nada permitido" (uma tupla vazia). O executor usa essa
    distinção para saber se há fronteira a policiar.
    """

    name: str
    kind: str
    format: str = DEFAULT_FORMAT
    typical_seconds: int | None = None
    use_when: str | None = None
    purpose: str | None = None
    data_scope_kinds: tuple[str, ...] | None = None
    interfaces: tuple[Mapping[str, Any], ...] = ()


def may_delegate(
    delegator: str,
    delegator_team_members: Iterable[str],
    target_accepts_from: Iterable[str],
    target_name: str,
) -> bool:
    """As DUAS pontas concordam? Ver a regra 1 no cabeçalho do módulo.

    `delegator` é o nome de quem pede a delegação — é o que permite decidir
    "o alvo me aceita" (a segunda ponta): sem o nome do delegador a função não
    tem como responder essa pergunta, só "o alvo aceita alguém".
    """
    listed = target_name in set(delegator_team_members or ())
    accepts = set(target_accepts_from or ())
    accepted = "*" in accepts or delegator in accepts
    return listed and accepted


def _spec(doc: Mapping[str, Any]) -> Mapping[str, Any]:
    return doc.get("spec") or {}


def _name(doc: Mapping[str, Any]) -> str:
    return str((doc.get("metadata") or {}).get("name") or "")


def targets_for(
    delegator: str, documents: Iterable[Mapping[str, Any]]
) -> list[DelegationTarget]:
    """Os alvos que `delegator` pode alcançar, derivados dos documentos.

    Ver a regra 2: a consulta é por QUEM DECLARA o bloco, nunca por Kind.
    """
    docs = list(documents)
    team: set[str] = set()
    for doc in docs:
        if _name(doc) == delegator:
            team = set(_spec(doc).get("team_members") or ())
            break

    out: list[DelegationTarget] = []
    for doc in docs:
        block = _spec(doc).get("delegation_target_for")
        if not isinstance(block, Mapping):
            continue
        name = _name(doc) or str(_spec(doc).get("name") or "")
        if name == delegator:
            continue
        accepts = block.get("agents") or ()
        if not may_delegate(delegator, team, accepts, name):
            continue
        scope = _spec(doc).get("data_scope")
        out.append(
            DelegationTarget(
                name=name,
                kind=str(doc.get("kind") or ""),
                format=str(block.get("format") or DEFAULT_FORMAT),
                typical_seconds=block.get("typical_seconds"),
                use_when=block.get("use_when"),
                purpose=block.get("purpose"),
                data_scope_kinds=(
                    tuple(scope.get("kinds") or ())
                    if isinstance(scope, Mapping)
                    else None
                ),
                interfaces=tuple(_spec(doc).get("supported_interfaces") or ()),
            )
        )
    return out
