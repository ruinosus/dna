"""A política de delegação — pura, e é a fronteira de autorização.

Ela decide, por chamada, quem pode pedir trabalho a quem. Um erro aqui não é bug
de feature: é fronteira de autorização. Por isso a política mora sozinha, sem
transporte, sem parse e sem timeout no mesmo arquivo — a lição de 29/07 no
dna-cloud foi que a política pura estava CERTA nos treze defeitos e o erro estava
sempre na montagem em volta. Manter a parte correta pequena é o ponto.

As propriedades pinadas:

1. **A allowlist é DUPLA.** O delegador declara (`team_members`) E o alvo aceita
   (`delegation_target_for.agents`). Uma ponta só é autorização unilateral.
2. **O roster é DERIVADO, não enumerado** — atravessa `Agent` e `RemoteAgent`
   por quem DECLARA o bloco, nunca por uma lista de Kinds.
3. **`"*"` aceita qualquer delegador**, mas ainda exige a outra ponta.

Nota de implementação: a assinatura de `may_delegate` carrega o NOME do
delegador como primeiro argumento (`delegator, delegator_team_members,
target_accepts_from, target_name`). A versão de três argumentos (sem o nome do
delegador) não é decidível — "o alvo me aceita" não dá pra responder sem saber
quem é "eu". Ver a nota no Step 3 do plano de Task 2.
"""
from __future__ import annotations

from dna.application.delegation import DelegationTarget, may_delegate, targets_for


# ── 1. a allowlist dupla ────────────────────────────────────────────────────


def test_both_ends_must_agree():
    # o caso feliz: o delegador lista o alvo E o alvo aceita o delegador
    assert may_delegate("supervisor", ["converter"], ["supervisor"], "converter") is True


def test_the_delegator_alone_is_not_enough():
    """Só `team_members` é autorização unilateral — o alvo nunca consentiu.

    Remova a checagem do lado do alvo e isto morre: qualquer agente poderia
    puxar trabalho de qualquer outro só por listá-lo."""
    assert may_delegate("supervisor", ["converter"], [], "converter") is False


def test_the_target_alone_is_not_enough():
    """Só `delegation_target_for` também não basta — o delegador não o declarou.

    Um alvo que aceita `"*"` não vira alvo de quem não o listou."""
    assert may_delegate("supervisor", [], ["*"], "converter") is False


def test_a_wildcard_target_still_needs_the_delegator_to_list_it():
    assert may_delegate("supervisor", ["converter"], ["*"], "converter") is True
    assert may_delegate("supervisor", ["outro"], ["*"], "converter") is False


def test_a_target_that_accepts_someone_else_refuses_us():
    assert may_delegate("supervisor", ["converter"], ["jarvis"], "converter") is False


# ── 2. o roster derivado ────────────────────────────────────────────────────


def _agent_doc(name, accepts, **extra):
    """Um documento `Agent` que declara o bloco de delegação."""
    spec = {"instruction": "…", "delegation_target_for": {"agents": accepts, **extra}}
    return {"kind": "Agent", "metadata": {"name": name}, "spec": spec}


def _remote_doc(name, accepts, scope_kinds=("SourceArtifact",), **extra):
    spec = {
        "name": name,
        "description": "…",
        "supported_interfaces": [{"transport": "jsonrpc", "url": "https://x/a2a"}],
        "data_scope": {"kinds": list(scope_kinds)},
        "delegation_target_for": {"agents": accepts, **extra},
    }
    return {"kind": "RemoteAgent", "metadata": {"name": name}, "spec": spec}


def _supervisor(team):
    return {
        "kind": "Agent",
        "metadata": {"name": "supervisor"},
        "spec": {"team_members": list(team)},
    }


def test_the_roster_spans_BOTH_kinds():
    """A propriedade central. O roster é 'quem declara o bloco e me aceita' —
    não 'os Agents, e também os RemoteAgents'.

    Faça-o filtrar por Kind e isto morre, junto com a capacidade de um terceiro
    tipo de alvo entrar sem tocar em quem delega."""
    docs = [
        _supervisor(["local-conv", "remote-conv"]),
        _agent_doc("local-conv", ["supervisor"], format="json"),
        _remote_doc("remote-conv", ["supervisor"], format="json"),
    ]
    targets = targets_for("supervisor", docs)
    assert {t.name for t in targets} == {"local-conv", "remote-conv"}
    assert {t.kind for t in targets} == {"Agent", "RemoteAgent"}


def test_a_document_without_the_block_is_not_a_target():
    docs = [
        _supervisor(["plain"]),
        {"kind": "Agent", "metadata": {"name": "plain"}, "spec": {"instruction": "…"}},
    ]
    assert targets_for("supervisor", docs) == []


def test_a_target_the_supervisor_did_not_list_is_absent():
    docs = [_supervisor([]), _agent_doc("lonely", ["*"])]
    assert targets_for("supervisor", docs) == []


def test_the_target_carries_what_the_delegator_needs_to_narrate_and_parse():
    """`format` dirige o parse do retorno; `typical_seconds` e `use_when` dirigem
    a narração e a escolha do alvo. Sem eles o delegador adivinha."""
    docs = [
        _supervisor(["conv"]),
        _agent_doc(
            "conv", ["supervisor"], format="slug", typical_seconds=9, use_when="quando X"
        ),
    ]
    (t,) = targets_for("supervisor", docs)
    assert (t.format, t.typical_seconds, t.use_when) == ("slug", 9, "quando X")


def test_a_remote_target_carries_its_data_scope_and_interfaces():
    """O executor (Task 4) precisa dos dois para recusar fora de escopo e para
    saber onde chamar."""
    docs = [_supervisor(["r"]), _remote_doc("r", ["supervisor"], scope_kinds=["Invoice"])]
    (t,) = targets_for("supervisor", docs)
    assert t.data_scope_kinds == ("Invoice",)
    assert t.interfaces[0]["url"] == "https://x/a2a"


def test_a_local_target_has_no_data_scope():
    """Um Agent local não atravessa fronteira — `data_scope` é do remoto.
    `None` (e não uma tupla vazia) diz 'não se aplica', não 'nada permitido'."""
    docs = [_supervisor(["c"]), _agent_doc("c", ["supervisor"])]
    (t,) = targets_for("supervisor", docs)
    assert t.data_scope_kinds is None


def test_the_default_format_is_text():
    """O kernel documenta `format` default `text`. O roster não inventa outro."""
    docs = [_supervisor(["c"]), _agent_doc("c", ["supervisor"])]
    (t,) = targets_for("supervisor", docs)
    assert t.format == "text"
