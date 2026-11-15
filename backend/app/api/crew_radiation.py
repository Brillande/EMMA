"""La tripulación ante un evento solar, de un vistazo (decimoctava ronda, U8, §5.38.8).

Por qué existe: la conversación de ideación del equipo, ante un evento de partículas solares,
pregunta «¿Dónde está la tripulación? … ¿Cuál es la dosis actual de cada astronauta?». EMMA ya
tenía cada pieza, pero cada una en un sitio: la ubicación declarada en `GET /api/crew`, sin
ninguna dosis; la dosis de misión y la de carrera en el estado de cada tripulante, uno a uno; y el
evento solar y el refugio en la escala aguda de ese mismo estado. Para contestar había que abrir el
estado de cada persona. Esta ruta las pone juntas, una fila por tripulante, sin calcular nada
nuevo:

- **Ubicación**: la que declaró la consola o, si no hay, la que estiman las anclas de módulo (con
  `source` y `location_state`), para el instante de referencia de la tripulación, con la misma
  regla que el estado (`crew_whereabouts` y `analysis.location.view`).
- **Dosis**: la de misión (INFERIDA) y la de carrera de la escala de radiación del estado de cada
  uno (`analysis.radiation.scales`, con las lecturas que lee su estado y la dosis previa de su
  perfil), con su rótulo de tipo tal cual lo da esa escala. Una prueba compara cada cifra con la
  de `GET /api/status`: si el estado cambia cómo la calcula, esta ruta no puede quedarse atrás.
  Por eso se pasa por `_assess`, como `/crew`, y no por un filtro propio de lecturas: cuesta lo
  mismo que la vista de tripulación y no puede leer otras lecturas que el estado. Un tripulante
  sin estado analizable no desaparece: sale con su ubicación y con lo que falta dicho (salvo, en
  Tierra, el que no tiene ninguna lectura llegada antes del corte: ese aún no existe allí).
- **Evento y refugio**: el evento que eligió el estado (`active_solar_event`), con el mismo
  bloque que la radiación del hábitat (`api.habitat.solar_event_block`, al que se le pasa ese
  evento, sin otra consulta ni otra pasada por las lecturas: vigente, ninguno o «no se sabe»),
  y el procedimiento de refugio de Orion que ya da la escala aguda (`time_to_action`).

Lo que NO hace, a propósito: ningún factor de blindaje ni cuánto bajaría la dosis en otro módulo
(el refugio por módulo está en «No se adopta» de `docs/contexto/README.md`), y la ubicación no
corrige ninguna cifra. Es descriptiva: no firma nada, no cambia ningún nivel, alerta ni hipótesis,
y no añade ninguna constante a `rules_version`. Para Tierra, con `until`: lecturas, ubicaciones y
perfil hasta su corte; el evento, como en el estado, es el del reloj real.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException

from app.analysis.location import LOCATION_BASIS, sensing
from app.analysis.location import view as location_view
from app.analysis.radiation import mission_dose, time_to_action
from app.analysis.radiation import scales as radiation_scales
from app.api.habitat import solar_event_block
from app.api.mission import crew_whereabouts, latest_profile
from app.api.routes import SettingsDep, StoreDep, _assess, _Assessment
from app.core import i18n
from app.core.config import Settings
from app.core.storage import ObservationStore

crew_radiation_router = APIRouter()

DISPLAY = "La tripulación ante un evento solar"
BASIS = (
    "por tripulante, la ubicación que declaró la consola o, si no hay, la que estiman las anclas "
    "de módulo, y la dosis que ya calcula su estado (la de esta misión y la de carrera, con su "
    "tipo); el evento solar es el que elige el estado y el refugio, el procedimiento que ya "
    "enseña su escala aguda"
)
# `LOCATION_BASIS` y los textos de cada fila son los de `analysis.location`: los del estado.
MISSION_MISSING = (
    "sin dosis de esta misión: no hay dos lecturas de tasa de dosis desde el inicio de la misión "
    "con las que integrarla"
)
NO_SHIELDING = (
    "Sin factores de blindaje: EMMA no modela una nave concreta ni el refugio de cada módulo, así "
    "que no compara un módulo con otro, y la ubicación declarada no corrige ninguna cifra."
)
NOT_EVALUATED = (
    "Se muestra y no se evalúa: cada cifra es la del estado de cada tripulante, y esta vista no "
    "cambia ningún nivel, alerta ni hipótesis."
)
STATE_MISSING = (
    "sin dosis en esta vista: su estado no tiene hasta este instante ninguna lectura que entre en "
    "el análisis (medida, no inferida, predicha ni descriptiva, y con fecha analizable); puede "
    "tener otras lecturas, que esta vista no cuenta"
)
# Las dos respuestas de `_assess` que son «este tripulante no tiene estado», no un fallo.
_STATELESS = frozenset({404, 422})
NO_EVENT_SHELTER = (
    "sin evento solar vigente en el estado: no hay tiempos de refugio que contar"
)
i18n.en_many({
    DISPLAY: "The crew facing a solar event",
    BASIS: (
        "per crew member, the location declared on the console or, if there is none, the one "
        "estimated from the module anchors, and the dose their status already computes (this "
        "mission's and the career dose, each with its type); the solar event is the one the "
        "status picks, and the shelter is the procedure its acute scale already shows"
    ),
    MISSION_MISSING: (
        "no dose for this mission: there are not two dose-rate readings since the start of the "
        "mission to integrate it from"
    ),
    NO_SHIELDING: (
        "No shielding factors: EMMA does not model a specific spacecraft or the shelter of each "
        "module, so it does not compare one module with another, and the declared location "
        "does not correct any figure."
    ),
    NOT_EVALUATED: (
        "Shown, not evaluated: each figure is the one in each crew member's status, and this "
        "view does not change any level, alert or hypothesis."
    ),
    STATE_MISSING: (
        "no dose in this view: up to this instant their status has no reading that enters the "
        "analysis (measured, not inferred, predicted or descriptive, and with a date that can "
        "be analysed); they may have other readings, which this view does not count"
    ),
    NO_EVENT_SHELTER: (
        "no solar event in force in the status: there are no shelter times to count"
    ),
})


@crew_radiation_router.get("/crew/radiation")
def crew_radiation(
    store: StoreDep, settings: SettingsDep, until: dt.datetime | None = None
) -> dict[str, Any]:
    """Por tripulante, su ubicación declarada y su dosis, junto al evento solar y el refugio.

    Solo lee: compone lo que ya calculan el estado de cada uno y la vista de tripulación.
    """
    if until is not None and until.tzinfo is None:
        # Un `until` sin zona horaria no es «sin datos»: se dice, como en `/status`.
        raise HTTPException(status_code=422, detail="`until` debe llevar zona horaria")
    assessed: dict[str, _Assessment | None] = {}
    for subject in sorted(store.subjects()):
        try:
            assessed[subject] = _assess(settings, store, subject, None, None, until)
        except HTTPException as exc:
            # Sin estado analizable (solo descriptivas, inferidas o predichas, o fechas que no se
            # pueden analizar) no hay dosis que enseñar; la fila sigue, con su ubicación. Otro
            # código no es «sin lecturas»: no se disfraza de eso.
            if exc.status_code not in _STATELESS:
                raise
            # En Tierra, quien no tiene nada llegado antes del corte no está todavía en su vista.
            if not store.query(subject, until=until):
                continue
            assessed[subject] = None
    states = [item for item in assessed.values() if item is not None]
    if not states:
        raise HTTPException(status_code=404, detail="no hay tripulantes con datos")
    # El mismo instante de referencia que `crew_overview`: el más reciente de la tripulación.
    reference = max(item.latest for item in states)
    # DONKI es el mismo para toda la tripulación: el evento y la edad del primer estado, como en
    # `crew_overview`, para que toda la respuesta nombre un solo evento. Dicho con la misma pieza
    # que la radiación del hábitat, a la que se le pasa ese evento (no consulta otra vez).
    first = states[0]
    active = first.status.active_solar_event
    solar = solar_event_block((active, first.solar_age))
    return _in_language({
        "display": i18n.loc(DISPLAY),
        "basis": i18n.loc(BASIS),
        "reference_time": reference.isoformat(),
        "solar_event": solar,
        # El refugio con el procedimiento de Orion, desde el evento hasta el instante de
        # referencia de la tripulación (no el de cada uno: va una vez). Sin evento, nada que
        # contar, y se dice. Para Tierra, como en el estado, el evento es el del reloj real y el
        # tiempo transcurrido se cuenta hasta su referencia: si el evento es posterior, sin cifra
        # y con su frase (`time_to_action`).
        "shelter": time_to_action(active.time, reference) if active is not None else None,
        "shelter_missing_text": None if active is not None else NO_EVENT_SHELTER,
        "location_basis": i18n.loc(LOCATION_BASIS),
        "crew": [
            _member(settings, store, subject, item, reference, until)
            for subject, item in assessed.items()
        ],
        "shielding": i18n.loc(NO_SHIELDING),
        "evaluated": False,
        "note": i18n.loc(NOT_EVALUATED),
    }, "shelter_missing_text")


def _in_language(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    """`payload` con las frases de «falta» de `keys` en el idioma de la petición.

    Las constantes se quedan en la línea en que se deciden (cada una tiene su mutante) y el idioma
    se pone al salir.
    """
    for key in keys:
        if payload[key] is not None:
            payload[key] = i18n.loc(payload[key])
    return payload


def _member(
    settings: Settings,
    store: ObservationStore,
    subject: str,
    assessed: _Assessment | None,
    reference: dt.datetime,
    until: dt.datetime | None,
) -> dict[str, Any]:
    """Un tripulante: su ubicación declarada y la dosis de misión y de carrera de su estado.

    La escala se compone con las mismas entradas que `GET /api/status` (las lecturas que lee su
    estado, el inicio de misión configurado y la dosis previa de su perfil, hasta `until`); de
    ella solo se toman la misión y la carrera. Su escala aguda no: el evento y el refugio van una
    vez para toda la tripulación. Sin estado analizable, la ubicación y lo que falta.
    """
    where = location_view(
        crew_whereabouts(store, subject, until, reference - sensing().lookback), reference
    )
    row: dict[str, Any] = {
        "subject": subject,
        "location": where["location"],
        "location_state": where["location_state"],
        "location_missing_text": where["location_missing_text"],
    }
    if assessed is None:
        return _in_language({
            **row, "mission": None, "mission_missing_text": None, "career": None,
            "state_missing_text": STATE_MISSING,
        }, "state_missing_text")
    scales = radiation_scales(
        active_event=None,
        event_time=None,
        now=assessed.latest,
        mission=mission_dose(assessed.observations, settings.mission_start),
        prior_career_msv=latest_profile(store, subject, until)["prior_career_dose_msv"],
        limit_msv=assessed.status.dose_limit_msv,
    )
    mission = scales["mission"]
    return _in_language({
        **row,
        "mission": mission,
        "mission_missing_text": None if mission is not None else MISSION_MISSING,
        "career": scales["career"],
        "state_missing_text": None,
    }, "mission_missing_text")
