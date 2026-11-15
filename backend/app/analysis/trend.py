"""Deteccion de tendencia: separar deriva sostenida de ruido.

Una sola lectura fuera de rango puede ser un artefacto. Lo que importa en una
mision larga es la **deriva sostenida**: el pulso en reposo que sube dos lpm por
semana durante dos meses es un hallazgo clinico, aunque ninguna lectura aislada
haya salido nunca del rango normal.

Se ajusta una recta por minimos cuadrados y se contrasta la pendiente contra su
propio error tipico. Sin esa prueba, cualquier serie ruidosa "tiene pendiente" y
el sistema alerta de todo.
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.analysis.cycle_phase import PhaseOffset, without_phase
from app.core import display, i18n
from app.ingest.codes import ReferenceBasis, get
from app.ingest.fhir import Context, VitalObservation

# Muestras minimas para intentar una tendencia. Con menos, la pendiente no
# significa nada.
MIN_POINTS = 8

# NO SE PUEDE LLAMAR TENDENCIA A UN TROZO DE CICLO CIRCADIANO.
#
# Ajustar una recta sobre menos de un dia no mide deriva: mide en que fase del
# ritmo diario empezo y acabo la ventana. Medido en MMASH sobre un sujeto **sano
# y sin deterioro**, el ajuste de 24 h daba una pendiente de **-92,9 lpm por
# semana**, significativa y por encima del umbral de relevancia. Nadie pierde 93
# lpm de pulso a la semana: la serie simplemente empezaba a las 10:00 y terminaba
# a las 09:45 del dia siguiente, recogiendo la rama descendente del ciclo.
#
# Peor aun: esa pendiente espuria **enmascaraba** la deriva ascendente de un
# deterioro inyectado, porque iba en sentido contrario.
#
# Se exigen varios ciclos completos para que la fase circadiana se promedie.
MIN_SPAN_DAYS = 3.0

# |t| por encima del cual se considera que la pendiente no es ruido. 2,0 es
# aproximadamente el 95 % de confianza para muestras de este tamano.
T_SIGNIFICANCE = 2.0

# SIGNIFICANCIA ESTADISTICA != SIGNIFICANCIA CLINICA.
#
# Con unos cientos de muestras, el contraste de la pendiente declara "real"
# cualquier deriva minuscula. Una caida de eficiencia del sueno de 0,37 % por
# semana es perfectamente detectable y clinicamente irrelevante. Alertar de eso
# en mision nominal es la via mas rapida a que la tripulacion ignore el sistema.
#
# Por eso una tendencia solo preocupa si ademas proyecta un cambio apreciable en
# un horizonte con sentido operativo: 15 % del rango de referencia a cuatro
# semanas vista.
RELEVANCE_HORIZON_WEEKS = 4.0
RELEVANCE_FRACTION_OF_RANGE = 0.15
# Para indicadores sin rango de referencia, el criterio es relativo a su nivel.
RELEVANCE_FRACTION_OF_LEVEL = 0.10

# LA PREGUNTA ERA LA EQUIVOCADA: "¿LA PENDIENTE ES DISTINTA DE CERO?"
# ------------------------------------------------------------------
# Se contrastaba la pendiente contra cero y, aparte, se exigia que su estimacion
# puntual superase el umbral de relevancia. Asi, una deriva real pero pequena
# —el nominal del simulador tiene cortisol y caida ortostatica al 67 % del
# umbral— solo necesitaba que el ruido pusiera el resto. Medido en 50
# tripulantes sanos simulados, dia a dia por el camino desplegado: WATCH el
# **7,4 %** de los dias, 0,74 episodios por tripulante-mes, **todo** de esta via.
#
# Ahora se contrasta contra el umbral: preocupa la deriva que, con confianza,
# es **mayor que lo clinicamente relevante**, no la que es distinta de cero.
# Mismo |t| >= 2, sobre |pendiente| - umbral. Mismos 50 tripulantes: WATCH el
# 0,4 % de los dias —sin factor de aislamiento; ver hallazgo 27—. Y deberia
# amortiguar la autocorrelacion de los wearables reales, que una revision
# estimo en x2,2 sobre el t del pulso de MMASH a 5 min: el umbral va en
# unidades absolutas, asi que un error tipico subestimado rebajaria la
# exigencia a "umbral + 0,9 errores", no a "0,9 errores". Estimado, **no
# medido** con un wearable real.
#
# El coste, por construccion: una deriva **por debajo** del umbral ya no se
# marca, aunque sea real. Es lo que el umbral declara.

# UNA RECTA SOBRE TODA LA MISION NO VE LO QUE EMPIEZA TARDE.
# ----------------------------------------------------------
# `/api/status` ajustaba sobre toda la historia. Dos defectos, medidos con una
# deriva de pulso inyectada a partir del dia 35 —escalada por el ritmo
# circadiano, como la produce el simulador: dormido, el pulso deriva menos—:
#
#   - A 1x el umbral **no se detectaba nunca** (0 de 20); a 2x, a los 22 dias.
#     La recta de toda la mision diluye un cambio reciente con semanas estables.
#   - Una deriva ya estabilizada se seguia marcando: el desfase circadiano
#     nominal se asienta el dia 14 y la recta de toda la historia lo marcaba
#     hasta el dia 28 (mediana de 30 tripulantes; maximo, 36). Con 21 dias,
#     hasta el 22. Se acorta, no desaparece: mientras la ventana contenga la
#     rampa, la recta la ve. Se intento vetarlo exigiendo que el tercio mas
#     reciente siga derivando: sin mas condiciones veta derivas reales cuando hay
#     pocos datos; exigiendo potencia, no veta nada. No se aplico (hallazgo 27).
#
# Acortar la ventana SIN cambiar el contraste empeoraba: 14 dias daban un
# dominio marcado sin motivo el 28,9 % de los dias (12,0 % con toda la
# historia), porque las pendientes de ruido crecen como W^-3/2 y saltaban el
# filtro de relevancia. Con el contraste contra el umbral, 21 dias detectan la
# deriva tardia en 20 de 20 casos —a 1x el umbral en 16 dias, a 2x en 10— sin
# marcar nunca antes de su inicio.
#
# 21 y no 28, y el precio se paga. Con 28 dias la alerta frente a una deriva en
# curso es mas continua —el desacondicionamiento queda marcado el 98 % de los
# dias, frente al 93 %— pero la deriva tardia tarda 3-4 dias mas en verse (20,
# 15 y 13 dias a 1x, 1,5x y 2x el umbral). En el nominal no hay diferencia. Se
# elige ver antes lo nuevo: con 22 minutos de retardo, ese es el problema que
# la tripulacion no puede delegar.
TREND_WINDOW = dt.timedelta(days=21)


class Direction(StrEnum):
    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"


@dataclass(frozen=True, slots=True)
class Trend:
    """Deriva de un indicador a lo largo de una ventana."""

    key: str
    slope_per_day: float
    t_statistic: float
    points: int
    span_days: float
    direction: Direction
    significant: bool
    mean_value: float
    # Error tipico de la pendiente, por dia. 0 si el ajuste es perfecto.
    standard_error: float = 0.0
    # La recta contiene un episodio que ya ceso (`analysis/episode.py`, §5.38.6): se describe
    # en pasado y no preocupa. Solo lo marca un `settle` de `trends_by_indicator`, y la regla
    # esta medida y SIN ADOPTAR: ningun camino que decide lo pasa (solo la sombra y la medida).
    closed_episode: bool = False

    @property
    def slope_per_week(self) -> float:
        return self.slope_per_day * 7.0

    @property
    def projected_change(self) -> float:
        """Cambio que la deriva acumularia en el horizonte de relevancia."""
        return self.slope_per_week * RELEVANCE_HORIZON_WEEKS

    @property
    def relevance_threshold(self) -> float:
        """Cambio minimo para que la deriva importe clinicamente."""
        code = get(self.key)
        if code.reference_low is not None and code.reference_high is not None:
            span = code.reference_high - code.reference_low
            if span > 0:
                return span * RELEVANCE_FRACTION_OF_RANGE
        return abs(self.mean_value) * RELEVANCE_FRACTION_OF_LEVEL

    @property
    def clinically_relevant(self) -> bool:
        """La estimacion puntual alcanza el umbral. Descriptivo: no decide."""
        return abs(self.projected_change) >= self.relevance_threshold

    @property
    def threshold_contrast(self) -> float:
        """(|pendiente| - umbral) / error tipico: cuanto supera el umbral clinico."""
        threshold_per_day = self.relevance_threshold / (RELEVANCE_HORIZON_WEEKS * 7.0)
        excess = abs(self.slope_per_day) - threshold_per_day
        if self.standard_error <= 0:
            return math.inf if excess >= 0 else -math.inf
        return excess / self.standard_error

    @property
    def confidently_relevant(self) -> bool:
        """La deriva supera el umbral clinico con confianza, no solo en promedio."""
        return self.threshold_contrast >= T_SIGNIFICANCE

    @property
    def is_concerning(self) -> bool:
        """Preocupa si es real, apreciable, y va en la direccion mala. Las tres."""
        if self.closed_episode:
            return False
        if not self.significant or self.direction is Direction.STABLE:
            return False
        if not self.confidently_relevant:
            return False
        code = get(self.key)
        # UNA GUIA NO ES UN UMBRAL DE ALARMA, TAMPOCO POR LA VIA DE TENDENCIA.
        # El umbral de relevancia sale del rango de referencia, y el de una guia
        # dice "convendria estar aqui", no "aqui esta la gente sana" (ver
        # `ReferenceBasis`). Se aplicaba a las desviaciones y no a las
        # tendencias: mientras una tendencia sola no llegaba a WATCH no se
        # notaba. Cuando llego (`risk._TREND_POINTS` = 20), el ejercicio
        # resistivo —unica guia del catalogo— empezo a marcar el dominio oseo
        # con un umbral derivado de una recomendacion. Se describe; no alerta.
        if code.reference_basis is ReferenceBasis.GUIDELINE:
            return False
        if code.concerning == "both":
            return True
        return (code.concerning == "high" and self.direction is Direction.RISING) or (
            code.concerning == "low" and self.direction is Direction.FALLING
        )

    def describe(self) -> str:
        if i18n.current() == "en":
            return self._describe_en()
        code = get(self.key)
        if not self.significant:
            return f"{code.display_es}: sin tendencia detectable"
        if self.closed_episode:
            # Sin la pendiente: la recta de la ventana no mide el episodio (ni su tamaño ni su
            # duracion), y «subió tanto por semana durante 21 días» contradice «ha vuelto».
            sense = "por encima" if self.direction is Direction.RISING else "por debajo"
            return (
                f"{code.display_es}: episodio cerrado; estuvo {sense} de su rango personal "
                f"dentro de los últimos {self.span_days:.0f} días y ha vuelto a su nivel previo, "
                f"no es una deriva en curso"
            )
        sense = "subiendo" if self.direction is Direction.RISING else "bajando"
        detail = (
            f"{code.display_es}: {sense} "
            f"{display.rate_per_week(self.key, abs(self.slope_per_week), code.unit)} "
            f"a lo largo de {self.span_days:.0f} días"
        )
        if not self.clinically_relevant:
            return f"{detail} (deriva real pero por debajo del umbral clínico)"
        if not self.confidently_relevant:
            return f"{detail} (sin confianza de que supere el umbral clínico)"
        return detail

    def _describe_en(self) -> str:
        """`describe` en inglés (`core/i18n.py`): las mismas ramas y la misma afirmación en cada
        una; el castellano de arriba no se toca."""
        name = get(self.key).display_es
        if not self.significant:
            return f"{name}: no detectable trend"
        days = f"{self.span_days:.0f}"
        if self.closed_episode:
            side = "above" if self.direction is Direction.RISING else "below"
            return (
                f"{name}: closed episode; it was {side} their personal range within the last "
                f"{days} days and has returned to its previous level, it is not an ongoing drift"
            )
        moving = "rising" if self.direction is Direction.RISING else "falling"
        rate = display.rate_per_week(self.key, abs(self.slope_per_week), get(self.key).unit)
        text = f"{name}: {moving} {rate} over {days} days"
        if not self.clinically_relevant:
            return f"{text} (a real drift, but below the clinical threshold)"
        if not self.confidently_relevant:
            return f"{text} (no confidence that it exceeds the clinical threshold)"
        return text


def linear_trend(
    key: str, times: Sequence[dt.datetime], values: Sequence[float]
) -> Trend | None:
    """Ajusta una recta y contrasta la pendiente contra su error tipico.

    Devuelve None si no hay puntos suficientes o si todas las marcas de tiempo
    coinciden (no hay eje sobre el que medir deriva).
    """
    if len(values) < MIN_POINTS or len(times) != len(values):
        return None

    origin = min(times)
    days = [(moment - origin).total_seconds() / 86400.0 for moment in times]

    # Sin varios ciclos completos, la pendiente mide fase circadiana, no deriva.
    if max(days) - min(days) < MIN_SPAN_DAYS:
        return None

    mean_x = statistics.fmean(days)
    mean_y = statistics.fmean(values)
    sxx = sum((x - mean_x) ** 2 for x in days)
    if sxx <= 0:
        return None  # todas las muestras en el mismo instante

    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(days, values, strict=True))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x

    residuals = [y - (intercept + slope * x) for x, y in zip(days, values, strict=True)]
    degrees_of_freedom = len(values) - 2
    residual_variance = sum(r * r for r in residuals) / degrees_of_freedom

    standard_error = 0.0
    if residual_variance <= 0:
        # Ajuste perfecto: la pendiente es real si no es cero.
        t_statistic = math.inf if slope != 0 else 0.0
    else:
        standard_error = math.sqrt(residual_variance / sxx)
        t_statistic = slope / standard_error if standard_error > 0 else 0.0

    significant = abs(t_statistic) >= T_SIGNIFICANCE
    if not significant:
        direction = Direction.STABLE
    else:
        direction = Direction.RISING if slope > 0 else Direction.FALLING

    return Trend(
        key=key,
        slope_per_day=slope,
        t_statistic=t_statistic,
        points=len(values),
        span_days=max(days) - min(days),
        direction=direction,
        significant=significant,
        mean_value=mean_y,
        standard_error=standard_error,
    )


# Lo que `trends_by_indicator` aplica a cada tendencia de cada estrato antes de elegir entre
# contextos: la tendencia, las lecturas del estrato en la ventana y el «ahora» de la evaluacion.
Settle = Callable[[Trend, Sequence[VitalObservation], dt.datetime], Trend]


PROJECTION_MODEL = "trend:ols-contexto@1"


def projection(trend: Trend) -> dict[str, Any] | None:
    """La deriva de una tendencia llevada al horizonte de relevancia, como PREDICHA.

    La especificacion del equipo (§2) pide separar medido, inferido y predicho. El
    motor ya calculaba `projected_change` para decidir si una deriva importa, pero no
    lo mostraba: aqui se expone con su incertidumbre y su modelo. Solo para derivas
    reales (`significant`): proyectar una pendiente que no se distingue del ruido
    seria presentar ruido como pronostico.

    Es una extrapolacion lineal de las ultimas semanas, no un pronostico clinico: la
    fisiologia no tiene por que seguir la recta.
    """
    if not trend.significant or trend.direction is Direction.STABLE:
        return None
    # Un episodio cerrado no es una deriva que pueda «seguir igual» (§5.38.6).
    if trend.closed_episode:
        return None
    code = get(trend.key)
    horizon_days = RELEVANCE_HORIZON_WEEKS * 7.0
    margin = T_SIGNIFICANCE * trend.standard_error * horizon_days
    change = trend.projected_change
    return {
        "key": trend.key,
        "display": code.display,
        "display_es": code.display_es,
        "unit": code.unit,
        # Un decimal mas que la lectura: un cambio proyectado es mas fino que el dato.
        "decimals": display.DECIMALS.get(trend.key, 1) + 1,
        "observation_type": "predicted",
        "model_version": PROJECTION_MODEL,
        "horizon_weeks": RELEVANCE_HORIZON_WEEKS,
        "window_days": round(trend.span_days, 1),
        "projected_change": round(change, 4),
        "projected_change_low": round(change - margin, 4),
        "projected_change_high": round(change + margin, 4),
        "clinically_relevant": trend.clinically_relevant,
        "concerning": trend.is_concerning,
        "basis": i18n.tr(
            f"extrapolación lineal de {display.number(trend.span_days, 0)} días a "
            f"{display.number(RELEVANCE_HORIZON_WEEKS, 0)} semanas si la deriva siguiera igual; "
            f"no es un pronóstico clínico",
            f"linear extrapolation of {display.number(trend.span_days, 0)} days to "
            f"{display.number(RELEVANCE_HORIZON_WEEKS, 0)} weeks if the drift continued "
            f"unchanged; it is not a clinical forecast",
        ),
    }


def trends_by_indicator(
    observations: Iterable[VitalObservation],
    window: dt.timedelta | None = TREND_WINDOW,
    now: dt.datetime | None = None,
    stratify_by_context: bool = True,
    settle: Settle | None = None,
    phase_offset: PhaseOffset | None = None,
) -> dict[str, Trend]:
    """Calcula la tendencia de cada indicador dentro de una ventana temporal.

    Por defecto, los ultimos `TREND_WINDOW` (ver arriba por que). `window=None`
    ajusta sobre toda la historia.

    `settle` recibe cada tendencia **de cada estrato**, con sus lecturas y el «ahora», y puede
    devolverla cambiada (`episode.closing`, §5.38.6). Va antes de elegir entre contextos: un
    episodio cerrado en uno no puede tapar una deriva viva en otro.
    Sin `settle` (lo que usa todo lo que decide), la tendencia es la de siempre.

    Se estratifica por contexto igual que la linea base, y por la misma razon:
    mezclar lecturas de sueno, reposo y ejercicio en un mismo ajuste hace que la
    pendiente dependa de cuanto de cada cosa cayo en cada extremo de la ventana.
    La tendencia del pulso **en reposo** es una magnitud clinica; la del pulso
    "en general" no lo es.

    `phase_offset` (`analysis/cycle_phase.py`, lote «ciclo») se resta a cada lectura antes de
    ajustar la recta. Es lo que de verdad hacia falta: medido con el motor sin tocar, la falsa
    alarma del ciclo venia de aqui —el escalon luteo visto por una recta de 21 dias es una
    «deriva»—, no de la lectura suelta. Sin el, la tendencia es la de siempre.
    """
    grouped: dict[tuple[str, Context], list[VitalObservation]] = {}
    for obs in observations:
        state = obs.context.family if stratify_by_context else Context.UNKNOWN
        grouped.setdefault((obs.key, state), []).append(obs)

    reference = now or max(
        (obs.effective for series in grouped.values() for obs in series),
        default=None,
    )
    if window is not None and reference is not None:
        cutoff = reference - window
        grouped = {key: _recent(series, cutoff) for key, series in grouped.items()}

    # Un indicador puede dar tendencia en varios contextos. Se queda la mas
    # preocupante: una deriva del pulso en reposo importa aunque la de esfuerzo
    # este limpia.
    results: dict[str, Trend] = {}
    for (key, _state), series in grouped.items():
        series.sort(key=lambda obs: obs.effective)
        # Sin la fase del ciclo, y la misma serie para `settle`: medir el episodio cerrado sobre
        # los valores en bruto mezclaria dos escalas con la recta.
        series = without_phase(series, phase_offset)
        trend = linear_trend(
            key,
            [obs.effective for obs in series],
            [obs.value for obs in series],
        )
        if trend is None:
            continue
        if settle is not None and reference is not None:
            trend = settle(trend, series, reference)
        current = results.get(key)
        if current is None or _supersedes(trend, current):
            results[key] = trend
    return results


def _recent(series: list[VitalObservation], cutoff: dt.datetime) -> list[VitalObservation]:
    """Lo posterior a `cutoff`, pero nunca menos de `MIN_POINTS` lecturas.

    Una ventana en dias castiga a lo que se mide poco. Con 21 dias, el PVT dos
    veces por semana o el NTx semanal no reunen los `MIN_POINTS` y perdian la
    via de tendencia **entera** —una deriva del PVT de 14 ms/semana, con umbral
    de 5,6, pasaba sin verse—. El simulador lo ocultaba: genera todo a la misma
    cadencia. A esos indicadores la ventana se les estira hasta sus ultimas
    `MIN_POINTS` lecturas: la pregunta sigue siendo "¿deriva ahora?", con la
    resolucion que su cadencia permite.
    """
    ordered = sorted(series, key=lambda obs: obs.effective)
    if len(ordered) >= MIN_POINTS:
        cutoff = min(cutoff, ordered[-MIN_POINTS].effective)
    return [obs for obs in ordered if obs.effective >= cutoff]


def _supersedes(candidate: Trend, incumbent: Trend) -> bool:
    """Que tendencia de un mismo indicador se queda, entre varios contextos.

    Preocupar gana siempre: una deriva del pulso **en reposo** importa aunque la
    de esfuerzo este limpia. A igualdad, la que mas claramente supera el umbral
    clinico: es el contraste que decide, asi que es el que ordena.
    """
    if candidate.is_concerning != incumbent.is_concerning:
        return candidate.is_concerning
    return candidate.threshold_contrast > incumbent.threshold_contrast
