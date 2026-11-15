"""Informe de validacion externa: que hace EMMA con personas sanas reales.

LA METRICA QUE IMPORTA
----------------------
**La tasa de falsa alarma sobre sujetos sanos.** Los 22 participantes de MMASH no
se deterioraron: eran adultos jovenes sanos viviendo un dia normal. Cualquier
hallazgo que EMMA produzca sobre ellos es, por construccion, una alarma que no
corresponde a un deterioro clinico.

Ese es el numero que hundio al Epic Sepsis Model —alertaba sobre el 18 % de todos
los ingresados— y es el que este informe mide en casa, antes de que lo mida otro.

DOS MATICES QUE EL INFORME RESPETA
----------------------------------
1. **Actividad fisica no es deterioro.** Un pulso de 128 lpm corriendo es
   fisiologia normal, no un hallazgo. MMASH declara las ventanas de actividad, asi
   que el informe separa la tasa en reposo de la tasa global. La tasa en reposo es
   la honesta.
2. **La linea base movil de EMMA esta dimensionada para misiones.** Ventana de 14
   dias y desfase de 12 h. MMASH dura 24 h, asi que con los parametros por
   defecto gran parte del dia no llega a tener base personal y cae al rango
   poblacional. El informe corre las dos configuraciones y las reporta por
   separado: mezclarlas ocultaria cual de las dos cosas se esta midiendo.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.analysis.baseline import BaselineEngine, Deviation
from app.analysis.episode import closing
from app.analysis.risk import RiskEngine, RiskLevel
from app.analysis.trend import Trend, trends_by_indicator
from app.ingest.codes import Domain, get
from app.ingest.fhir import VitalObservation
from app.validation.injection import Injection, inject, onset_after
from app.validation.mmash import MmashLoader, SubjectData

# Parametros de mision: los que usa EMMA en vuelo.
MISSION_WINDOW = dt.timedelta(days=14)
MISSION_LAG = dt.timedelta(hours=12)

# Parametros adaptados a un registro de 24 h. No son "los buenos": son los que
# permiten que un dataset de un dia ejercite la base personal en vez de caer
# siempre al rango poblacional.
SHORT_WINDOW = dt.timedelta(hours=4)
SHORT_LAG = dt.timedelta(minutes=30)

# El «ahora» del estado (`api.routes.CURRENT_WINDOW`), para la regla del episodio cerrado
# (§5.38.6). No se importa de alli: validar no carga la API ni el simulador. Una prueba los ata.
#
# La regla esta MEDIDA Y SIN ADOPTAR: `closed_episodes=False` por defecto, que es el motor que
# decide. Con `True` se mide como quedarian las dos metricas (invariante 5) si se adoptara.
STATE_WINDOW = dt.timedelta(days=2)


def _trends(
    observations: Sequence[VitalObservation],
    deviations: Sequence[Deviation],
    closed_episodes: bool,
) -> dict[str, Trend]:
    settle = closing(deviations, STATE_WINDOW) if closed_episodes else None
    return trends_by_indicator(observations, settle=settle)


@dataclass
class SubjectResult:
    subject: str
    observations: int
    beats: int
    artifact_rate: float
    deviations: int
    concerning: int
    concerning_at_rest: int
    observations_at_rest: int
    level: RiskLevel
    domains_flagged: tuple[str, ...] = ()

    @property
    def alarm_rate(self) -> float:
        return self.concerning / self.deviations if self.deviations else 0.0

    @property
    def alarm_rate_at_rest(self) -> float:
        if not self.observations_at_rest:
            return 0.0
        return self.concerning_at_rest / self.observations_at_rest


@dataclass
class ValidationReport:
    configuration: str
    subjects: list[SubjectResult] = field(default_factory=list)

    @property
    def total_deviations(self) -> int:
        return sum(item.deviations for item in self.subjects)

    @property
    def total_concerning(self) -> int:
        return sum(item.concerning for item in self.subjects)

    @property
    def alarm_rate(self) -> float:
        return self.total_concerning / self.total_deviations if self.total_deviations else 0.0

    @property
    def alarm_rate_at_rest(self) -> float:
        rest = sum(item.observations_at_rest for item in self.subjects)
        flagged = sum(item.concerning_at_rest for item in self.subjects)
        return flagged / rest if rest else 0.0

    @property
    def subjects_with_any_alert(self) -> int:
        return sum(1 for item in self.subjects if item.level is not RiskLevel.NOMINAL)

    @property
    def mean_artifact_rate(self) -> float:
        if not self.subjects:
            return 0.0
        return sum(item.artifact_rate for item in self.subjects) / len(self.subjects)

    def to_dict(self) -> dict[str, Any]:
        return {
            "configuration": self.configuration,
            "subjects": len(self.subjects),
            "observations": sum(item.observations for item in self.subjects),
            "beats": sum(item.beats for item in self.subjects),
            "mean_artifact_rate": round(self.mean_artifact_rate, 5),
            "deviations_evaluated": self.total_deviations,
            "concerning": self.total_concerning,
            "alarm_rate": round(self.alarm_rate, 5),
            "alarm_rate_at_rest": round(self.alarm_rate_at_rest, 5),
            "subjects_with_any_alert": self.subjects_with_any_alert,
        }

    def describe(self) -> str:
        lines = [
            f"Configuración: {self.configuration}",
            f"  sujetos                  {len(self.subjects)}",
            f"  latidos procesados       {sum(i.beats for i in self.subjects):,}",
            f"  artefactos rechazados    {self.mean_artifact_rate:.2%} (media por sujeto)",
            f"  lecturas evaluadas       {self.total_deviations:,}",
            f"  lecturas marcadas        {self.total_concerning:,}",
            f"  TASA DE ALARMA           {self.alarm_rate:.2%}",
            f"  TASA DE ALARMA EN REPOSO {self.alarm_rate_at_rest:.2%}",
            f"  sujetos con alguna alerta {self.subjects_with_any_alert}/{len(self.subjects)}",
        ]
        return "\n".join(lines)


def _is_at_rest(data: SubjectData, moment: dt.datetime) -> bool:
    return not data.is_active_at(moment)


def evaluate_subject(
    data: SubjectData,
    window: dt.timedelta,
    lag: dt.timedelta,
    closed_episodes: bool = False,
) -> SubjectResult:
    """Pasa el motor completo de EMMA por un sujeto real."""
    engine = BaselineEngine()
    deviations: Sequence[Deviation] = engine.evaluate_rolling(
        data.observations, window=window, lag=lag
    )

    # `Deviation.effective` dice cuando se tomo la lectura. Esto emparejaba por
    # (clave, valor) para reconstruirlo, con el comentario "`Deviation` no lleva
    # marca de tiempo": cierto cuando se escribio, falso desde que el estado de
    # tripulacion necesito seleccionar por tiempo. El 2,6 % de las desviaciones
    # acababan emparejadas con otra lectura distinta —las cifras se repiten
    # mucho— y la tasa en reposo salia del contexto equivocado.
    concerning_at_rest = 0
    observations_at_rest = 0
    for deviation in deviations:
        if _is_at_rest(data, deviation.effective):
            observations_at_rest += 1
            if deviation.is_concerning:
                concerning_at_rest += 1

    trends = _trends(data.observations, deviations, closed_episodes)
    status = RiskEngine().assess(data.subject, deviations, trends=trends)

    flagged = tuple(
        str(domain)
        for domain, risk in status.domains.items()
        if risk.level is not RiskLevel.NOMINAL
    )

    return SubjectResult(
        subject=data.subject,
        observations=len(data.observations),
        beats=data.beats,
        artifact_rate=data.artifact_rate,
        deviations=len(deviations),
        concerning=sum(1 for item in deviations if item.is_concerning),
        concerning_at_rest=concerning_at_rest,
        observations_at_rest=observations_at_rest,
        level=status.overall_level,
        domains_flagged=flagged,
    )


def run(
    loader: MmashLoader,
    window: dt.timedelta = MISSION_WINDOW,
    lag: dt.timedelta = MISSION_LAG,
    label: str = "parámetros de misión",
    limit: int | None = None,
    closed_episodes: bool = False,
) -> ValidationReport:
    """Ejecuta la validacion externa completa."""
    report = ValidationReport(configuration=label)
    subjects = loader.subjects()[:limit] if limit else loader.subjects()

    for name in subjects:
        data = loader.load(name)
        if not data.observations:
            continue
        report.subjects.append(
            evaluate_subject(data, window=window, lag=lag, closed_episodes=closed_episodes)
        )

    return report


def domain_breakdown(report: ValidationReport) -> dict[str, int]:
    """Cuantos sujetos han disparado alerta en cada dominio clinico."""
    counts = dict.fromkeys((str(domain) for domain in Domain), 0)
    for subject in report.subjects:
        for domain in subject.domains_flagged:
            counts[domain] += 1
    return counts


def indicator_coverage(data: SubjectData) -> dict[str, int]:
    """Que indicadores del catalogo llega a cubrir el dataset."""
    counts: dict[str, int] = {}
    for obs in data.observations:
        counts[obs.key] = counts.get(obs.key, 0) + 1
    return dict(sorted(counts.items()))


def uncovered_indicators(data: SubjectData) -> list[str]:
    """Indicadores del catalogo que MMASH no puede alimentar.

    Util para no afirmar que la validacion cubre mas de lo que cubre.
    """
    from app.ingest.codes import CATALOG

    covered = set(indicator_coverage(data))
    return sorted(key for key in CATALOG if key not in covered and get(key))


# --------------------------------------------------------------------------- #
# Sensibilidad: deterioros conocidos sobre fisiologia real
# --------------------------------------------------------------------------- #


@dataclass
class SensitivityResult:
    """Que ve el motor cuando el deterioro esta puesto a proposito.

    Se mide en **dos niveles**, y la distincion importa:

      `detected`         el deterioro produjo al menos una desviacion marcada.
      `flagged`          con el deterioro presente, el dominio acaba marcado.
                         Es la pregunta clinica: ¿lo ve la tripulacion?
      `escalated`        ademas, el nivel **subio** respecto al que ese sujeto
                         ya tenia. Mide poder discriminante, no deteccion.

    La diferencia importa. `escalated` penaliza a los sujetos que ya alertaban
    sin deterioro, asi que infravalora la deteccion: medido en la taquicardia
    sostenida, 12 sujetos pasaban de nominal a concern, 9 ya estaban en concern
    y solo 1 se escapaba. El escalado decia 55 %; los marcados eran 21 de 22.

    Medir solo desviaciones deja **ciega la deteccion por tendencia**: una
    taquicardia progresiva de +15 lpm/dia es justo lo que `trend.py` existe para
    captar, y no genera necesariamente desviaciones puntuales. Medir solo el
    primer nivel infravaloraba el sistema.
    """

    label: str
    subjects: int = 0
    detected: int = 0
    flagged: int = 0
    escalated: int = 0
    perturbed_readings: int = 0
    flagged_perturbed: int = 0

    @property
    def subject_detection_rate(self) -> float:
        """Sujetos en que el deterioro genero al menos una desviacion marcada."""
        return self.detected / self.subjects if self.subjects else 0.0

    @property
    def flagged_rate(self) -> float:
        """Sujetos cuyo dominio queda marcado con el deterioro presente."""
        return self.flagged / self.subjects if self.subjects else 0.0

    @property
    def escalation_rate(self) -> float:
        """Sujetos en que el deterioro llego a elevar el riesgo del dominio.

        Incluye la via de tendencia. Mide poder discriminante —el efecto del deterioro sobre el
        nivel que ese sujeto ya tenia—, no lo que ve la tripulacion: eso es `flagged_rate`
        (docstring de la clase).
        """
        return self.escalated / self.subjects if self.subjects else 0.0

    @property
    def reading_detection_rate(self) -> float:
        """Fraccion de lecturas perturbadas que quedan marcadas."""
        if not self.perturbed_readings:
            return 0.0
        return self.flagged_perturbed / self.perturbed_readings

    def describe(self) -> str:
        return (
            f"{self.label:<38} "
            f"desviación {self.subject_detection_rate:>4.0%}  "
            f"marcado {self.flagged}/{self.subjects} ({self.flagged_rate:>4.0%})  "
            f"escalado {self.escalation_rate:>4.0%}"
        )


def measure_sensitivity(
    loader: MmashLoader,
    build: Callable[[dt.datetime], Injection],
    label: str,
    window: dt.timedelta = MISSION_WINDOW,
    lag: dt.timedelta = MISSION_LAG,
    limit: int | None = None,
    closed_episodes: bool = False,
) -> SensitivityResult:
    """Inyecta un deterioro conocido en cada sujeto y mide si se detecta."""
    result = SensitivityResult(label=label)
    names = loader.subjects()[:limit] if limit else loader.subjects()

    for name in names:
        data = loader.load(name)
        if not data.observations:
            continue

        injection = build(onset_after(data.observations))
        series = inject(data.observations, injection)
        if not series.perturbed:
            continue

        result.subjects += 1
        result.perturbed_readings += series.perturbed

        # Identificar que desviaciones corresponden a lecturas perturbadas: por el momento de
        # la lectura (`Deviation.effective`), no por su valor. Emparejar por `(clave, valor)`
        # —el mismo fallo que se corrigio en la tasa en reposo de `evaluate_subject`— contaba
        # como acierto una lectura SANA, anterior al deterioro, marcada y con la misma cifra
        # que una perturbada: inflaba la sensibilidad con alarmas que no son del deterioro.
        affected = {(o.key, o.effective) for o in series.affected}
        deviations = BaselineEngine().evaluate_rolling(
            series.observations, window=window, lag=lag
        )

        hits = sum(
            1
            for item in deviations
            if item.is_concerning and (item.key, item.effective) in affected
        )
        result.flagged_perturbed += hits
        if hits:
            result.detected += 1

        # Nivel 2: el estado que llega a la tripulacion, incluida la via de
        # tendencia. Se compara contra el mismo sujeto SIN deterioro, porque
        # algunos ya alertan de por si: lo que se mide es el efecto de la
        # perturbacion, no el ruido de base.
        domain = get(injection.key).domain
        healthy = BaselineEngine().evaluate_rolling(data.observations, window=window, lag=lag)
        baseline_status = RiskEngine().assess(
            name,
            healthy,
            trends=_trends(data.observations, healthy, closed_episodes),
        )
        injected_status = RiskEngine().assess(
            name,
            deviations,
            trends=_trends(series.observations, deviations, closed_episodes),
        )
        order = [RiskLevel.NOMINAL, RiskLevel.WATCH, RiskLevel.CONCERN, RiskLevel.CRITICAL]
        if injected_status.domains[domain].level is not RiskLevel.NOMINAL:
            result.flagged += 1
        if order.index(injected_status.domains[domain].level) > order.index(
            baseline_status.domains[domain].level
        ):
            result.escalated += 1

    return result


def measure_all_sensitivity(
    loader: MmashLoader, limit: int | None = None, closed_episodes: bool = False
) -> list[SensitivityResult]:
    """Los deterioros de referencia, todos."""
    from app.validation.injection import REFERENCE_INJECTIONS

    return [
        measure_sensitivity(
            loader, build, label, limit=limit, closed_episodes=closed_episodes
        )
        for label, build in REFERENCE_INJECTIONS.items()
    ]
