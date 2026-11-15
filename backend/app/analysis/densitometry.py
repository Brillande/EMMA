"""La densitometria medida en Tierra, junto a la banda osea que EMMA infiere en vuelo.

POR QUE EXISTE
--------------
La banda de `analysis/inferred.py` estima la perdida de densidad mineral osea durante el vuelo:
es INFERIDA, una banda de poblacion aplicada al dia de mision, porque en vuelo la densidad no se
mide («no system to date measures bone density in-flight», OCHMO-MTB-013 Rev D, p. 19). Se mide
en Tierra, por densitometria (DXA), antes del lanzamiento y despues del regreso. La conversacion
de ideacion del equipo (`docs/contexto/conversacion-ideacion-v1.md`, hacia la linea 1460) pedia
justo esto: estimar en vuelo el deterioro musculoesqueletico «y contrastarlo despues con las
mediciones clinicas post-vuelo», el ciclo «prediccion durante mision -> resultado post-vuelo ->
validacion» (hacia la linea 571). Decision del usuario (2026-10-26): la DXA entra como indicador
descriptivo (`codes.DENSITOMETRY_KEYS`) y aqui se pone al lado de la banda.

QUE HACE, Y QUE NO
------------------
Por tripulante y por region (columna lumbar, cadera), toma la ultima medida de antes del
lanzamiento y la primera de despues del regreso, calcula la perdida medida en porcentaje del
valor previo y dice si cae dentro de la banda inferida para el dia de regreso, por encima (se
midio mas perdida de la que estima la banda) o por debajo (menos). La banda que se usa es la que
se sirve: la misma funcion y el mismo redondeo (`inferred.loss_band`), en el dia de regreso, que
es donde la banda se detiene en posvuelo.

- Es una comprobacion de la inferencia, no un veredicto clinico: no puntua, no alerta, no mueve
  ningun nivel (invariante 5) y no dice que una perdida sea buena o mala (invariante 7). El
  requisito de la norma frente al valor previo ([V1 4027], el 95 %) se cita en la medida leida
  (`data/instruments_read.json`) y aqui no se evalua.
- Solo compara la primera medida de despues del regreso, y solo si es de antes de 30 dias: el
  calendario de ejemplo de NASA la pone en «R+ < 30 days» ([V1 4026], p. 19; leerlo como el
  plazo de la comparacion es de EMMA). Una posterior incluye una recuperacion que EMMA no estima
  (la banda se queda en el dia de regreso), y compararla con la banda seria mezclar dos cosas.
- Y la previa, solo si es de los 180 dias antes del lanzamiento: el mismo calendario la pone en
  «L- 180/30 d (as close to launch as feasible)», y la de seleccion («AME L- 21/18 m») mezclaria
  en la perdida lo que cambio antes del vuelo (leer «L- 180» como el limite es de EMMA).
- El regreso es el de `core/mission.py` (el dia `duration_days`, como en la banda y en
  `phase_at`): aqui no se abre otro calendario. Una medida fechada antes de ese limite cuenta
  como de vuelo, y se dice.
- No descuenta el error de medida de la DXA: la norma nombra el cambio minimo significativo sin
  dar una cifra (p. 20), y no se inventa. Se dice.
- Solo lee lecturas MEDIDAS: una densitometria inferida o predicha no es una medida.
- Las lecturas fechadas en vuelo no se usan: la DXA no vuela.

No escribe nada en el ledger ni sale a la red.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from enum import StrEnum
from typing import Any

from app.analysis.inferred import cited, english_relevance, loss_band
from app.core import display, i18n
from app.core.mission import mission_day
from app.evidence import registry
from app.ingest.codes import BMD_DXA_HIP, BMD_DXA_LUMBAR_SPINE, DENSITOMETRY_KEYS, VitalCode
from app.ingest.fhir import ObservationType, VitalObservation
from app.ingest.names_es import spanish_name

# «R+ < 30 days» y «L- 180/30 d»: el calendario de ejemplo de NASA para una mision de 180 dias
# ([V1 4026]).
POSTFLIGHT_WINDOW_DAYS = 30.0
PREFLIGHT_WINDOW_DAYS = 180.0

# Las regiones, en el orden en que las nombra la norma de NASA ([V1 4026]: «total hip and
# lumbar spine»), con el nombre corto con que se ensenan.
REGIONS: tuple[tuple[VitalCode, str], ...] = (
    (BMD_DXA_HIP, "Cadera"),
    (BMD_DXA_LUMBAR_SPINE, "Columna lumbar"),
)


class Position(StrEnum):
    """Donde cae la perdida medida frente a la banda inferida."""

    WITHIN = "within"
    ABOVE = "above"
    BELOW = "below"


class CheckState(StrEnum):
    """Si una region se pudo comparar, y si no, por que."""

    COMPARED = "compared"
    NO_PREFLIGHT = "no_preflight"
    OLD_PREFLIGHT = "old_preflight"
    NO_POSTFLIGHT = "no_postflight"
    LATE_POSTFLIGHT = "late_postflight"
    ONLY_IN_FLIGHT = "only_in_flight"


# Las palabras las da el backend; las cifras las pinta la interfaz con su formato.
POSITION_STATEMENTS: dict[Position, str] = {
    Position.WITHIN: "La pérdida medida cae dentro de la banda inferida para el día de regreso.",
    Position.ABOVE: (
        "La pérdida medida queda por encima de la banda inferida: la densitometría da más "
        "pérdida de la que estima la banda."
    ),
    Position.BELOW: (
        "La pérdida medida queda por debajo de la banda inferida: la densitometría da menos "
        "pérdida de la que estima la banda."
    ),
}
STATE_STATEMENTS: dict[CheckState, str] = {
    CheckState.NO_PREFLIGHT: (
        "Hay densitometría de después del regreso, pero ninguna de antes del lanzamiento: sin "
        "el valor previo no hay pérdida medida que poner junto a la banda."
    ),
    CheckState.OLD_PREFLIGHT: (
        "La última densitometría de antes del lanzamiento es de más de 180 días antes: el "
        "calendario de ejemplo de NASA pone la previa entre 180 y 30 días antes, y una anterior "
        "mezclaría lo que cambió antes del vuelo. No se pone junto a la banda."
    ),
    CheckState.NO_POSTFLIGHT: (
        "Hay densitometría de antes del lanzamiento. La comparación llega con la de después del "
        "regreso, que el calendario de ejemplo de NASA pone en menos de 30 días."
    ),
    CheckState.LATE_POSTFLIGHT: (
        "La primera densitometría de después del regreso es de 30 días o más tarde: incluye una "
        "recuperación que EMMA no estima, y no se pone junto a la banda."
    ),
    CheckState.ONLY_IN_FLIGHT: (
        "Las densitometrías registradas están fechadas entre el lanzamiento y el día de regreso "
        "de la misión, y la densitometría no se mide en vuelo: no se ponen junto a la banda."
    ),
}
# Si ademas hay lecturas fechadas en vuelo y la region tiene previa o posvuelo, se dice que se
# apartaron: si no, una DXA de despues del aterrizaje fechada antes del dia de regreso de la
# configuracion desapareceria sin decirlo.
IN_FLIGHT_NOTE = (
    "Hay además densitometrías fechadas entre el lanzamiento y el día de regreso de la misión: "
    "la densitometría no se mide en vuelo, y no se ponen junto a la banda."
)
RELATION = (
    "La densitometría (DXA) es una medida de esta persona, tomada en Tierra antes del "
    "lanzamiento y después del regreso; la banda es inferida, de población. Ponerlas juntas "
    "comprueba la inferencia: no es un veredicto clínico, y no mueve ningún nivel ni alerta."
)
PRECISION_NOTE = (
    "La comparación no descuenta el error de medida de la densitometría: la norma de NASA nombra "
    "el cambio mínimo significativo sin dar una cifra."
)
SOURCE = registry.cite(
    "ochmo-mtb-013",
    "dónde y cuándo se mide la densidad ósea: en Tierra, por DXA, antes del lanzamiento y en "
    "menos de 30 días del regreso (páginas 19 y 20)",
)


# Cómo se nombra cada cosa. Lo da el backend: la interfaz no escribe palabras de fase ni texto
# clínico, solo pone las cifras con su formato.
PREFLIGHT_LABEL = "antes del lanzamiento"
POSTFLIGHT_LABEL = "después del regreso"
LOSS_LABEL = "pérdida medida desde antes del lanzamiento"
BAND_LABEL = "pérdida acumulada que estima la banda para el día de regreso"

# El inglés de todas las frases fijas de arriba (`core/i18n.py`); se resuelve al servir, en
# `_region` y `against_band`. Los estados y las posiciones (`within`, `no_preflight`…) son claves
# y no se traducen.
_REGION_EN: dict[str, str] = {BMD_DXA_HIP.key: "Hip", BMD_DXA_LUMBAR_SPINE.key: "Lumbar spine"}
i18n.en_many({
    POSITION_STATEMENTS[Position.WITHIN]: (
        "The measured loss falls within the band inferred for the return day."
    ),
    POSITION_STATEMENTS[Position.ABOVE]: (
        "The measured loss is above the inferred band: densitometry gives more loss than the "
        "band estimates."
    ),
    POSITION_STATEMENTS[Position.BELOW]: (
        "The measured loss is below the inferred band: densitometry gives less loss than the "
        "band estimates."
    ),
    STATE_STATEMENTS[CheckState.NO_PREFLIGHT]: (
        "There is densitometry from after the return, but none from before launch: without "
        "the previous value there is no measured loss to put beside the band."
    ),
    STATE_STATEMENTS[CheckState.OLD_PREFLIGHT]: (
        "The last densitometry before launch is from more than 180 days earlier: NASA's example "
        "schedule puts the preflight one between 180 and 30 days before, and an earlier one "
        "would mix in what changed before the flight. It is not put beside the band."
    ),
    STATE_STATEMENTS[CheckState.NO_POSTFLIGHT]: (
        "There is densitometry from before launch. The comparison comes with the one after the "
        "return, which NASA's example schedule puts at less than 30 days."
    ),
    STATE_STATEMENTS[CheckState.LATE_POSTFLIGHT]: (
        "The first densitometry after the return is from 30 days or later: it includes a "
        "recovery that EMMA does not estimate, and it is not put beside the band."
    ),
    STATE_STATEMENTS[CheckState.ONLY_IN_FLIGHT]: (
        "The densitometries on record are dated between launch and the mission's return day, "
        "and densitometry is not measured in flight: they are not put beside the band."
    ),
    IN_FLIGHT_NOTE: (
        "There are also densitometries dated between launch and the mission's return day: "
        "densitometry is not measured in flight, and they are not put beside the band."
    ),
    RELATION: (
        "Densitometry (DXA) is a measurement of this person, taken on Earth before launch and "
        "after the return; the band is inferred, from population data. Putting them together "
        "checks the inference: it is not a clinical verdict, and it moves no level or alert."
    ),
    PRECISION_NOTE: (
        "The comparison does not discount the measurement error of densitometry: the NASA "
        "standard names the least significant change without giving a figure."
    ),
    PREFLIGHT_LABEL: "before launch",
    POSTFLIGHT_LABEL: "after the return",
    LOSS_LABEL: "loss measured since before launch",
    BAND_LABEL: "cumulative loss the band estimates for the return day",
})
english_relevance(
    SOURCE,
    "where and when bone density is measured: on Earth, by DXA, before launch and within "
    "30 days of the return (pages 19 and 20)",
)


def _reading(
    item: VitalObservation, start: dt.date, return_day: float, label: str
) -> dict[str, Any]:
    day = mission_day(item.effective, start)
    after = day - return_day
    return {
        "label": i18n.loc(label),
        "value": item.value,
        "effective": item.effective.isoformat(),
        "mission_day": round(day, 1),
        # Dias desde el regreso: antes del lanzamiento no tiene sentido, y no se da.
        "days_after_return": round(after, 1) if day >= return_day else None,
        # Cuando, con la notacion de NASA (L- antes del lanzamiento, R+ tras el regreso) y la
        # cifra con el formato de toda cifra (F.5.6): con un decimal, R+29,6 no se lee R+30.
        "when_display": (
            f"R+{display.number(after, 1)} d" if day >= return_day
            else f"L-{display.number(-day, 1)} d"
        ),
    }


def _region(
    code: VitalCode,
    name: str,
    readings: list[VitalObservation],
    start: dt.date,
    return_day: float,
    band: dict[str, float],
) -> dict[str, Any]:
    ordered = sorted(readings, key=lambda item: item.effective)
    before = [item for item in ordered if mission_day(item.effective, start) < 0]
    after = [item for item in ordered if mission_day(item.effective, start) >= return_day]
    in_flight = len(ordered) - len(before) - len(after)
    preflight = before[-1] if before else None
    postflight = after[0] if after else None
    loss: float | None = None
    position: Position | None = None
    # Por orden: lo que falta antes que lo que sobra, para que el motivo dicho sea el primero
    # que impide comparar (sin previa, una posvuelo tardia no es el problema).
    if preflight is None and postflight is None:
        state = CheckState.ONLY_IN_FLIGHT
    elif postflight is None:
        state = CheckState.NO_POSTFLIGHT
    elif preflight is None or preflight.value <= 0:
        # El catalogo no admite una densidad de cero (`physical_min`); la guarda es por si.
        state = CheckState.NO_PREFLIGHT
    elif -mission_day(preflight.effective, start) > PREFLIGHT_WINDOW_DAYS:
        state = CheckState.OLD_PREFLIGHT
    elif mission_day(postflight.effective, start) - return_day >= POSTFLIGHT_WINDOW_DAYS:
        state = CheckState.LATE_POSTFLIGHT
    else:
        state = CheckState.COMPARED
        loss = round((preflight.value - postflight.value) / preflight.value * 100, 2)
        if loss > band["loss_pct_high"]:
            position = Position.ABOVE
        elif loss < band["loss_pct_low"]:
            position = Position.BELOW
        else:
            position = Position.WITHIN
    statement = i18n.loc(
        POSITION_STATEMENTS[position] if position is not None else STATE_STATEMENTS[state]
    )
    if in_flight and state is not CheckState.ONLY_IN_FLIGHT:
        statement = f"{statement} {i18n.loc(IN_FLIGHT_NOTE)}"
    # Una previa que no vale (densidad de cero) no se ensena: la frase dice que no hay previa.
    shown_preflight = None if state is CheckState.NO_PREFLIGHT else preflight
    return {
        "key": code.key,
        "region": i18n.tr(name, _REGION_EN.get(code.key, name)),
        # `name_es` da el nombre del catálogo en inglés; en castellano, el mismo `spanish_name`.
        "display_es": i18n.tr(spanish_name(code.key).text, code.display),
        "unit": code.unit,
        # Los decimales con que se lee la cifra, los mismos de toda lectura del indicador.
        "decimals": display.DECIMALS[code.key],
        "state": str(state),
        "preflight": (
            None if shown_preflight is None
            else _reading(shown_preflight, start, return_day, PREFLIGHT_LABEL)
        ),
        "postflight": (
            None if postflight is None
            else _reading(postflight, start, return_day, POSTFLIGHT_LABEL)
        ),
        # Las de despues de la que se compara: recuperacion, que la banda no estima.
        "later_postflight": len(after) - 1 if after else 0,
        # Las fechadas en vuelo, que no se usan: la DXA no vuela.
        "in_flight": in_flight,
        "measured_loss_pct": loss,
        "position": None if position is None else str(position),
        "statement": statement,
    }


def against_band(
    readings: Iterable[VitalObservation], *, mission_start: dt.date, return_day: float
) -> dict[str, Any] | None:
    """La densitometria del tripulante junto a la banda en el dia de regreso; `None` si no hay.

    `readings` puede traer de todo (lo que devolvio el almacen): aqui se toman solo las
    densitometrias medidas. Sin ninguna, `None`, y la banda sale como antes, campo a campo.
    """
    by_key: dict[str, list[VitalObservation]] = {}
    for item in readings:
        if item.key in DENSITOMETRY_KEYS and item.observation_type is ObservationType.MEASURED:
            by_key.setdefault(item.key, []).append(item)
    if not by_key:
        return None
    band = loss_band(max(0.0, return_day))
    return {
        "observation_type": str(ObservationType.MEASURED),
        "relation": i18n.loc(RELATION),
        "band_day": band["mission_day"],
        "band": {"loss_pct_low": band["loss_pct_low"], "loss_pct_high": band["loss_pct_high"]},
        "postflight_window_days": POSTFLIGHT_WINDOW_DAYS,
        "preflight_window_days": PREFLIGHT_WINDOW_DAYS,
        "loss_label": i18n.loc(LOSS_LABEL),
        "band_label": i18n.loc(BAND_LABEL),
        "precision_note": i18n.loc(PRECISION_NOTE),
        "source": cited(SOURCE),
        "regions": [
            _region(code, name, by_key[code.key], mission_start, return_day, band)
            for code, name in REGIONS
            if code.key in by_key
        ],
    }
