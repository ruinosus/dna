"""O que ESTE deployment consegue fazer — medido, e nunca declarado por tabela.

## A pergunta não é sobre o modelo, é sobre o DEPLOYMENT

MEDIDO em 02/08/2026, a mesma sonda em dois recursos Azure:

===================  ==========================  =========================
capacidade           `oai-dna-cloud`/gpt-5-mini  `hub-ai-foundry`/gpt-5.4
===================  ==========================  =========================
``input_file``       sim                         sim
``code_interpreter`` sim                         sim
``image_generation`` **não** (falta deployment)  sim
===================  ==========================  =========================

Uma tabela indexada por nome de modelo teria dado a MESMA resposta para as duas
colunas. ``image_generation`` depende de existir um deployment de imagem
*naquele recurso* — é fato do deployment, não do modelo.

## Por que não dá para perguntar ao provider

Tentado antes de desenhar, contra o endpoint real:

* ``GET /openai/v1/models`` responde — e lista **181 modelos**, que é o catálogo
  do que PODE ser implantado, não o que está. As capacidades são grossas
  (``chat_completion``, ``inference``): não dizem ``responses``, não distinguem
  imagem.
* ``GET /openai/v1/deployments`` → **404**. Não existe no plano de dados.
* ``GET /openai/v1/models/<deployment>`` → **404**. O catálogo é indexado por id
  de MODELO, não por nome de deployment.
* O plano de GERÊNCIA responde certo (``capabilities.responses: "true"``) e
  exige credencial de Azure — que um runtime não tem e não deveria ter.

Sobra tentar. E sai barato porque os erros do provider são **nominativos**: ele
responde ``The API deployment for this resource does not exist``, não um "falhou"
mudo. Preservar essa mensagem diz mais que qualquer tabela — ela nomeia o que
falta.

## ⚠️ Este módulo NÃO mede

Ele carrega o vocabulário, o resultado e a REGRA de compatibilidade. Medir é I/O
e mora em quem tem o cliente — o mesmo desenho de ``agent_grant``, que decide sem
tocar em banco, e pelo mesmo motivo: uma regra que precisa de rede para ser
exercitada é uma regra cujos casos difíceis ninguém roda.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

__all__ = [
    "CAPABILITIES",
    "CAPABILITY_INPUT_FILE",
    "CAPABILITY_CODE_INTERPRETER",
    "CAPABILITY_IMAGE_GENERATION",
    "CapabilityReport",
    "MissingCapability",
    "require_capabilities",
]

#: O modelo lê um ARQUIVO anexado à mensagem (`input_file` da Responses API).
CAPABILITY_INPUT_FILE = "input_file"

#: O modelo roda código num sandbox. É o caminho da PLANILHA — sem ele um
#: tabular grande só tem caminhos ruins: truncado pelo provider, ou truncado
#: por nós.
CAPABILITY_CODE_INTERPRETER = "code_interpreter"

#: O provider gera imagem. Depende de um deployment de imagem NO RECURSO, e é a
#: capacidade que mais varia entre deployments do mesmo modelo.
CAPABILITY_IMAGE_GENERATION = "image_generation"

#: O vocabulário fechado. Fechado de propósito: uma capacidade que ninguém sabe
#: medir não pode ser exigida, e um nome livre viraria exatamente isso — uma
#: exigência que nenhuma sonda consegue satisfazer nem refutar.
CAPABILITIES = frozenset(
    {
        CAPABILITY_INPUT_FILE,
        CAPABILITY_CODE_INTERPRETER,
        CAPABILITY_IMAGE_GENERATION,
    }
)


class MissingCapability(RuntimeError):
    """O deployment não faz o que este agente exige — e a mensagem diz o quê.

    Os campos existem separados do texto porque quem CAPTURA precisa saber quais
    capacidades faltaram sem fazer parse da mensagem — parse de texto de erro é
    acoplamento que quebra na primeira melhoria de redação. É a mesma forma do
    ``GrantRefused``.
    """

    def __init__(
        self,
        *,
        missing: Iterable[str],
        deployment: str,
        reasons: Mapping[str, str] | None = None,
    ) -> None:
        self.missing = sorted(set(missing))
        self.deployment = deployment
        self.reasons = dict(reasons or {})

        detalhes = "; ".join(
            f"{name}: {self.reasons[name]}" for name in self.missing if self.reasons.get(name)
        )
        super().__init__(
            f"o deployment {deployment!r} não oferece "
            + ", ".join(self.missing)
            + (f" — {detalhes}" if detalhes else "")
            + ". A medição é de `dna.runtime.capabilities`; rode a sonda de novo "
            "se o deployment mudou."
        )


@dataclass(frozen=True)
class CapabilityReport:
    """O que uma medição encontrou, com QUANDO e o PORQUÊ de cada ausência.

    ``measured_at`` não é adorno. Capacidade sem data é afirmação sem validade:
    o provider ganha formatos e perde deployments, e um relatório de três meses
    atrás pode estar descrevendo um recurso que já não existe. Quem lê precisa
    poder decidir se confia.
    """

    #: `(endpoint, deployment)` — a chave real. Só o nome do modelo não basta:
    #: o mesmo `gpt-5-mini` responde diferente em dois recursos.
    endpoint: str
    deployment: str
    #: Nome → suportado. Uma capacidade AUSENTE do mapa é diferente de `False`:
    #: ausente é "ninguém mediu", `False` é "mediu e não tem".
    supported: Mapping[str, bool]
    measured_at: str
    #: Nome → a mensagem do provider, quando ele deu uma. É o que torna a recusa
    #: acionável em vez de um "não suportado" que manda adivinhar.
    reasons: Mapping[str, str] = field(default_factory=dict)

    def has(self, capability: str) -> bool:
        """⚠️ Desconhecido conta como AUSENTE.

        A alternativa — otimismo — trocaria uma recusa clara no início por uma
        falha no meio do stream, que é onde este produto já aprendeu que dói
        mais. Ausência FECHA, como em todo portão deste SDK.
        """
        return bool(self.supported.get(capability, False))

    @property
    def missing(self) -> list[str]:
        return sorted(c for c in CAPABILITIES if not self.has(c))


def require_capabilities(
    report: CapabilityReport | None, required: Iterable[str]
) -> None:
    """Levanta ANTES de executar quando falta capacidade exigida.

    ## Por que antes, e não no meio

    A alternativa é o provider recusar durante a chamada — e aí a recusa chega
    como falha de stream, sem nomear o que faltava. É a mesma disciplina que a
    porta A2A já aplica ao recusar no boot: um processo que não sobe é mais
    honesto que um que sobe servindo o que não pode.

    ## ``report=None`` NÃO bloqueia

    Ninguém mediu ainda — e transformar "não sei" em "não pode" quebraria todo
    deployment que ainda não rodou a sonda, inclusive os que suportam tudo. A
    ausência de medição é um problema de operação, não uma negação de
    capacidade, e o lugar de resolvê-la é a sonda.

    A assimetria com ``CapabilityReport.has`` é deliberada: **dentro** de um
    relatório, desconhecido fecha (mediu-se o resto, aquilo não apareceu); **sem
    relatório nenhum**, não há medição a interpretar.
    """
    required_set = {c for c in required if c}
    if not required_set:
        return

    unknown = required_set - CAPABILITIES
    if unknown:
        raise ValueError(
            "capacidade desconhecida exigida: "
            + ", ".join(sorted(unknown))
            + f". Conhecidas: {', '.join(sorted(CAPABILITIES))}."
        )

    if report is None:
        return

    missing_ = [c for c in required_set if not report.has(c)]
    if missing_:
        raise MissingCapability(
            missing=missing_, deployment=report.deployment, reasons=report.reasons
        )


def report_from_probe(
    payload: Mapping[str, Any], *, measured_at: str
) -> CapabilityReport:
    """Converte a saída da sonda (`--json`) num relatório.

    A sonda vive no deployment (ela precisa de rede e de chave); o SDK só sabe
    LER o que ela produziu. É a mesma fronteira de sempre: a regra é daqui, o
    I/O é de quem tem o cliente.
    """
    caps = payload.get("capacidades") or {}
    supported, reasons = {}, {}
    for name, r in caps.items():
        if name not in CAPABILITIES:
            # Uma capacidade que este SDK não conhece é IGNORADA, não é erro: a
            # sonda pode ser mais nova que o runtime que lê o resultado.
            continue
        supported[name] = bool(r.get("ok"))
        if r.get("motivo"):
            reasons[name] = str(r["motivo"])
    return CapabilityReport(
        endpoint=str(payload.get("endpoint") or ""),
        deployment=str(payload.get("modelo") or ""),
        supported=supported,
        measured_at=measured_at,
        reasons=reasons,
    )
