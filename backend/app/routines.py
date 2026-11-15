# SPDX-License-Identifier: AGPL-3.0-or-later
"""¿Cada medida periódica está al día? `estado_rutina.clasificar` de Polaris, tal cual.

Por qué existe: una medida que deja de llegar no avisa. Un pulsómetro sin batería, una PVT que
nadie hace o una báscula que no se usa se parecen, desde el análisis, a "todo normal": la línea
base no se mueve porque no hay nada que moverla. Polaris ya distingue "no había nada que hacer"
de "lleva un mes rota" con las fechas que se tienen; aquí se le dan las de EMMA.

* **Ejecución** = la última lectura firmada de esa medida (cualquier confianza).
* **Éxito** = la última que el análisis usa (confianza ≥ `LOW_CONFIDENCE_THRESHOLD`).
* **Ahora** = el instante de referencia del estado (la última lectura de cualquier medida, o el
  corte de Tierra), no el reloj: es el "ahora" de todo EMMA (Control 7).
* **Periodo** = `app/data/routines.json`. Todos son parámetros de diseño, declarados como tales.

Un estado `rota` dice que falta un dato, no que el tripulante esté mal: no es una alerta clínica
y no entra en el riesgo.

MÁS A MENUDO MIENTRAS DURA UN EVENTO SOLAR (2026-11-02)
-------------------------------------------------------
Idea del equipo: ante un evento crítico inminente para la tripulación (una tormenta solar), que
la monitorización se intensifique y se centre en lo que más importa. Con un periodo de 6 h para la
dosis, una lectura que faltara en plena subida de un evento de partículas tardaría 12 h en verse
«rota»: el refugio de Orion se monta en 1 h. Por eso, con el evento que el estado da por activo
(`analysis.risk.active_solar_event`, el mismo criterio y no una copia), las rutinas de
`during_event` de `routines.json` se juzgan con su periodo acortado; cada una dice cuál vale
(`period_source`: `design` o `event`), el de siempre y el evento que lo acorta, y lleva un orden de
prioridad (`priority`) con el que la lista se ordena. Es solo orden y marca, como la hipótesis
solar de `analysis/context.py`: no cambia el riesgo, ni las alertas, ni la caducidad del evento, y
«rota» sigue sin ser alerta. Un evento posterior al ahora de las rutinas (el corte de Tierra, por
ejemplo) todavía no ha acortado nada, como el refugio que no ha empezado
(`radiation.time_to_action`). Los periodos, normales y de evento, entran en la versión de reglas
(`core/versioning.py`): deciden lo que la tripulación ve como al día.

TAMBIÉN CON LA DOSIS DE A BORDO POR ENCIMA DE SU LÍMITE (2026-11-04)
-------------------------------------------------------------------
Sin red, sin DONKI: el estado no tiene evento activo y la monitorización no se intensificaba
nunca, ni siquiera con el dosímetro de la tripulación en 1400 µGy/h (escenario `spe-event`). A
bordo de Orion el aviso de refugio lo da la dosimetría de la nave, no DONKI (la ficha
`nasa-artemis2-eyes-on-sun` de `analysis/context.py`). Por eso, sin evento de DONKI en curso, las
mismas rutinas de `during_event` se acortan también mientras la **última** lectura de tasa de dosis
del tripulante, en el ahora de las rutinas, cruza su límite de peligro con la regla del motor
(`baseline.crossed_danger_limit`, no una copia). En cuanto una lectura vuelve bajo el límite, los
periodos vuelven a los de diseño: es la vuelta a la normalidad que la demo enseña
(`spe-event-recovery`). No se llama «evento solar»: una tasa de dosis alta no dice por sí sola que
lo hubo (`analysis/context.py`); el disparador se declara aparte (`active_trigger`, `kind`
`dose`) y `active_event` sigue siendo solo el de DONKI. Con los dos, manda el de DONKI. Igual que el
del evento: solo orden y marca, sin riesgo, alertas ni caducidad.

Licencia y origen (AGPL §5a): usa `polaris/tools/estado_rutina.py` de la copia literal de Polaris,
sin modificarla (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris,
«Beyond the Protocol»); se carga con `app.polaris.load`. De EMMA: las fechas y los periodos que se
le dan (`app/data/routines.json`).
"""

from __future__ import annotations

import datetime as dt
import json
from functools import cache
from pathlib import Path
from typing import Any

from app import polaris
from app.analysis.baseline import crossed_danger_limit
from app.core import display, i18n
from app.environment.donki import SolarEvent
from app.ingest.codes import get
from app.ingest.fhir import LOW_CONFIDENCE_THRESHOLD, VitalObservation

DATA = Path(__file__).resolve().parent / "data" / "routines.json"

# De dónde sale el periodo con que se juzga cada rutina.
DESIGN = "design"
EVENT = "event"

# Lo que dice una rutina con el periodo acortado, y la respuesta entera mientras dura el evento.
# Redactado aquí: la interfaz lo enseña tal cual. Describe la cadencia, no pide medir nada.
EVENT_PERIOD_NOTE = "periodo acortado durante el evento solar {event}: de {design} h a {period} h"
EVENT_NOTE = (
    "Evento solar {event} en curso: {count} medidas se esperan más a menudo y van primero, por "
    "orden de prioridad; no cambia el riesgo ni las alertas"
)
# Lo que dice la respuesta sin evento en curso. La consola solo lo dice en voz alta cuando un
# evento acaba (`frontend/src/assistant/proactive.ts`): sin esta frase tendría que redactarla ella.
EVENT_OVER_NOTE = (
    "Sin evento solar en curso: las medidas se esperan con su periodo de diseño; no cambia el "
    "riesgo ni las alertas"
)
# Lo mismo cuando acorta la dosis de a bordo y no un evento de DONKI (ver la cabecera).
DOSE_KEY = "absorbed-dose-rate"
DOSE_TRIGGER = "dose"
SOLAR_TRIGGER = "solar-event"
DOSE_PERIOD_NOTE = (
    "periodo acortado mientras la tasa de dosis de a bordo supera su límite de peligro: de "
    "{design} h a {period} h"
)
DOSE_NOTE = (
    "Tasa de dosis de a bordo por encima de su límite de peligro ({value}, límite {limit}; "
    "lectura del {moment} UTC): {count} medidas se esperan más a menudo y van primero, por "
    "orden de prioridad; no cambia el riesgo ni las alertas"
)
DOSE_OVER_NOTE = (
    "Sin evento solar en curso y con la tasa de dosis de a bordo bajo su límite de peligro: las "
    "medidas se esperan con su periodo de diseño; no cambia el riesgo ni las alertas"
)


# Lo que dice la respuesta cuando el nivel de misión deja de esperar alguna rutina
# (`core/mission_modes.py`). Una suspendida no cuenta como atrasada ni rota: nadie la debe.
SUSPENDED_NOTE = (
    "Nivel de misión «{level}»: {count} de estas medidas no se esperan mientras rija; si llegan, "
    "entran y se analizan igual"
)

# El inglés de las frases de arriba (`core/i18n.py`), con los mismos huecos: se resuelven al
# servir (`i18n.loc(...).format(...)`), y las constantes se quedan como están.
i18n.en_many({
    EVENT_PERIOD_NOTE: (
        "period shortened during solar event {event}: from {design} h to {period} h"
    ),
    EVENT_NOTE: (
        "Solar event {event} in progress: {count} measurements are expected more often and go "
        "first, in priority order; it does not change the risk or the alerts"
    ),
    EVENT_OVER_NOTE: (
        "No solar event in progress: measurements are expected at their design period; it does "
        "not change the risk or the alerts"
    ),
    DOSE_PERIOD_NOTE: (
        "period shortened while the onboard dose rate exceeds its danger limit: from "
        "{design} h to {period} h"
    ),
    DOSE_NOTE: (
        "Onboard dose rate above its danger limit ({value}, limit {limit}; reading of "
        "{moment} UTC): {count} measurements are expected more often and go first, in priority "
        "order; it does not change the risk or the alerts"
    ),
    DOSE_OVER_NOTE: (
        "No solar event in progress and the onboard dose rate below its danger limit: "
        "measurements are expected at their design period; it does not change the risk or the "
        "alerts"
    ),
    SUSPENDED_NOTE: (
        "Mission level «{level}»: {count} of these measurements are not expected while it is "
        "in force; if they arrive, they are stored and analysed just the same"
    ),
})


def with_mission_level(
    body: dict[str, Any], level: str, level_display: str, suspended: frozenset[str]
) -> dict[str, Any]:
    """La respuesta de `evaluate` con lo que el nivel de misión deja de esperar.

    Por qué existe: con el nivel reducido o mínimo firmado, la consola seguía dando por atrasadas
    las medidas que el propio nivel suspende. Solo se marca cada rutina (`suspended`) y se
    recuentan los estados sin las suspendidas; el estado de cada una sigue calculado igual, y nada
    de esto llega al riesgo ni a las alertas (invariante 5).
    """
    off = 0
    counts: dict[str, int] = {}
    for routine in body["routines"]:
        routine["suspended"] = routine["key"] in suspended
        if routine["suspended"]:
            off += 1
            continue
        counts[routine["state"]] = counts.get(routine["state"], 0) + 1
    return {
        **body,
        "counts": counts,
        "mission_level": level,
        # El nombre del nivel, el mismo que da `/api/mission-mode`: la consola lo dice cuando cambia
        # sin tener que leer otro sondeo ni redactarlo.
        "mission_level_display": level_display,
        "suspended_note": (
            i18n.loc(SUSPENDED_NOTE).format(level=level_display, count=off) if off else None
        ),
    }


@cache
def _tool() -> Any:
    return polaris.load("estado_rutina")


@cache
def load() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(DATA.read_text(encoding="utf-8"))
    for key, item in data["routines"].items():
        get(key)  # una rutina de un indicador que no existe es un error de configuración
        if not isinstance(item.get("period_hours"), int | float) or item["period_hours"] <= 0:
            raise ValueError(f"rutina '{key}': period_hours tiene que ser positivo")
    _check_during_event(data)
    return data


def _check_during_event(data: dict[str, Any]) -> None:
    """Las rutinas de evento: declaradas, más cortas que las de siempre y con prioridad única."""
    priorities: list[int] = []
    for key, item in data.get("during_event", {}).get("routines", {}).items():
        if key not in data["routines"]:
            raise ValueError(f"rutina de evento '{key}': no es una rutina declarada")
        period = item.get("period_hours")
        design = data["routines"][key]["period_hours"]
        if not isinstance(period, int | float) or not 0 < period < design:
            # Durante un evento se mide más, nunca menos: alargar un periodo escondería un hueco.
            raise ValueError(
                f"rutina de evento '{key}': el periodo tiene que acortar el de siempre"
            )
        priority = item.get("priority")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError(f"rutina de evento '{key}': priority tiene que ser un entero")
        priorities.append(priority)
    if len(priorities) != len(set(priorities)):
        raise ValueError("rutinas de evento: dos con la misma prioridad")


def evaluate(
    observations: list[VitalObservation],
    now: dt.datetime | None = None,
    event: SolarEvent | None = None,
) -> dict[str, Any]:
    """El estado de cada rutina declarada, con sus fechas y su periodo.

    `event` es el evento solar que el estado da por activo (`analysis.risk.active_solar_event`
    sobre los SEP que lee el estado), o nada. Sin él la respuesta es la de siempre, con los
    campos del evento vacíos.
    """
    data = load()
    last_run: dict[str, dt.datetime] = {}
    last_ok: dict[str, dt.datetime] = {}
    for item in observations:
        if item.key not in data["routines"]:
            continue
        if item.key not in last_run or item.effective > last_run[item.key]:
            last_run[item.key] = item.effective
        if item.confidence >= LOW_CONFIDENCE_THRESHOLD and (
            item.key not in last_ok or item.effective > last_ok[item.key]
        ):
            last_ok[item.key] = item.effective
    if now is None:
        now = max((item.effective for item in observations), default=dt.datetime.now(dt.UTC))
    in_force = event_in_force(event, now)
    # Sin evento de DONKI, la dosis de a bordo (ver la cabecera); con él, manda el evento.
    dose = dose_in_force(observations, now) if in_force is None else None
    during: dict[str, Any] = (
        data.get("during_event", {}) if in_force is not None or dose is not None else {}
    )
    shortened: dict[str, Any] = during.get("routines", {})
    classify = _tool().clasificar
    routines = []
    for key, item in data["routines"].items():
        hours = shortened[key]["period_hours"] if key in shortened else item["period_hours"]
        period = dt.timedelta(hours=float(hours))
        routines.append({
            "key": key,
            "display": get(key).display,
            "display_es": get(key).display_es,
            "period_hours": hours,
            # La base es texto de `routines.json`: su inglés, de su hermano. Los periodos y las
            # prioridades (lo que entra en la versión de reglas) no pasan por él.
            "basis": i18n.localized(
                during["basis"] if key in shortened
                else item.get("basis", data["default_basis"]),
                DATA,
            ),
            "state": classify(last_run.get(key), last_ok.get(key), period, now),
            "last_run": last_run[key].isoformat() if key in last_run else None,
            "last_success": last_ok[key].isoformat() if key in last_ok else None,
            **_event_fields(key, item, shortened, in_force, dose),
        })
    if shortened:
        # Solo orden: las del evento primero, por su prioridad; el resto, como estaba.
        routines.sort(key=lambda routine: (routine["priority"] is None, routine["priority"] or 0))
    counts: dict[str, int] = {}
    for routine in routines:
        counts[routine["state"]] = counts.get(routine["state"], 0) + 1
    return {
        "now": now.isoformat(), "counts": counts, "routines": routines,
        "active_event": in_force.to_dict() if in_force is not None else None,
        # Qué acorta los periodos ahora: el evento de DONKI, la dosis de a bordo o nada.
        "active_trigger": _trigger(in_force, dose),
        "event_note": _event_note(in_force, dose, len(shortened)),
        "event_over_note": (
            None if in_force is not None or dose is not None
            # Con alguna lectura de dosis, la frase dice también que está bajo su límite.
            else i18n.loc(DOSE_OVER_NOTE) if any(item.key == DOSE_KEY for item in observations)
            else i18n.loc(EVENT_OVER_NOTE)
        ),
    }


def dose_in_force(
    observations: list[VitalObservation], now: dt.datetime
) -> VitalObservation | None:
    """La última lectura de tasa de dosis hasta `now`, si cruza su límite de peligro; o nada.

    La última buena (confianza ≥ `LOW_CONFIDENCE_THRESHOLD`, la que usa el análisis) y no
    posterior a `now`: una del futuro no ha acortado nada todavía, como el evento
    (`event_in_force`). Solo por arriba: es lo que sube en un evento de partículas.
    """
    readings = [
        item for item in observations
        if item.key == DOSE_KEY and item.effective <= now
        and item.confidence >= LOW_CONFIDENCE_THRESHOLD
    ]
    if not readings:
        return None
    last = max(readings, key=lambda item: item.effective)
    limit = crossed_danger_limit(last)
    return last if limit is not None and last.value > limit else None


def _trigger(event: SolarEvent | None, dose: VitalObservation | None) -> dict[str, Any] | None:
    if event is not None:
        return {"kind": SOLAR_TRIGGER, "event_id": event.event_id, "time": event.time.isoformat()}
    if dose is None:
        return None
    return {
        "kind": DOSE_TRIGGER,
        "key": dose.key,
        "subject": dose.subject,
        "value": dose.value,
        "unit": dose.code.unit,
        "limit": crossed_danger_limit(dose),
        "effective": dose.effective.isoformat(),
        "source": dose.source,
    }


def _event_note(event: SolarEvent | None, dose: VitalObservation | None, count: int) -> str | None:
    if not count:
        return None
    if event is not None:
        return i18n.loc(EVENT_NOTE).format(event=event.event_id, count=count)
    if dose is None:
        return None
    limit = crossed_danger_limit(dose) or 0.0
    return i18n.loc(DOSE_NOTE).format(
        value=display.quantity(dose.key, dose.value, dose.code.unit),
        limit=display.quantity(dose.key, limit, dose.code.unit),
        moment=f"{dose.effective.astimezone(dt.UTC):%Y-%m-%d %H:%M}",
        count=count,
    )


def event_in_force(event: SolarEvent | None, now: dt.datetime) -> SolarEvent | None:
    """El evento que acorta periodos en `now`: el que el estado da por activo, si ya empezó.

    Uno posterior a `now` (el corte de Tierra, o datos anteriores al reloj real) todavía no ha
    acortado nada: juzgar con él lecturas anteriores las daría por atrasadas antes de que hubiera
    motivo. La caducidad es la del estado (`api.routes.SOLAR_EVENT_RELEVANCE`): aquí no hay otra.
    """
    return event if event is not None and event.time <= now else None


def _event_fields(
    key: str,
    item: dict[str, Any],
    shortened: dict[str, Any],
    event: SolarEvent | None,
    dose: VitalObservation | None = None,
) -> dict[str, Any]:
    """De dónde sale el periodo de una rutina y, si lo acorta el evento o la dosis, cuál y por
    qué. `event_id` es solo el de DONKI: con la dosis va vacío y `trigger` lo dice."""
    if key not in shortened or (event is None and dose is None):
        return {
            "period_source": DESIGN, "design_period_hours": item["period_hours"],
            "event_id": None, "priority": None, "period_note": None, "trigger": None,
        }
    period = shortened[key]["period_hours"]
    design = display.number(float(item["period_hours"]), 0)
    shorter = display.number(float(period), 0)
    return {
        "period_source": EVENT,
        "design_period_hours": item["period_hours"],
        "event_id": event.event_id if event is not None else None,
        "priority": shortened[key]["priority"],
        "period_note": (
            i18n.loc(EVENT_PERIOD_NOTE).format(
                event=event.event_id, design=design, period=shorter
            )
            if event is not None
            else i18n.loc(DOSE_PERIOD_NOTE).format(design=design, period=shorter)
        ),
        "trigger": SOLAR_TRIGGER if event is not None else DOSE_TRIGGER,
    }


# RACHAS: CUÁNTOS PERIODOS SEGUIDOS LLEGÓ CADA MEDIDA (decisión del usuario, 2026-11-02).
#
# Por qué existe: el reto pide «un sistema de gamificación que ayude a los astronautas a implicarse
# en las tareas que cuidan su salud». `evaluate` solo mira la última lectura: dice si una medida va
# a su ritmo ahora, no cuánto tiempo lleva yendo. La racha es esa cifra, contada con las mismas
# lecturas y el mismo ahora, para que quien mide vea su constancia sin que nadie la juzgue.
#
# Por qué NO es adherencia (docs/contexto/README.md, porcentaje de adherencia descartado): una tasa
# de adherencia exige una pauta prescrita, y los periodos de `routines.json` son parámetros de
# diseño de EMMA, no una pauta. Por eso la cifra es un recuento («N periodos seguidos»), sin
# porcentaje, rotulado «ritmo de diseño», sin color ni animación de premio (la tabla F.5-1 no tiene
# un significado de «premio») y sin felicitaciones: la frase la redacta el backend y pasa el filtro
# de lenguaje (`text_guard`, invariante 7). Tampoco entra en el riesgo ni en ninguna alerta: ningún
# módulo de `analysis/` ni de `advisor/` la lee (lo vigila `tests/test_streaks.py`).

STREAK_TEXT: dict[str, str] = {
    "label": "Ritmo de diseño: periodos seguidos con lectura buena",
    "note": (
        "Periodos de diseño que abarca la última serie de lecturas buenas sin un hueco mayor que "
        "el periodo, si la última llegó dentro de él. El periodo es un parámetro de diseño, no "
        "una pauta prescrita: la cifra no mide adherencia ni entra en el riesgo."
    ),
    "one": "periodo seguido",
    "many": "periodos seguidos",
    "longest": "la más larga",
}
i18n.en_many({
    STREAK_TEXT["label"]: "Design cadence: consecutive periods with a good reading",
    STREAK_TEXT["note"]: (
        "Design periods spanned by the latest run of good readings with no gap longer than the "
        "period, if the last one arrived within it. The period is a design parameter, not a "
        "regimen set by a clinician: the figure does not measure adherence and does not enter "
        "the risk."
    ),
    STREAK_TEXT["one"]: "consecutive period",
    STREAK_TEXT["many"]: "consecutive periods",
    STREAK_TEXT["longest"]: "the longest",
})


def _periods(first: dt.datetime, last: dt.datetime, period: dt.timedelta) -> int:
    """Cuántos periodos abarca una serie sin huecos: uno por la primera lectura, y uno más por
    cada periodo entero que pasa hasta la última (lecturas cada P durante 10 P: 11)."""
    return (last - first) // period + 1


def streaks(
    observations: list[VitalObservation], now: dt.datetime | None = None
) -> dict[str, Any]:
    """Por rutina declarada: la racha vigente y la más larga, en periodos de diseño.

    Los bordes son los de `estado_rutina`, para que la racha nunca cuente como seguido lo que el
    estado de la rutina dio por atrasado:

    * Una lectura **buena** es la que `evaluate` llama éxito: confianza ≥
      `LOW_CONFIDENCE_THRESHOLD`. Una de confianza baja no suma ni tapa un hueco, porque el
      análisis no la usa.
    * Una **serie** son lecturas buenas seguidas sin un hueco mayor que P entre dos de ellas
      (justo P no corta: «justo en P sigue al día»). Su longitud es `_periods`.
    * **Racha vigente** = la serie que acaba en la última lectura buena, si esta tiene P o menos
      respecto a `now`; si no, 0 (la rutina ya está atrasada).
    * **Racha más larga** = la serie más larga de todas, la vigente incluida. Solo depende de las
      lecturas, no de `now`: no baja porque pase el tiempo.
    * Lo posterior a `now` no cuenta (un dato del futuro no es constancia).
    * `now` es el de `evaluate`: el del estado o el corte de Tierra, que da quien llama.

    Las lecturas son de un solo tripulante, como en `evaluate` (`/api/timeline/routines` pide un
    `subject`): mezclar dos sería atribuirle a uno la constancia de otro, y se rechaza. El texto
    (`STREAK_TEXT`) pasa el filtro de lenguaje en las pruebas (`tests/test_streaks.py`).
    """
    data = load()
    if len({item.subject for item in observations}) > 1:
        raise ValueError("las rachas se cuentan por tripulante: llegan lecturas de varios")
    if now is None:
        now = max((item.effective for item in observations), default=dt.datetime.now(dt.UTC))
    good: dict[str, list[dt.datetime]] = {}
    for item in observations:
        if (
            item.key in data["routines"]
            and item.confidence >= LOW_CONFIDENCE_THRESHOLD
            and item.effective <= now
        ):
            good.setdefault(item.key, []).append(item.effective)
    routines = []
    for key, item in data["routines"].items():
        period = dt.timedelta(hours=float(item["period_hours"]))
        times = sorted(good.get(key, []))
        longest = current = 0
        first: dt.datetime | None = None
        for index, moment in enumerate(times):
            if first is None or moment - times[index - 1] > period:
                first = moment
            current = _periods(first, moment, period)
            longest = max(longest, current)
        if not times or now - times[-1] > period:
            current = 0
        routines.append({
            "key": key,
            "display_es": get(key).display_es,
            "period_hours": item["period_hours"],
            "basis": i18n.localized(item.get("basis", data["default_basis"]), DATA),
            "current": current,
            "longest": longest,
            "unit": i18n.loc(STREAK_TEXT["one"] if current == 1 else STREAK_TEXT["many"]),
        })
    return {
        "label": i18n.loc(STREAK_TEXT["label"]),
        "note": i18n.loc(STREAK_TEXT["note"]),
        "longest_label": i18n.loc(STREAK_TEXT["longest"]),
        "routines": routines,
    }
