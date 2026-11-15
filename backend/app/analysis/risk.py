"""Puntuacion de riesgo por dominio clinico.

Combina tres fuentes: desviaciones respecto a la linea base personal, tendencias
sostenidas, y el estado del entorno (radiacion, meteorologia espacial).

DECISION DE DISENO: el aislamiento modula el umbral
---------------------------------------------------
Cuando no hay consulta posible con el cirujano de vuelo, el mismo hallazgo
clinico merece escalarse antes. En tierra, ante un hallazgo ambiguo se espera y
se repite la medida porque la ayuda esta a minutos. A 22 minutos de ida y vuelta
esa espera tiene un coste distinto: si la situacion se deteriora, la ventana de
actuacion ya se cerro.

Por eso `assess()` toma la ventana de comunicaciones y aplica un factor de
aislamiento. No es un adorno: es la traduccion de la premisa del reto a logica.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache

from app.analysis.baseline import Deviation, Severity
from app.analysis.trend import Trend
from app.core import display, i18n
from app.environment.donki import Severity as SolarSeverity
from app.environment.donki import SolarEvent
from app.environment.ephemeris import CommsWindow
from app.ingest.codes import Domain, get

# Puntos que aporta cada desviacion segun su gravedad.
_SEVERITY_POINTS: dict[Severity, float] = {
    Severity.NONE: 0.0,
    Severity.MILD: 10.0,
    Severity.MODERATE: 25.0,
    Severity.SEVERE: 45.0,
}

# Lo que pesa una tendencia sostenida en mala direccion: la deriva lenta es
# precisamente lo que el ojo humano no ve en una mision larga.
#
# UNA DERIVA CONFIRMADA LLEGA SOLA A LA TRIPULACION: EXACTAMENTE EL UMBRAL DE
# WATCH. Valia 15, con un comentario que decia "pesa como una desviacion
# moderada" (25). Con 15, **una tendencia sola no llegaba nunca a la
# tripulacion** sin retardo de comunicaciones: una deriva de pulso que empezaba a
# mitad de mision, detectada por la via de tendencia en 20 de 20 casos, marcaba
# el dominio en 1 de 10. Solo el factor de aislamiento de Marte la hacia visible.
#
# Medido sin retardo, 15 frente a 20:
#
#   - Deriva tardia visible: 1/10 -> 10/10, a los 16, 12 y 9 dias (1x, 1,5x y 2x
#     el umbral). Desacondicionamiento marcado: 93 % -> 100 % de los dias.
#   - El coste, en tripulantes sanos: la adaptacion circadiana real de las
#     semanas 2-3 sale como WATCH (62,5 % de los dias 14-25), y en regimen
#     estable queda un 1,4 % de dias en WATCH. Es lo mismo que ya ocurria con el
#     retardo de Marte: orbita baja y Marte se comportan igual.
#
# 20 y no 25: en todo lo medido dan lo mismo, y 20 es el minimo que cumple lo
# que se decidio —que una deriva confirmada se vea— sin pesar mas de lo
# necesario al combinarse con otros hallazgos camino de CONCERN.
_TREND_POINTS = 20.0

# Multiplicador maximo por aislamiento, alcanzado con retardo alto.
_MAX_ISOLATION_FACTOR = 1.35

# Puntos que aporta consumir el 100 % del limite de dosis de carrera. Coincide
# con el umbral de CRITICAL a proposito.
_DOSE_LIMIT_POINTS = 70.0

# COMBINACION CON RENDIMIENTOS DECRECIENTES
#
# Sumar hallazgos linealmente hace que cuatro desviaciones leves (15 puntos cada
# una) alcancen el nivel critico. Eso es clinicamente falso y, peor, produce
# fatiga de alarma: la tripulacion aprende a ignorar el sistema justo antes de
# que importe.
#
# El hallazgo mas grave marca el suelo, y cada hallazgo adicional aporta la mitad
# que el anterior. Asi, muchos hallazgos leves elevan la vigilancia sin llegar a
# critico, y el nivel critico exige gravedad real, no acumulacion.
_ADDITIONAL_FINDING_DECAY = 0.5


# EL MAXIMO DE MUCHAS MUESTRAS RUIDOSAS NO ES EVIDENCIA
#
# Tomar el z-score mas extremo de un indicador a lo largo de la mision garantiza
# falsos hallazgos: el maximo de 160 muestras gaussianas ronda |z| = 3 por puro
# azar, asi que **todos** los indicadores acabarian mostrando una desviacion
# moderada aunque no ocurra nada.
#
# En su lugar se toma el percentil 90: la lectura que el 10 % mas extremo supera.
# Con pocas muestras equivale al maximo (conserva sensibilidad ante un evento
# agudo), y con muchas resiste tanto los artefactos aislados como la inflacion
# por valor extremo.
_FINDING_PERCENTILE = 0.90

# COMPARACIONES MULTIPLES: LA MAGNITUD AISLADA NO ES EVIDENCIA
#
# Se vigilan 24 indicadores a la vez. Con ~8 lecturas recientes de cada uno son
# ~190 contrastes por evaluacion: a 2 sigma se esperan unas 9 desviaciones
# espurias, y alguna llegara a 3 sigma. Un sistema que alerte con eso alarma en
# cada ciclo aunque no ocurra nada.
#
# Por eso un hallazgo exige **persistencia**: que se desvie al menos esta
# fraccion de las lecturas recientes. El ruido no persiste; un problema si.
_PERSISTENCE_FRACTION = 0.30

# Red de seguridad: un hallazgo **grave** se reporta aunque sea aislado. La
# persistencia protege del ruido, pero no debe volver ciego al sistema ante un
# evento agudo real.
#
# ESTO ESTABA ROTO. La red se condicionaba a |z| >= 6, y cuando la gravedad paso
# a decidirse por cuantiles empiricos el z-score dejo de gobernarla: un hallazgo
# grave con z moderado ya no la disparaba. El episodio agudo inyectado detectaba
# el 90 % de las desviaciones y **escalaba el 0 %** de las veces, porque sus ~25
# lecturas en una ventana de 280 no llegaban al 30 % de persistencia y la red no
# lo rescataba.
#
# Ahora la red mira la gravedad, que es lo que el resto del motor usa.
_ALWAYS_REPORT_SEVERITY = Severity.SEVERE

# ...pero UNA SOLA LECTURA EXTREMA TAMPOCO ES EVIDENCIA.
#
# La primera version de la red dejaba pasar un unico hallazgo grave aislado, y
# eso llevaba a **9 de 22 sujetos sanos al nivel CONCERN**, todos por un solo
# hallazgo con 0,4 % de persistencia: una lectura de unas 250.
#
# Asi que la red exime del **porcentaje** de persistencia, no de la evidencia: un
# evento agudo real produce una rafaga de lecturas graves, no una suelta.
#
# CUANTAS LECTURAS HACEN UNA RAFAGA DEPENDE DE CUANTAS HAY.
# ---------------------------------------------------------
# Esto fue una constante, `3`. Era **la respuesta para la ventana de MMASH**,
# congelada, y fallaba a los dos lados de ella:
#
#   - Con pocas lecturas, demasiado estricta. A 12 muestras/dia la ventana
#     actual tiene 25 lecturas de pulso. Medido: una arritmia simulada con **2
#     lecturas graves en ventana quedaba en "nominal"**, y la misma arritmia a
#     24 muestras/dia, con 3 entre 49, se detectaba. El motor perdia el evento
#     al tener menos datos, no por tener menos evidencia.
#   - Con muchas, demasiado laxa. Un wearable continuo da cientos o miles de
#     lecturas por ventana, y el azar alcanza 3 graves casi seguro.
#
# Ahora se exige el menor numero de lecturas graves que, dadas n lecturas, seria
# tan sorprendente en una persona sana como lo es 3 en la ventana validada.
#
# QUE SUCESO SE CUENTA — Y EL MODELO EQUIVOCADO QUE SE USO PRIMERO
# ----------------------------------------------------------------
# La primera version modelaba cada lectura grave como un suceso de percentil
# (p = 0,001 por cola, el corte p99,9). **En ningun dato disponible ocurre uno
# solo**: declarar "grave" por cuantil exige 1000 muestras de base, y la mayor
# base de MMASH tiene 116; la del simulador a 24/dia, 336. Todas las lecturas
# graves medidas son **cruces de limite de peligro**, cuya tasa en gente sana es
# otra. Lo detecto una revision estadistica independiente.
#
# Ahora se usa la tasa medida de ese suceso: `_HEALTHY_SEVERE_RATE`, las
# lecturas graves por lectura en los 22 sanos de MMASH, todas de pulso. Una
# prueba externa la vuelve a medir y falla si se desvia: el numero sigue a los
# datos, no a la memoria de quien lo escribio. **Y ya lo hizo**: era 0,49 % (30
# de 6132) hasta que el hallazgo 28 dejo de leer "cero pasos con el acelerometro
# quitado" como reposo; sin esas lecturas mal etiquetadas, 0,34 %.
#
# Dos cautelas que no se esconden:
#
#   - Los cruces se concentran: un sujeto aporta 18 de los 30 y 14 de 22 no
#     tienen ninguno. Una binomial con la tasa agregada no describe a ninguna
#     persona concreta; da la forma de la escala, no una probabilidad calibrada.
#   - La tasa es del pulso, el unico indicador de MMASH con cruces. Aplicarla a
#     los demas es un supuesto. Y la via de percentil sigue **sin validar**:
#     solo se activa con wearables de alta cadencia, que ningun dataset de los
#     disponibles ejercita. Su tasa nominal (~0,2-0,4 % por lectura con bases de
#     1000-2000) queda por debajo de la medida, asi que esta regla es con ella
#     mas exigente, no menos — mientras la autocorrelacion no lo invierta.
_HEALTHY_SEVERE_RATE = 0.0034

# El ancla. En el modelo de arriba, la configuracion validada —k = 3 sobre las
# ventanas que MMASH produce de verdad, 249-303 lecturas, medidas instrumentando
# esta funcion— equivale a una sorpresa entre el 18,6 % y el 34,4 %. Cualquier
# valor de ese intervalo reproduce exactamente lo validado.
#
# **No es una tasa de falsa alarma**: la binomial agregada la sobreestima porque
# los cruces se concentran en pocas personas. La real se mide —2 de 22 sanos
# marcados— y la vigila la validacion externa.
#
# Historial, porque los dos intentos anteriores los cazo esa validacion:
#
#   - 0,005 sobre el modelo de percentil, razonando con una sola cola: el pulso
#     pasaba a exigir 4 y la taquicardia sostenida inyectada cayo al **68 %** de
#     sujetos marcados, bajo el suelo del 75 %, sin ganar nada en falsa alarma.
#   - 0,02, tomando "n = 250-280" de un comentario anterior que nadie habia
#     medido: las ventanas llegan a 303, cuatro exigian 4 y la sostenida perdia
#     un sujeto (82 % -> 77 %).
#
# El ancla se reajusta cuando la tasa cambia, porque lo que se conserva es el
# **comportamiento** validado, no el numero: con 0,49 % el intervalo era
# [18,6 %, 34,4 %) y valia 0,25; con la tasa de 0,34 % es [8,6 %, 20,8 %) y vale
# 0,15. La tabla de umbrales apenas se mueve —2 con ventanas cortas, 3 en la de
# MMASH, 4 con 576 lecturas—, que es justo lo que se espera de un ancla.
_BURST_SURPRISE = 0.15

# Nunca una sola. Un cruce aislado de un limite de peligro es con mas
# probabilidad un artefacto de sensor que un evento.
_MIN_BURST = 2


@lru_cache(maxsize=4096)
def min_severe_readings(readings: int) -> int:
    """Lecturas graves necesarias para que no sean atribuibles al azar.

    Menor k >= `_MIN_BURST` tal que P(X >= k) <= `_BURST_SURPRISE`, con
    X ~ Binomial(`readings`, `_HEALTHY_SEVERE_RATE`). Si ni todas las lecturas
    bastarian, devuelve un valor mayor que `readings`: no hay rafaga posible.

    La distribucion se acumula en escala logaritmica. Con `math.comb` el calculo
    desbordaba el float a partir de ~22 000 lecturas, y un wearable a 1 Hz llega
    ahi en unas 6 h de ventana: `/api/status` habria respondido 500 justo con el
    dispositivo que mas datos da.
    """
    rate = _HEALTHY_SEVERE_RATE
    log_pmf = readings * math.log1p(-rate)  # log P(X = 0)
    step = math.log(rate) - math.log1p(-rate)
    below = 0.0  # P(X < k)
    for k in range(1, readings + 1):
        below += math.exp(log_pmf)  # suma P(X = k - 1)
        if k >= _MIN_BURST and 1.0 - below <= _BURST_SURPRISE:
            return k
        log_pmf += math.log(readings - k + 1) - math.log(k) + step  # -> log P(X = k)
    return max(_MIN_BURST, readings + 1)


def representative_deviation(deviations: Sequence[Deviation]) -> Deviation | None:
    """La lectura que resume el estado de un indicador, no la mas llamativa.

    Devuelve None si las desviaciones no son persistentes y ninguna alcanza el
    umbral de valor extremo: en ese caso lo que hay es ruido.
    """
    if not deviations:
        return None

    concerning = [item for item in deviations if item.is_concerning]
    if not concerning:
        return None

    ordered = sorted(concerning, key=lambda item: abs(item.z_score), reverse=True)

    # Red de seguridad ante un evento agudo real: una rafaga de lecturas graves
    # cuenta aunque no alcance el porcentaje de persistencia, porque un episodio
    # corto es una fraccion pequena de una ventana larga.
    severe = [item for item in concerning if item.severity is _ALWAYS_REPORT_SEVERITY]
    if len(severe) >= min_severe_readings(len(deviations)):
        return max(severe, key=lambda item: abs(item.z_score))

    if len(concerning) / len(deviations) < _PERSISTENCE_FRACTION:
        return None

    index = int(len(deviations) * (1.0 - _FINDING_PERCENTILE))
    return ordered[index] if index < len(ordered) else ordered[-1]


def combine_findings(points: Sequence[float]) -> float:
    """Agrega las puntuaciones de varios hallazgos con peso decreciente."""
    if not points:
        return 0.0
    ordered = sorted(points, reverse=True)
    total = 0.0
    weight = 1.0
    for value in ordered:
        total += value * weight
        weight *= _ADDITIONAL_FINDING_DECAY
    return total


class RiskLevel(StrEnum):
    NOMINAL = "nominal"
    WATCH = "watch"
    CONCERN = "concern"
    CRITICAL = "critical"

    @property
    def display(self) -> str:
        """Como se nombra ante la tripulacion; el valor es la clave de la API."""
        return i18n.tr(_LEVEL_DISPLAY[self], _LEVEL_DISPLAY_EN[self])

    @property
    def label(self) -> str:
        """La misma palabra como rotulo suelto (insignia, cabecera): con mayuscula inicial."""
        return self.display.capitalize()


# UNA PALABRA POR NIVEL, Y LA DICE EL BACKEND.
#
# CONCERN se llamaba «preocupación» aqui (resumenes, motivos, cronica) y «Precaución» en la
# insignia de la interfaz, que tenia su propia tabla: el mismo nivel con dos nombres segun donde
# se leyera. Decision del usuario (2026-10-09): es «precaución», la palabra de la clase de
# alerta del Apendice F (Caution). La interfaz ya no la escribe: la recibe (`wording.py`).
# Cambiar una palabra de aqui no mueve ningun nivel: solo como se nombra.
_LEVEL_DISPLAY: dict[RiskLevel, str] = {
    RiskLevel.NOMINAL: "nominal",
    RiskLevel.WATCH: "vigilancia",
    RiskLevel.CONCERN: "precaución",
    RiskLevel.CRITICAL: "crítico",
}

# Las mismas palabras en inglés (`core/i18n.py`): el vocabulario común de toda la interfaz. Va en
# una tabla aparte y no en el registro de `i18n.en`: «precaución» puede nombrar otra cosa en otro
# módulo (la clase de alerta del Apéndice F), y aquí es el nivel CONCERN.
_LEVEL_DISPLAY_EN: dict[RiskLevel, str] = {
    RiskLevel.NOMINAL: "nominal",
    RiskLevel.WATCH: "watch",
    RiskLevel.CONCERN: "concern",
    RiskLevel.CRITICAL: "critical",
}


_LEVEL_THRESHOLDS: tuple[tuple[float, RiskLevel], ...] = (
    (70.0, RiskLevel.CRITICAL),
    (45.0, RiskLevel.CONCERN),
    (20.0, RiskLevel.WATCH),
)


def level_for(score: float) -> RiskLevel:
    for threshold, level in _LEVEL_THRESHOLDS:
        if score >= threshold:
            return level
    return RiskLevel.NOMINAL


def isolation_factor(comms: CommsWindow | None) -> float:
    """Cuanto se amplifica el riesgo por no poder consultar con la Tierra.

    Crece con el retardo y satura: pasado cierto punto, mas retardo no cambia la
    conducta — ya estas completamente solo.
    """
    if comms is None or not comms.autonomy_required:
        return 1.0
    # Satura alrededor de los 40 min de ida y vuelta.
    progress = min(comms.round_trip_minutes / 40.0, 1.0)
    return 1.0 + (_MAX_ISOLATION_FACTOR - 1.0) * progress


@dataclass(frozen=True, slots=True)
class DomainRisk:
    domain: Domain
    score: float
    level: RiskLevel
    drivers: tuple[str, ...]

    def describe(self) -> str:
        # El inglés del nombre del dominio es de quien lo define (`ingest/codes.py`): si lo
        # registra con `i18n.en`, aquí, donde se sirve, sale; si no, queda como está.
        domain = i18n.loc(self.domain.display)
        if not self.drivers:
            return f"{domain}: nominal"
        return f"{domain} ({self.level.display}): " + "; ".join(self.drivers)


@dataclass(frozen=True, slots=True)
class CrewHealthStatus:
    """Estado completo de un tripulante en un instante."""

    subject: str
    domains: dict[Domain, DomainRisk]
    comms: CommsWindow | None
    isolation_factor: float
    cumulative_dose_msv: float
    dose_limit_msv: float
    active_solar_event: SolarEvent | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def overall_level(self) -> RiskLevel:
        """El peor dominio manda: un riesgo critico no se promedia con dos nominales."""
        if not self.domains:
            return RiskLevel.NOMINAL
        order = [RiskLevel.NOMINAL, RiskLevel.WATCH, RiskLevel.CONCERN, RiskLevel.CRITICAL]
        return max((risk.level for risk in self.domains.values()), key=order.index)

    @property
    def dose_fraction(self) -> float:
        if self.dose_limit_msv <= 0:
            return 0.0
        return self.cumulative_dose_msv / self.dose_limit_msv

    def domains_needing_attention(self) -> list[DomainRisk]:
        return sorted(
            (risk for risk in self.domains.values() if risk.level is not RiskLevel.NOMINAL),
            key=lambda risk: risk.score,
            reverse=True,
        )


class RiskEngine:
    """Convierte desviaciones, tendencias y entorno en riesgo por dominio."""

    def __init__(self, dose_limit_msv: float = 600.0) -> None:
        self.dose_limit_msv = dose_limit_msv

    def assess(
        self,
        subject: str,
        deviations: Sequence[Deviation],
        trends: dict[str, Trend] | None = None,
        comms: CommsWindow | None = None,
        solar_events: Iterable[SolarEvent] | None = None,
        cumulative_dose_msv: float = 0.0,
    ) -> CrewHealthStatus:
        # UN INFORME ES DE UNA PERSONA. NO SE MEZCLAN TRIPULANTES.
        #
        # EMMA vigila a una tripulacion, no a un individuo. Sin esta comprobacion,
        # pasar por error lecturas de dos personas produce un informe que atribuye
        # a una los hallazgos de la otra, y lo hace **en silencio**: el resultado
        # es plausible, esta bien formado y es clinicamente falso. Es el tipo de
        # fallo que no se detecta leyendo la salida.
        #
        # El coste de comprobarlo es una pasada sobre la lista. El coste de no
        # hacerlo es tratar a la persona equivocada.
        intruders = {dev.subject for dev in deviations if dev.subject != subject}
        if intruders:
            raise ValueError(
                f"informe de {subject!r} con lecturas de "
                f"{', '.join(sorted(repr(other) for other in intruders))}"
            )

        trends = trends or {}
        factor = isolation_factor(comms)

        findings: dict[Domain, list[float]] = {domain: [] for domain in Domain}
        drivers: dict[Domain, list[str]] = {domain: [] for domain in Domain}

        # Un indicador aporta un unico hallazgo, por muchas lecturas que tenga:
        # cien lecturas altas del pulso siguen siendo un hallazgo, no cien.
        by_key: dict[str, list[Deviation]] = {}
        for deviation in deviations:
            by_key.setdefault(deviation.key, []).append(deviation)

        representative = {
            key: found
            for key, series in by_key.items()
            if (found := representative_deviation(series)) is not None
        }

        for deviation in representative.values():
            if not deviation.is_concerning:
                continue
            domain = get(deviation.key).domain
            findings[domain].append(_SEVERITY_POINTS[deviation.severity])
            drivers[domain].append(deviation.describe())

        for trend in trends.values():
            if not trend.is_concerning:
                continue
            domain = get(trend.key).domain
            findings[domain].append(_TREND_POINTS)
            drivers[domain].append(trend.describe())

        active_event = self._active_solar_event(solar_events)
        notes: list[str] = []

        if active_event is not None:
            findings[Domain.RADIATION].append(
                45.0 if active_event.severity is SolarSeverity.SEVERE else 30.0
            )
            drivers[Domain.RADIATION].append(i18n.tr(
                f"evento solar activo: {active_event.event_type} {active_event.event_id}",
                f"active solar event: {active_event.event_type} {active_event.event_id}",
            ))

        dose_fraction = cumulative_dose_msv / self.dose_limit_msv if self.dose_limit_msv else 0.0
        if dose_fraction > 0:
            # Escalado calibrado para que alcanzar el 100 % del limite de carrera
            # entre por si solo en CRITICAL: rebasarlo termina una mision, no es
            # un motivo de vigilancia.
            findings[Domain.RADIATION].append(
                min(dose_fraction * _DOSE_LIMIT_POINTS, 100.0)
            )
            drivers[Domain.RADIATION].append(i18n.tr(
                f"dosis acumulada {display.number(cumulative_dose_msv, 1)} mSv "
                f"({display.percent(dose_fraction, 0)} del límite de carrera)",
                f"cumulative dose {display.number(cumulative_dose_msv, 1)} mSv "
                f"({display.percent(dose_fraction, 0)} of the career limit)",
            ))

        if factor > 1.0 and comms is not None:
            notes.append(i18n.tr(
                f"Umbrales ajustados por aislamiento: respuesta de Tierra a "
                f"{display.number(comms.round_trip_minutes, 0)} min "
                f"(factor {display.number(factor, 2)})",
                f"Thresholds adjusted for isolation: a reply from Earth takes "
                f"{display.number(comms.round_trip_minutes, 0)} min "
                f"(factor {display.number(factor, 2)})",
            ))

        domains = {}
        for domain in Domain:
            # El factor de aislamiento amplifica el riesgo clinico, no el
            # ambiental: la distancia no cambia la dosis, cambia lo que cuesta
            # equivocarse al interpretarla.
            raw = combine_findings(findings[domain])
            adjusted = raw * factor if domain is not Domain.RADIATION else raw
            final = min(round(adjusted, 1), 100.0)
            domains[domain] = DomainRisk(
                domain=domain,
                score=final,
                level=level_for(final),
                drivers=tuple(drivers[domain]),
            )

        return CrewHealthStatus(
            subject=subject,
            domains=domains,
            comms=comms,
            isolation_factor=factor,
            cumulative_dose_msv=cumulative_dose_msv,
            dose_limit_msv=self.dose_limit_msv,
            active_solar_event=active_event,
            notes=tuple(notes),
        )

    @staticmethod
    def _active_solar_event(events: Iterable[SolarEvent] | None) -> SolarEvent | None:
        return active_solar_event(events)


def active_solar_event(events: Iterable[SolarEvent] | None) -> SolarEvent | None:
    """El evento solar que el estado da por activo: el más reciente de gravedad alta o severa.

    Función pura, fuera del motor, para que quien necesite el mismo evento sin evaluar el riesgo
    (las rutinas durante un evento, `app/routines.py`) use este criterio y no una copia.
    """
    if not events:
        return None
    relevant = [
        event
        for event in events
        if event.severity in {SolarSeverity.HIGH, SolarSeverity.SEVERE}
    ]
    return max(relevant, key=lambda event: event.time) if relevant else None
