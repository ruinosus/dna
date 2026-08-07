"""``dna copilot`` — kits de copiloto instaláveis (F3 do adr-copiloto-como-dado).

Um KIT é um diretório de DOCUMENTOS DNA (YAML com apiVersion/kind/metadata/
spec): tipicamente um ``Copilot`` (com ``spec.surfaces[]``), o(s) ``Agent``
que ele monta, o ``KindDefinition`` do domínio e ``PromptTemplate``s de voz.
Instalar = escrever cada doc pelo ``kernel.write_instance`` — TODOS os guards
da porta disparam (schema na escrita, tombstones, layer policy), exatamente
como o ``dna specify import`` já faz para o Spec Kit. Nada aqui reimplementa
validação.

A prova do desenho (spikes + F1/F2): o template de vitrine
``copilot-kits/contrato-intake`` não carrega UMA linha de código — a surface
de instância já é schema-directed (``update_instance_draft`` funciona para
qualquer Kind), então um fluxo novo completo é só dados.

## Aprovação de Kind — o humano continua no circuito

Um ``KindDefinition`` sem ``approved_by`` instala INERTE (parseia, não
registra, não valida docs) — o mesmo funil do ``author_kind``. A flag
``--approve`` carimba o OPERADOR (git user.email) como aprovador no ato da
instalação: rodar o comando com a flag É o ato humano, no self-host. No SaaS
a aprovação continua no portal.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import click

from dna._yaml import safe_load as _yaml_safe_load

from dna_cli._ctx import dna_session, fail, print_json

#: Ordem de escrita: definições antes de quem as referencia. Kinds
#: desconhecidos do mapa vão ao final, na ordem do diretório.
_ORDEM = {"KindDefinition": 0, "PromptTemplate": 1, "Agent": 2, "Copilot": 3}


@dataclass(frozen=True)
class KitDoc:
    path: Path
    kind: str
    name: str
    raw: dict


def scan_kit(root: Path) -> list[KitDoc]:
    """Todos os docs DNA do kit, ordenados para escrita. Arquivo YAML sem a
    forma de doc (sem apiVersion/kind/metadata.name) é IGNORADO com aviso —
    um kit pode carregar README/fixtures sem quebrar a instalação."""
    docs: list[KitDoc] = []
    for f in sorted(root.rglob("*.yaml")) + sorted(root.rglob("*.yml")):
        try:
            raw = _yaml_safe_load(f.read_text())
        except Exception as exc:  # noqa: BLE001 — YAML ilegível
            raise fail(f"{f}: YAML ilegível — {exc}") from exc
        if not isinstance(raw, dict):
            continue
        kind = raw.get("kind")
        nome = ((raw.get("metadata") or {}).get("name")) if isinstance(raw.get("metadata"), dict) else None
        if not (raw.get("apiVersion") and isinstance(kind, str) and isinstance(nome, str)):
            click.secho(f"  (ignorado: {f.name} não tem forma de instância DNA)", fg="yellow")
            continue
        docs.append(KitDoc(path=f, kind=kind, name=nome, raw=raw))
    docs.sort(key=lambda d: _ORDEM.get(d.kind, 99))
    return docs


def _operador() -> str:
    try:
        out = subprocess.run(
            ["git", "config", "user.email"], capture_output=True, text=True, timeout=5
        )
        email = (out.stdout or "").strip()
        if email:
            return email
    except Exception:  # noqa: BLE001 — identidade é rótulo, não gate
        pass
    return "operator"


@click.group("copilot", help="Copilot kits — fluxos completos instaláveis como instâncias.")
def copilot() -> None:
    """\b
      dna copilot install copilot-kits/contrato-intake --scope meu-escopo
      dna copilot install <dir> --dry-run     # lista o plano, escreve nada
      dna copilot install <dir> --approve     # o operador aprova o Kind no ato
      dna copilot provenance                  # quem veio de onde — e quem não diz
    """


@copilot.command("install")
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@click.option("--scope", default=None, help="Scope de destino (default: env / sole scope).")
@click.option("--approve", is_flag=True,
              help="Carimba o OPERADOR (git user.email) como aprovador dos "
                   "KindDefinition do kit — o ato humano, no self-host.")
@click.option("--dry-run", is_flag=True, help="Lista o plano; escreve nada.")
@click.option("--json", "as_json", is_flag=True, help="Saída legível por máquina.")
def install(path, scope, approve, dry_run, as_json) -> None:
    """Instala um kit de copiloto: cada doc pelo ``kernel.write_instance``,
    com todos os guards da porta."""
    docs = scan_kit(Path(path))
    if not docs:
        raise fail(f"nenhuma instância DNA encontrado em {path}")

    plano = [{"kind": d.kind, "name": d.name, "file": str(d.path)} for d in docs]
    if dry_run:
        if as_json:
            print_json({"plan": plano, "written": 0})
        else:
            click.secho(f"Plano do kit ({len(docs)} docs):", bold=True)
            for p in plano:
                click.echo(f"  {p['kind']}/{p['name']}  ←  {p['file']}")
        return

    # O funil de REGISTRO parseia com TypedKindDefinition e warn-skipa o que
    # não parseia — um Kind gravado mas imparseável fica escrito e nunca vira
    # porta, e o autor só descobre num log de outro processo. Validar AQUI,
    # com o MESMO parser e ANTES de qualquer escrita, transforma esse silêncio
    # em recusa na mão de quem pode corrigir. (Medido: o kit de vitrine
    # instalou sem `alias` e o wizard achou um Kind fantasma.)
    from dna.kernel.models import TypedKindDefinition

    for d in docs:
        if d.kind != "KindDefinition":
            continue
        try:
            TypedKindDefinition.from_raw(d.raw)
        except Exception as exc:  # noqa: BLE001 — recusa didática
            raise fail(
                f"{d.path.name}: KindDefinition {d.name!r} não registraria — {exc}"
            ) from exc

    kinds_inertes: list[str] = []
    written = 0
    with dna_session(scope) as s:
        for d in docs:
            raw = dict(d.raw)
            if d.kind == "KindDefinition":
                spec = dict(raw.get("spec") or {})
                if approve and not spec.get("approved_by"):
                    spec["approved_by"] = _operador()
                    raw["spec"] = spec
                elif not spec.get("approved_by"):
                    kinds_inertes.append(d.name)
            s.run(s.kernel.write_instance(scope, d.kind, d.name, raw))
            written += 1

    if as_json:
        print_json({"plan": plano, "written": written, "inert_kinds": kinds_inertes})
        return
    click.secho(f"Kit instalado: {written} instância(s).", fg="green", bold=True)
    for p in plano:
        click.echo(f"  {p['kind']}/{p['name']}")
    if kinds_inertes:
        click.secho(
            "\n⚠️  Kind(s) instalados INERTES (sem aprovação): "
            + ", ".join(kinds_inertes)
            + "\n    Aprove no portal — ou reinstale com --approve para o "
            "operador aprovar no ato (self-host).",
            fg="yellow",
        )


@copilot.command("provenance")
@click.option("--scope", default=None, help="Scope a ler (default: env / sole scope).")
@click.option("--tenant", default=None, help="Ler os copilotos deste tenant.")
@click.option("--json", "as_json", is_flag=True, help="Saída legível por máquina.")
def provenance(scope, tenant, as_json) -> None:
    """De onde veio cada copiloto — e quem ainda não disse.

    ``Copilot.created_by`` é a relação reflexiva que a `s-procedencia-do-agente`
    instalou: quem cria um copiloto é um copiloto. Ela é OPCIONAL, e a ausência
    dela é **não-respondida**, jamais "escrito à mão" — presumir seria fabricar
    um passado para os copilotos que nasceram antes do campo existir.
    """
    from dna_cli.copilot_provenance import provenance_report

    rel = provenance_report(scope=scope, tenant=tenant)
    if as_json:
        print_json(dict(rel))
        return

    if not rel["store_readable"]:
        # NUNCA "tudo respondido": a diferença entre "ninguém tem procedência"
        # e "não consegui perguntar" é a diferença entre um achado e um silêncio.
        click.secho(
            "⚠  o store não pôde ser lido — nada aqui é uma resposta sobre os "
            "copilotos, e nenhum deles foi contado como respondido.",
            fg="red",
        )
        return
    if rel.total == 0:
        click.echo("nenhum Copilot neste scope (nada a reportar, e nada afirmado).")
        return

    for nome in rel["answered"]:
        click.echo(f"  ✓ {nome}  (cadeia: {rel['depths'][nome]})")
    for nome in rel["dangling"]:
        # Dono diferente do `unanswered` logo abaixo, e por isso linha própria:
        # aqui alguém ESCREVEU um nome que não existe (ou o alvo foi apagado).
        click.secho(f"  ⚠ {nome}  — o criador declarado não existe", fg="yellow")
    for nome in rel["unanswered"]:
        click.echo(f"  · {nome}  — não-respondido")
    for nome in rel["cycles"]:
        click.secho(
            f"  ✖ {nome}  — a cadeia volta a si mesma (topologia impossível)",
            fg="red",
        )

    click.echo(
        f"\n{len(rel['answered'])}/{rel.total} com procedência declarada"
        f" · {len(rel['unanswered'])} não-respondido(s)"
        f" · {len(rel['dangling'])} pendurado(s)"
    )
    click.echo(
        "a cadeia inteira, elo a elo: "
        "dna graph refs Copilot <nome> --direction out --depth 5"
    )
